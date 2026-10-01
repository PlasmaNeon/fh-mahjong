# Face-symmetry averaging probe — registration

**Registered 2026-09-30, before any run.** Authorized by the user in the post-lap queue ("More-symmetries
probe"). Codex consults are suspended until the user re-enables them.

## Question

Does averaging the strongest policy over all 72 face symmetries (`--symmetry-average faces`) beat averaging
it over the 6 suit permutations (`--symmetry-average suits`)? No training: the same checkpoint, a larger
averaging group.

## Why it can work

Besides the suits, the rules treat ranks 1-9 and 9-1 identically and the three dragons identically.
`internal/rl/observation_symmetry_test.go` proves both facts for the code: the encoder is equivariant under
all 72 face symmetries (except the best-discard look-ahead tie-break scalars, as for suits), and every
rollout win scores the same after each symmetry. Rank reversal became exact with the wild-run fix (a wild
fills the bottom of a run, `fix(rules): a wild fills any position of a run`). Averaging over suits gained
+0.0369 on `anchor075`; the net is no more symmetric after augmented training (the suit-augment lap), so the
other symmetries likely carry the same kind of noise.

## Protocol

- Checkpoint: aug `iter_150` of the suit-augment lap (`c5ff807b…`), the strongest policy.
- Candidate: `--symmetry-average faces` (72 views). Comparator: the same checkpoint with
  `--symmetry-average suits`.
- Both through the batched evaluator with identical settings (`--batched-eval-slots 256`, default batched
  inference, greedy, chongci, step cap 4000, event window 128) and one bridge build that includes the
  wild-run fix.
- Seeds: **2,720,000–2,724,999** (5,000 × 4 duplicate seats). Never used before. One run each, no
  screening, no rerun.
- **Pass iff** `fh-mj-compare` clustered CI95 lower bound > 0 **and** large-loss(candidate) ≤ comparator +
  0.015.
- A pass makes face averaging the evaluation and serving rule for the strongest policy (72 rows per
  decision; CPU serving latency must be measured before deployment). A fail keeps suit averaging.

## Outcome — 2026-09-30: FAIL

Commit `a4bca0b7` (includes the wild-run fix), one bridge build (`5d04b35a…`). Seeds 2,720,000–2,724,999.

| aug `iter_150` | mean placement | large-loss |
|---|---|---|
| `faces` (72 views) | +0.4630 | 0.0523 |
| `suits` (6 views) | +0.4543 | 0.0519 |

Paired delta **+0.0087 ± 0.0102** (CI95 [−0.0015, +0.0189]): the lower bound is below 0, so the probe fails.
Suit averaging stays the decision rule.
