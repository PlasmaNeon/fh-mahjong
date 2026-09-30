# Suit-augment extension lap — registration

**Registered 2026-09-30, before any run.** Authorized by the user in the post-lap queue ("Extended aug lap if
PASS"); the suit-augment lap passed (`20260929-suit-augment-lap.md`).

## Question

Does 150 more iterations of suit-augmented PPO from aug `iter_150` beat aug `iter_150`, both played
suit-averaged? The first lap gained +0.0114 over `anchor075` in 150 iterations; this asks whether the curve
is still rising.

## Run

| | |
|---|---|
| Init | aug `iter_150` of the suit-augment lap (`c5ff807b…`) |
| Recipe | identical to the suit-augment lap's aug arm: batched collector, 256 slots, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment` |
| Iterations | 150 |
| Training seeds | 2,650,000–2,697,999 (never used) |
| Code | commit `bc6b3cec`, the same bridge build as the first lap (`3142fe71…`) |

One arm, no control: the first lap already measured augmentation against plain training.

## Evaluation (fixed now; no screening, no selection)

Only the new `iter_150` is evaluated, through the batched evaluator (256 slots), on fresh seeds
**2,710,000–2,714,999** (5,000 × 4 duplicate seats), one bridge build.

- **Primary:** new `iter_150` suit-averaged vs aug `iter_150` suit-averaged. **Pass iff** clustered CI95 lower
  bound > 0 and large-loss(new) ≤ large-loss(aug `iter_150`) + 0.015.
- **Secondary (descriptive):** new `iter_150` suit-averaged vs `anchor075` suit-averaged.

A pass makes the new `iter_150` (suit-averaged) the strongest policy. A fail keeps aug `iter_150`; the run is
not extended, re-evaluated on another window, or reselected.
