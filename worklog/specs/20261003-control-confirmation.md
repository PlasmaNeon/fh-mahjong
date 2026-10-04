# Distill-control confirmation — registration

**Registered 2026-10-03, before any run.** Authorized by the user ("start #2"). Evaluation only; no
training.

## Question

Does the suit-distillation lap's control `iter_150` (`ea6d4d41…`) beat extension `iter_150` (`3fdfe246…`),
both played suit-averaged?

The control is 150 more suit-augmented PPO iterations from `3fdfe246` (β = 0). On the distill lap's window it
read +0.0105 ± 0.0102 over `3fdfe246`, descriptive only under that registration
(`20261002-suit-distill-lap.md`). Extension lap 2 (300 iterations from `3fdfe246`) read +0.0079 ± 0.0106.
Both point to a small gain that neither registration could test.

## Policies

| | checkpoint | sha256 |
|---|---|---|
| Candidate | `/root/fh-mahjong-runs/suit-distill-20261002/control/ckpt/iter_150.pt` | `ea6d4d41…` |
| Comparator | `/root/fh-mahjong-runs/suit-augment-ext-20260930/aug/ckpt/iter_150.pt` | `3fdfe246…` |

## Evaluation (fixed now; no screening, no selection)

- Code and bridge: the distill lap's checkout, commit `b16b5c0c` (descends from both rules fixes,
  `6c354655` and `785b3b85`), bridge `9541ed94…`. Both reports use this one bridge.
- Batched evaluator, 256 slots, greedy, `--symmetry-average suits`, chongci, step cap 4000, event window 128.
- Fresh seeds **3,200,000–3,209,999** (10,000 × 4 duplicate seats). 10,000 seeds put the clustered CI95
  half-width near ±0.0075, against ±0.0105 at 5,000.
- **Pass iff** clustered CI95 lower bound of candidate − comparator > 0 and large-loss(candidate) ≤
  large-loss(comparator) + 0.015.

A pass makes control `iter_150` (`ea6d4d41`, suit-averaged) the strongest registered policy and the init and
comparator for the next lap. A fail keeps `3fdfe246`; the candidate is not re-evaluated on another window.

## Outcome — 2026-10-04: PASS

Commit `b16b5c0c`, bridge `9541ed94…`. Seeds 3,200,000–3,209,999 (10,000 × 4), batched evaluator (256 slots),
40,000 episodes and no truncations per report.

| suit-averaged | mean placement | large-loss |
|---|---|---|
| control `iter_150` (`ea6d4d41`) | +0.4562 | 0.0488 |
| extension `iter_150` (`3fdfe246`) | +0.4480 | 0.0496 |

- **Primary:** control − `3fdfe246` **+0.0082 ± 0.0073** (seed-clustered CI95 [+0.0009, +0.0155]): **PASS**.
- Large-loss 0.0488 vs 0.0496: passes the + 0.015 rule.
- `fh-mj-compare` also prints the placement-reshape "tail gate" (4th-share delta ≤ −0.010), which this
  registration does not use: 4th-share delta −0.0008 [−0.0044, +0.0027].

Control `iter_150` (`ea6d4d41`, `/root/fh-mahjong-runs/suit-distill-20261002/control/ckpt/iter_150.pt`), played
suit-averaged, is the strongest registered policy and the init for the next lap. Reports and the comparison are in
`/root/fh-mahjong-runs/control-confirm-20261003/eval/`.
