# GRP-Shaped Reward for Online PPO — Design

**Date:** 2026-06-28
**Status:** Approved (brainstorming → ready for implementation plan)

## Context

Every prior online-PPO configuration plateaued at **parity** with the heuristic anchor: dense
per-hand *score* reward, 256-match batches, self-play opponent pool, and entropy/lr tuning all
land within noise of the anchor (`mean_reward ≈ +0.006 ± 0.037` duplicate-seat). The fixes
eliminated the original catastrophic regression (−0.42) but did not surpass the anchor. The
remaining untested lever is the **reward signal**: dense per-hand *score* is myopic and is
essentially the objective the anchor already maximizes, so self-play converges back to it.

The systems that actually beat strong opponents (Suphx, Mortal) use **Global Reward Prediction
(GRP)** — a learned model that predicts the game's final outcome from a mid-game state — to give
the policy a denser, less myopic, *placement-oriented* reward. This spec integrates GRP into the
PPO reward to change *what the agent optimizes* (winning/ranking) rather than just reducing
variance.

The repo already has the GRP building blocks: `ai/src/fh_mahjong_ai/global_ev.py`
(`GlobalEVNet(planes, scalars) → scalar`, `global_ev_targets(..., reward_shaping="placement")`,
`regression_metrics`, `constant_baseline_metrics`) and the `fh-mj-train-global-ev` CLI. We build
on these, not reinvent.

## Goal

Make PPO optimize a GRP-predicted **placement** signal so it can exceed the heuristic anchor,
reusing the existing GlobalEV infrastructure and the existing PPO pipeline (`collect_rollouts`,
`train_ppo`, parallel collector, MLflow), while keeping the duplicate-seat **net** eval
comparable to the established anchor baseline.

## Non-Goals (YAGNI)

- **Online GRP retraining.** GRP is trained offline once and frozen during PPO (decided). Periodic
  refresh is a future option, not built now.
- **Action-conditioned GRP** (`ActionGlobalEVNet`). The reward uses the state-value `GlobalEVNet`
  only.
- **Oracle/lookahead guiding** (the other Suphx ingredient). Out of scope.

## Decisions (from brainstorming)

1. **Mechanism:** reward = GRP placement-value delta (changes the objective to ranking).
2. **GRP target:** placement values (rank `1, ⅓, −⅓, −1`), via `reward_shaping="placement"`.
3. **GRP freshness:** trained offline once, frozen during the whole PPO run.
4. **Eval:** add a placement metric; keep the net metric for anchor comparability.

---

## Section 1 — Phase 1: train + validate the GRP model (offline, mostly existing)

1. Generate anchor self-play trajectories with terminal outcomes (existing data-gen via the Go
   bridge; the anchor playing all seats), carrying `terminal_rewards` (per-seat net) and seats.
2. Train `GlobalEVNet` with `reward_shaping="placement"` using `fh-mj-train-global-ev`, producing a
   frozen GRP checkpoint that predicts the acting seat's final placement value from
   `(planes, scalars)`.
3. **Validation gate (validate-before-build):** `regression_metrics` on a held-out split must beat
   `constant_baseline_metrics`. If GRP cannot predict placement better than a constant, it carries
   no usable signal — stop before the expensive PPO run.

This phase is run with existing tooling; the only new code is whatever small glue/validation
reporting is needed. The deliverable is a frozen GRP `.pt` + its validation metrics.

## Section 2 — Phase 2: GRP-shaped reward in `collect_rollouts` (the new core)

When a GRP checkpoint is configured, the per-decision reward for the learning seat is replaced by
the GRP-predicted change in placement value:

- At each learner decision `t`, compute `g_t = GRP(obs_t)` = the learning seat's predicted
  placement value at that state (a scalar in roughly `[-1, 1]`).
- **Non-terminal step `t`:** `reward_t = g_{t+1} − g_t` (improvement in predicted placement between
  consecutive learner decisions).
- **Terminal step:** `reward_last = realized_placement − g_last`, where `realized_placement` is the
  learning seat's placement value computed from the final standings (rank → `placement_values`).

This telescopes so the return over a match ≈ `realized_placement − g_0`: dense placement reward,
shaped at every step by GRP, grounded in the actual final rank. It **replaces** the env's per-hand
score reward for the learning seat (the env still drives the game; we just recompute the reward
from GRP instead of `step.rewards`).

**Gating / backward-compat:** controlled by a new `grp_checkpoint: Optional[Path]` (and the
placement values) on `PPOConfig`/CLI. When unset (default), `collect_rollouts` uses the current
score reward unchanged — existing tests and the score-based runs are byte-identical. When set,
`collect_rollouts` loads the frozen `GlobalEVNet` and uses the GRP-delta reward.

**Cost:** one extra small-net forward (`GlobalEVNet`, state-only) per learner decision, on the CPU
workers. Negligible relative to the env step.

**realized_placement** is derived from the terminal per-seat net (the env's match-end standings)
via the same ranking as `placement_shaped_returns`, using the configured `placement_values`.

## Section 3 — Eval: placement metric (judge on the new objective)

The duplicate-seat eval gains a **placement** metric: for each completed episode, compute the
learning seat's placement value from the final standings, and report mean placement (with the same
sem/ci95 treatment as the net metric). It is reported **alongside** the existing net `mean_reward`
(unchanged), so GRP-PPO is judged on placement (its objective) while net stays comparable to the
anchor's established baseline. A placement **baseline for the anchor** is computed once for
comparison.

## Section 4 — Integration / parallel / MLflow

- **Parallel collector:** the frozen GRP checkpoint (a CPU `state_dict`) is shipped to each worker
  once at collector init (it never changes), alongside the existing model/config. Workers
  reconstruct the `GlobalEVNet` and use it in `collect_rollouts`. Determinism across
  sequential/parallel is preserved (GRP is deterministic given the state; reward computation adds
  no RNG).
- **MLflow:** Phase 1 logs GRP regression metrics vs baseline; Phase 2 PPO logs both placement and
  net per iteration.
- **`train_ppo`:** threads the GRP checkpoint to the (sequential and parallel) collectors; no change
  to GAE/update/checkpointing.

## Section 5 — Error handling

- A configured but missing/incompatible GRP checkpoint fails fast at `train_ppo` start (clear
  error), before the expensive loop.
- GRP forward runs under `torch.no_grad()` in `eval()`, frozen (`requires_grad_(False)`), like the
  opponents.
- `placement_values` must have length 4; validated at config use.

## Section 6 — Testing (TDD)

- **GRP-delta reward math:** with a mock/stub GRP returning known per-state values, a non-terminal
  step's reward equals `g_{t+1} − g_t`, and the terminal step equals `realized_placement − g_last`.
- **Telescoping:** over a mock match, the summed learner reward equals `realized_placement − g_0`.
- **Backward-compat:** `grp_checkpoint=None` produces byte-identical rollouts to the current score
  reward (existing `collect_rollouts`/PPO tests pass unchanged).
- **Placement eval metric:** a controlled final-standings input yields the expected placement value;
  reported alongside net.
- **Parallel:** GRP shipped to workers; parallel GRP-reward rollouts match the sequential path over
  the same seeds.
- **Validation gate:** `regression_metrics` vs `constant_baseline_metrics` comparison is exercised
  (Phase 1 glue).

## Success Criteria

- Phase 1: a frozen GRP model whose held-out placement prediction beats the constant baseline
  (otherwise stop).
- Phase 2: `grp_checkpoint=None` is behavior-preserving; with GRP set, the per-decision reward is
  the GRP placement delta and the return telescopes to realized placement.
- End goal: a GRP-shaped PPO run that exceeds the anchor on the **placement** metric (and ideally
  does not regress net), judged by the duplicate-seat gate — answering whether a placement-oriented
  objective breaks the parity that score-based reward could not.
