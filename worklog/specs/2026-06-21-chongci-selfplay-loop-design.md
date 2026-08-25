# Chongci Self-Play Improvement Loop — Design

**Date:** 2026-06-21
**Status:** Approved (brainstorming complete; ready for implementation plan)

## Goal

A repeatable, CI-gated mixed self-play improvement loop for the Chongci RL agent:
generate self-play data with the current best policy, train a fresh candidate on
all accumulated data, and promote it only on a confidence-interval-confirmed
improvement. The loop is **monotonic** — the deployed "current best" only changes
on a CI-confirmed gain, so it can never regress the agent; a bad iteration costs
compute, not quality.

This is the "proven path": mixed self-play → IQL → duplicate-seat promotion is the
only approach that has ever produced a promoted Chongci checkpoint. Prior work
(see `worklog/rl-experiment/chongci-rl-experiment-progress.md`) showed that *fine-tuning*
the promoted anchor regresses it and that reward-target tweaks (placement shaping)
do not help; this loop deliberately avoids fine-tuning the rolling best.

## Scope

In scope: the orchestration loop only. It reuses the existing (single-env,
sequential) self-play generation as-is.

Out of scope (possible follow-ups): parallel/faster generation; a rotating frozen
opponent pool of all past promotions; oracle auxiliaries; automatic updates to the
global `best-checkpoints.json` registry.

## Key Decisions

- **Candidate training:** each iteration trains a *fresh* IQL from a **fixed init**
  (specified once at loop start; default = the promoted anchor, frozen) on the
  anchor's original data mix **plus all accumulated self-play**, full epochs, with
  **no `--max-transitions` truncation** (truncation biased a prior campaign). The
  candidate is never a fine-tune of the rolling best.
- **Opponent pool:** each match fills seats with the **current best** (2 seats) +
  **heuristic** (1) + **random** (1), rotated across windows. Pool = current best
  each iteration (no growing frozen pool in this scope).
- **Promotion gate:** two-stage CI gate (cheap screen → confirm), with side-metric
  guards on tail risk.
- **Implementation:** a Python package module + thin `fh-mj-selfplay-loop` CLI with
  unit-tested gate and ledger logic, calling existing generate/train/evaluate code
  as library functions.

## Architecture & Components

Follows the repo convention (`fh-mj-*` CLI + tests). Calls existing code as library
functions so the loop is testable end-to-end on the mock bridge.

- `ai/src/fh_mahjong_ai/selfplay_loop.py` — core library:
  - `LoopConfig` (dataclass): iterations, episodes/iter, seed schedule, seat-policy
    template, fixed init, base data, gate thresholds, screen/confirm seed sets,
    train hyperparams, patience, device, match_mode.
  - `GateThresholds` (dataclass) + `gate_decision(...)` — pure, unit-tested
    two-stage promotion logic over eval-report dicts.
  - `LoopLedger` — JSON state (iteration, current best, accumulated data, cached
    best eval, per-iteration history, consecutive non-promotions); load/save;
    resumable.
  - `run_iteration(...)` / `run_loop(...)` — orchestration calling
    `collect_mixed_selfplay_episodes` + storage, `train_iql(...)`,
    `evaluate_duplicate_seats(...)`.
- `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py` — CLI `fh-mj-selfplay-loop`.
- `ai/tests/test_selfplay_loop.py` — tests for the gate, the ledger, and a tiny
  mock-bridge iteration.
- `ai/pyproject.toml` — add the `fh-mj-selfplay-loop` entry point.
- `ai/AGENTS.md` — document the new module, CLI, and tests.

## Iteration Flow (iteration N)

1. **Generate self-play.** `episodes_per_iter` Chongci matches; current best in 2
   seats + heuristic + random (rotated by window); seed window
   `start_seed + N*seed_stride`, disjoint from eval seeds. Shards →
   `run_dir/iterN/selfplay/`; appended to the accumulated-data list.
2. **Train candidate.** `train_iql` from the fixed init on `base_data` (anchor's
   original ~409k-transition mix) + all accumulated self-play dirs via repeated
   `--data`, full epochs, no truncation → `run_dir/iterN/candidate/`.
3. **Gate** (see below) → promote or reject.
4. **Persist ledger** after every step (resumable mid-iteration).

Data grows each iteration (anchor mix + N self-play windows): candidates see
strictly more data over time, which is the mechanism by which they eventually
surpass the anchor. Memory is a future concern; datasets are array-backed and the
training box has headroom, so no truncation for now.

**Eval caching:** screen/confirm seeds are fixed, so the current best's evals are
cached in the ledger and recomputed only when the best changes — saving one full
eval per iteration.

## Two-Stage Promotion Gate

Pure functions over eval-report dicts (which expose `mean_reward`,
`mean_reward_ci95`, `large_loss_rate`, `positive_reward_rate`).

```
GateThresholds:
  screen_margin  = 0.05   # candidate within margin of best to earn a confirm run
  large_loss_eps = 0.0    # candidate.large_loss <= best.large_loss + eps
  positive_eps   = 0.02   # candidate.positive  >= best.positive  - eps

screen_pass(cand_screen, best_screen):
    cand.mean_reward >= best.mean_reward - screen_margin

confirm_promote(cand_confirm, best_confirm, thr):
    (cand.mean_reward - cand.mean_reward_ci95) >= best.mean_reward          # CI-separated
    AND cand.large_loss_rate      <= best.large_loss_rate      + thr.large_loss_eps
    AND cand.positive_reward_rate >= best.positive_reward_rate - thr.positive_eps
```

Flow per iteration:
1. **Screen** at `screen_seeds` (default 80): eval candidate; compare to best's
   cached 80-seed eval. If `not screen_pass` → reject (skip confirm). Common, cheap
   path.
2. **Confirm** at `confirm_seeds` (default 240): eval candidate + best on the same
   seeds. Promote iff `confirm_promote`.

`gate_decision(...)` returns a typed result —
`REJECTED_SCREEN | REJECTED_CONFIRM | PROMOTED` plus both reports — recorded in the
ledger history. The CI-separation requirement is the explicit guard against the
noisy-promotion failure mode that has repeatedly misled this project. The
side-metric guards reject a higher-mean but worse-tail-risk candidate, matching
Chongci's tail sensitivity.

## Ledger & State

`run_dir/ledger.json`, saved after every step:

```
iteration, fixed_init, base_data[], current_best,
current_best_eval{ screen, confirm }, accumulated_selfplay[],
history[ { iter, candidate, screen_metrics, confirm_metrics?, decision } ],
consecutive_non_promotions
```

`current_best` starts as the promoted anchor (or `--initial-best`). `--resume`
reloads and continues from `iteration+1`. The loop stops at `--iterations` or after
`--patience` consecutive non-promotions.

## CLI

`fh-mj-selfplay-loop`:
`--run-dir --iterations --episodes-per-iter --base-init --base-data --initial-best
--start-seed --seed-stride --screen-seeds --confirm-seeds --epochs --batch-size
--lr --patience --match-mode chongci --device --resume` (gate thresholds
overridable).

The loop does **not** modify `best-checkpoints.json`; promoting a successful loop
winner into the global registry stays a deliberate manual step.

## Testing

`ai/tests/test_selfplay_loop.py` (mock bridge / tiny model):

- `gate_decision`: promote (CI-separated + side metrics ok); reject-on-screen;
  reject-on-CI-overlap; reject-on-large-loss-regression; reject-on-positive-drop.
- `LoopLedger`: save/load round-trip; resume continues at the right iteration;
  best-eval cache invalidated when best changes.
- End-to-end: one mock-bridge iteration produces a candidate and updates the
  ledger.

## Execution

Remote 4090, background nohup, resumable. ~1h per iteration (generation ~20 min +
training a few min + screen/confirm evals). Run ~5–10 iterations overnight.

## Acceptance Criteria

- `fh-mj-selfplay-loop` runs N iterations end to end on the mock bridge in tests and
  on the Go bridge on the training box.
- The ledger is written after each step and `--resume` continues correctly.
- A candidate is promoted only when it passes the two-stage CI gate; the deployed
  current best never regresses.
- The gate and ledger logic are covered by unit tests.
