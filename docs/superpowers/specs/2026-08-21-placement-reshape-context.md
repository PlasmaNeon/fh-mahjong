# Placement-reshape experiment — session handoff context (2026-08-21)

**Status: AUTHORIZED, not yet designed.** User directive (2026-08-21): try training with
asymmetric placement reward **(10, 5, 1, −10)** and see how it goes, in a fresh worktree
and fresh session. This doc is the starting context for that session.

## Where the project stands (stage + conclusion as of 2026-08-21)

- **data-scale-960/mb768 is CLOSED (2026-08-20)** — scientifically valid NULL.
  Confirmation (1500 paired seeds x 4 duplicate seats vs anchor075): mean_delta
  +0.0175, clustered CI95 [−0.0010, +0.0360] → not significant; large-loss gate
  passed (0.0487 vs 0.0505). Ratified wording: estimate compatible with either no
  improvement or a small positive effect below the experiment's resolution.
- Disposition (Codex consult, concurred on all points): **anchor075 remains
  champion**; ds960 **iter_050 is a retained research artifact that FAILED
  confirmation — never promote or deploy it**; evidence archived read-only at
  `/root/fh-mahjong-runs/data-scale-960/` on the 4090/WSL box (**do not write there**);
  spec + Final Outcome merged as PR #218; live status file retired.
- Track record vs restart-iter075 anchors: r2 null, deep16 null, gru-width
  unconfirmed (collapsed), ds960 null. Local saturation verdict stands. The close-out
  permits reopening training only for **new information / a genuinely different
  objective** — this experiment is exactly that ground.

## Why (10, 5, 1, −10) is a genuinely different objective

Settled analysis from the closing discussion:

- Only the **shape** of the placement vector matters. Mean and scale are invisible to
  both the GRP gradient (group-relative advantage normalization) and eval significance
  (delta and CI scale together). (10, 3.33, −3.33, −10) would be identical to the
  current (1, 1/3, −1/3, −1).
- (10, 5, 1, −10) mean-subtracted ≈ **(+8.5, +3.5, −0.5, −11.5)**: 4th place is
  catastrophic, 3rd nearly neutral, modest 1st-vs-2nd gap. Expected policy shift:
  strongly risk-averse / defensive play (early folds, deal-in avoidance), possibly at
  the cost of raw win rate (current champion already wins ~75% of matches vs the
  heuristic bots with the symmetric reward).

## Mandatory before any run

1. **Codex design consult** (standing instruction since 2026-07-19, `codex:rescue`,
   gpt-5.6-sol, MEDIUM effort, debate to agreement). **Open question the user must
   settle first: which thread is canonical** — user-designated
   `019f49e8-8f48-7042-b176-df12d8719753` (resume via
   `codex exec resume <id> ... -m gpt-5.6-sol -c model_reasoning_effort=medium`)
   or A9-successor `01a0147d-c23d-76b3-a585-1a0c4bc09456` (companion-resumable,
   holds the full ds960 context). **Never consult both in parallel.**
2. **Pre-registered spec** in the ds960 style (this directory): budget, milestones,
   screening cadence, kill rule, selection rule, confirmation gate, no optional
   stopping, no auto-chaining.

## Key design decisions to settle in the consult

- **Training reward**: `PPOConfig.grp_placement_values` → (10, 5, 1, −10)
  (`ai/src/fh_mahjong_ai/` config; shape is what matters — consider whether to
  normalize to zero-mean explicitly for numerical hygiene, it is gradient-equivalent).
- **Eval gate metric**: `_EVAL_PLACEMENT_VALUES` (evaluate.py:84) is currently "kept
  in sync" with the training reward. Recommendation carried over from the discussion:
  the confirmation gate should probably STAY on the canonical symmetric
  (1, 1/3, −1/3, −1) for comparability with anchor075 — which deliberately breaks the
  sync invariant. Decide explicitly, document in the spec, and update the evaluate.py
  comment accordingly. Also report shape-native descriptive stats (4th-place rate,
  deal-in rate, large-loss rate) since that is what the new objective targets.
- **Comparator**: anchor075 (the champion). Note an asymmetric-objective model may
  trade mean placement for tail safety — decide up front what "success" means: beat
  champion on the canonical metric, or hit a pre-registered tail-risk target without
  losing more than X on the canonical metric.
- **Run dir**: fresh directory on the box (e.g. `/root/fh-mahjong-runs/placement-reshape/`).
  The ds960 dir is a read-only archive.

## Ops traps that carry over (from the ds960 runbook)

- ssh to the box can double-execute commands; `sort -u` on ssh output collapses
  attribution — label lines explicitly.
- Box file mtimes display in −0700 local, not UTC.
- Worktree-isolation guard blocks compound/redirect Bash — use python3 heredocs or
  the Write tool for file writes outside plain commands.
- Pool wrapper drops `round_outcome` (long-standing trap; see scale-roadmap memory).
- Use `uv run --project ai ...` for all Python; `go run ./cmd/server` package form.

## Progress tracking

Live progress record: `.claude/docs/placement-reshape-experiment.md` (in the main
checkout `/Users/plasma/fh-mahjong/.claude/docs/`, shared across worktrees, NOT in
auto-memory — user convention: project progress tracking lives under `.claude/docs`).
Update it at each major transition (spec ratified -> running -> verdict) rather than
creating parallel records.
