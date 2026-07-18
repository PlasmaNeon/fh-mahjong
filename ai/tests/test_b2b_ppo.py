import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import (
    AUX_LOSS_WEIGHT,
    PPOConfig,
    RolloutBatch,
    compute_gae,
    concat_rollout_batches,
    ppo_update,
)

ENV = EnvConfig(bridge_kind="mock")


def _batch(n, window=8, seed=0, with_events=True):
    rng = np.random.default_rng(seed)
    kwargs = {}
    if with_events:
        kwargs = dict(
            events=rng.integers(0, 0x10000, size=(n, window), dtype=np.uint32),
            event_lengths=rng.integers(0, window + 1, size=n).astype(np.int32),
            dealin_labels=rng.integers(0, 2, size=n).astype(np.float32),
            rank_labels=rng.integers(-1, 5, size=n).astype(np.int64),
        )
    return RolloutBatch(
        planes=rng.random((n, 51, 42, 1), dtype=np.float32),
        scalars=rng.random((n, 58), dtype=np.float32),
        action_mask=np.ones((n, 204), dtype=np.int8),
        actions=rng.integers(0, 204, size=n),
        old_logprobs=rng.random(n).astype(np.float32) * -1,
        values=rng.random(n).astype(np.float32),
        rewards=rng.random(n).astype(np.float32),
        dones=(rng.random(n) < 0.1).astype(np.float32),
        **kwargs,
    )


def test_concat_keeps_event_rows_aligned():
    a, b = _batch(5, seed=1), _batch(3, seed=2)
    a_events0 = a.events[0].copy()
    merged = concat_rollout_batches([a, b])
    assert merged.events.shape == (8, 8)
    assert merged.event_lengths.shape == (8,)
    assert np.array_equal(merged.events[0], a_events0)
    assert merged.rank_labels.shape == (8,)


def test_concat_legacy_batches_without_events():
    merged = concat_rollout_batches([_batch(4, with_events=False), _batch(2, with_events=False)])
    assert merged.events is None and merged.rank_labels is None


def test_ppo_update_with_aux_heads_runs_and_reports():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(32)
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    config = PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=16)
    metrics = ppo_update(model, optimizer, batch, adv, ret, config)
    for key in ("belief_loss", "dealin_loss", "rank_loss"):
        assert key in metrics and np.isfinite(metrics[key])
    assert AUX_LOSS_WEIGHT == 0.1


def test_ppo_update_legacy_model_unchanged_metrics():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(16, with_events=False)
    batch = RolloutBatch(**{**batch.__dict__, "planes": batch.planes[:, :39]})
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    metrics = ppo_update(model, optimizer, batch, adv, ret, PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=8))
    assert "belief_loss" not in metrics  # legacy metric schema untouched


def test_rank_ce_ignores_masked_rows():
    # All rank labels -1 -> rank CE contributes exactly 0 and stays finite.
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4)
    batch = _batch(16, seed=5)
    batch.rank_labels[:] = -1
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 1.0, 0.95)
    metrics = ppo_update(model, optimizer, batch, adv, ret, PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=8))
    assert metrics["rank_loss"] == 0.0


def test_aux_gradients_reach_trunk():
    model = PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))
    batch = _batch(8, seed=7)
    planes = torch.from_numpy(batch.planes)
    scalars = torch.from_numpy(batch.scalars)
    events = torch.from_numpy(batch.events.astype(np.int64))
    lengths = torch.from_numpy(batch.event_lengths.astype(np.int64))
    features = model.encode(planes, scalars, events, lengths)
    aux = model.aux_predictions(features)
    target = torch.sigmoid(torch.randn_like(aux["belief"]))
    loss = torch.nn.functional.binary_cross_entropy_with_logits(aux["belief"], target)
    loss.backward()
    assert model.trunk[0].weight.grad is not None
    assert model.trunk[0].weight.grad.abs().sum() > 0
