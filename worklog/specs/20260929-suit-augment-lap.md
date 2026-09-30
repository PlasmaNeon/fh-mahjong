# Suit-augmented training lap — registration

**Registered 2026-09-29, before any run.** Authorized by the user ("merge and continue with 2 and 3");
Codex consults are suspended until the user re-enables them.

## Question

Does warm-started PPO with suit-permutation augmentation (`--suit-augment`) produce a checkpoint that beats
the current best policy, `anchor075` played suit-averaged? The trained net is not suit-equivariant
(averaging its six views gained +0.0369, `20260929-suit-symmetry-probe.md`); augmentation trains every
view on-policy, which may push the net itself toward the averaged policy and beyond it.

## Arms (run side by side, identical except the flag)

| | aug | control |
|---|---|---|
| Init | `anchor075` (`ce9d867f…`) | same |
| Collector | batched, 256 slots, 1 group | same |
| Recipe | 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32 | same |
| `--suit-augment` | **on** | off |
| Iterations | 150 | 150 |
| Training seeds | 2,600,000–2,647,999 | the same seeds (paired) |

The control isolates augmentation from "more training from the champion on the batched collector".

## Evaluation (fixed now; no screening, no selection)

Only `iter_150` of each arm is evaluated, through the batched evaluator (256 slots, batched inference),
on fresh seeds **2,700,000–2,704,999** (5,000 × 4 duplicate seats), one bridge build.

- **Primary:** aug `iter_150` suit-averaged vs `anchor075` suit-averaged. **Pass iff** clustered CI95
  lower bound > 0 and large-loss(aug) ≤ anchor + 0.015.
- **Secondary (descriptive):** aug vs control, both suit-averaged; control vs `anchor075`, both
  suit-averaged; aug plain vs `anchor075` plain (does augmentation make the net itself more
  symmetric?).

A pass makes aug `iter_150` (suit-averaged) the new best policy. A fail records the null; the arms are not
extended, re-evaluated on another window, or reselected.
