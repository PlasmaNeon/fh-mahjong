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

## Outcome — 2026-10-01: FAIL

Commit `25d4b103`, one bridge build (`7861d124…`); 300 iterations, exited cleanly (paused 01:22–09:00 PDT by
SIGSTOP, which does not change the computation). Seeds 2,900,000–2,904,999 (5,000 × 4), batched evaluator
(256 slots), all suit-averaged.

| | mean placement | large-loss |
|---|---|---|
| `iter_300` | +0.4702 | 0.0487 |
| extension `iter_150` | +0.4623 | 0.0499 |
| `anchor075` | +0.4455 | 0.0476 |

- **Primary:** `iter_300` − extension `iter_150` **+0.0079 ± 0.0106** (CI95 [−0.0027, +0.0185]): the lower
  bound is below 0, so the lap fails.
- Secondary: `iter_300` − `anchor075` +0.0247 ± 0.0109.

Extension `iter_150` (`3fdfe246…`), played suit-averaged, stays the strongest policy. The gain per lap has
shrunk (+0.0114 and +0.0159 per 150 iterations, then +0.0079 over 300): this recipe is near its plateau.
