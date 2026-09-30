# Suit-symmetry averaging probe — registration

**Registered 2026-09-29, before any run.** Authorized by the user ("merge and go on"); Codex consults are
suspended until the user re-enables them.

## Question

Does averaging `anchor075`'s policy over the six suit permutations (`--symmetry-average suits`) beat the
plain `anchor075` against the heuristic bots? No training: the same checkpoint, a different decision rule.

## Why it can work

The rules treat man, pin and sou identically and the encoder is suit-equivariant
(`internal/rl/observation_symmetry_test.go`), so the optimal policy is too. A trained net is not exactly
equivariant; averaging its six views cancels suit-specific noise, the same way board-symmetry averaging
helps Go engines. The best-discard look-ahead scalars (33–35, 37, 40) are tie-broken by face order and
are passed through unpermuted.

## Protocol

- Candidate: `anchor075` (`ce9d867f…`) with `--symmetry-average suits`. Comparator: the same checkpoint,
  plain.
- Both through the batched evaluator with identical settings: `--batched-eval-slots 256`, default
  batched inference, greedy, chongci, step cap 4000, event window 128, one bridge build.
- Seeds: **2,500,000–2,504,999** (5,000 × 4 duplicate seats). Never used before. One run each, no
  screening, no rerun.
- **Pass iff** `fh-mj-compare` clustered CI95 lower bound > 0 **and** large-loss(candidate) ≤
  comparator + 0.015.
- A pass makes suit averaging a candidate serving rule for the champion (latency ~6× the forward, still
  well inside the 200 ms budget); deployment is a separate decision. A fail closes this probe; the maps
  stay available for training-time augmentation, which is a separate question.

## Outcome — 2026-09-29: PASS

Seeds 2,500,000–2,504,999 (5,000 × 4), commit `4bc5a73`, one bridge build (`48ec4d00…`), batched evaluator
(256 slots) on both sides.

| | suit-averaged | plain |
|---|---|---|
| Mean placement | **+0.4823** | +0.4454 |
| Large-loss rate | 0.0426 | 0.0505 |
| Deal-in rate | 0.0992 | 0.1006 |

- Paired delta **+0.0369 ± 0.0107** (clustered CI95 [+0.0262, +0.0476]) — the placement gate passes.
- Large-loss 0.0426 ≤ 0.0505 + 0.015 — passes (and is lower). 4th-share Δ −0.0116 [−0.0165, −0.0067],
  large-loss Δ −0.0078 [−0.0115, −0.0042], training-utility Δ +0.0329 [+0.0231, +0.0426].
- Evaluation wall time: plain 808 s, suit-averaged 1,002 s (6× rows, one batched forward per round).

`anchor075` + suit averaging is a gate-qualified serving rule. Deployment is a separate decision and needs
`fh-mj-serve-policy` to apply the same averaging. Reports: `/root/fh-mahjong-runs/symmetry-probe-20260929/`.
