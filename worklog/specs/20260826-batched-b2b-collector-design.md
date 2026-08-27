# `batched-b2b-collector` — GPU-batched rollout collection for the champion recipe

Status: **RATIFIED 2026-08-26 — AUTHORIZED WITH AMENDMENTS** by Codex design consult
(fresh thread, GPT-5.6-Sol, high effort). Ruling: **Stage-0 implementation only; training
use, default selection, and G1–G3 execution remain unauthorized until the gates pass.**
Amendments 1–8 are folded in below. **Post-Stage-0 consult 2026-08-27 (fresh thread,
GPT-5.6-Sol, high): CONDITIONALLY RATIFIED.** Merge with `collector=process` is
authorized once the hard-bounded numeric gate (G0.1b), the per-iteration G0.6, and a
full-suite rerun at final HEAD pass. G1–G3, training use and the default switch stay
unauthorized. PR #232.

Worktree `batched-b2b-collector`, branch `experiment/batched-b2b-collector`.

This is a throughput change, not an objective change. It must be semantics-preserving
and is gated on exactness proofs, not on placement results. It never promotes a
checkpoint by itself.

## Problem

`fh-mj-train-b2b` (the champion recipe) spends ~94 % of each iteration collecting
rollouts:

| Stage (ds960 lap, workers=10, 4090 box) | Wall clock | Source |
|---|---|---|
| Collection, 960 matches | ~29 min | `specs/2026-08-12-data-scale-960-proposal.md` |
| PPO update, mb768 × 4 epochs | ~2 min | same |

The Go simulator is not the cost. `BenchmarkEnvStepChongci` plays a full Chongci match
in ~2.5 ms (M1 Pro); 960 matches ≈ 2.5 s. The cost is the Python collector's
inference shape (`train_b2b.py`):

- `_b2b_worker_loop` (l.726): each spawn worker runs the 96ch × 4-block CNN + event
  GRU on **CPU, `set_num_threads(1)`, `device="cpu"`**.
- `collect_b2b_rollouts` (l.588): **one forward per decision** — `unsqueeze(0)` on
  every tensor, `dist.sample()` per row.
- Worker count is memory-capped at 10 (each holds a model copy plus its whole chunk of
  trajectories; two laps were OOM-killed). The GPU idles for the whole 29 minutes.

## Design

Reuse the batched path that already exists for the oracle recipe and extend it to
B2b's extra outputs.

### Existing pieces (no redesign)

- `internal/rl/envpool.go` — `EnvPool` steps N envs per FFI call; `SlotState` already
  carries `step_rewards` (reset rewards included, `envpool.go:93`), `terminated`,
  `truncated`, and **`round_outcome`** at nonterminal hand boundaries, at the terminal
  step, and on truncation (`env.go:343,363,382,391`). **No Go/proto change is required;
  Python pool decoding and configuration parity are required.**
- `ai/.../envpool.py` — `GoEnvPool` decodes flat plane/scalar/mask/event buffers.
  **Gaps:** `SlotMeta` has no `round_outcome` — `GoEnvPool._decode_response` and
  `InProcessEnvPool` both discard it (the "pool wrapper drops round_outcome" trap
  recorded against ds960); `make_selfplay_pool` drops `chongci_starting_score`,
  `chongci_bust_threshold`, `chongci_max_hands` (the process collector copies all
  three, `train_b2b.py:503`); the event window is whatever the caller's `EnvConfig`
  says — the caller must bind it to `model.model_config.event_window`.
- `ai/.../batched_selfplay.py` — `collect_selfplay_rollouts_batched`: one pool call +
  one batched forward per round, per-match numpy RNG, seed-order emission, slot-count
  invariance test. Lacks events, hindsight labels, placement bonus, telemetry.

### Changes

1. **`envpool.py`** — add `round_outcome: Optional[dict]` to `SlotMeta`, decoded with
   the bridge's existing `_decode_round_outcome`. Both `GoEnvPool` and
   `InProcessEnvPool` populate it. `make_selfplay_pool` copies
   `chongci_starting_score`, `chongci_bust_threshold`, `chongci_max_hands`.

2. **`train_b2b.py`** — factor the match-end tail of `collect_b2b_rollouts` (exact
   final scores, placement-bonus fail-closed checks, `placement_utilities`,
   telemetry row, `_assemble_hindsight_labels`, seat-contiguous emission) into one
   pure function `_finalize_b2b_match(match_state, config, cfg) -> (rows, telemetry)`.
   The process collector calls it; so does the batched one. Label semantics are then
   shared by construction, not by mirroring.

3. **New `batched_b2b.py`** — `collect_b2b_rollouts_batched(env_config, model, config,
   base_seed, pool, inference_mode)`. Per-slot `_B2bMatchState` extends
   `batched_selfplay._MatchState` with `seat_events`, `seat_lengths`, `seat_hand_ids`,
   `hand_outcomes`, `match_net` (accumulated from every `step_rewards`, reset
   included). Round loop:
   - pool step → for each returned slot: credit `step_rewards`, record
     `round_outcome` (closes the current hand id), on terminal/truncated finalize.
   - build one batch over pending rows: planes, scalars, mask, tail-windowed events,
     lengths → **one `model(...)` forward on `config.device`**.
   - temperature-scale, mask, sample per row with the match's numpy RNG
     (`sample_masked_action`); log-probability comes from a **shared Torch helper**
     (`masked_policy_distribution(...).log_prob`) used by both collectors, not the
     NumPy float64 log-softmax — the rollout digest hashes `old_logprobs` byte-for-byte.
     Value from the same forward.
   - flush completed matches in seed order.
   `inference_mode="per_row"` keeps the CPU exactness path. Three slot counts are
   distinct and all three are reported: **requested** (`pool_slots`), **allocated**
   (what `GoEnvPool` constructs — `min(pool_slots, matches_per_iter)`; the trainer and
   bench never allocate surplus envs) and **effective-live** (slots that held a match
   during the round). A larger `pool_slots` than the match count is not a stress test.

4. **Config / CLI** — `PPOConfig.collector` and `pool_slots` already exist. Honour
   them in `train_b2b`'s collector selection (l.1449): `"batched"` builds
   `make_selfplay_pool(...)` with B2b's `EnvConfig` (oracle observation on, event
   window = model window) and ignores `num_workers`. Expose `--collector` and
   `--pool-slots` on `fh-mj-train-b2b` and `fh-mj-collect-bench`. Resume echo
   (`train_state.py`): **`collector` is rejected-on-change** (it changes the action-RNG
   mapping); `pool_slots` is logged-not-rejected only within an already-batched lineage
   once slot-count invariance (G0.2) has passed. A legacy echo without these keys reads
   as `collector="process"`. Tests: uninterrupted-vs-resumed equality, and pool cleanup
   on exception.

5. **Stale-library handshake** — `GoEnvPool` already raises on a pre-B2a library when
   the event window is nonzero; the B2b chongci "zero outcomes across completed
   matches" check moves into `_finalize_b2b_match`'s caller so both collectors keep it.

### What changes semantically

- **Action sampling RNG stream.** The process collector samples with the global torch
  RNG seeded per match; the batched one uses per-match numpy RNGs. Trajectories under
  sampling are therefore a different draw from the same policy distribution — the same
  class of change as a different `base_seed`. Bit-identity between collectors is only
  provable in greedy mode; the gates below are built around that.
- Nothing else: observations, masks, rewards, events, labels, bonus, telemetry are the
  same functions of the same Go state.

### Hard prohibition

This collector must never be enabled in, or used to resume, the placement-reshape
lineage (`experiment/placement-reshape-10-5-1-n10`, seeds 650320–698319). Its frozen
seeds, collector, action-RNG mapping, bridge snapshot, and checkpoints stay untouched.
The resume rejection in change 4 mechanically prevents a collector change on an
existing `train_state.pt`; a *fresh* run under that lineage's name is governance, not
code — there is no lineage identifier to enforce it. A legacy echo without a
`collector` key reads as the literal `"process"`, never the dataclass default, so a
later default switch cannot reinterpret old states. Making the pool the B2b default
requires a new post-lap authorization.

### Out of scope

- Batching `fh-mj-evaluate` (same batch-1 shape; separate follow-up).
- PPO update tuning (AMP, `torch.compile`, larger minibatch): ≤ 2 min/iter today.
- Go-side optimization: not on the critical path.
- The legacy `fh-mj-train-ppo` / GRP path.

## Gates

All gates run on `experiment/batched-b2b-collector`; none touches the running
placement-reshape lap or its frozen manifest. GPU benches wait for that lap to finish
— never share the 4090 with a live lap.

### G0 — Exactness (Mac, CPU, `pytest`)

1. **Transport/orchestration identity (greedy, per-row).** With argmax action
   selection injected into both collectors, `inference_mode="per_row"`, Go bridge, same
   seed block (≥ 32 chongci matches incl. at least one truncated and one bust): the
   `collect-bench` digest over every `RolloutBatch` field (planes, scalars, masks,
   actions, logprobs, values, rewards, dones, events, event_lengths, dealin_labels,
   rank_labels) and the `match_telemetry` list are **byte-equal** between
   `collect_b2b_rollouts` and `collect_b2b_rollouts_batched`. Exactness is possible
   only because logprobs come from the shared Torch helper.
1b. **Production-batched numeric parity (CPU).** Same setup with
   `inference_mode="batched"`. The *semantic digest* (every `RolloutBatch` field except
   `old_logprobs`/`values`, plus `truncated_matches` and telemetry) is **byte-exact**;
   excluding the two float fields from the hash does not waive their gate. Registered
   hard ceilings on the excluded floats, absolute (relative error is unstable near 0),
   measured at **production width** (anchor075, 96ch × 4 blocks, GRU) as well as on
   the test net, and compared **per field** — never one collapsed maximum:
   - non-finite logits / logprobs / values: 0
   - legal logits: max |Δ| ≤ 5e-5 (selected-action logprob alone is insufficient)
   - `old_logprobs`: max |Δ| ≤ 5e-5
   - `values`: max |Δ| ≤ 5e-6
   Report per field and comparison: element count, non-finite count, mismatch count,
   p50/p95/p99/p99.9/max |Δ|, and the count beyond both the legacy `atol=1e-6,
   rtol=1e-5` (diagnostic only) and the hard ceiling. Measured 2026-08-26 on CPU:
   logprobs max 2.7e-5, values 1.8e-6. The pytest gate uses the test net; the
   `fh-mj-collect-bench` gate enforces the same ceilings at production width and
   **exits non-zero** on any violation.
   **CUDA is gated, not merely documented.** Pre-registered before any CUDA number is
   seen: hard ceilings legal logits and logprobs 1e-4, values 1e-5. Procedure: a fixed
   three-repeat greedy calibration block sets each operational threshold to 2 × the
   calibration maximum, capped by the ceiling; validation runs on a disjoint fixed seed
   block. Exceeding the cap stops the work; the cap is never widened afterwards.
2. **Slot-count invariance.** Same digest for `pool_slots ∈ {1, 7, 64}` under sampling
   (per-match RNG makes this exact, as `batched_selfplay` already proves).
3. **Placement-bonus fail-closed parity.** The truncated-match, zero-decision-seat, and
   reset-terminal raises fire identically from the shared finalizer.
4. **Round-outcome plumbing (ordered).** Assert the ordered outcome sequence and
   payloads per slot across: a nonterminal hand boundary, the terminal hand, truncation
   after a completed hand, and the reset-terminal fail-closed case; `hand_id`
   assignment matches the process collector's. `outcomes_seen > 0` alone does not pass.
5. **Ragged GRU.** Batched vs per-row forward parity at event lengths `{0, 1, W−1, W}`
   with poisoned padding values: tail selection at `length−1`, zero-length rows produce
   the zero-history output, numeric parity within the 1b tolerance.
6. **Training parity.** Two-iteration CPU run from the same model, optimizer, seed
   schedule and minibatch generator, process collector vs pool collector (per-row,
   greedy): rollout, GAE inputs, advantages, returns, reported metrics, and the model
   **and optimizer** state **after each iteration** byte-equal. Then the same with
   `inference_mode="batched"`: rollout floats within the 1b ceilings; registered
   update tolerance max |Δ| ≤ 1e-5 on every parameter and on every optimizer moment
   after each iteration.

### G1 — Throughput and memory (box, after the current lap)

Arms: process control `--workers 10`; batched candidates `--pool-slots {128,256,320}`.
Exactly 320 matches per measured cycle. Each arm runs one excluded warmup, then
**three genuine consecutive collect → PPO cycles on one persistent pool and one
persistent model/optimizer** — the trainer's lifetime, not a fresh deep-copy per
cycle — over three fixed consecutive seed blocks. All candidates run to completion;
no early stopping, no dropping a slow candidate. Throughput uses sampled production
inference; numeric parity is a separate greedy CUDA calibration/validation run per
G0.1b.

Register before launch: commit, anchor SHA, bridge SHA, model shape and event window,
PyTorch/CUDA/cuDNN versions, TF32 and determinism settings, GPU identity, memory
limit.

Record per cycle: collection time and `matches/s`, update time, transition rows,
truncations, RSS, cgroup peak, and CUDA allocated **and reserved** peaks measured
**separately for collection and for the PPO update**; requested / allocated /
effective-live slot counts; allocator retention across cycles (the iteration-boundary
retention failures of ds960 are the reason for three cycles).

Acceptance: **≥ 10× the process arm's collection throughput** for some candidate,
aggregate RSS ≤ 20 GiB, CUDA peak ≤ 20 GB. Pick the **smallest** slot count within
10 % of the best — speed alone never justifies a resource count.

The Mac CPU bench (2026-08-26: 32 matches, 209 s at 8 slots, 231 s at 32, no process
baseline) is diagnostic only and has no bearing on this gate.

### G2 — Distributional sanity (box, screening window `910000+`)

320 matches, sampled, champion checkpoint, both collectors: mean/σ of per-seat
trajectory return, `dealin_positive_rate`, `rank_label_coverage`, truncation count,
bust count. Reported side by side; any |Δ| beyond 2σ of the process collector's own
seed-to-seed variation stops the work and returns to consultation.

### G3 — Recipe sanity lap (box)

Champion recipe (anchor075 warm start, 320 matches/iter) for 25 iterations, **twice
from the same anchor and seed schedule: once with the process collector (control), once
with the batched collector**. `fh-mj-compare` batched-vs-control and each vs the
champion on the screening window; the expectation is that the two arms are within the
clustered CI of each other. Neither arm can back a promotion — this is a "did we break
training" check.

If G0 fails: fix; it is a bug. If G1 misses 10×: profile the Python round loop before
touching anything else — Go is 2.5 ms/match, so the residual is Python. If G2 or G3
fails: stop and return to consultation.

## Expected effect

With Go negligible, per-decision cost drops from one single-thread CPU forward to
1/N of a batched GPU forward plus Python row bookkeeping. Iteration time ≈ collection
at the G1-measured rate + 2 min update. At 10× the 960-match iteration is ~5 min and
the 150-iteration lap ~12 h instead of ~3.3 days; at 320 matches/iter (the ds960 NULL
says 960 buys nothing) it is ~3 min/iter.

## Stages

| Stage | Where | Content |
|---|---|---|
| 0 | Mac | Changes 1–5, G0.1–G0.6 green, `fh-mj-collect-bench --collector batched` runs on mock and Go bridges on CPU |
| 1 | Box, post-lap | G1 bench; record measured slot count and rate here |
| 2 | Box | G2 + G3; consult on the readout before the collector becomes the default |

Consult before Stage 1 with the G0 results in hand.
