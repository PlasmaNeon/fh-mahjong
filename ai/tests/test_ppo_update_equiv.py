"""`ppo_update` against the pre-2026-09-27 implementation (`_ppo_update_reference`).

The production update encodes once and keeps its telemetry on the device. The
forward values are bit-identical; the gradient sums the policy/value and aux paths
through one trunk graph instead of two, so it matches to float summation order.
"""
import copy

import numpy as np
import pytest
import torch

from _ppo_update_reference import reference_ppo_update
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch, compute_gae, ppo_update

ENV = EnvConfig(bridge_kind="mock")


def _model(aux: bool) -> PolicyValueNet:
    torch.manual_seed(0)
    extra = dict(event_window=8, privileged_critic=True, aux_heads=True) if aux else {}
    return PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=2, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16, **extra))


def _batch(n: int, seed: int, aux: bool, window: int = 8) -> RolloutBatch:
    rng = np.random.default_rng(seed)
    kwargs = {}
    if aux:
        kwargs = dict(
            events=rng.integers(0, 0x10000, size=(n, window), dtype=np.uint32),
            event_lengths=rng.integers(0, window + 1, size=n).astype(np.int32),
            dealin_labels=rng.integers(0, 2, size=n).astype(np.float32),
            rank_labels=rng.integers(-1, 5, size=n).astype(np.int64),
        )
    mask = (rng.random((n, 204)) < 0.3).astype(np.int8)
    actions = np.array([rng.choice(np.flatnonzero(row)) if row.any() else 0 for row in mask])
    mask[np.arange(n), actions] = 1
    return RolloutBatch(
        planes=rng.random((n, 51 if aux else 39, 42, 1), dtype=np.float32),
        scalars=rng.random((n, 58), dtype=np.float32),
        action_mask=mask,
        actions=actions,
        old_logprobs=-rng.random(n).astype(np.float32) * 3,
        values=rng.random(n).astype(np.float32),
        rewards=rng.standard_normal(n).astype(np.float32),
        dones=(rng.random(n) < 0.1).astype(np.float32),
        **kwargs,
    )


def _run(update, model, batch, config, lr):
    model = copy.deepcopy(model)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr)
    adv, ret = compute_gae(batch.rewards, batch.values, batch.dones, 0.99, 0.95)
    torch.manual_seed(13)
    metrics = update(model, optimizer, batch, adv, ret, config)
    grads = {k: p.grad.detach().clone() for k, p in model.named_parameters() if p.grad is not None}
    state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    return metrics, grads, state, torch.get_rng_state()


def test_policy_value_over_encoded_features_is_forward():
    model = _model(aux=True).eval()
    batch = _batch(12, seed=1, aux=True)
    planes = torch.from_numpy(batch.planes)
    scalars = torch.from_numpy(batch.scalars)
    mask = torch.from_numpy(batch.action_mask)
    events = torch.from_numpy(batch.events.astype(np.int64))
    lengths = torch.from_numpy(batch.event_lengths.astype(np.int64))
    with torch.no_grad():
        logits, value = model(planes, scalars, mask, events=events, event_lengths=lengths)
        features = model.encode(planes, scalars, events, lengths)
        logits2, value2 = model.policy_value(features, planes, mask)
    assert torch.equal(logits, logits2)
    assert torch.equal(value, value2)


@pytest.mark.parametrize("host_transfer", [False, True])
def test_single_step_gradient_matches_reference(host_transfer):
    """One minibatch, one epoch: the gradient left on the parameters is the
    step's gradient. It must match the double-encode reference to float
    summation order, and every metric must match."""
    model = _model(aux=True)
    batch = _batch(24, seed=2, aux=True)
    config = PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=24,
                       minibatch_device_transfer=host_transfer)
    ref_metrics, ref_grads, _, ref_rng = _run(reference_ppo_update, model, batch, config, lr=0.0)
    metrics, grads, _, rng = _run(ppo_update, model, batch, config, lr=0.0)
    assert ref_grads.keys() == grads.keys()
    for key, ref in ref_grads.items():
        torch.testing.assert_close(grads[key], ref, rtol=1e-5, atol=1e-7, msg=key)
    assert metrics.keys() == ref_metrics.keys()
    for key, ref in ref_metrics.items():
        assert metrics[key] == pytest.approx(ref, rel=1e-6, abs=1e-7), key
    assert torch.equal(rng, ref_rng)


@pytest.mark.parametrize("aux", [True, False])
def test_training_matches_reference(aux):
    """Two epochs, ragged final minibatch, lr > 0: weights track the reference."""
    model = _model(aux=aux)
    batch = _batch(37, seed=3, aux=aux)
    config = PPOConfig(device="cpu", ppo_epochs=2, minibatch_size=8)
    ref_metrics, _, ref_state, ref_rng = _run(reference_ppo_update, model, batch, config, lr=1e-3)
    metrics, _, state, rng = _run(ppo_update, model, batch, config, lr=1e-3)
    for key, ref in ref_state.items():
        torch.testing.assert_close(state[key], ref, rtol=1e-4, atol=1e-6, msg=key)
    for key, ref in ref_metrics.items():
        assert metrics[key] == pytest.approx(ref, rel=1e-4, abs=1e-6), key
    assert torch.equal(rng, ref_rng)


def test_no_labelled_rank_rows_gives_zero_rank_loss_and_gradient():
    model = _model(aux=True)
    batch = _batch(16, seed=4, aux=True)
    batch.rank_labels[:] = -1
    config = PPOConfig(device="cpu", ppo_epochs=1, minibatch_size=16)
    ref_metrics, ref_grads, _, _ = _run(reference_ppo_update, model, batch, config, lr=0.0)
    metrics, grads, _, _ = _run(ppo_update, model, batch, config, lr=0.0)
    assert metrics["rank_loss"] == 0.0 == ref_metrics["rank_loss"]
    assert torch.count_nonzero(grads["rank_head.weight"]) == 0
    for key, ref in ref_grads.items():
        torch.testing.assert_close(grads[key], ref, rtol=1e-5, atol=1e-7, msg=key)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
@pytest.mark.parametrize("aux", [True, False])
def test_graphed_step_matches_eager_step_on_cuda(aux, monkeypatch):
    """The CUDA-graphed minibatch step runs the eager step's kernels: two epochs
    with a ragged final minibatch (eager, after the graph owns the gradient
    buffers) must track the eager-only update."""
    from fh_mahjong_ai import ppo as ppo_mod

    model = _model(aux=aux).cuda()
    batch = _batch(37, seed=5, aux=aux)
    config = PPOConfig(device="cuda", ppo_epochs=2, minibatch_size=8,
                       minibatch_device_transfer=True)
    monkeypatch.setattr(ppo_mod, "GRAPHED_UPDATE_STEP", False)
    eager_metrics, eager_grads, eager_state, _ = _run(ppo_update, model, batch, config, lr=1e-3)
    monkeypatch.setattr(ppo_mod, "GRAPHED_UPDATE_STEP", True)
    metrics, grads, state, _ = _run(ppo_update, model, batch, config, lr=1e-3)
    assert grads.keys() == eager_grads.keys()
    for key, ref in eager_state.items():
        torch.testing.assert_close(state[key], ref, rtol=1e-5, atol=1e-7, msg=key)
    for key, ref in eager_metrics.items():
        assert metrics[key] == pytest.approx(ref, rel=1e-5, abs=1e-7), key
