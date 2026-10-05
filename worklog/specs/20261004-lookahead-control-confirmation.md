# Look-ahead-lap control confirmation — registration

**Registered 2026-10-04, before any run.** Authorized by the user ("Yes" to confirming the lap's control arm).
Evaluation only; no training.

## Question

Does the look-ahead lap's control `iter_150` (`f9662491…`) beat control `iter_150` of the distill lap (`ea6d4d41…`),
both played suit-averaged?

The control is 150 more suit-augmented PPO iterations from `ea6d4d41` (version 0, pipeline groups 2). On the lap's
window it read +0.0093 ± 0.0072 over `ea6d4d41`, descriptive only under that registration
(`20261004-discard-call-lookahead-planes.md`).

## Policies

| | checkpoint | sha256 |
|---|---|---|
| Candidate | `/root/fh-mahjong-runs/lookahead-20261004/control/ckpt/iter_150.pt` | `f9662491…` |
| Comparator | `/root/fh-mahjong-runs/suit-distill-20261002/control/ckpt/iter_150.pt` | `ea6d4d41…` |

## Evaluation (fixed now; no screening, no selection)

- Code and bridge: the lap's worktree, commit `6920dadd`, bridge `7f7c2338…`. Both reports use this one bridge.
- Batched evaluator, 256 slots, greedy, `--symmetry-average suits`, chongci, step cap 4000, event window 128.
- Fresh seeds **3,270,000–3,279,999** (10,000 × 4 duplicate seats).
- **Pass iff** clustered CI95 lower bound of candidate − comparator > 0 and large-loss(candidate) ≤
  large-loss(comparator) + 0.015.

A pass makes the lap's control `iter_150` (`f9662491`, suit-averaged) the strongest registered policy. A fail keeps
`ea6d4d41`; the candidate is not re-evaluated on another window.
