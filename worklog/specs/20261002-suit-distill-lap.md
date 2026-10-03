# Suit-distillation lap — design and registration

**Design approved in chat 2026-10-02** (approach A: KL to the suit-averaged teacher; mechanism and protocol
sections). Codex consults are suspended until the user re-enables them. The protocol below is registered
before any run; the pre-launch measurements are appended before launch.

## Question

Does PPO with a distillation term toward the net's own suit-averaged policy produce a checkpoint that beats
extension `iter_150` (`3fdfe246…`), both played suit-averaged?

Plain training has plateaued: extension lap 2 (300 iterations from `3fdfe246`) gained +0.0079, not
significant (`20260930-suit-augment-extension-2.md`). The suit-averaged policy is a proven stronger teacher
than the net (+0.0369 on `anchor075`, `20260929-suit-symmetry-probe.md`), and augmentation alone did not move
the net toward it (averaging still adds ~+0.045 to augmented checkpoints, `20260929-suit-augment-lap.md`).
Distilling the teacher into the net, then averaging the improved net, may compound.

## Mechanism

All of it is off by default and byte-identical when off.

- **`PPOConfig.suit_distill_coef`** (β, default 0.0). β > 0 requires `collector="batched"` (raises
  otherwise, like `suit_augment`), is rejected-on-change by `--resume-from-state`, and legacy train states
  read it as 0.0. CLI: `fh-mj-train-b2b --suit-distill-coef β` (an error with `--collector process`).
- **Teacher.** When β > 0 the batched collector runs, after each round's acting forward, one extra no-grad
  forward over the six suit permutations of the round's stored rows (`suit_symmetry.permute_rows`, so in the
  augmented view each row was stored in). The six views' masked log-probabilities are re-indexed to the
  stored view and averaged — the `suit_averaged_log_probs` arithmetic — giving `teacher_logprobs`
  `[rows, 204]` float32, illegal actions at float32's finite minimum. In `per_row` inference mode it runs
  one decision at a time (six rows per forward), so the teacher equals `suit_averaged_log_probs` on that row
  exactly. The acting forward, sampling, `old_logprobs` and `values` are untouched. The teacher is the
  collection-time policy, the same snapshot as `old_logprobs`.
- **Storage.** `RolloutBatch.teacher_logprobs` (optional, `None` when β = 0), carried per seat through
  `_B2bMatchState`/`_finalize_b2b_match` and the row sink like `logprobs`. About 0.8 KB per row, ~10% of
  a row's planes.
- **Loss.** `ppo_update` adds `β · mean_rows Σ_legal p_t · (log p_t − log π_θ)`, with `p_t = exp(teacher)`
  on legal actions and 0 elsewhere, written with `torch.where` so masked entries never produce NaN and no
  host sync breaks the CUDA-graph capture. The minibatch gather (both `minibatch_device_transfer` paths)
  carries the teacher rows. A `distill_kl` metric (the unweighted mean KL) is logged per iteration beside
  the PPO metrics when β > 0.
- **β = 1.0, fixed, no sweep.** The term's logit gradient is (π_θ − p_t), on the scale of the net–teacher
  gap; the PPO surrogate's is on the scale of normalized advantages (~1). At β = 1 distillation is a steady
  pull that stays secondary to PPO.

## Correctness gates (tests, before any run)

- β = 0: the three process-collector golden digests and the batched-collector parity/digest tests are
  unchanged.
- `teacher_logprobs` equals `suit_averaged_log_probs` on the stored rows exactly in `per_row` mode, with and
  without `suit_augment`.
- The KL term is 0 when the teacher equals the net's policy, positive otherwise, and one gradient step
  lowers it.
- Same seeds give the same collection digest with β > 0 (greedy `per_row` and sampled `batched`).
- The config, CLI and resume contracts above raise as specified.

## Pre-launch measurements (recorded here before launch; they do not change the protocol)

1. Pace: three iterations of both arms side by side on screening seeds (base 910,000, never cited), giving
   the measured seconds per iteration and the lap's expected duration.
2. Starting scale: mean KL(teacher ‖ net) over one 320-match collection of `3fdfe246` on screening seeds.

## Protocol

| | distill | control |
|---|---|---|
| Init | extension `iter_150` (`3fdfe246…`) | same |
| Recipe | batched collector, 256 slots, 1 group, 320 matches/iteration, minibatch 256, 2 epochs, lr 2e-5, entropy 0, γ 0.99, chongci, step cap 4000, event window 128, privileged critic, aux heads, fp32, `--suit-augment` | same |
| `--suit-distill-coef` | **1.0** | 0 |
| Iterations | 150 | 150 |
| Training seeds | 3,000,000–3,047,999 (never used) | the same seeds (paired) |

- Code: the implementation PR's merge commit, which descends from both rules fixes (`6c354655` wild runs,
  `785b3b85` prevailing wind); one bridge build at that commit for training and evaluation. No report from
  this lap is paired with a report from an older bridge.
- Both arms run side by side on the box; nothing else uses the GPU during the lap.

## Evaluation (fixed now; no screening, no selection)

Only `iter_150` of each arm is evaluated, through the batched evaluator (256 slots, default batched
inference, greedy), on fresh seeds **3,100,000–3,104,999** (5,000 × 4 duplicate seats).

- **Primary:** distill `iter_150` suit-averaged vs `3fdfe246` suit-averaged. **Pass iff** clustered CI95
  lower bound > 0 and large-loss(distill) ≤ large-loss(`3fdfe246`) + 0.015.
- **Secondary (descriptive):** distill vs control, both suit-averaged (does distillation itself help?);
  distill plain vs `3fdfe246` plain (did the net absorb the averaged policy?); control vs `3fdfe246`, both
  suit-averaged.

A pass makes distill `iter_150` (suit-averaged) the strongest policy. A fail records the null: the arms are
not extended, re-evaluated on another window, or rerun with another β.
