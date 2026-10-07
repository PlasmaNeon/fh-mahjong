# Continuation lap, 450 iterations — registration

**Registered 2026-10-06, before any run.** Authorized by the user ("yes" to a longer continuation lap from the
strongest policy, evaluated only at the end).

## Question

Do 450 more iterations of the current recipe from look-ahead-lap control `iter_150` (`f9662491…`) beat that
checkpoint, both played suit-averaged?

Continuation is the one lever that keeps paying: two consecutive 150-iteration laps confirmed +0.0082
(`20261003-control-confirmation.md`) and +0.0074 (`20261004-lookahead-control-confirmation.md`). The search
teacher (`20261005-search-teacher-diagnostic.md`) and look-ahead planes (`20261004-discard-call-lookahead-planes.md`)
both failed. This lap asks whether three laps' worth of iterations, evaluated once, compound.

## Run

| | |
|---|---|
| Init | `/root/fh-mahjong-runs/lookahead-20261004/control/ckpt/iter_150.pt` (`f9662491…`) |
| Recipe | batched collector, 256 slots, 2 pipeline groups, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment`, look-ahead version 0 |
| Iterations | 450 |
| Training seeds | 4,000,000–4,143,999 (never used) |
| Code | `main` at launch (descends from both rules fixes), one bridge build for training and evaluation |

One arm, alone on the GPU; peer sessions are told before launch. Pausing for a speed-up session follows the
standing rule (SIGSTOP at an iteration boundary does not change the computation).

## Evaluation (fixed now; no screening, no selection)

Only `iter_450` is evaluated, through the batched evaluator (256 slots, greedy, `--symmetry-average suits`), on fresh
seeds **4,150,000–4,159,999** (10,000 × 4 duplicate seats).

- **Primary:** `iter_450` − `f9662491`, both suit-averaged. **Pass iff** clustered CI95 lower bound > 0 and
  large-loss(`iter_450`) ≤ large-loss(`f9662491`) + 0.015.

A pass makes `iter_450` (suit-averaged) the strongest registered policy. A fail keeps `f9662491`; the run is not
extended, re-evaluated on another window, or reselected among earlier checkpoints.
