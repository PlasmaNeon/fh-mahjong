from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, RolloutBatch, masked_policy_distribution
from fh_mahjong_ai.ach import ach_policy_loss, ach_update


def _tiny_model():
    env = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    mcfg = ModelConfig(channels=4, residual_blocks=1, plane_feature_dim=8,
                       scalar_hidden_dim=8, trunk_hidden_dim=8, value_hidden_dim=8, q_hidden_dim=8)
    return PolicyValueNet(env, mcfg), env


def _synthetic_batch(env, n=16):
    rng = np.random.default_rng(0)
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    return RolloutBatch(
        planes=rng.standard_normal((n, *env.plane_shape)).astype(np.float32),
        scalars=rng.standard_normal((n, env.scalar_features)).astype(np.float32),
        action_mask=mask,
        actions=rng.integers(0, env.action_space_size, size=n).astype(np.int64),
        old_logprobs=np.full(n, -1.386, dtype=np.float32),  # log(1/4)
        values=np.zeros(n, dtype=np.float32),
        rewards=rng.standard_normal(n).astype(np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )


def test_hedge_threshold_blocks_saturated_logit_gradient():
    # Sample 0: taken-action logit 3.0 > beta 2.0 with positive weight -> saturated -> grad ~0.
    # Sample 1: taken-action logit 1.0 < beta with positive weight -> not saturated ->
    #           loss = -(y_eff*w).mean() so grad = -w/n = -1/2.
    logits = torch.tensor([[3.0, 0.0, 0.0, 0.0],
                           [1.0, 0.0, 0.0, 0.0]], requires_grad=True)
    actions = torch.tensor([0, 0])
    weights = torch.tensor([1.0, 1.0])
    loss, saturated = ach_policy_loss(logits, actions, weights, beta=2.0)
    loss.backward()
    assert bool(saturated[0]) is True and bool(saturated[1]) is False
    assert abs(logits.grad[0, 0].item()) < 1e-7
    assert logits.grad[1, 0].item() == pytest.approx(-0.5)


def test_hedge_threshold_blocks_saturated_negative_advantage_logit_gradient():
    # Symmetric (w<0) clause of the hedge: an already-very-negative logit with a
    # negative weight is saturated (don't push it further down) -> grad ~0; a mild
    # negative logit is not.
    # Sample 0: taken-action logit -3.0 <= -beta with w<0 -> saturated -> grad ~0.
    # Sample 1: taken-action logit -1.0 > -beta with w<0 -> not saturated ->
    #           loss = -(y_eff*w).mean() so grad = -w/n = -(-1.0)/2 = +0.5.
    logits = torch.tensor([[-3.0, 0.0, 0.0, 0.0],
                           [-1.0, 0.0, 0.0, 0.0]], requires_grad=True)
    actions = torch.tensor([0, 0])
    weights = torch.tensor([-1.0, -1.0])
    loss, saturated = ach_policy_loss(logits, actions, weights, beta=2.0)
    loss.backward()
    assert bool(saturated[0]) is True and bool(saturated[1]) is False
    assert abs(logits.grad[0, 0].item()) < 1e-7
    assert logits.grad[1, 0].item() == pytest.approx(0.5)


def test_neurd_reduction_grad_equals_advantage_when_beta_infinite():
    # beta = +inf -> nothing saturates -> taken-logit grad = -adv/n (regret/replicator update).
    logits = torch.tensor([[0.5, 0.0, 0.0, 0.0],
                           [0.2, 0.0, 0.0, 0.0]], requires_grad=True)
    actions = torch.tensor([0, 0])
    adv = torch.tensor([0.7, -0.4])
    loss, saturated = ach_policy_loss(logits, actions, adv, beta=float("inf"))
    loss.backward()
    assert not bool(saturated.any())
    assert logits.grad[0, 0].item() == pytest.approx(-0.7 / 2)
    assert logits.grad[1, 0].item() == pytest.approx(0.4 / 2)


def test_ach_update_increases_prob_of_positive_advantage_action():
    model, env = _tiny_model()
    n = 8
    mask = np.ones((n, env.action_space_size), dtype=np.int8)
    planes = np.zeros((n, *env.plane_shape), dtype=np.float32)
    scalars = np.zeros((n, env.scalar_features), dtype=np.float32)
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        old_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    batch = RolloutBatch(
        planes=planes, scalars=scalars, action_mask=mask,
        actions=np.full(n, 2, dtype=np.int64),
        old_logprobs=np.full(n, old_lp, dtype=np.float32),
        values=np.zeros(n, dtype=np.float32),
        rewards=np.zeros(n, dtype=np.float32),
        dones=np.zeros(n, dtype=np.float32),
    )
    adv = np.ones(n, dtype=np.float32)
    ret = np.zeros(n, dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-2)
    ach_update(model, opt, batch, adv, ret,
               PPOConfig(minibatch_size=8, ppo_epochs=5, entropy_coef=0.0,
                         normalize_advantages=False, ach_beta=2.0, device="cpu"))
    with torch.no_grad():
        logits, _ = model(torch.zeros(1, *env.plane_shape), torch.zeros(1, env.scalar_features),
                          torch.ones(1, env.action_space_size, dtype=torch.int8))
        new_lp = float(masked_policy_distribution(logits).log_prob(torch.tensor([2]))[0])
    assert new_lp > old_lp


def test_ach_update_metrics_finite_and_does_not_mutate_batch():
    model, env = _tiny_model()
    batch = _synthetic_batch(env)
    planes_before = batch.planes.copy()
    actions_before = batch.actions.copy()
    adv = np.ones(len(batch), dtype=np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    metrics = ach_update(model, opt, batch, adv, ret,
                         PPOConfig(minibatch_size=8, ppo_epochs=2, device="cpu"))
    for key in ("policy_loss", "value_loss", "entropy", "approx_kl",
                "clip_fraction", "saturated_fraction", "mean_abs_logit"):
        assert np.isfinite(metrics[key]), key
    np.testing.assert_array_equal(batch.planes, planes_before)
    np.testing.assert_array_equal(batch.actions, actions_before)


def test_ach_update_handles_minibatch_not_dividing_n_and_normalization():
    model, env = _tiny_model()
    batch = _synthetic_batch(env, n=16)
    adv = np.linspace(-1.0, 1.0, len(batch)).astype(np.float32)
    ret = np.zeros(len(batch), dtype=np.float32)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    # minibatch_size=5 does not divide 16; normalize_advantages=True must run cleanly.
    metrics = ach_update(model, opt, batch, adv, ret,
                         PPOConfig(minibatch_size=5, ppo_epochs=1,
                                   normalize_advantages=True, device="cpu"))
    assert np.isfinite(metrics["policy_loss"])
    assert 0.0 <= metrics["saturated_fraction"] <= 1.0


def test_ach_update_policy_gradient_flows_only_through_taken_logit():
    # Regression for the "importance ratio left in the autograd graph" bug: the
    # NeuRD policy loss must treat the IS-corrected advantage as a detached
    # COEFFICIENT, so per sample the gradient reaches EXACTLY ONE logit (the taken
    # action's). If the ratio (a function of every logit via log-prob/softmax)
    # leaked into the graph, all logits in the row would receive gradient.
    # Isolate the policy loss: value_coef=0, entropy_coef=0, beta=inf (no
    # saturation), single epoch, lr=0 (inspect grad only, no update). We assert the
    # per-row one-hot STRUCTURE, which is permutation-independent (ach_update
    # shuffles the minibatch, so captured row order != batch order).
    model, env = _tiny_model()
    n = 6
    batch = _synthetic_batch(env, n=n)  # all-legal mask; nonzero advantages below
    adv = np.linspace(-1.0, 1.0, n).astype(np.float32)  # no zero entries
    ret = np.zeros(n, dtype=np.float32)
    captured = {}

    def hook(_module, _inp, out):
        logits = out[0]
        logits.retain_grad()
        captured["logits"] = logits

    handle = model.register_forward_hook(hook)
    opt = torch.optim.SGD(model.parameters(), lr=0.0)
    ach_update(model, opt, batch, adv, ret,
               PPOConfig(minibatch_size=n, ppo_epochs=1, entropy_coef=0.0, value_coef=0.0,
                         normalize_advantages=False, ach_beta=float("inf"), device="cpu"))
    handle.remove()
    grad = captured["logits"].grad  # (n, action_space_size)
    nonzero_per_row = (grad.abs() > 1e-6).sum(dim=1)
    # Exactly one logit per sample receives gradient — proves the IS weight is
    # detached (else softmax would spread gradient across all action_space_size logits).
    assert torch.equal(nonzero_per_row, torch.ones(n, dtype=nonzero_per_row.dtype)), \
        f"expected one gradient-carrying logit per row, got counts {nonzero_per_row.tolist()}"
