# Eval Hygiene + Observation Double-Count Fix (Spec A) — Design

**Date:** 2026-07-14
**Branch:** `claude/eval-hygiene` (off main @ 97a84c9)
**Status:** Approved design → implementation plan next

## Context

This is Spec A of the three-spec final-campaign rebuild (A: this; B: history/belief
representation rebuild with privileged critic; C: γ=1 placement-objective ablation).
It comes first because everything downstream depends on trustworthy measurement, and
because a confirmed observation defect has been corrupting every net's training input
at interrupt decisions all campaign.

Origin: the GPT-5.6 Codex methodology audit (2026-07-14) of the seven-lever campaign,
cross-validated by an independent literature survey. Two audit findings are actionable
now:

1. **Observation defect (CONFIRMED in code):** `handleDiscard` appends the discarded
   tile to `player.Discards` (internal/engine/game.go:813) and then sets
   `State.ActiveDiscard` to the same tile (game.go:821). `publicSeenCounts`
   (internal/rl/observation.go:495-503) sums BOTH `player.Discards` and
   `ActiveDiscard` — so during every WAIT_DISCARDS window, the tile being claimed is
   double-counted in the public-seen counts. Interrupt decisions (pon/chii/ron) are
   exactly where the visible count of that face matters most.
2. **Evaluation methodology:** (a) the paired CI treats 480 placements (120 wall
   seeds × 4 duplicate rotations) as iid — rotations within a seed are correlated, so
   the CI is miscalibrated by an unmeasured cluster design effect; (b) the `870000+`
   seed window was used for checkpoint selection (iter_200/240/275) AND later gates —
   winner's-curse bias of roughly +0.035 expected on the champion's number; (c) 480
   placements (CI ±0.075-0.082) cannot resolve the +0.03-0.05 effects the remaining
   levers predict.

## 1. The double-count fix

**Change:** remove the `faceCountsFromTile(state.ActiveDiscard)` term from
`publicSeenCounts` (observation.go:502).

**Why this is always correct (the invariant):** the `Discards` append (game.go:813)
executes immediately before `ActiveDiscard` is assigned (game.go:821) in the same
handler; claims that remove the discard from the pile also nil `ActiveDiscard`; the
no-interrupt turn-advance nils it too. Therefore whenever `ActiveDiscard != nil`, the
same tile is already present in the discarder's `Discards` — the term is always a
duplicate, never a unique contribution. (Alternatives rejected: fixing the engine by
deferring the append touches gameplay/UI/paipu semantics for the same arithmetic;
dynamic dedup is equivalent extra code guarding an impossible case.)

**Regression test (RED on current code):** construct a WAIT_DISCARDS window (a
discard with a live claim available) and assert the claimed face is counted exactly
once in the encoded observation's seen-counts plane/scalars; assert a non-window
state's counts are unchanged by the fix.

**Champion compatibility — measure, then decide.** The frozen champion
(`chongci_selfplay_deep4_phaseb1_iter275_39ch`) was trained on the corrupted
encoding; the fix shifts its inputs at interrupt decisions. Protocol:

- Paired eval on the fresh screening window (`910000+`, 480 placements): champion
  under FIXED encoder vs champion under BUGGY encoder (both vs the same opponents;
  identical seeds; the compare tool of §2 computes the clustered paired diff).
- **Decision rule:** if fixed ≥ buggy within the clustered CI (expected — the
  corruption is a small count shift on one face), the fix ships unconditionally
  (serving + training + eval). If fixed is CI-worse, serving gets a temporary
  `--compat-double-count` encoder flag pinned to the current champion until Spec B
  retrains on the fixed encoding; training and all NEW runs use the fixed encoder
  regardless. The flag, if ever created, is deleted at the first post-fix promotion.

## 2. Evaluator statistics upgrade

**Report additions (backward-compatible; existing fields unchanged):** duplicate-seat
reports gain

- `per_seed_mean_placements`: one 4-rotation mean per wall seed (length = seeds);
- `mean_placement_ci95_clustered`: t-interval over the per-seed means;
- `cluster_design_effect`: ratio of clustered to naive variance (diagnostic — makes
  the within-seed correlation visible instead of assumed).

Clustering method: per-seed means + t-interval (n ≥ 120 seeds makes this as robust
as a bootstrap, with none of the resampling machinery). The naive fields stay for
continuity with all historical reports.

**New CLI `fh-mj-compare`** (`ai/src/fh_mahjong_ai/scripts/compare_reports.py`):
takes two duplicate-seat report JSONs produced on the SAME seed window, validates
seed alignment (identical seed lists, refuses otherwise), and prints the
seed-clustered PAIRED difference: per-seed paired deltas, mean, clustered CI95,
plus large-loss rates side by side and a machine-readable JSON output mode
(`--json`). This replaces the ad-hoc aggregator scripts shipped to the box all
campaign, and is the single tool every future gate verdict must come from.

## 3. Seed-window policy and power

Documented in this spec and appended to the progress note's maintenance protocol:

- **`870000+` is RETIRED** for any promotion decision (burned: used for
  iter_200/240/275 selection and every subsequent gate).
- **Screening window: `--start-seed 910000`,** `--online-episodes 120` (480
  placements): cheap looks, checkpoint selection, intermediate curiosity.
  Unlimited use; never cite for promotion.
- **Confirmation window: `--start-seed 950000`,** `--online-episodes 1500`
  (6000 placements, ~6h box time — user-approved budget): final gates ONLY.
  Every promotion or lever-verdict claim must cite a confirmation-window run
  with the clustered paired CI from `fh-mj-compare`. (The two windows never
  overlap: screening consumes seeds well below 950000 at these episode counts.)
- Power reference (iid-optimistic; multiply by the measured design effect):
  1500 seeds → CI half-width ≈ ±0.03; 80% power for a true +0.05 at ~550 seeds,
  for +0.03 at ~1530 seeds.

## Deliverables & sequencing

1. Go: observation fix + regression tests (`internal/rl`).
2. Python: report additions + `fh-mj-compare` + tests (chunk-invariant, seed-
   alignment refusal, clustered-vs-naive sanity on synthetic data).
3. Docs: seed-window policy into the progress-note protocol section; AGENTS.md
   updates for touched dirs.
4. Operational close-out (post-merge, on the 4090): the champion fixed-vs-buggy
   paired screening eval; apply the decision rule; record the measured
   `cluster_design_effect` of the screening window in the progress note — it
   calibrates all of Spec B's planned run sizes.

## Out of scope

- Spec B (history/belief representation + privileged critic) and Spec C (γ=1
  placement objective) — separate specs, designed after this lands.
- Any retraining. Spec A only fixes instruments and inputs.
- Backfilling historical reports with clustered stats (the old numbers stand as
  recorded; comparisons across the fix are annotated, not rewritten).

## Risks

- Champion degradation under the fixed encoder — bounded by the measure-then-decide
  rule and the compat flag escape hatch.
- The clustered CI may come out WIDER than the naive one (positive within-seed
  correlation), retroactively weakening some historical margins — that is the point;
  the progress note gains one honest sentence about it rather than silence.
