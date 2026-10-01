# Suit-augment extension lap 2 — registration

**Registered 2026-09-30, before any run.** Authorized by the user ("Yes" to the 300-iteration extension
from the extension lap's `iter_150`, fp32).

## Question

Do 300 more iterations of suit-augmented PPO from the extension lap's `iter_150` beat that checkpoint,
both played suit-averaged? Each 150-iteration lap from `anchor075` has passed (+0.0114, then +0.0159); this
asks whether the curve is still rising over a longer stretch.

## Run

| | |
|---|---|
| Init | extension lap `iter_150` (`3fdfe246…`), the strongest policy |
| Recipe | identical to the extension lap: batched collector, 256 slots, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment` |
| Iterations | 300 |
| Training seeds | 2,800,000–2,895,999 (never used) |
| Code | commit `25d4b103` (`main`, includes the wild-run rules fix), one bridge build for training and evaluation |

The rules fix changes the environment, so every report in this lap comes from the post-fix bridge;
none is paired with a pre-fix report.

## Evaluation (fixed now; no screening, no selection)

Only `iter_300` is evaluated, through the batched evaluator (256 slots), on fresh seeds
**2,900,000–2,904,999** (5,000 × 4 duplicate seats).

- **Primary:** `iter_300` suit-averaged vs extension `iter_150` suit-averaged. **Pass iff** clustered CI95
  lower bound > 0 and large-loss(`iter_300`) ≤ large-loss(extension `iter_150`) + 0.015.
- **Secondary (descriptive):** `iter_300` suit-averaged vs `anchor075` suit-averaged.

A pass makes `iter_300` (suit-averaged) the strongest policy. A fail keeps extension `iter_150`; the run is
not extended, re-evaluated on another window, or reselected.
