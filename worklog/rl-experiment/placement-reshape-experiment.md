# Placement-reshape experiment — progress tracking

Status: **SPEC RATIFIED 2026-08-21 — Stage 0 authorized, training NOT yet authorized.**
Worktree `placement-reshape`, branch `experiment/placement-reshape-10-5-1-n10`.
Spec: `worklog/specs/2026-08-21-placement-reshape-design.md` (Codex consult in a
FRESH thread — user settled the canonical-thread question that way; GPT-5.6-Sol medium).

## Ratified design (2026-08-21) — supersedes the "settled conclusion" section below

- **Premise correction:** the champion recipe is `fh-mj-train-b2b` and does NOT use GRP /
  `grp_placement_values` — its reward is raw per-hand score/1000. The canonical
  (1,⅓,−⅓,−1) vector lives only in the eval gate and was never "in sync" with B2b.
- **Intervention = Option A:** additive terminal bonus `λ·v(final_rank)` on every seat's
  last transition, on top of the unchanged dense reward. `v` = (10,5,1,−10) centered +
  RMS-matched = (0.8602, 0.3542, −0.0506, −1.1638); **λ = 0.5·σ_R/σ_V** frozen from a
  Stage-0 320-match anchor075 collection (seeds 720000–720319). k=1.0 rejected
  (rank/score correlated → co-dominant).
- **Eval gate stays canonical symmetric** (frozen, independent); evaluate.py comment rewritten.
- **Success = tail-primary:** 4th-share delta ≤ −0.010 & CI upper < 0; canonical delta
  CI lower > −0.030; large-loss delta CI upper ≤ +0.005. Pass → tail-specialist champion;
  anchor075 stays canonical champion unless canonical CI lower > 0 & LL ≤ +0.015.
- **Protocol:** 150 iters, 320/mb256, base-seed 650000, screens 25..150 @910000–910119,
  kill@100 iff both 75&100 canonical < −0.060 AND 4th delta > −0.005, selection by lowest
  4th delta among eligible, confirmation 1500×4 @1300000+. Any truncation = hard stop.
- **Stage 0 still open:** bonus wiring + parity tests, λ calibration + return-scale gates
  (RMS ≤1.35, p99 ≤1.50, critic MSE ≤2.00), rank-share histogram + deal-in availability in
  evaluate.py, read γ/λ_GAE from the ds960 archive (consult assumed 0.99/0.95 — unverified).

## Pre-ratification context (historical)


## Where this came from (stage at authorization, 2026-08-21)

[[project_scale_roadmap]] — data-scale-960/mb768 CLOSED 2026-08-20 as a scientifically
valid NULL (+0.0175, CI95 [−0.0010, +0.0360] crosses zero; large-loss gate passed).
anchor075 remains champion; ds960 iter_050 is a retained research artifact — **never
promote or deploy it**. Box archive `/root/fh-mahjong-runs/data-scale-960/` is
read-only; spec PR #218 merged. The close-out ruling allows reopening training only
for "new information / a genuinely different objective."

## Conclusion of the placement-weights discussion (settled with the user)

- Only the **shape** of the placement-value vector matters. Mean and scale are
  invisible both to the GRP gradient (group-relative advantage normalization divides
  scale out, baseline absorbs the mean) and to eval significance (delta and CI scale
  together). E.g. (10, 3.33, −3.33, −10) ≡ current (1, ⅓, −⅓, −1) exactly.
- Current vector is symmetric, zero-mean, equally spaced (step ⅔) — `evaluate.py`
  `_EVAL_PLACEMENT_VALUES`, kept in sync with `PPOConfig.grp_placement_values`.
- **(10, 5, 1, −10)** is a real objective change: effective incentives after mean-
  subtraction ≈ (+8.5, +3.5, −0.5, −11.5) — 4th place is catastrophic, 3rd nearly
  neutral. Expected policy shift: strongly risk-averse / defensive play (fold early,
  avoid deal-in), possibly at the cost of win rate vs heuristics (aggressive champion
  already wins ~75% of matches).
- (10, 5, −5, −10) variant = symmetric "protect-top-half" shape (middle gap doubled);
  discussed but NOT the one chosen.

## The authorized experiment

User directive 2026-08-21: "Let's try (10,5,1,-10) and see how it goes, start a new
worktree and new session." This is the sanctioned "genuinely different objective"
ground — a NEW experiment, not a ds960 rerun.

- Worktree: `/Users/plasma/fh-mahjong/.claude/worktrees/placement-reshape`,
  branch `experiment/placement-reshape-10-5-1-n10` (off main), context doc
  `worklog/specs/2026-08-21-placement-reshape-context.md` committed there.
- **Still pending before any run:** Codex design consult ([[feedback_codex_next_steps_consult]]
  — MANDATORY; canonical-thread question still open: user-designated `019f49e8…` vs
  A9-successor `01a0147d…`, never both) and a pre-registered spec (gate metric,
  milestones, kill rule) in the ds960 style.
- **Key design decision to settle in the consult:** training reward becomes
  (10,5,1,−10), but the eval gate metric should probably STAY the canonical symmetric
  (1,⅓,−⅓,−1) for comparability with the champion — this deliberately breaks the
  "kept in sync" invariant between `grp_placement_values` and `_EVAL_PLACEMENT_VALUES`
  noted in evaluate.py:84. Decide explicitly and document. Also report shape-native
  descriptive stats (4th-place rate, deal-in rate, large-loss rate) since that's what
  the new objective targets.
- Comparator: anchor075 (restart-iter075 champion). Hardware/paths: the 4090/WSL box
  per [[project_scale_roadmap]]; do NOT write into the read-only ds960 archive dir —
  use a fresh run dir.
