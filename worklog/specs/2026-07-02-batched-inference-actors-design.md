# Batched-Inference Actor Architecture — Design

**Status:** approved design, ready for implementation plan.
**Branch:** `claude/batched-inference-actors`.

## Goal

Raise self-play rollout throughput ≥3× (expected ~6×) by replacing per-worker
CPU inference with a **Go env pool stepped over batched FFI** feeding **one
batched GPU forward per round** in a single Python process — while preserving
the collection layer's correctness invariants (per-seat-contiguous GAE
trajectories, δ feature-dropout semantics, reproducibility).

Scope: the **self-play collection path only** (`train_selfplay_oracle`). The
existing `collect_selfplay_rollouts` / `ParallelSelfplayCollector` stay
untouched and remain the default until the operational gate passes. Oracle
(`train_oracle`) and `train_ppo` collectors are out of scope.

## Profiled facts (4090 box, 24 cores, 31 GB, 4-block net)

- Rollout is CPU-core-bound, not memory-bound (~380 MB/worker; 13% RAM at 10
  workers). Scaling near-linear to ~8 workers, knee ~16: 0.61 / 0.91 / 1.03
  matches/s at 8 / 16 / 20 workers (best ≈ 2,076 decisions/s).
- The Go env step is ~2 µs/decision after the shanten-table embed (PR #140).
  **Env compute is negligible; the per-decision cost is Python**: protobuf
  `repeated float` obs decode, batch-1 CPU inference (~2 ms on the 4-block
  net), and per-decision FFI marshaling.
- The GPU is idle during the entire rollout phase (only `ppo_update` uses it).
- Spawn-worker IPC costs ~2×: in-process 468 dec/s vs spawn nw=1 243 dec/s.

Conclusion: there is nothing on the env side worth parallelizing with
processes. The design removes the Python per-decision overhead instead.

## Decisions (user-approved)

1. **Determinism:** run-to-run bit-identity for a fixed config + CPU-exact
   cross-config tests (see §Determinism). Strict cross-config bit-exactness on
   GPU is impossible in principle (batch-composition-dependent float rounding)
   and is not required.
2. **Scope:** self-play only; new collector lands alongside the old one behind
   a trainer flag; old path stays default until the gate passes.
3. **Approach:** Go env-pool + batched FFI + single Python process (approach A
   over SEED-RL-style actor processes and async dynamic batching — async was
   ruled out by the determinism requirement; actor processes solve an
   expensive-env problem we do not have).
4. Python owns the seed schedule (Go never self-resets a slot); flat byte
   buffers ride inside a proto envelope (versioned structure, ~zero decode
   cost); default `pool_slots = 128`.

## Architecture

```
┌─ Python (single process) ─────────────────────────────────┐
│ collect_selfplay_rollouts_batched()                       │
│   round loop:                                             │
│     commands ────────────► FHEnvPoolStep (1 FFI call)     │──► Go: M envs,
│     ◄──────── flat buffers (planes/scalars/masks) + meta  │    goroutine per
│     np.frombuffer → one GPU forward (all pending rows)    │    commanded slot
│     per-match RNG sampling + δ-mask + seat bookkeeping    │
└───────────────────────────────────────────────────────────┘
```

Each round, every live slot advances exactly one decision (a mahjong match has
one acting seat at a time), so M live slots produce a batch of M rows.

## Components

### 1. Go env pool — `internal/rl/envpool.go` + `cmd/rlbridge` exports

New c-shared exports (same `FHBytesResult`/error conventions as `FHEnvStep`):

- `FHEnvPoolNew(requestPtr, len) -> handle` — request `EnvPoolNewRequest`;
  creates `slots` independent `rl.Env` instances (no shared state).
- `FHEnvPoolStep(handle, requestPtr, len) -> FHBytesResult` — request
  `EnvPoolStepRequest`; applies each `SlotCommand` (step / reset / skip) to its
  slot **in a goroutine** (WaitGroup join), then serializes one
  `EnvPoolStepResponse`.
- `FHEnvPoolClose(handle)`.

Proto additions to `proto/game.proto` (regenerate Go, Python, **and TS**
bindings per the standing rule):

```proto
message EnvPoolNewRequest {
  EnvConfig config = 1;
  uint32 slots = 2;
}

message SlotCommand {
  uint32 slot = 1;
  oneof cmd {
    uint32 action_id = 2;   // step this slot
    uint64 reset_seed = 3;  // reset this slot with a new match seed
    bool skip = 4;          // slot idle this round (seeds exhausted)
  }
}

message EnvPoolStepRequest {
  repeated SlotCommand commands = 1;
}

message SlotState {
  uint32 slot = 1;
  uint32 seat = 2;                 // acting seat of the returned observation
  bool terminated = 3;
  bool truncated = 4;
  repeated float step_rewards = 5; // per-seat rewards for THIS step (len 4)
  bool has_observation = 6;        // false when terminated/truncated/skipped
  RoundOutcome round_outcome = 7;
  string error = 8;                // per-slot failure (empty = ok)
}

message EnvPoolStepResponse {
  repeated SlotState slots = 1;    // one per commanded slot, ascending slot id
  // Flat observation buffers for slots with has_observation, concatenated in
  // ascending slot order. planes: float32 LE, C-order [rows, C, H, W].
  bytes planes = 2;
  bytes scalars = 3;               // float32 LE [rows, scalar_count]
  bytes action_masks = 4;          // uint8 [rows, action_space_size]
  uint32 plane_channels = 5;
  uint32 plane_height = 6;
  uint32 plane_width = 7;
  uint32 scalar_count = 8;
  uint32 action_space_size = 9;
}
```

Notes:
- Reset commands return the first observation the same way (a reset that
  terminates immediately returns `terminated=true, has_observation=false` —
  today's "match ends during reset" case).
- Goroutine fan-out cannot affect results: slots share no state, and each
  env's evolution is a pure function of (seed, action sequence).

### 2. Python env-pool abstraction — `ai/src/fh_mahjong_ai/envpool.py`

One interface, two implementations:

- `GoEnvPool(env_config, slots)` — ctypes wrapper over the new exports;
  decodes flat buffers with `np.frombuffer(...).reshape(rows, ...)` (views, no
  per-element decode).
- `InProcessEnvPool(env_config, slots)` — loops `slots` ordinary bridges
  (mock or go) in-process behind the same interface. This is the unit-test
  path (the mock bridge is Python-only) and the CPU-exactness path.

Interface (duck-typed like the bridges):

```python
class PoolStepResult:
    slots: list[SlotMeta]        # slot, seat, terminated, truncated,
                                 # step_rewards, has_observation, error
    planes: np.ndarray           # (rows, C, H, W) float32
    scalars: np.ndarray          # (rows, S) float32
    action_masks: np.ndarray     # (rows, A) int8
    row_of_slot: dict[int, int]  # slot id -> row index

pool.step(commands: list[SlotCommand-like]) -> PoolStepResult
pool.close()
```

### 3. Batched collector — `ai/src/fh_mahjong_ai/batched_selfplay.py`

`collect_selfplay_rollouts_batched(env_config, model, config, base_seed,
drop_prob, pool) -> RolloutBatch`

Per-slot `MatchState` carries exactly today's per-match logic:

- Four per-seat buffer sets (planes/scalars/masks/actions/logprobs/values/
  rewards); reward crediting `seat_rewards[k][-1] += step_rewards[k]` for every
  seat with a decision, applied from each round's `SlotState.step_rewards`.
- `mask_rng = np.random.default_rng(base_seed + m)` — the δ feature-dropout
  stream, drawn once per decision in the match's own decision order; with
  probability `drop_prob` zero plane channels 39:51 of that row **and record
  the masked row** (PPO must update on what the policy saw).
- `sample_rng = np.random.default_rng([base_seed + m, 17])` — a separate
  per-match stream for action sampling.
- On match end, per-seat contiguous emission with `dones=[0]*(n-1)+[1]`
  (the Phase-2 GAE invariant), seats 0..3 in order — unchanged from today.

Round loop:

1. Build commands: `reset_seed` for empty slots with seeds remaining
   (seed schedule: `base_seed + m`, m = 0..matches_per_iter-1, assigned in
   order as slots free up), `action_id` for slots with a sampled action,
   `skip` for idle slots. First round resets slots 0..min(slots, T)-1 with
   seeds base..base+min(slots, T)-1.
2. `pool.step(commands)`; apply per-slot rewards/termination bookkeeping.
3. Apply δ-mask per pending row (per-match `mask_rng`).
4. Inference over all pending rows:
   - `inference_mode="batched"` (production): one forward, on
     `config.device`.
   - `inference_mode="per_row"` (test): each row forwarded alone — same
     orchestration path, exactness-friendly granularity.
5. Sample per row with the shared helper (below); store action/logprob/value
   in the slot's `MatchState`.
6. Repeat until all matches emitted; **flush completed matches into the
   RolloutBatch in seed order** (buffer out-of-order completions).

Sampling helper (module-level, unit-tested):

```python
def sample_masked_action(logits_row, mask_row, temperature, rng):
    legal = np.flatnonzero(mask_row > 0)
    scaled = logits_row[legal].astype(np.float64) / max(temperature, 1e-6)
    shifted = scaled - scaled.max()                      # stable log-softmax,
    log_probs = shifted - np.log(np.exp(shifted).sum())  # no scipy dependency
    idx = rng.choice(len(legal), p=np.exp(log_probs))
    return int(legal[idx]), float(log_probs[idx])
```

Same distribution family as today (Categorical over temperature-scaled masked
logits); the RNG moves from the global torch generator to the per-match numpy
generator, which is what makes sampling independent of batch composition. The
new path does not call `torch.manual_seed` at all.

### 4. Trainer wiring

- `PPOConfig` gains `collector: str = "process"` and `pool_slots: int = 128`.
- `train_selfplay_oracle` picks the collector by flag;
  `fh-mj-train-selfplay-oracle` gains `--collector {process,batched}` and
  `--pool-slots`. **Default stays `process` until the operational gate
  passes** (flip is a follow-up one-liner).

## Determinism

A match's trajectory is a pure function of (its seed, its own decisions): the
model is frozen during collection and both RNG streams are seeded per-match.
Guarantees, strongest first:

1. **`per_row` mode on CPU: full-array RolloutBatch equality across ANY slot
   count** (slots=1 == slots=8 == sequential), because scheduling can only
   reorder emission and emission is pinned to seed order. This is stronger
   than the old sorted-rewards invariant.
2. **`batched` mode: run-to-run bit-identity for a fixed config** (same seeds,
   same slots, same device): the round schedule, batch composition, and
   forward results are deterministic; GPU forwards are deterministic run-to-
   run for identical inputs on the same hardware.
3. **`batched` vs `per_row`: statistical equivalence** (same match set, close
   reward statistics), not bit-equality — GPU float rounding varies with batch
   composition, which is inherent to batching and accepted by design.

## Error handling

- `SlotState.error` non-empty → Python raises with slot id + match seed
  context (legality is mask-enforced, so an illegal-action error is a bug
  signal, not a runtime case).
- Match terminates during reset → nothing recorded, slot gets the next seed
  (today's `continue` semantics).
- Truncation → the match's blocks are still emitted, flags mirrored to
  today's behavior.
- Seeds exhausted → idle slots receive `skip` until all matches drain.
- GPU OOM → `pool_slots` is the knob; the batch never exceeds live slots.
- Pool handle lifecycle: `close()` idempotent; collector uses try/finally
  like today's bridge handling.

## Testing

Go (`internal/rl/envpool_test.go`):
- `TestEnvPoolMatchesSingleEnv` — pool of 4 stepped to completion equals four
  single-env runs on the same seeds (slot independence, goroutine safety).

Python (`ai/tests/test_batched_selfplay.py`):
- `test_sample_masked_action_matches_categorical` — helper's distribution and
  logprob agree with `torch.distributions.Categorical` semantics on fixed
  logits (same probabilities; RNG stream is numpy).
- `test_batched_slot_count_invariance_exact` — `per_row` CPU, slots=1 vs
  slots=8 on the mock pool → full-array equality of every RolloutBatch field.
- `test_batched_run_to_run_identical` — same config twice → identical batch.
- `test_batched_records_all_four_seats` — ~4× transitions of a single seat;
  dones at per-seat block ends (contiguity regression, mirrors the Phase-2
  test).
- `test_batched_feature_dropout` — drop_prob=1.0 → recorded planes channels
  39:51 all zero; 0.0 → nonzero.
- `test_batched_vs_per_row_statistical` — same seeds → same match count,
  close mean rewards (loose tolerance).
- `test_train_selfplay_oracle_batched_collector` — 2 iters on mock via
  `--collector batched` → checkpoints + history with `delta`.

Operational gate (on the 4090, post-merge, before flipping the default):
1. Throughput A/B: `batched --pool-slots 128` vs `process --num-workers 16`
   on identical config → require **≥3× decisions/s** (expect ~6×).
2. Short training run (~10 iters) → losses/entropy in family with the process
   collector; extracted-student eval not degraded.

## Out of scope (explicit)

- Double-buffered pools overlapping Go stepping with GPU forwards (~last
  20%); revisit only if the gate shows the GPU idle-waiting on rounds.
- `RemoteEnvPool` sharding slots across hosts — the pool interface permits
  it; nothing else is built now.
- Migrating `collect_oracle_rollouts` / `train_ppo` collection.
- Removing the process collectors (kept as fallback and reference).

## File inventory

- `proto/game.proto` — pool messages (+ regen Go/Python/TS bindings).
- `internal/rl/envpool.go`, `internal/rl/envpool_test.go`.
- `cmd/rlbridge/main.go` — `FHEnvPoolNew/Step/Close` exports.
- `ai/src/fh_mahjong_ai/envpool.py` — `GoEnvPool`, `InProcessEnvPool`.
- `ai/src/fh_mahjong_ai/batched_selfplay.py` — collector + sampling helper.
- `ai/src/fh_mahjong_ai/ppo.py` — `PPOConfig.collector` / `pool_slots`.
- `ai/src/fh_mahjong_ai/oracle.py` — `train_selfplay_oracle` collector switch.
- `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py` — CLI flags.
- `ai/tests/test_batched_selfplay.py`.
- AGENTS.md updates (`ai/`, `internal/rl/`, `cmd/rlbridge/`).
