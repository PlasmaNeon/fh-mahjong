# Online PPO: Parallel Rollouts + Dense Per-Hand Reward — Design

**Date:** 2026-06-26
**Status:** Approved (brainstorming → ready for implementation plan)
**Branch context:** follows `claude/ppo-anchor-validation` (PR #93). The first online
PPO-vs-frozen-anchor run regressed (anchor `mean_reward=-0.062 ±0.104` vs
`ppo_final=-0.424 ±0.099`, non-overlapping CIs). Diagnosis: catastrophic
signal-to-noise — a 16-match batch and a single **sparse terminal reward** diffused
across a ~440-step Chongci horizon. This spec fixes both root causes.

## Goal

Make a warm-started PPO learner able to actually **beat the frozen heuristic anchor**
under the duplicate-seat CI gate, by removing the two variance/credit-assignment
bottlenecks from the first run:

1. **Dense per-hand reward** — the Go env emits each hand's score delta instead of one
   net number at match end, so credit lands on the decision that caused a win/deal-in.
2. **Parallel rollout generation** — collect hundreds of self-play matches per
   iteration to cut gradient variance, using a process pool of full-match workers.

These are independent in code (Go+config vs pure-Python infra) but coupled in effect:
dense reward is the correctness fix, parallelism is the scale fix. Implement
reward first (validate cheaply), then parallelism.

## Non-Goals (YAGNI)

- Batched/vectorized single-process env (Approach B) — large ragged-scheduler rewrite, deferred.
- Go-side inference via ONNX export (Approach C) — brittle with per-iteration weight updates, deferred.
- GlobalEV / GRP reward modeling — separate future direction.
- Placement-aware reward is wired as an **off-by-default** flag only; not the training target now.

---

## Section 1 — Dense per-hand reward (Go env)

### Where
`rlenv/env.go`, function `advanceToDecision` (and the analogous behavior is already
correct in `advanceToTerminalWithHeuristics` for branch eval — out of scope). **No proto
change**: `EnvStepResponse.rewards` (field 2, `repeated float`) already exists and is
already decoded by the Python bridge.

### Problem
In Chongci mode the round-end branch readies the next round and `continue`s, **discarding**
the per-hand payout. The only reward that ever reaches Python is `matchEndRewards` — the
net score change over the entire match. `roundRewards(state)` already computes the per-seat
payout/1000; it is simply never returned in Chongci mode.

### Change
Accumulate per-hand payouts across every round resolved within a single `Step` call, and
return the accumulation on whichever path exits the loop:

```go
// inside advanceToDecision, before the loop:
pending := make([]float32, 4)

// PHASE_ROUND_END, Chongci branch:
if e.game.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
    addInto(pending, roundRewards(e.game.State)) // capture per-hand Δ
    if err := e.readyAllPlayersForNextRound(); err != nil { return nil, err }
    continue
}
```

Every `return` inside the loop carries `pending` instead of `make([]float32, 4)`:
- the next-decision (learning-seat observation) return,
- the `PHASE_MATCH_END` return (so the final hand's payout is not lost — add `pending`
  to the existing `matchEndRewards`, or return `pending` plus optional placement bonus; see below),
- both truncation returns (`MaxDecisions` / branch-max — carry whatever accrued).

One step's reward = sum of all per-hand payouts resolved since the learning seat's previous
decision (normally exactly one hand; more when several hands pass between two of the
learning seat's turns).

### Reward definition (decided)
- **Default:** per-hand score Δ only (`roundRewards`/1000 accumulated). Pure score
  maximization — rewards big wins, punishes big deal-ins.
- **Optional (off by default):** terminal placement bonus added to `pending` **only** on
  the `MATCH_END` path, gated by a config flag (e.g. `ChongciConfig`/`EnvConfig` boolean).
  Kept as a future direction; not the training target now.

### Match-end reconciliation
Sum of per-hand rewards over a match ≈ `matchEndRewards` net (modulo bust settlement).
Decision: on `MATCH_END`, return the accumulated `pending` (the per-hand stream) as the
authoritative reward, NOT `matchEndRewards`, to avoid double-counting. This keeps the
per-step reward stream's sum self-consistent and keeps `train_ppo`'s `mean_reward` and
`evaluate_duplicate_seats` on the same scale as the prior anchor run (so results stay
comparable). The optional placement bonus, when enabled, is the only term added on top.

### Tests (Go)
- A Chongci match yields **non-zero per-hand rewards at intermediate steps** (today: all
  zero until match end).
- Sum of per-hand rewards over a match ≈ match-end net (within tolerance).
- Classic mode reward path unchanged (existing tests stay green).
- Placement-bonus flag OFF → byte-identical to per-hand-only.

---

## Section 2 — Parallel rollout collection (Python)

### New file
`ai/src/fh_mahjong_ai/parallel_rollouts.py` — one class:

```python
class ParallelRolloutCollector:
    def __init__(self, env_config, model_config, frozen_state_dict, ppo_config, num_workers): ...
    def start(self) -> None       # spawn persistent workers
    def collect(self, learner_state_dict, base_seed, matches_per_iter) -> RolloutBatch
    def close(self) -> None       # sentinel + join
```

### Workers (persistent, `spawn` context)
Each worker process, once at startup: imports torch, builds its own Go bridge, constructs a
learner net + a frozen-anchor net (frozen loaded from `frozen_state_dict`, sent once). Then
blocks on a task queue. Workers do **CPU** inference — the model is tiny, batch-1 forward is
sub-ms, and this keeps the single GPU free for the update and avoids N CUDA contexts.

Rationale for persistent (not recreate-per-iteration): online PPO runs many iterations;
re-importing torch and re-`dlopen`ing the cgo bridge in 16 fresh processes every iteration is
wasteful. Persistent workers amortize startup to ~zero.

### Per-iteration data flow
1. Main broadcasts `(learner_state_dict_cpu, seed_range)` to each worker's input queue.
2. Worker `load_state_dict`s the new learner weights, runs the **existing** `collect_rollouts`
   for its assigned matches, puts its `RolloutBatch` (numpy) on the result queue.
3. Main gathers all worker batches and concatenates into one flat `RolloutBatch`.
   Each match is self-contained and `dones=1` marks each match end, so `compute_gae` over the
   concatenation is already correct — **no change to GAE or `ppo_update`**.

### Seed partitioning
Worker `w` of `W` gets matches `[w, w+W, w+2W, …]` from the iteration's seed base — disjoint,
deterministic, reproducible, and identical match coverage to the single-process loop.

### Refactor for reuse
Extract the inner single-match loop of `collect_rollouts` so both the sequential path and the
worker call the same code. `collect_rollouts(matches_per_iter=k)` remains the public sequential
API; tests, the mock bridge, and `num_workers=1` use it unchanged (behavior-preserving).

---

## Section 3 — Wiring into training + config

### `PPOConfig` additions
- `num_workers: int = 1` (1 = sequential; preserves current behavior and all existing tests).
- `dense_reward: bool = True` and `placement_bonus: bool = False`, threaded through `EnvConfig`
  into the bridge's config message so the Go env knows whether to emit per-hand rewards / bonus.

### `train_ppo` (`ppo.py`)
- `num_workers > 1`: construct `ParallelRolloutCollector` once before the loop; each iteration
  call `collector.collect(model_state_dict_cpu, seed, matches_per_iter)`; `close()` in `finally`.
- `num_workers == 1`: call `collect_rollouts` exactly as today.
- Everything downstream (GAE, `ppo_update`, eval gate, checkpointing) unchanged.

### CLI (`scripts/train_ppo.py`)
Add `--num-workers`, `--dense-reward/--no-dense-reward`, `--placement-bonus`. The campaign
config also raises `--matches-per-iter` into the hundreds (e.g. 256) — the point of the work.

---

## Section 4 — Error handling

- **Worker crash:** if any worker returns an exception or dies, `collect()` raises with the
  worker's traceback and `close()`s the pool — fail fast; never train on a partial/biased batch.
- **Bridge cleanup:** each worker `close()`s its Go bridge (cgo handle) on shutdown; `finally`
  in `train_ppo` guarantees `collector.close()`.
- **Empty batch:** per-worker empty batches (all resets degenerate) are tolerated; main raises
  if the **concatenated** batch is empty (same invariant `collect_rollouts` enforces today).
- **Go side:** `addInto` guards length-4 slices; classic-mode path untouched so existing Go
  tests stay green.

---

## Section 5 — Testing (TDD)

### Go (`rlenv/env_test.go`)
- Chongci match yields non-zero per-hand rewards at intermediate steps.
- Sum of per-hand rewards ≈ match-end net.
- Classic mode reward unchanged.
- Placement-bonus OFF → identical to per-hand-only.

### Python (`tests/test_ppo.py` + new `tests/test_parallel_rollouts.py`)
- `num_workers=2` with the **mock bridge**: same shape invariants and `dones` structure as
  sequential.
- **Determinism:** parallel(W=2) and sequential over the same seed set yield matching per-match
  reward sums.
- Worker-exception propagation raises in `collect()`.
- `close()` joins cleanly (no orphaned processes).
- Existing PPO tests stay green unchanged (proves `num_workers=1` is behavior-preserving).

### Validation sequence (cheap → expensive)
1. Go test: dense rewards exist and reconcile.
2. Python mock test: parallel correctness + determinism.
3. Short real-bridge smoke: 2 workers × 4 matches.
4. Full warm-started campaign vs the frozen anchor, judged by the duplicate-seat CI gate.

## Success Criteria

- Dense reward: intermediate Chongci steps carry non-zero per-hand payouts; per-match sum
  reconciles with match-end net.
- Parallel: `num_workers=N` produces rollouts deterministically equivalent (per-match reward
  sums) to sequential, with throughput scaling roughly linearly to ~16 workers.
- End goal: a warm-started PPO run with dense reward + hundreds of matches/iter **beats the
  frozen anchor** on the CI gate (mean_reward CI above the anchor, no large_loss regression).
  If it still does not, the next levers are exploration (entropy/temperature) and more
  iterations — not more infra.
