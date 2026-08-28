import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet

ENV39 = EnvConfig(bridge_kind="mock")  # plane_shape (39, 42, 1), 58 scalars, 204 actions


def _rand_obs(batch, channels=39, seed=0):
    rng = np.random.default_rng(seed)
    planes = torch.from_numpy(rng.random((batch, channels, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((batch, 58), dtype=np.float32))
    mask = torch.zeros((batch, 204), dtype=torch.int8)
    mask[:, :8] = 1
    return planes, scalars, mask


def _rand_events(batch, window, seed=1):
    rng = np.random.default_rng(seed)
    events = torch.from_numpy(
        rng.integers(0, 0x10000, size=(batch, window), dtype=np.uint32).astype(np.int64)
    )
    lengths = torch.from_numpy(rng.integers(0, window + 1, size=(batch,)).astype(np.int64))
    return events, lengths


def test_default_config_state_dict_unchanged():
    # Dormancy: the default model's parameter names must not mention any new module.
    model = PolicyValueNet(ENV39, ModelConfig())
    keys = set(model.state_dict().keys())
    for banned in ("event_encoder", "privileged_encoder", "belief_head", "dealin_head", "rank_head"):
        assert not any(banned in k for k in keys), banned
    assert model.wants_events is False


def test_b2b_flags_create_modules_and_forward_shapes():
    config = ModelConfig(event_window=16, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(ENV39, config)
    keys = set(model.state_dict().keys())
    for expected in ("event_encoder", "privileged_encoder", "belief_head", "dealin_head", "rank_head"):
        assert any(expected in k for k in keys), expected

    planes, scalars, mask = _rand_obs(4, channels=51)
    events, lengths = _rand_events(4, 16)
    logits, value = model(planes, scalars, mask, events=events, event_lengths=lengths)
    assert logits.shape == (4, 204) and value.shape == (4,)

    features = model.encode(planes, scalars, events=events, event_lengths=lengths)
    aux = model.aux_predictions(features)
    assert aux["belief"].shape == (4, 12, 42)
    assert aux["dealin"].shape == (4,)
    assert aux["rank"].shape == (4, 5)


def test_policy_ignores_oracle_channels_and_privileged_feeds_value_only():
    # Same 39ch content, different oracle channels -> identical LOGITS,
    # (generally) different VALUES.
    config = ModelConfig(event_window=8, privileged_critic=True, aux_heads=True)
    model = PolicyValueNet(ENV39, config)
    model.eval()
    planes51a, scalars, mask = _rand_obs(3, channels=51, seed=2)
    planes51b = planes51a.clone()
    planes51b[:, 39:51] = torch.rand_like(planes51b[:, 39:51])
    events, lengths = _rand_events(3, 8)
    with torch.no_grad():
        la, va = model(planes51a, scalars, mask, events=events, event_lengths=lengths)
        lb, vb = model(planes51b, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(la, lb, atol=1e-6)
    assert not torch.allclose(va, vb, atol=1e-6)

    # 39ch input (eval/serving shape): privileged slice substituted with zeros, no crash.
    planes39 = planes51a[:, :39]
    with torch.no_grad():
        lc, _ = model(planes39, scalars, mask, events=events, event_lengths=lengths)
    assert torch.allclose(la, lc, atol=1e-6)


def test_event_encoder_gather_and_zero_length():
    config = ModelConfig(event_window=4)
    model = PolicyValueNet(ENV39, config)
    model.eval()
    planes, scalars, mask = _rand_obs(2)
    # Row 0: two real events then padding; row 1: zero-length.
    events = torch.zeros((2, 4), dtype=torch.int64)
    events[0, 0] = 0x140  # self draw face 5
    events[0, 1] = 0x4A51  # tsumogiri discard face 41 by right
    lengths = torch.tensor([2, 0], dtype=torch.int64)
    feats = model.event_encoder(events, lengths)
    assert feats.shape == (2, config.event_hidden_dim)
    assert torch.all(feats[1] == 0), "zero-length row must yield zeros"
    # Padding must not influence the gathered feature: changing pad slots is a no-op.
    events2 = events.clone()
    events2[0, 2] = 0x8B7
    feats2 = model.event_encoder(events2, lengths)
    assert torch.allclose(feats[0], feats2[0], atol=0), "padding leaked into the GRU feature"


def test_event_window_zero_forward_matches_legacy_signature():
    model = PolicyValueNet(ENV39, ModelConfig())
    planes, scalars, mask = _rand_obs(2)
    logits, value = model(planes, scalars, mask)  # legacy 3-arg call still works
    assert logits.shape == (2, 204)


def test_greedy_policy_threads_events():
    from fh_mahjong_ai.policies import TorchGreedyPolicy
    from fh_mahjong_ai.types import Observation

    model = PolicyValueNet(ENV39, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16, event_window=8))
    policy = TorchGreedyPolicy(model, device="cpu")
    rng = np.random.default_rng(9)
    mask = np.zeros(204, dtype=np.int8)
    mask[:4] = 1
    obs = Observation(
        seat=0,
        planes=rng.random((39, 42, 1), dtype=np.float32),
        scalars=rng.random(58, dtype=np.float32),
        action_mask=mask,
        event_history=np.asarray([0x140, 0x4A51], dtype=np.uint32),
    )

    # Contract test: the model must actually receive a non-None events tensor
    # when it wants_events, not just "the call doesn't crash" (which passes
    # trivially even if TorchGreedyPolicy silently drops the history).
    received = {}
    real_forward = model.forward

    def spying_forward(planes, scalars, action_mask, events=None, event_lengths=None):
        received["events"] = events
        received["event_lengths"] = event_lengths
        return real_forward(planes, scalars, action_mask, events=events, event_lengths=event_lengths)

    model.forward = spying_forward
    choice = policy.choose(obs)
    assert received["events"] is not None
    assert received["event_lengths"] is not None
    assert 0 <= choice.action_id < 4


def test_ragged_gru_batched_matches_per_row_with_poisoned_padding():
    # G0.5 (batched-b2b-collector): rows with lengths {0, 1, W-1, W}, padding
    # slots filled with garbage ids. Batched forward == each row alone, and
    # the length-0 row == the no-history forward (events=None).
    window = 8
    config = ModelConfig(event_window=window, privileged_critic=True, aux_heads=True)
    torch.manual_seed(0)
    model = PolicyValueNet(ENV39, config)
    model.eval()
    lengths_list = [0, 1, window - 1, window]
    planes, scalars, mask = _rand_obs(len(lengths_list), channels=51, seed=3)
    rng = np.random.default_rng(5)
    events = torch.from_numpy(rng.integers(1, 0x10000, size=(4, window), dtype=np.uint32)
                              .astype(np.int64))
    lengths = torch.tensor(lengths_list, dtype=torch.int64)
    with torch.no_grad():
        logits_b, values_b = model(planes, scalars, mask, events=events, event_lengths=lengths)
        for i, n in enumerate(lengths_list):
            poisoned = events[i : i + 1].clone()
            poisoned[0, n:] = 0xFFFF  # padding must be inert
            logits_1, value_1 = model(planes[i : i + 1], scalars[i : i + 1], mask[i : i + 1],
                                      events=poisoned, event_lengths=lengths[i : i + 1])
            assert torch.allclose(logits_b[i], logits_1[0], atol=1e-6, rtol=1e-5), n
            assert torch.allclose(values_b[i], value_1[0], atol=1e-6, rtol=1e-5), n
        logits_none, value_none = model(planes[:1], scalars[:1], mask[:1])
        logits_none3, value_none3 = model(planes[3:4], scalars[3:4], mask[3:4])
    assert torch.allclose(logits_b[0], logits_none[0], atol=1e-6, rtol=1e-5)
    assert torch.allclose(values_b[0], value_none[0], atol=1e-6, rtol=1e-5)
    # sanity: a full-length history actually changes the output
    assert not (torch.allclose(logits_b[3], logits_none3[0]) and
                torch.allclose(values_b[3], value_none3[0]))
