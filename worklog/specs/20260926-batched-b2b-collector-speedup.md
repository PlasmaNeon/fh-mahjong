# `batched-b2b-collector` speedup — the G1 miss was defects, not the premise

Status: **MERGED 2026-09-26 as `605c5ee` (PR #242).** Supersedes the throughput verdict of
[`20260826-batched-b2b-collector-design.md`](20260826-batched-b2b-collector-design.md)
(G1 FALSIFIED at 0.99×). `collector=process` stays the default. G2/G3 and the default switch
still need their own authorization, and the batched collector must never enter the
placement-reshape lineage (that spec's hard prohibition stands).

## Result

4090 box, 320 matches, 320 slots, anchor075 (96ch × 4 blocks, 128-step event GRU, privileged
critic, aux heads), `fh-mj-collect-bench`, steady collection, control and candidate
interleaved, commit `2e86464`:

| Arm | Run A | Run B | Mean |
|---|---|---|---|
| process, 10 workers (same Go as the candidate) | 364.7 s | 349.7 s | 357.2 s |
| batched, 320 slots | 42.8 s | 44.8 s | **43.8 s** |

- **11.2×** the G1 control (491.2 s, the collector production ran), **8.2×** the process
  collector with the same Go.
- `--full-cycle`, three collect → PPO cycles: collect 45.7 / 44.5 / 40.7 s, update
  122.7 / 125.2 / 127.2 s. An iteration drops from ~680 s to ~170 s; **the PPO update is now
  ~74% of it.**
- Per-collection split at 320 slots: pool 16 s, forward 9.6 s, decision step 4.4 s, other
  3.0 s, final `RolloutBatch` stack ~4.8 s.
- During collection the GPU idles in P5 (700–1,400 MHz of 3,105), so a graph replay takes
  3.3 ms against ~1.2 ms at full clocks. That is the Windows NVIDIA power mode, not code.

Evidence is two interleaved pairs, not G1's five-interleave, three-cycle protocol. It
establishes the order of magnitude, not a registered acceptance.

## Causes

| Cause | Where the time went | Fix |
|---|---|---|
| Wild routes enumerated placements | `calcSevenPairsWithWilds` / `calcIndependenceWithWilds` tried every multiset of wild positions over 34 types (7,140 for 3 wilds), ~500× per observation: **89% of Go env-step CPU** | Exact closed forms; per-suit MIS tables for independence |
| Every draw ran every route | `findUsefulTiles` ran a full `Analyze` for all 34 draws | One tile moves seven-pairs / independence shanten by ≤ 1, so those routes are skipped when they cannot matter; nothing is evaluated at tenpai; the standard route resumes a cached suit chain |
| Goroutine per slot | Scheduler time, fresh stacks regrown every round, 26.7 MB garbage per round | `GOMAXPROCS` workers, parallel row packing into pre-sized buffers |
| Launch-bound forward | ~125 kernels, 1.8 ms host vs ~1 ms GPU per round | CUDA-graph replays at 32-row buckets, per collection call; `cudnn.benchmark` during collection |
| Per-row Python | A `Categorical` per row, `rng.choice` validation, per-row copies | One `masked_logprobs` per round, batched sampler, whole-round arrays, zero-reward fast path |

Go env step: **2,992 → 65 µs** (`BenchmarkEnvStepChongci`). A two-group pipeline (Go stepping
one half while the GPU runs the other) was tried and was **slower**: two half-size eager
forwards launch twice the kernels.

## Exactness

- The old implementations are test oracles: wild routes (every suit mask; 60,000 random
  hands under `SHANTEN_EXHAUSTIVE=1`), unpruned `findUsefulTiles` (40,000 hands),
  `standardPrefix` vs `calcStandard`, `packObservationRows` vs `appendObservationRow`,
  `masked_logprobs` vs `masked_logprob`, the batched sampler vs `rng.choice` (action and
  generator state).
- The three process-collector golden digests are unchanged and G0.1 passes. Every step after
  the cuDNN change reproduced the same 631,458 rows on the box.
- **CUDA G0.1b passes** on the graphed, autotuned path (64 matches, pool 64): legal logits
  p99.9 7.6e-6 / max 1.5e-5 (ceilings 3e-5 / 1e-4); `old_logprobs` max 7.2e-6 (7e-5);
  `values` max 7.2e-7 (6e-6).
- Autotuning picks algorithms by timing, so batched-mode floats and sampled trajectories can
  differ between processes. That is the G0.1b class; `per_row` and CPU are unaffected.

## Before the batched collector can become the default

1. G1-protocol confirmation on a quiet box: five interleaves, three full cycles, memory under
   production rollout lifetime.
2. G2 distributional sanity and G3 recipe sanity lap, as registered in the design spec.
3. Post-lap authorization, outside the placement-reshape lineage.

## Rules

- **Profile the whole path before ruling a design falsified.** Phase timers say where time
  is charged, not why. Use Go pprof, cProfile and CUDA events on the real loop before
  concluding.
- **Measure GPU time inside the real loop, not in a tight microbenchmark.** Clocks, launch
  overhead and batch shape all differ there.
- **Keep the replaced implementation as a test oracle** when optimizing a pure function the
  observations depend on.
