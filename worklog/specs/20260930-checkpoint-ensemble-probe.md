# Checkpoint-ensemble probe — registration

**Registered 2026-09-30, before any run.** Authorized by the user in the post-lap queue ("Checkpoint-ensemble
probe"). Codex consults are suspended until the user re-enables them.

## Question

Does an ensemble of `anchor075`, aug `iter_150` and control `iter_150` (the suit-augment lap), played
suit-averaged, beat aug `iter_150` alone, played suit-averaged? No training: three existing checkpoints,
one decision rule.

## Decision rule

`fh_mahjong_ai.ensemble.LogProbEnsemble`: the mean of the members' masked log-probabilities, then the
suit averaging on top (`--symmetry-average suits`), greedy. The members share one architecture (96 channels,
4 blocks, event window 128, privileged critic, aux heads).

## Protocol

- Candidate: `--checkpoint` aug `iter_150` (`c5ff807b…`) `--ensemble-checkpoint` control `iter_150`
  (`bd58a944…`) `--ensemble-checkpoint` `anchor075` (`ce9d867f…`), `--symmetry-average suits`.
- Comparator: aug `iter_150` alone, `--symmetry-average suits`.
- Both through the batched evaluator with identical settings (`--batched-eval-slots 256`, default batched
  inference, greedy, chongci, step cap 4000, event window 128) and one bridge build.
- Seeds: **2,730,000–2,734,999** (5,000 × 4 duplicate seats). Never used before. One run each, no
  screening, no rerun.
- **Pass iff** `fh-mj-compare` clustered CI95 lower bound > 0 **and** large-loss(candidate) ≤ comparator +
  0.015.
- A pass makes the ensemble a candidate evaluation and serving rule (3× the forward cost); a fail keeps the
  single checkpoint.

## Outcome — 2026-09-30: FAIL

Commit `a4bca0b7`, the same bridge build as the face-symmetry probe (`5d04b35a…`). Seeds
2,730,000–2,734,999, all suit-averaged.

| | mean placement | large-loss |
|---|---|---|
| ensemble (aug + control `iter_150` + `anchor075`) | +0.4602 | 0.0501 |
| aug `iter_150` alone | +0.4512 | 0.0536 |

Paired delta **+0.0089 ± 0.0098** (CI95 [−0.0009, +0.0187]): the lower bound is below 0, so the probe
fails. 4th-share Δ −0.0052 [−0.0100, −0.0005] (descriptive). The single checkpoint stays the decision
rule.
