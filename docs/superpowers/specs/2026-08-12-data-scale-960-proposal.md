# `data-scale-960/mb768` — gradient-noise test on the modern recipe

Status: **RATIFIED 2026-08-12** by Codex consult (canonical session
`019f49e8-8f48-7042-b176-df12d8719753`, GPT-5.6-Sol medium), with amendments
recorded below. Verdict: "approve one narrowly scoped reopening" — this is a
single pre-registered scale experiment, NOT a reopened training ladder; the
result returns to consultation.

## Ratification amendments (Codex, 2026-08-12)

1. **Critical correction — coupled minibatch.** 960 matches at minibatch 256
   would ~triple optimizer steps between policy refreshes (data volume, update
   count, and policy lag change together — not a noise test). The ratified
   intervention couples `minibatch_size 256 → 768` with `matches_per_iter
   320 → 960` as ONE pre-registered scale change: ~equal optimizer steps and
   policy refreshes per iteration, 3× rows per gradient. (Verified:
   `PPOConfig.minibatch_size = 256` at `ppo.py:119`, shuffled minibatch loop,
   ppo_epochs 2.)
2. **lr frozen, null terminal** for this protocol — no post-null lr arm
   (coefficient chasing).
3. **Paired-seed control variates rejected as a prior step** — not actually
   free (needs extra trajectories or altered advantage estimation = new
   estimator with its own hypothesis + gauntlet); symmetric all-4-seat
   self-play already captures much of the seat pairing.
4. **Interpretation scoping:** a confirm *supports but does not prove*
   "gradient noise was binding" (no concurrent randomized 320 control); a null
   closes 960/768 under this recipe and removes the evidentiary basis for
   another capacity lap now (it does not prove self-play capacity scaling
   impossible). Small ReZero alphas are not uniquely a starvation signature.
5. **Seed condition verified:** training range 500000..644000 (960×150 = 144k
   seeds) does not overlap prior training ranges (100k–148k, 200k–248k,
   400k–453k, 4M, 8M) or any eval window (≥870000).

## Motivation

The 2026-08-06 campaign-retirement verdict was precise: *warm-started symmetric
self-play PPO **@320 matches/iter** with this reward/recipe/anchor is locally
saturated — NOT an architecture or RL ceiling.* All three capacity laps (deep8
replay, deep4+12-ReZero, GRU-width) held data constant at 320 matches/iter, so
growing params **cut** data-per-param instead of scaling it. The deep16
diagnostic (ReZero alphas pinned at 0.0002–0.0006 all run) is a
starved-optimizer signature, not a capacity-ceiling signature. The literature
pattern agrees: big nets pay off only with proportional data (Suphx/Mortal:
millions of human games; AlphaZero-line: self-play volume scaled with model
size plus search-amplified targets).

Raising matches/iter was explicitly carved out of the throughput roadmap item
as "a separate intervention — that changes gradient noise" and has never been
tested in the modern era (events + aux + privileged critic + restart-iter075
anchor).

**Hypothesis:** gradient noise per update at 320 matches/iter is the binding
constraint on the modern recipe. Prediction: 3× data per update improves the
*current* net. If confirmed → capacity laps get retested at the new data scale
(the first fair "bigger net via self-play" test of the campaign). If null →
self-play capacity scaling is closed with real evidence; the human-data
flywheel remains the sole path.

## Governance flag (consult question 1)

The ratified 2026-08-06 8-item list says training reopens only for *new
information / genuinely different objective / evidence-backed aux changes*. A
data-scale lap is none of those — but the saturation verdict is explicitly
scoped "@320 matches/iter", so this experiment is a direct test of that pinned
clause. The consult must explicitly reopen the list or reject the proposal.

## Design

**One intervention (coupled, per amendment 1):** `matches_per_iter 320 → 960`
+ `minibatch_size 256 → 768`. Everything else frozen: champion recipe, warm
start from restart-iter075 (sha `ce9d867f…`), lr 2e-5, ppo_epochs 2, entropy
0, δ=1, chongci, unchanged aux weights, event window 128, residual_blocks 4,
event_hidden 128, 150 iterations.

### Stage 0 — prerequisites (no training)

1. **Full-pipeline preflight (amended):** bench a complete **collect + PPO
   update** (not collection alone — `ppo_update` puts the whole rollout on
   GPU, so host RAM and CUDA peak are both at risk) at 960/mb768, workers
   10/16/20 with the post-PR-#146 process collector (448 was memory-proven;
   960 is 2.1× that). Measure: host peak RSS, CUDA peak allocation,
   transition rows, optimizer steps, throughput, label coverage, truncation,
   KL, clip fraction. Worker count must not alter collected rows or labels.
2. **If 960 cannot complete under the existing path: stop and return to
   consultation.** The GoEnvPool port is NOT auto-authorized (own gauntlet;
   mind the `round_outcome` drop + missing B2b hindsight-label assembly trap —
   single-env-vs-pool parity required).
3. **Telemetry code change (small, gauntleted):** aggregate PPO telemetry over
   ALL minibatches — current final-minibatch-only metrics are inadequate for
   comparing batch scales.
4. Wall-clock estimate from the bench; ballpark from old profiles
   (~0.6–0.9 matches/s) → ~25–35 min/iter → 150 iters ≈ 2.5–3.5 days on the
   4090.

### Stage 1 — the lap

| Item | Value |
|---|---|
| Iters | 150 (equal-iterations, not equal-compute — hypothesis is noise *per update*) |
| Base seed | 500000 (fresh training range; prior laps used 100000/200000/400000) |
| Run dir | `/root/fh-mahjong-runs/data-scale-960/` |
| Screenings | 25/50/75/100/125/150 vs **regenerated restart-iter075** comparator, 910000+, 120 seeds, `fh-mj-compare` |
| Kill rule | kill@100 iff both iter-75 and iter-100 < −0.06 |
| Confirmation | best pre-registered screening ckpt, fresh window **1190000+** (≤1150000 all burned), 1500 seeds/side, back-to-back |
| Gate | paired clustered CI > 0 AND large_loss ≤ comparator + 0.015 |
| Protocol | no optional stopping; confirmation runs regardless of screening shape; no auto-chaining — result returns to consult |

### Decision tree

- **Confirms** → noise was binding. Next consult decision: rerun a capacity
  lap (GRU-width or deep16-ReZero) *at 960*, budget scaled by measured param
  ratio.
- **Null** → modern recipe not noise-limited at 3×; self-play capacity path
  closed; ratified priorities (promotion, provenance, human corpus) continue
  unchanged.

## Pre-registered risks

- **The 448 precedent:** phaseB2 (320→448, 2026-07-05) plateaued with no
  promotion. Defense: 1.4× was a weak multiplier, on the pre-events/pre-aux
  net, different anchor, judged against a fresher champion. Still the
  strongest prior against this experiment.
- **Fixed lr at 3× effective batch is a mild confound** (larger batches
  typically tolerate/want higher lr). RESOLVED by consult: lr stays frozen and
  a null is terminal for this protocol — no lr arm (verdict 3); the null is
  correspondingly scoped to "960/768 under this recipe" (amendment 4).
- No conflict with paipu-v2 provenance work (different machine, different
  track); provenance still ships before shadow-gate games resume regardless.

## Consult verdicts (all questions resolved 2026-08-12)

1. Reopen training? **Yes, once** — the "@320" scoping makes one scale
   experiment legitimate; no automatic capacity run afterward.
2. **960, equal iterations** — 640 is too close to the historical 448 null;
   coupled minibatch scaling keeps optimizer steps ~equal at 3× experience.
3. **lr frozen; no lr rerun on null.**
4. **No paired-seed control variates first** (see amendment 3).
5. **Seeds accepted** conditionally; condition verified (amendment 5).

Final line from the session record: *"Ratified: `data-scale-960/mb768` will
proceed under exactly the pre-registered protocol stated above, with no
amendments."*
