"""Clipped-NeuRD / ACH (Actor-Critic Hedge) policy update.

Drop-in alternative to ``ppo_update``: identical signature and the same
minibatch / epoch / grad-norm-clip / optimizer-step machinery. The only
difference is the policy loss. Where PPO's clipped surrogate yields a logit
gradient carrying a softmax ``(1 - pi)`` factor (vanilla policy gradient),
NeuRD makes the taken action's LOGIT gradient equal the advantage, so logits
accumulate advantage the way CFR accumulates regret. The ACH ``hedge``
threshold ``beta`` bounds logit magnitude (a trust region replacing PPO's
ratio clip), and a PPO-style clipped importance ratio (``clip_eps``) corrects
for off-policy drift when the batch is reused across epochs.
"""
from __future__ import annotations

import numpy as np
import torch

from .ppo import PPOConfig, RolloutBatch, masked_policy_distribution


def ach_policy_loss(masked_logits: torch.Tensor, actions: torch.Tensor,
                    weights: torch.Tensor, beta: float):
    """NeuRD/ACH policy loss on a minibatch.

    ``weights`` is the per-sample effective replicator weight ``w_t`` (the
    importance-corrected advantage). The loss is ``-(y_eff * weights).mean()``
    where ``y_eff`` is the taken action's logit, so the gradient on that logit
    is ``-weights / n`` — gradient descent adds ``weights`` to the logit. When
    the logit is already saturated beyond ``+/-beta`` in the direction
    ``weights`` would push it, its gradient is zeroed (the hedge threshold).

    The threshold is applied to the RAW network logit, not a policy-centered one.
    This is intentional and faithful to NeuRD/ACH: the update is replicator
    dynamics on the logit parameters themselves, and capping the raw logit is what
    bounds its unbounded absolute growth (the logit-blow-up guard). Softmax is
    shift-invariant, so a policy-relative parameterization would be a different
    method than the one this A/B is meant to test.

    Returns ``(loss, saturated_mask)``.
    """
    y_t = masked_logits.gather(1, actions.unsqueeze(1)).squeeze(1)
    saturated = ((y_t >= beta) & (weights > 0)) | ((y_t <= -beta) & (weights < 0))
    y_eff = torch.where(saturated, y_t.detach(), y_t)
    loss = -(y_eff * weights).mean()
    return loss, saturated


def ach_update(model, optimizer, batch: RolloutBatch,
               advantages: np.ndarray, returns: np.ndarray,
               config: PPOConfig) -> dict:
    device = config.device
    n = len(batch)
    planes = torch.from_numpy(np.asarray(batch.planes, dtype=np.float32)).to(device)
    scalars = torch.from_numpy(np.asarray(batch.scalars, dtype=np.float32)).to(device)
    action_mask = torch.from_numpy(np.asarray(batch.action_mask, dtype=np.int8)).to(device)
    actions = torch.from_numpy(np.asarray(batch.actions, dtype=np.int64)).to(device)
    old_logprobs = torch.from_numpy(np.asarray(batch.old_logprobs, dtype=np.float32)).to(device)
    adv_t = torch.from_numpy(np.asarray(advantages, dtype=np.float32)).to(device)
    ret_t = torch.from_numpy(np.asarray(returns, dtype=np.float32)).to(device)
    if config.normalize_advantages:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    beta = config.ach_beta
    last = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "approx_kl": 0.0,
            "clip_fraction": 0.0, "saturated_fraction": 0.0, "mean_abs_logit": 0.0}
    model.train()
    for _ in range(config.ppo_epochs):
        perm = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch_size):
            idx = perm[start : start + config.minibatch_size]
            masked_logits, value = model(planes[idx], scalars[idx], action_mask[idx])
            dist = masked_policy_distribution(masked_logits)
            new_logprobs = dist.log_prob(actions[idx])
            ratio = torch.exp(new_logprobs - old_logprobs[idx])
            rho = torch.clamp(ratio, 1.0 - config.clip_eps, 1.0 + config.clip_eps)
            # The (IS-corrected, clipped) advantage is a COEFFICIENT on the logit
            # gradient, not part of the differentiated objective. Detach it so the
            # only gradient path is through the taken logit y_eff (a pure regret /
            # NeuRD update). Leaving rho in the graph would backprop through the
            # log-prob ratio, adding a spurious policy-gradient term and pushing the
            # non-taken logits too — i.e. a PPO/NeuRD hybrid, not ACH.
            w = (rho * adv_t[idx]).detach()

            policy_loss, saturated = ach_policy_loss(masked_logits, actions[idx], w, beta)
            value_loss = torch.nn.functional.mse_loss(value, ret_t[idx])
            entropy = dist.entropy().mean()
            loss = policy_loss + config.value_coef * value_loss - config.entropy_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), config.max_grad_norm)
            optimizer.step()

            with torch.no_grad():
                approx_kl = (old_logprobs[idx] - new_logprobs).mean()
                clip_fraction = (torch.abs(ratio - 1.0) > config.clip_eps).float().mean()
                saturated_fraction = saturated.float().mean()
                y_t = masked_logits.gather(1, actions[idx].unsqueeze(1)).squeeze(1)
                mean_abs_logit = y_t.abs().mean()
            last = {
                "policy_loss": float(policy_loss.item()),
                "value_loss": float(value_loss.item()),
                "entropy": float(entropy.item()),
                "approx_kl": float(approx_kl.item()),
                "clip_fraction": float(clip_fraction.item()),
                "saturated_fraction": float(saturated_fraction.item()),
                "mean_abs_logit": float(mean_abs_logit.item()),
            }
    return last
