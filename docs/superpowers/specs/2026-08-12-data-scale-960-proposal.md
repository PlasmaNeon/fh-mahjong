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

## Amendment 2 (Codex consult, 2026-08-12, post-preflight)

The Stage 0 stop clause TRIGGERED: the 960-match preflight OOM'd the 31GB
box during the first warmup collection at workers=10 (dmesg: workers killed
at anon-rss 5.1–6.7GB, bench master at 8.4GB) — the process collector
dispatches one task per worker per collect, so each worker held its entire
96-match trajectory block. Consult ruling (same canonical session): **approve
bounded sequential dispatch inside the existing `ParallelB2bCollector`,
conditionally** — a collection-transport amendment, NOT a change to the
scientific intervention (the 960/768 hypothesis remains untested; this is
not a training null).

Conditions (all implemented):
1. Chunk cap FROZEN at **320 matches** for this lap: preflight seed blocks
   700000–700319 / 700320–700639 / 700640–700959; analogous contiguous
   blocks during training.
2. Canonical row order preserved (chunks in ascending seed-block order,
   worker results in worker-id order); no reordering scheduler.
3. Cap exposed and persisted: `PPOConfig.collect_dispatch_chunk`
   (`--collect-dispatch-chunk` / bench `--dispatch-chunk`), in the resume
   config echo (logged-not-rejected on change, like `num_workers` — digest-
   proven semantics-neutral), legacy states back-filled via the echo
   whitelist. Bench and trainer exercise the identical collector path.
4. Gauntlet before the canonical bench rerun: unit tests for seed coverage /
   order / remainder / duplication / error propagation; exact digest parity
   unchunked-vs-chunked at a non-divisible match count; chunked-digest
   repeatability. Then the COMPLETE registered 960/mb768 bench at workers
   10/16/20 with every original gate (digest + rows/labels equality, host
   peak ≤ ~26GB, CUDA allocated ≤ ~20GB, label coverage, ~zero truncation),
   recording process-tree RSS and the chunk cap in the artifact.
5. If chunked collection fails, parent RSS lacks headroom, or the
   full-rollout CUDA update fails → STOP, return to consultation. Minibatched
   host-to-device transfer NOT auto-authorized; GoEnvPool NOT authorized.
6. All scientific protocol elements stay frozen (anchor, 960/768, lr, seeds,
   150 iters, screenings, kill rule, confirmation window and gates).

## Amendment 3 (Codex consult, 2026-08-14, post-Amendment-2 preflight)

Amendment 2's stop clause triggered when the chunk-320 workers remained
bounded (~1.3GB each — the Amendment 2 worker fix WORKED) but the benchmark
master accumulated the full 960-match rollout (anon-rss 17.0GB + ~5.3GB
swapped at kill) and the 31GiB-default WSL2 instance OOM-killed the
benchmark. This is an infrastructure failure, not a training null; the
960/768 hypothesis remains untested. The Windows host has 64GB physical
RAM, so the WSL2 cap is raised operationally to `memory=52GB`, with no
code, data-path, numerical, or scientific-protocol change. After restart,
the effective WSL memory limit must be recorded and the identical
chunk-320 full-cycle bench rerun at workers 10/16/20, seeds 700000–700959.

The restated host gate is peak aggregate process-tree RSS ≤40GiB, leaving
≥12GiB nominal headroom under the verified 52GiB cap (log master RSS and
summed child RSS separately for diagnosis; the hard go/no-go is the
aggregate figure); CUDA allocated remains ≤20GiB and every digest,
rows/labels, truncation, and coverage gate remains unchanged. The eventual
150-iteration lap runs under the same cap and RSS gate, monitored
continuously — crossing 40GiB is a hard stop back to consultation.

A whole-process-tree cgroup-v2 guard of `memory.high=44GiB`,
`memory.max=48GiB`, `memory.swap.max=0`, and `memory.oom.group=1` is
recommended (containment ceilings only — they do not relax the 40GiB
scientific go/no-go; if cgroup enforcement isn't available, proceed under
the 52GiB cap with the launch lock guard and external monitoring, logged
as an exception). If the clean bench exceeds 40GiB, hits the cgroup
ceiling, fails collection, or fails the full CUDA update, stop and return
to consultation. Disk spilling, float16 host storage, 640 matches,
GoEnvPool, and minibatched host-to-device transfer remain unauthorized.

(The failed 2026-08-12 attempt is additionally non-scoring because a
duplicate bench stack — an ssh-level double-execution quirk, since fixed
with a flock launch guard — contaminated the box at kill time; only the
clean rerun counts as a measurement.)

## Amendment 4 (Codex consult, 2026-08-14, post-Amendment-3 clean preflight)

Amendment 3's clean single-stack rerun triggered its stop clause. Under a
verified 50 GiB WSL cap and whole-tree cgroup containment, the workers=10
chunk-320 phase reached the 48 GiB cgroup ceiling after 64m50s; the master
was 33.8 GiB anonymous RSS and still growing, with ten bounded workers
totaling approximately 16 GiB. The cgroup terminated the complete stack
and preserved the box. This is a third infrastructure failure, not a
training null; the 960/768 hypothesis remains untested. No further RAM
increase is authorized.

Authorize a measurement-only memory profile of the unchanged current path
at 320 and 640 matches, workers=10, chunk=320, using fresh processes and
the corresponding base-seed-700000 prefixes. Required accounting includes
master and child RSS, smaps/PSS where available, cgroup current/peak,
live RolloutBatch field shape/dtype/nbytes and ownership, and checkpoints
after every dispatch, outer concatenation field, collector return, GAE,
dtype/device conversion, and update. `tracemalloc` is supplemental only.

After profiling, authorize one targeted copy-elimination change limited
to redundant object ownership, field lifetime, allocator retention, and
unnecessary host dtype copies. Full in-memory rollout semantics,
chunk/order, field values and dtypes at consumer boundaries, GAE/PPO
mathematics, and full-rollout device transfer remain unchanged. Disk
spill/memmap, float16 storage, streaming GAE, minibatched host-to-device
transfer, GoEnvPool, and a 640-match scientific intervention remain
unauthorized (640 is authorized only as an infrastructure
profiling/parity workload).

Trust requires exact baseline-versus-optimized canonical rollout digest
parity at a three-chunk non-divisible small case and at 640
matches/chunk320/workers10; byte-identical GAE outputs and device-input
tensors; identical minibatch ordering and optimizer-step count; and
post-update model/optimizer parity under the established
unchanged-baseline CUDA determinism envelope. Repeat optimized collection
must reproduce the digest. The optimized 320/640 memory slope must
project workers-10 aggregate 960 peak ≤36 GiB before the canonical bench
is attempted (a pre-bench spending guard, not a new gate).

The registered host gate remains peak aggregate process-tree RSS ≤40 GiB
under the verified 50 GiB WSL cap (containment `memory.high=44GiB`,
`memory.max=48GiB`, `swap.max=0`, `oom.group=1` unchanged); CUDA ≤20 GiB
and all digest, rows/labels, truncation, and coverage gates remain
unchanged. If profiling cannot identify the copies, parity fails,
projected peak exceeds 36 GiB, or the canonical workers 10/16/20
full-cycle bench exceeds 40 GiB or otherwise fails, stop and return to
consultation. No further in-box engineering or infrastructure escalation
is automatic; the next ruling must choose a larger-memory machine or
close 960 on this hardware.

Candidate copy sites flagged during the consult (hypotheses to be
confirmed by the profile, not conclusions): the chunk-list accumulation
in the chunked dispatch loop (`oracle.py`), optional-array concatenation
without the same release choreography as required fields
(`concat_rollout_batches`, `ppo.py`), and dtype-normalizing NumPy
conversions before device transfer (`ppo_update`, `ppo.py`).

## Amendment 5 (Codex consult, 2026-08-15, post-Amendment-4 memory profile)

Amendment 4 completed cleanly: all four registered 320/640 profile runs
exited zero, and the measurement instrumentation plus digest-parity tests
merged as PR #202. The profile identifies two independent infrastructure
limits. First, the Amendment-3 host kill occurred during the outer
`np.concatenate` transient: at 960, the planes sources and destination
would coexist at approximately 30.4 GiB in the master. The master is not a
steady three-copy accumulator. Second, the ten persistent spawn workers
consume approximately 18.4 GiB independent of chunk size. Measured aggregate
host peaks were 29.5 GiB at 320 and 40.1-40.2 GiB at 640, projecting
approximately 50.7-51.0 GiB at 960 on the unchanged path.

The profile also establishes a new independent CUDA blocker. Full-cycle peak
allocated memory was 9.32 GiB at 320 and 16.49 GiB at 640, projecting
approximately 23.7 GiB at 960, above both the registered 20 GiB gate and the
practical capacity of the 24 GB RTX 4090. Therefore host-only copy elimination
cannot make the registered full-rollout device-transfer path viable. These
are infrastructure failures, not training nulls; the 960/768 scientific
hypothesis remains untested.

Ruling: authorize option (i), conditionally. The complete RolloutBatch remains
in host memory, while each registered minibatch is synchronously transferred
to CUDA inside the unchanged PPO update loop. No asynchronous prefetch,
double buffering, disk or memmap storage, float16 rollout storage, streaming
GAE, GoEnvPool, or PPO/data/scientific change is authorized. Global advantage
normalization, minibatch size 768, two PPO epochs, CUDA permutation generation,
losses, auxiliary targets, optimizer behavior, and all other mathematics
remain unchanged.

Also authorize closing and joining the persistent worker pool after the final
dispatch result has been received and before outer rollout concatenation.
The pool is recreated for the next iteration. Shutdown must preserve complete
seed coverage and canonical row order, occur on exception paths, and be used
identically by the trainer and full-cycle profiler.

Trust requires:

1. Exact baseline-versus-candidate canonical rollout digest parity, including
   shapes, dtypes, bytes, order, labels, and truncation, at a three-chunk
   non-divisible small case and at 640 matches/workers10/chunk320/seeds700000+.
   Repeated candidate collection must reproduce the digest.
2. Byte-identical GAE advantages and returns. Advantage normalization remains
   global over the full rollout, and every normalized advantage minibatch
   delivered to CUDA must be byte-identical to baseline.
3. Identical initial model, optimizer, CPU RNG, and CUDA RNG states; identical
   CUDA `torch.randperm` call order and permutations for both epochs; and
   identical minibatch indices and optimizer-step count
   `2 * ceil(rows / 768)`.
4. For every optimizer step, including the ragged tail, identical shape,
   dtype, layout/stride, and bytes for CUDA planes, scalars, action masks,
   actions, old log-probabilities, normalized advantages, returns, events,
   event lengths, deal-in labels, rank labels, and derived belief targets.
   Per-minibatch event casting is allowed only when the resulting CUDA int64
   tensor is byte-identical to baseline.
5. Exact non-floating model/optimizer/RNG state after the update, with floating
   model parameters, optimizer tensors, and aggregated telemetry no farther
   from baseline than the fixed established unchanged-baseline CUDA
   determinism envelope. The envelope may not be widened after candidate
   results are observed. Any unexplained parity failure stops this branch.

After parity, rerun optimized full-cycle profiles at 320 and 640 using fresh
processes/cgroups, workers=10, chunk=320, and the registered seed prefixes.
For aggregate host RSS and CUDA allocated memory, project conservatively as
`P960 = max(P320, P640, P640 + (P640 - P320))`. Do not attempt the canonical
960 bench unless projected host peak is <=36 GiB and projected CUDA allocated
peak is <=20 GiB.

The canonical Stage-0 bench is restated from workers 10/16/20 to workers=10
only. The measured persistent-worker footprint makes the 16/20 phases
knowingly infeasible and they add no scientific evidence. Workers=10 is
frozen for both the canonical bench and the lap; workers=6 is not an automatic
fallback. The 960/mb768 full-cycle bench must complete under the unchanged
whole-tree containment (`memory.high=44GiB`, `memory.max=48GiB`,
`memory.swap.max=0`, `memory.oom.group=1`) with aggregate process-tree RSS
<=40 GiB, CUDA allocated <=20 GiB, no host or CUDA OOM, expected rows and
optimizer steps, zero truncation, and healthy labels/telemetry.

If parity fails, either 320/640 projection guard fails, or the canonical
workers=10 960 full-cycle bench fails any registered gate, stop all further
in-box engineering. Option (ii), a machine with sufficient host RAM and VRAM,
is then the remaining execution branch; closing 960 remains available by
consultation.

Measured workers=10 throughput implies approximately 29 minutes collection
plus 2 minutes update per iteration, or 77.5 hours for 150 iterations. Even
with approximately one additional minute per iteration for pool recreation,
the estimate is approximately 80 hours (3.33 days), within the registered
2.5-3.5-day runbook ballpark. Screening, confirmation, and downtime are
budgeted separately. Wall clock does not authorize adaptive worker-count or
protocol changes.

All scientific controls remain frozen: anchor and checkpoint SHA, coupled
960/768 intervention, lr=2e-5, two PPO epochs, reward and auxiliary recipe,
chunk=320, training and evaluation seed windows, 150 iterations, screening
schedule, kill rule, fresh confirmation window, clustered paired-CI gate,
large-loss delta cap, no optional stopping, and no automatic capacity lap.

## Amendment 6 (Codex consult, 2026-08-15, post-Amendment-5 CUDA gauntlet)

Amendment 5 implementation merged as PR #203. CPU bit-parity tests passed,
and the on-box 640-match/workers10/chunk320/seeds700000+ gauntlet completed.
Conditions 1-4 passed: the candidate reproduced the recorded pre-Amendment-5
rollout digest, repeated through an automatic pool restart, and matched the
real-bridge non-divisible chunk case; GAE remained unchanged; both update
paths executed exactly 3308 optimizer steps; and the complete permutation,
minibatch-index, and device-input hash sequence matched through both epochs,
including the ragged tail.

The candidate reduced CUDA peak allocation from 16.49 GiB to 2.26 GiB
(7.3x) while update time changed from 96 seconds to 99 seconds (+3%).
The change therefore has the measured memory and performance behavior
authorized by Amendment 5.

Condition 5 did not pass its original numerical envelope. The envelope was
fixed before candidate observation from one repeated baseline pair:
maximum per-tensor parameter delta 1.888e-03 and maximum metric delta
8.9e-06. Candidate versus baseline1 reached 2.702e-03, with approximately
30 of 150 tensors outside their individual one-pair envelopes. The worst
tensor was `event_encoder.embedding.weight`; all discrepancies remained
the same order of magnitude as baseline self-divergence.

Ruling: adjudicate this result as explained but not yet a condition-5 pass.
The byte-identical 3308-step input sequence, CPU bit parity, and nonzero
baseline self-divergence make CUDA backward nondeterminism the supported
explanation. A single baseline pair is not a calibrated bound for a
maximum over approximately 150 tensors, so exceeding it by 1.4x is not
evidence of a semantic update-path defect. Condition 5 nevertheless remains
open until an exact deterministic-mode proof passes.

Authorize deterministic-mode equivalence proof only. Run four fresh
processes in order: legacy full-device B1, legacy full-device B2,
minibatched-H2D C1, and minibatched-H2D C2. All use the identical recorded
640-match rollout, anchor bytes, model/optimizer initialization, RNG state,
minibatch configuration, software stack, and RTX 4090.

`CUBLAS_WORKSPACE_CONFIG=:4096:8` must be present before PyTorch import or
CUDA initialization. Each process must use
`torch.use_deterministic_algorithms(True, warn_only=False)`,
`torch.set_deterministic_debug_mode("error")`,
`torch.backends.cudnn.benchmark=False`, and
`torch.backends.cudnn.deterministic=True`. TF32, matmul precision, PyTorch,
CUDA, cuDNN, driver, and GPU settings must be identical and recorded.

Every operation is considered deterministically supported only if the full
3308-step update completes without a deterministic-algorithm exception or
warning and B1 equals B2 bit for bit. No operator, model, optimizer, loss,
minibatch, or hyperparameter substitution is allowed.

Pass requires B1 == B2 == C1 == C2 with zero tolerance for the complete
permutation/index sequence; every condition-4 forward and loss/target tensor;
all final model parameters and buffers; all optimizer tensors, counters, and
parameter-group state; per-step and aggregate metric digests; CPU/CUDA RNG
states; and optimizer-step count. Tensor comparisons include presence, dtype,
shape, layout/stride, and bytes. The prior nondeterministic candidate result
is excluded from this new proof.

The proposed K=5 distributional envelope is not authorized as an automatic
fallback. A maximum-pairwise range from five baseline runs is not calibrated
for simultaneous per-tensor maxima and has no pre-registered family-wise
error rule. If any deterministic operator is unavailable, B1 differs from
B2, or any candidate comparison differs, stop and return to consultation.
Do not change the implementation or proceed to memory profiling.

On an exact deterministic pass, Amendment 5 resumes unchanged: run fresh
optimized 320/640 full-cycle profiles at workers=10/chunk320, apply
`P960 = max(P320, P640, P640 + (P640 - P320))`, require projected aggregate
host peak <=36 GiB and projected CUDA allocated peak <=20 GiB, then run the
canonical workers=10 960/mb768 full-cycle bench under the unchanged cgroup,
<=40 GiB aggregate host gate, <=20 GiB CUDA allocated gate, and all existing
science/telemetry gates.

Deterministic mode is proof-only. The optimized profiles, canonical bench,
and lap must run in fresh processes under the frozen production CUDA
configuration, with deterministic mode disabled and
`CUBLAS_WORKSPACE_CONFIG` absent. All scientific controls remain frozen.

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
