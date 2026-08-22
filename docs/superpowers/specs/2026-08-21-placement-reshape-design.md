# `placement-reshape` — asymmetric terminal placement utility on the champion recipe

Status: **RATIFIED 2026-08-21** by Codex design consult (fresh thread, GPT-5.6-Sol
medium effort; user settled the canonical-thread question by opening a fresh
thread for this experiment) and approved by the user the same day. Ruling:
**"AUTHORIZED FOR SPECIFICATION AND STAGE 0 under Option A with k = 0.5; GRP and
the legacy trainer are out of scope. Training remains unauthorized until the λ
calculation, reward-placement parity tests, actual-return scale gates,
zero-truncation preflight, and eval metric gauntlet pass."**

This is a single pre-registered experiment in the `data-scale-960` style. It is
NOT a reopened training ladder; the result returns to consultation.

Worktree `placement-reshape`, branch `experiment/placement-reshape-10-5-1-n10`.
Context handoff: `2026-08-21-placement-reshape-context.md`. Live progress record:
`/Users/plasma/fh-mahjong/.claude/docs/placement-reshape-experiment.md` (main
checkout, shared across worktrees).

## Motivation

The 2026-08-06 retirement verdict and the 2026-08-20 ds960 NULL close the
symmetric-objective ladder (r2 null, deep16 null, gru-width collapsed, ds960
null vs `anchor075`). The close-out permits reopening training only for **new
information or a genuinely different objective**. This experiment changes the
objective: the user directive is an asymmetric placement utility **(10, 5, 1,
−10)** — mean-subtracted ≈ (+8.5, +3.5, −0.5, −11.5): 4th place catastrophic,
3rd nearly neutral, modest 1st-vs-2nd gap. Predicted policy shift: defensive /
risk-averse play (earlier folds, deal-in avoidance), plausibly at some cost in
mean placement. Tail safety is what the objective optimizes, so tail metrics are
the primary readout.

## Corrections to the handoff premise (verified in code, 2026-08-21)

1. **The champion recipe does not use placement shaping.** `anchor075` and every
   lap in the track record are trained by `fh-mj-train-b2b` (`train_b2b.py`:
   symmetric 4-seat self-play, event history, aux heads, privileged critic). Its
   reward is the raw per-hand Chongci score delta / 1000 from the Go env
   (`train_b2b.py:522`). `PPOConfig.grp_checkpoint` / `grp_placement_values`
   exist only on the legacy `fh-mj-train-ppo` GRP path. Final rank reaches B2b
   only as a hindsight aux-head label (`rank_labels`, class 4 = bust). The
   handoff doc's lever (`grp_placement_values → (10,5,1,−10)`) would not have
   touched the champion's training signal.
2. **"Only shape matters; scale is invisible" is only half true.** Advantage
   normalization (`ppo.py:294`) makes the *policy* gradient scale-free, but
   `value_loss = mse_loss(value, ret_t)` (`ppo.py:378`) is on raw returns and
   shares the trunk. Scale is therefore a real variable and is controlled
   explicitly below (λ calibration + Stage-0 return-scale gates).
3. **`_EVAL_PLACEMENT_VALUES` was never "in sync" with B2b training.** The
   canonical symmetric vector (1, ⅓, −⅓, −1) has only ever been the independent
   longitudinal evaluation utility for this campaign. The `evaluate.py` comment
   claiming a sync invariant is rewritten (see Eval gate).

## Consult verdicts

| # | Question | Verdict |
|---|---|---|
| Q1 | Vector scale | Register the centered, RMS-matched vector `v`; scale is controlled by the product `λ·v`, not `v` alone. A terminal bonus is not a uniform return rescale: under γ=0.99, λ_GAE=0.95 its direct advantage contribution decays as 0.9405^d (0.54 @10 decisions, 0.047 @50, 0.0022 @100). Stage 0 must measure actual GAE returns and critic loss. |
| Q2 | How the reward enters B2b | **Option A** (additive terminal bonus on top of the unchanged dense score reward). B (replace dense reward with sparse placement) rejected: discards the champion's dense signal and is extremely attenuated under γ=0.99; changing γ would be a second intervention. C (rank-conditioned score scaling) rejected as unprincipled. GRP eliminated entirely. `k = 0.5`, not 1.0 (see λ). |
| Q3 | Eval gate metric | Canonical symmetric gate **frozen**; the B2b correction strengthens this. Asymmetric `training_utility_mean` reported as secondary, paired, seed-clustered, **non-gating**. |
| Q4 | Success definition | **Tail-primary** (thresholds below). Pass ⇒ tail-specialist champion; `anchor075` stays canonical champion unless canonical superiority independently clears. |
| Q5 | Tail stats | Eval-side 4th-place share is **gating**; B2b `rank_labels` are integrity telemetry only (decision-weighted, bust ≠ 4th, and 4-seat self-play 4th share is mechanically ~25%). |
| Q6 | Budget | 150 iters, 320/mb256, warm start `anchor075`; freeze the champion's actual discounting (see Stage 0 item 5). |
| Q7 | Governance | **YES** — clears the "genuinely different objective" bar; not a continuation of the retired dense-score ladder. |

## Design

### The intervention (one registered change)

For every seat `s` of every **completed** match, at that seat's final recorded
transition:

```
r_terminal_new(s) = r_terminal_score(s) + λ · v(final_rank(s))
```

All preceding dense score rewards are unchanged. Because B2b learns all four
seats, the bonus is applied to every seat, not one nominal learner.

- `v` = (10, 5, 1, −10) mean-subtracted and RMS-matched to the canonical vector:
  **`v = (0.8601670494, 0.3541864321, −0.0505980617, −1.1637554197)`**, RMS
  0.7453559925 (= canonical RMS). Registered to full precision; any rescaling of
  `v` is cancelled by inverse rescaling of λ, so `v` is fixed for auditability.
- Placement is computed from **exact final scores** (integer points, same
  rounding as `_assemble_hindsight_labels`), descending; **tied rank slots
  average their utilities** (so the per-match bonus sum is always zero). Never
  derived from `rank_labels` (class 4 = bust, not a 4th-place utility).
- **λ = 0.5 · σ_R / σ_V**, frozen from the Stage-0 calibration collection:
  over all 4 × 320 seat-match observations, `R` = accumulated dense match-net
  reward (score/1000 units), `V` = `v(final_rank)` with averaged ties; σ with
  `ddof=0`. The empirical terminal-bonus std is then exactly half the existing
  match-net std. At this k the unique 4th-place bonus ≈ −0.78 σ_R.
  Rationale for rejecting k=1.0: rank is derived from score, so the two are
  strongly positively correlated; equal component stds would push the
  composite match return to ~1.7–2.0× the existing std (~3–4× MSE) —
  co-dominant double counting, not a tilt.
- **λ is never adjusted post hoc.** If a Stage-0 gate fails, return to consult.

### Eval gate (frozen canonical) and the sync comment

`_EVAL_PLACEMENT_VALUES` stays (1, ⅓, −⅓, −1). The `evaluate.py` comment is
replaced with the consult's wording:

```python
# Frozen canonical longitudinal evaluation utility by rank (1st..4th).
# This metric is intentionally independent of trainer reward functions.
# Modern Spec B2b trains on dense Chongci score deltas; reward-objective
# experiments may add separately registered terminal utilities. Do not
# synchronize this constant to any training reward configuration.
# Step-limit truncations remain scored as canonical worst placement.
```

Secondary, non-gating report: paired seed-clustered delta of the asymmetric
training utility (`v` applied to eval ranks, truncation = min(v)).

### Success definition (pre-registered, tail-primary)

Confirmation = the selected milestone vs **regenerated `anchor075`**, 1500
paired seeds × 4 duplicate seats, fresh window **1300000–1301499**, paired
seed-clustered CI95, back-to-back, `fh-mj-compare` (config_check=strict,
bridge_check=match, window_check=match).

| Metric | Role | Pass condition |
|---|---|---|
| 4th-place share delta | **primary** | ≤ −0.010 AND CI95 upper < 0 |
| canonical mean-placement delta | non-inferiority | CI95 lower > −0.030 |
| large-loss rate delta | safety | CI95 upper ≤ +0.005 |
| deal-in rate delta | descriptive | reported, not gating |
| asymmetric training-utility delta | descriptive | reported, not gating |

All three gating conditions must hold. **Pass ⇒ the checkpoint is recorded as
a tail-specialist champion** (a distinct role; deployment is a separate consult
decision). `anchor075` remains the canonical champion **unless** canonical
superiority independently clears: canonical mean-placement CI95 lower > 0 AND
candidate large-loss rate ≤ anchor075 + 0.015 (the historical canonical gate).

4th-place share is computed at **match level from final scores**: ties allocate
fractional occupancy; a truncated match counts as **full** 4th-place occupancy
for the learning seat (the objective's terminal rank does not exist, and
omitting it would censor). The 4th-share SEM at 1500×4 is expected ≈ 0.005–0.007,
so the primary threshold demands a real effect of roughly −0.02; accepted
knowingly as a strict test.

### Stage 0 — prerequisites (no training)

All code changes are gauntleted (unit tests + digest parity) before the box is
touched. Order matters: 1 → 5 → 2 → 3 → 4 is acceptable; λ must be frozen
before the scale gates run.

1. **Terminal-bonus wiring in `train_b2b`.** New `PPOConfig` fields
   `placement_bonus_values: tuple | None` and `placement_bonus_lambda: float`
   (default None / 0.0 = off), CLI `--placement-bonus-values` /
   `--placement-bonus-lambda`, persisted in the frozen config and train state
   (resume config echo: **rejected-on-change**, not logged — the bonus is the
   scientific intervention). Parity tests:
   - exactly one bonus attached per seat per completed match, at the seat's
     final recorded transition;
   - per-match bonus sum = 0 within 1e-6, including ties (test 2-way, 3-way,
     4-way ties and a busted seat);
   - reward tensors otherwise byte-identical to the unshaped path;
   - λ = 0 (or values None) reproduces the champion rollout digest exactly;
   - a truncated match receives **no** bonus and is counted (see 3).
2. **λ calibration collection.** One frozen registered collection of **320
   complete `anchor075` self-play matches**, champion collection recipe, fresh
   diagnostic seeds **720000–720319**. Compute σ_R, σ_V (ddof=0), freeze
   `λ = 0.5·σ_R/σ_V` in the spec's Amendment record with the raw σ values and
   the collection digest. Then, on the **identical frozen batch** with a cloned
   anchor model, compare raw vs bonus-shaped GAE — all must pass:
   - shaped-return RMS / raw-return RMS ≤ **1.35**;
   - shaped |return| p99 / raw |return| p99 ≤ **1.50**;
   - initial shaped critic MSE / raw critic MSE ≤ **2.00**;
   - all advantages and returns finite; normalized-advantage std valid and
     nondegenerate;
   - bonus telemetry (mean, RMS, p99, per-rank occupancy) recorded.
   Any failure → stop, return to consult. Do not lower λ.
3. **Zero-truncation rule.** Any truncated match **fails** the Stage-0
   collection and the scientific lap (hard stop, back to consult). The
   ds960 "halt only above 2% truncation" rule does not apply to this objective.
4. **Eval metric gauntlet (`evaluate.py`).** Add a match-level rank-share
   histogram (`placement_rank_shares` 1st..4th, fractional ties, truncation =
   full 4th) plus `fourth_place_rate`; add the asymmetric secondary utility;
   verify `deal_in` is actually populated on the opponent-pool path (the pool
   wrapper is known to drop `round_outcome` — if deal-in degrades to "unknown"
   on the eval path used here, fix or document before the lap). Tests: known
   hand-built outcomes incl. ties/truncation; `fh-mj-compare` must emit paired
   clustered CIs for 4th-share, large-loss and canonical placement.
   Training-side telemetry (integrity only, per iteration): match-level rank
   occupancy, tie/bust counts, bonus mean/RMS/p99, per-seat occupancy for
   seat-bias detection, and the decision-weighted aux label distribution
   (named as such).
5. **Freeze the champion discounting from the archive.** Read the ds960
   archived frozen config (`/root/fh-mahjong-runs/data-scale-960/`, read-only)
   and record `gamma` / `gae_lambda` actually used by `anchor075`'s lineage.
   Consult assumed the CLI defaults (γ=0.99, λ_GAE=0.95); the ds960 spec's
   "δ=1" is ambiguous and the γ=1 invariant in memory belongs to the legacy GRP
   path. Whatever the archive says is frozen verbatim; if it is γ=1, the
   Q1 decay arithmetic is moot but nothing else changes.
6. **Wall-clock** from the Stage-0 collection; ballpark from ds960 at 320
   matches/iter ≈ 3× faster per iter than the 960 lap.

### Stage 1 — the lap

| Item | Value |
|---|---|
| Trainer | `fh-mj-train-b2b`, champion recipe frozen: warm start `anchor075` (restart-iter075), lr 2e-5, ppo_epochs 2, entropy 0, minibatch 256, 320 matches/iter, chongci, event window 128, residual_blocks 4, event_hidden 128, privileged critic on, aux heads on, `AUX_LOSS_WEIGHT` 0.1, normalized advantages, max-grad-norm unchanged, optimizer unchanged, γ / λ_GAE per Stage-0 item 5 |
| Intervention | `--placement-bonus-values v --placement-bonus-lambda λ` (frozen) |
| Iters | 150 |
| Base seed | **650000**; training seeds 650000–698319 inclusive (no overlap with 100k–148k, 200k–248k, 400k–453k, 500k–644k, 700k–701k, 720k diag, 4M, 8M, or any eval window ≥ 870000) |
| Run dir | `/root/fh-mahjong-runs/placement-reshape/` (the ds960 dir is a read-only archive) |
| Screenings | 25/50/75/100/125/150 vs regenerated `anchor075`, seeds 910000–910119, 120 paired seeds × 4 seats, `fh-mj-compare`; report canonical delta, 4th-share delta, large-loss delta, deal-in, asymmetric utility |
| Kill rule | kill @100 iff **both** screens 75 and 100 have canonical mean-placement delta < −0.060 **and** 4th-place delta > −0.005 (i.e. losing on the canonical metric without buying tail safety) |
| Eligibility | milestone eligible iff 4th-place delta ≤ −0.005, canonical delta ≥ −0.050, large-loss delta ≤ +0.010, zero integrity/truncation failures |
| Selection | lowest 4th-place delta among eligible; within 0.001 → higher canonical delta; then earlier milestone. No eligible milestone ⇒ NULL, no confirmation run |
| Confirmation | selected milestone, seeds 1300000–1301499, 1500 paired seeds × 4 seats, back-to-back vs regenerated anchor075 |
| Protocol | no optional stopping; no extension; no second confirmation; no auto-chaining — result returns to consult |

Warm-starting a symmetric-reward champion onto a tilted objective may produce an
early transient (the critic must absorb the new terminal spike); the kill rule
is deliberately placed at 100 with a two-screen requirement so a transient at
25/50 cannot kill the lap.

### Decision tree

- **Tail-primary pass, canonical not superior** → tail-specialist champion
  recorded; anchor075 stays canonical champion; next consult decides whether
  the specialist is deployed (e.g. as an alternative seat policy).
- **Tail-primary pass AND canonical superiority** → promotion candidate for
  canonical champion via the standard promotion path.
- **Null / kill** → the asymmetric-utility objective at k=0.5 is closed under
  this recipe; no λ sweep, no k sweep, no (10,5,−5,−10) variant without fresh
  authorization.

## Pre-registered risks

- **Correlated components.** Rank is a function of score, so the bonus partly
  re-rewards what the dense signal already rewards; k=0.5 and the Stage-0
  scale gates bound this. If the RMS gate fails, the correct response is
  consult, not a smaller λ.
- **Critic shock.** The terminal spike lands on recent decisions; early
  screenings may dip. Handled by the kill-rule placement.
- **Mechanical 4th share in self-play.** Training-side 4th share ≈ 25% by
  construction; only the eval delta vs anchor075 is evidence.
- **Deal-in availability.** Pool wrapper drops `round_outcome`; Stage-0 item 4
  verifies the eval path used here actually reports deal-in.
- **Strict primary threshold.** −0.010 with CI upper < 0 needs ≈ −0.02 real
  effect at the registered sample size. Accepted by the user 2026-08-21.
- **Ops traps carried over** from the ds960 runbook: ssh double-execution
  (flock launch guard), box mtimes in −0700, worktree guard blocks compound
  Bash, `uv run --project ai` only, do not write into the ds960 archive.

## Amendments

(none yet — λ, σ_R, σ_V, γ/λ_GAE from the archive, and the Stage-0 gate
results are recorded here when Stage 0 completes)
