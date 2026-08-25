# Placement-reshape experiment — progress tracking

**Status 2026-08-25: Stage 0 COMPLETE — code merged (PR #220), box gates all green
(spec Amendment 2), pre-Stage-1 consult RATIFIED launch as pre-registered.** Next: freeze
the launch manifest, then Stage 1. Update at each transition (running → verdict); do not
start a parallel record.

- **Spec** → [`../specs/2026-08-21-placement-reshape-design.md`](../specs/2026-08-21-placement-reshape-design.md)
- **Context** → [`../specs/2026-08-21-placement-reshape-context.md`](../specs/2026-08-21-placement-reshape-context.md)
- **Stage 0 plan** → [`../plans/20260822-placement-reshape-stage0.md`](../plans/20260822-placement-reshape-stage0.md)
- **Branch** — `experiment/placement-reshape-10-5-1-n10` (merged)

## Why

The ds960 close-out permits reopening training only for "new information or a genuinely
different objective." Changing the training objective is that ground. User directive
2026-08-21: *"Let's try (10,5,1,-10) and see how it goes."*

`fh-mj-train-b2b` trains on the raw per-hand score/1000 and does not use GRP or
`grp_placement_values`. The canonical `(1, ⅓, −⅓, −1)` vector is a frozen, independent eval
gate metric. This experiment adds a placement objective to training; it does not retune an
existing one.

## Design (ratified 2026-08-21)

Additive terminal bonus `λ·v(final_rank)` on every seat's last transition, on top of the
unchanged dense reward.

```text
v = (10, 5, 1, −10) centered + RMS-matched = (0.8602, 0.3542, −0.0506, −1.1638)
λ = 0.5 · σ_R/σ_V,  frozen from a Stage-0 320-match anchor075 collection (seeds 720000–720319)
```

`k = 1.0` rejected: rank and score are correlated, so at full strength the bonus becomes
co-dominant with the dense reward rather than a shaping term.

The eval gate stays canonical and symmetric — frozen and independent of the training
reward.

**Success is tail-primary:**

```text
4th-share delta   ≤ −0.010 and CI upper < 0
canonical delta   CI lower > −0.030
large-loss delta  CI upper ≤ +0.005
```

A pass makes it a *tail-specialist* champion; anchor075 stays canonical champion unless the
canonical CI lower clears 0 with large-loss ≤ +0.015.

**Protocol.** 150 iterations at 320 matches / minibatch 256, base seed 650000. Screens
25..150 against 910000–910119. Kill at 100 only if *both* the 75 and 100 canonical deltas
are < −0.060 AND the 4th delta is > −0.005. Selection by lowest 4th delta among eligible.
Confirmation 1500×4 at 1300000+. Any truncation is a hard stop.

## Expected effect

Effective incentives after mean subtraction ≈ `(+8.5, +3.5, −0.5, −11.5)`: 4th place is
catastrophic, 3rd nearly neutral. Predicted shift is strongly risk-averse defensive play —
fold early, avoid deal-in — possibly costing win rate against heuristics, since the
aggressive champion already wins ~75% of matches.

The vector's **shape** drives the policy gradient (advantage normalization divides scale
out); scale is NOT invisible — the value loss regresses raw returns on the shared trunk —
so it is controlled by the frozen λ calibration and the Stage-0 return-scale gates. A
symmetric "protect-top-half" variant `(10, 5, −5, −10)` was discussed and not chosen.

## Stage 0 (merged, PR #220)

Bonus wiring and parity tests, λ calibration tool (`fh-mj-placement-calibrate`), rank-share
histogram and deal-in availability in `evaluate.py`, tail-metric eval gate keys.

## Before any launch

1. **Calibrate λ** — 320-match anchor075 collection, seeds 720000–720319. Return-scale
   gates: RMS ≤ 1.35, p99 ≤ 1.50, critic MSE ≤ 2.00.
2. **Read γ and λ_GAE from the ds960 archive.** The consult assumed 0.99/0.95; unverified.
3. **Codex consult** on the calibration result, then explicit launch authorization.

Comparator is anchor075. Run on the 4090 box in a fresh run directory — the ds960 archive
at `/root/fh-mahjong-runs/data-scale-960/` is read-only. Trap: the generic Python pool
wrapper drops `round_outcome`, so a naive pool switch silently corrupts aux training.

## Stage 0 box measurements (2026-08-25) — all gates green

Archived γ=0.99, λ_GAE=0.95 confirmed. λ = 0.8567442838065646 (k=0.5; σ_R 1.2772, σ_V
0.7454, corr 0.8419; digest 6b3eda33…). Scale gates 1.1322 / 1.2007 / 1.3360 — PASS.
Positive-λ digest parity PASS (4× 3e228283… vs no-bonus b9f89979…). Screening completeness
PASS (parity 0, unknown_hands 0, deal-in ~0.102, seeds 910000–910119, zero truncations).
Full numbers: spec Amendment 2. Box artifacts `/root/fh-mahjong-runs/placement-reshape/stage0/`.
Pre-Stage-1 consult (GPT-5.6-Sol medium, resumed thread): **RATIFIED** — launch exactly as
pre-registered; confirmation window 1300000–1301499 confirmed fresh vs the spent-window list.
