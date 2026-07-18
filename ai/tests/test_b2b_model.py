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
