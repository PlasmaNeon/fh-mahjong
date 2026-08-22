# Online Self-Play RL (PPO, slice 1) — Design

**Date:** 2026-06-24
**Status:** Approved (brainstorming complete; ready for implementation plan)

## Goal

Add the project's first **online reinforcement learning** phase: PPO that
fine-tunes the promoted anchor by playing fresh Chongci matches against frozen
anchor opponents, learning from per-hand score rewards, to discover strategy the
offline pipeline cannot.

This is the Suphx RL-phase recipe adapted to our constraints. Every prior approach
(BC, IQL, the self-play loop, streamed big-batch) is **offline** learning on
**heuristic-generated** data and is therefore bounded by the heuristic — offline +
conservative training cannot discover actions absent from the data (see
`worklog/rl-experiment/chongci-rl-experiment-progress.md`). Online RL breaks that ceiling
because the agent explores beyond the data and learns from the outcomes of its own
actions. We have no large real paipu corpus (so Mortal's offline-on-human-logs
path is closed), which is exactly why the online Suphx route is the one open to us.

## Scope

Slice 1: a minimal but complete, single-process PPO learner — 1 learning seat vs 3
frozen-anchor seats, dense per-hand reward, warm-started from the anchor, with the
existing duplicate-seat CI gate as the "did we beat the anchor" check.

Out of scope (explicit follow-ups): self-play opponent pool (all seats learning);
parallel/distributed rollout collection; swapping in `GlobalEVNet` (GRP) as the
reward; oracle guiding; runtime policy adaptation.

## Key Decisions

- **Warm-start, not from scratch.** Load the promoted anchor into the learning
  `PolicyValueNet` (policy + value). A second frozen copy is the opponent. From
  scratch is infeasible (sparse delayed reward, huge action space). This is the
  AlphaGo/Suphx/Mortal pattern: pretrain then RL.
- **Algorithm: PPO** — clipped surrogate, GAE advantages, entropy bonus, action
  masking. A robust modern member of the entropy-regularized policy-gradient family
  Suphx used; fits the policy+value warm-start directly.
- **Opponents: frozen anchor** (3 seats) for slice 1 — stationary and competent,
  the cleanest stable setup and a direct "beat the anchor" test; evolves to a
  self-play pool later.
- **Reward: dense per-hand score delta**, gamma-discounted, value critic for
  long-horizon credit. Chongci's objective is net score, so per-hand score is
  directly meaningful (unlike Riichi placement, which is why Suphx/Mortal needed a
  learned GRP). Upgrade path: swap in `GlobalEVNet` as a GRP-style reward later.
- **On-policy:** each iteration collects fresh rollouts from the current policy,
  updates, discards. No shards, no offline buffer — the structural break from all
  prior work.

## Architecture & Components

- `ai/src/fh_mahjong_ai/ppo.py` — new module:
  - `PPOConfig` (dataclass): `iterations`, `matches_per_iter`, `gamma`,
    `gae_lambda`, `clip_eps`, `entropy_coef`, `value_coef`, `ppo_epochs`,
    `minibatch_size`, `lr`, `max_grad_norm`, `sample_temperature`, `eval_interval`,
    eval seed config, device.
  - `RolloutBatch` (dataclass): flat arrays `planes, scalars, action_mask, actions,
    old_logprobs, values, rewards, dones`, plus per-match index boundaries.
  - `collect_rollouts(bridge, policy_model, frozen_anchor, config, ...) ->
    RolloutBatch` — plays `matches_per_iter` full matches; learning seat samples
    from the masked policy (records logprob+value), frozen-anchor seats act from the
    frozen copy; per-hand score deltas attached as rewards at the seat's most-recent
    decision in each resolved hand; `done` only at match end.
  - `compute_gae(rewards, values, dones, match_boundaries, gamma, lambda) ->
    (advantages, returns)` — per-match backward GAE; advantages normalized.
  - `ppo_update(model, optimizer, batch, advantages, returns, config) -> metrics`
    — masked clipped surrogate + value loss + entropy, `ppo_epochs` × minibatches,
    grad-norm clip.
  - `train_ppo(...)` — warm-start → loop { collect → GAE → update → periodic CI
    gate → checkpoint }; logs learning signals.
- `ai/src/fh_mahjong_ai/scripts/train_ppo.py` — CLI `fh-mj-train-ppo`.
- `ai/tests/test_ppo.py` — unit + mock-bridge + e2e tests.
- `ai/pyproject.toml` — `fh-mj-train-ppo` entry point.
- `ai/AGENTS.md` — document module, CLI, tests.

**Reused as-is:** `PolicyValueNet` (`forward -> (masked_logits, value)` = PPO
actor+critic); the Go bridge / `MahjongEnv`; `generate_selfplay`'s
`resolve_seat_policies`/`build_runtime_policies`/`build_bridge` for frozen-anchor
seats; `evaluate_duplicate_seats` (CI fields) for the gate; `storage`
load/save checkpoint.

## Rollout Collection

Per match: learning seat = 0, seats 1–3 = frozen anchor. At each learning-seat
decision: forward `(masked_logits, value)`, masked `Categorical`, sample with
`sample_temperature`, record `(obs, action, logprob, value, hand_index)`. When a
hand resolves, attach the learning seat's score delta for that hand as the reward
on its most-recent decision in that hand (other steps reward 0). `done` only at
match end so credit flows across hands via the value bootstrap. Output is a flat
on-policy batch with per-match boundaries; nothing persisted.

Slice 1 is single-process (one match at a time). Sampling (not greedy) for the
learning seat is required — it is the exploration that lets PPO surpass the anchor.

## PPO Math

GAE per match (backward):
```
delta_t  = r_t + gamma * V(s_{t+1}) * (1 - done_t) - V(s_t)
A_t      = delta_t + gamma * lambda * (1 - done_t) * A_{t+1}
return_t = A_t + V(s_t)
```
`V(s_{t+1})` = next learning-seat value (0 at match end). Advantages normalized
across the batch.

PPO update (`ppo_epochs` × minibatches): recompute masked `Categorical`;
`ratio = exp(new_logprob(action) - old_logprob)`; policy loss
`-mean(min(ratio*A, clip(ratio,1-eps,1+eps)*A))`; value loss
`value_coef*MSE(value, return)`; entropy bonus `-entropy_coef*mean(masked_entropy)`;
total = policy + value - entropy; `clip_grad_norm_(max_grad_norm)`.

Masking discipline: logits `-inf`-masked to legal actions before every
`Categorical` (sample, old/new logprob, entropy). Go validates every emitted action
as the final authority.

## Training Loop, Warm-start, Eval

- Warm-start: anchor → learning model (policy+value); frozen copy → opponents
  (`eval`, no grad). AdamW low LR (1e-5–3e-5) to fine-tune without erasing the
  pretrain.
- Loop for `iterations`: collect_rollouts → compute_gae → ppo_update → log signals
  (mean per-match reward, mean hand value of agent wins, policy entropy, clip
  fraction, value loss, KL vs old policy) → every `eval_interval`, run
  `evaluate_duplicate_seats` vs the anchor on a fixed seed set and record CI
  metrics → checkpoint each iteration, tag best-by-gate.
- Success: a checkpoint that beats the anchor on the CI gate (CI-separated mean
  reward, no large-loss regression) — what offline never achieved.
- Guardrails: monitor KL/entropy; entropy collapse or KL blow-up signals lower LR /
  higher entropy_coef. `sample_temperature` and `entropy_coef` are first-class
  knobs.

## Error Handling

- Action masking enforced at every distribution; Go bridge rejects any illegal
  emitted action (final authority).
- Empty/degenerate rollouts (no learning-seat decisions in a match) are skipped, not
  fed to the update.
- Eval failures are logged and do not abort training; the latest checkpoint is kept.

## Testing

`ai/tests/test_ppo.py` (CPU; mock bridge / tiny model / synthetic tensors):
- `compute_gae`: exact values on a known sequence; per-match reset; `lambda=1` →
  Monte-Carlo returns.
- Masked categorical: logprob/entropy over legal actions only; 1-legal-action mask →
  ~0 entropy and ~0 prob on illegal.
- `ppo_update`: finite losses on a synthetic batch; clipped ratio uses `old_logprob`
  correctly (positive-advantage action's prob increases after an update).
- `collect_rollouts` (mock): well-formed equal-length arrays; `done` only at match
  end; per-match boundaries present.
- `train_ppo` e2e (mock, tiny): 1–2 iterations complete, write a checkpoint, finite
  losses.
- CLI smoke: `fh-mj-train-ppo` 1-iteration mock run via argv.

## Acceptance Criteria

- `fh-mj-train-ppo` runs the full online loop end to end on the mock bridge (tests)
  and on the Go bridge on the GPU box.
- It is genuinely on-policy: fresh rollouts each iteration from the current policy,
  no offline buffer.
- Warm-start loads the anchor (policy+value); opponents are the frozen anchor.
- Per-hand rewards + GAE + masked clipped PPO update with an entropy bonus, all
  unit-tested.
- The eval gate reports CI metrics vs the anchor each `eval_interval`.
- New logic (GAE, PPO update, masked dist, rollout assembly) is covered by tests.
