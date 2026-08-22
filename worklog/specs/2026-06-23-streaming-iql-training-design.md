# Streaming IQL Training (Memory-Efficient Replay) — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorming complete; ready for implementation plan)

## Goal

Let IQL training consume self-play datasets larger than RAM by **streaming**
batches from the sharded `.npz` store instead of loading every transition into an
in-memory array buffer. This is the prerequisite to scaling the self-play loop:
the big-batch validation run was OOM-killed during training on a 31 GB box (see
`worklog/rl-experiment/chongci-rl-experiment-progress.md`, "Big-Batch Loop Validation"),
which showed the binding constraint is **training memory**, not generation speed.
With streaming, the loop can use far more data per iteration, and we can finally
test whether more data lets a candidate beat the anchor.

## Scope

In scope: a streaming replay buffer (PyTorch `IterableDataset` + `DataLoader`),
opt-in wiring into `fh-mj-train-iql` and `fh-mj-selfplay-loop`, and tests.

Out of scope: parallel self-play *generation* (separate shelved spec); changing
the IQL math, model, or storage format; supporting the pairwise / risk-trace
auxiliary paths under streaming.

## Key Decisions

- **Mechanism:** PyTorch `torch.utils.data.IterableDataset` + `DataLoader`
  (batching, collate, multi-worker prefetch) — leans on the standard library
  rather than a hand-rolled sampler. `num_workers > 0` also parallelizes shard
  loading.
- **Coverage:** true streaming — one epoch yields **every** row exactly once, with
  local shuffling via a bounded in-iterator shuffle buffer + per-epoch shard-order
  shuffle.
- **Interface:** `StreamingReplayBuffer` exposes the same `.sample(batch_size)` /
  `__len__` as `ArrayReplayBuffer`, so `DiscreteIQLTrainer` and the IQL math are
  untouched — only buffer construction changes.
- **Rollout:** opt-in via `--stream` (train CLI) / `--stream-training` (loop),
  default OFF. Small datasets keep the existing fast in-memory path; big-data runs
  enable streaming. Non-breaking, and lets us validate equivalence first.
- **Scope boundary:** streaming supports the standard IQL path only; combining it
  with `--pairwise-data` / risk-trace options raises a clear error.

## Architecture & Components

- `ai/src/fh_mahjong_ai/streaming_data.py` — new module:
  - `build_shard_index(data_paths) -> tuple[list[tuple[Path, int]], int]` —
    enumerate `(shard_path, n_rows)` across the repeated `--data` dirs from their
    manifests, plus the total row count. No arrays loaded.
  - `TransitionIterableDataset(IterableDataset)` — `__iter__` yields per-transition
    samples reconstructed to the IQL fields. Handles multi-worker shard
    partitioning (`get_worker_info`, `shard i -> worker i % W`), per-epoch
    shard-order shuffle (seed = `base_seed + epoch + worker_id`), and a bounded
    shuffle buffer (`shuffle_buffer` rows) for local row shuffling.
  - `collate_transitions(samples) -> TrainBatch` — stack a list of per-row samples
    into the existing `TrainBatch` dataclass; pairwise fields defaulted; tensors
    kept on CPU (the trainer moves to device).
  - `StreamingReplayBuffer` — wraps `DataLoader(dataset, batch_size,
    num_workers=stream_workers, collate_fn=collate_transitions, drop_last=True)`;
    persistent iterator; `.sample(batch_size)` returns the next `TrainBatch`,
    rebuilding the iterator (next epoch, reshuffled) on `StopIteration`; `__len__`
    = total rows.
- `ai/src/fh_mahjong_ai/scripts/train_iql.py` — modify: `stream`,
  `stream_shuffle_buffer` (default 50000), `stream_workers` (default 2) params +
  CLI flags. When `stream=True`, build a `StreamingReplayBuffer` instead of
  `load_iql_replay_buffer`. Raise `ValueError` if combined with
  `--pairwise-data`/risk-trace.
- `ai/src/fh_mahjong_ai/selfplay_loop.py` — modify: `LoopConfig.stream_training`
  (+ `stream_shuffle_buffer`, `stream_workers`); `run_iteration` forwards them to
  `train_iql`. CLI `--stream-training` etc.
- `ai/tests/test_streaming_data.py` — new tests.
- `ai/AGENTS.md` — document the module, flags, and tests.

## Per-Row Reconstruction

Each yielded sample mirrors `ArrayReplayBuffer.sample`'s per-row logic exactly so
streaming and in-memory produce equivalent batches:

- `planes, scalars, action_mask, action_id` from the shard row.
- `returns` = `terminal_rewards[row, seat]`, or placement-shaped via
  `placement_shaped_returns(terminal_rewards[row], placement_values)[seat]` when
  `reward_shaping == "placement"`.
- `steps_to_done` from the shard (fallback 0).
- `next_planes, next_scalars, next_action_mask` from the shard.
- `reward` = `rewards[row, seat]` (fallback 0); `done` = `terminated or truncated`.
- `sample_weight` from the shard (fallback 1.0).
- pairwise fields defaulted (`-1` ids, `0.0` weights/targets).

## Data Flow (one epoch)

```
StreamingReplayBuffer.sample() x (total // batch_size) calls = one epoch
  DataLoader -> TransitionIterableDataset.__iter__ (per worker):
     shards_for_worker = [s for i,s in enumerate(index) if i % W == worker_id]
     shuffle(shards_for_worker)
     for shard in shards_for_worker:
        rows = np.load(shard); shuffle(row order)
        feed rows through shuffle_buffer -> yield reconstructed samples
     drain shuffle_buffer
  collate_transitions -> TrainBatch (CPU)
  -> trainer moves to device, runs IQL step (unchanged)
on StopIteration: rebuild iterator (epoch+1, reshuffled)
```

## Memory & Determinism

- Peak memory ≈ `stream_workers × (shuffle_buffer + one shard)` rows × ~13 KB —
  bounded and tunable, independent of total dataset size.
- Seeded RNG per `(epoch, worker)` → reproducible runs.
- Workers are CPU-only (loading + collate); no CUDA in workers.

## Error Handling

- `--stream` + (`--pairwise-data` | `--risk-trace-*` | `--pairwise-*weight`) →
  `ValueError` (unsupported; needs in-memory cross-row matching).
- Empty dataset / missing manifest → clear error from `build_shard_index`.
- `target_mode` `td` / `global_ev_td` work unchanged (next-state fields present in
  every row).

## Testing

`ai/tests/test_streaming_data.py` (CPU; tiny synthetic shards via
`write_transitions_npz_shards`):

- `build_shard_index`: correct shard list + total across multiple dirs.
- Epoch completeness: one pass yields every `action_id` / `episode_index` exactly
  once — no duplicates, no drops — tested with `shuffle_buffer` < dataset and with
  `num_workers` 0 and 2.
- Field equivalence: streamed batch `returns` match `ArrayReplayBuffer` for the
  same rows, both raw and `reward_shaping="placement"`.
- `.sample()` contract: returns a `TrainBatch` of `batch_size`, wraps across
  epochs without raising, `__len__` == total rows.
- Scope guard: `train_iql(stream=True, pairwise_data_paths=[...])` raises
  `ValueError`.
- End to end: `fh-mj-train-iql --stream` on synthetic shards trains 1 epoch and
  writes a checkpoint; `run_loop(..., stream_training=True)` completes a
  mock-bridge iteration.

## Acceptance Criteria

- `StreamingReplayBuffer` trains IQL on a sharded dataset without materializing it
  in memory; peak memory is bounded by `shuffle_buffer`/`stream_workers`, not
  dataset size.
- One epoch sees every transition exactly once; runs are reproducible per seed.
- `--stream` / `--stream-training` are opt-in; the in-memory path is unchanged when
  off.
- Streaming + auxiliary-path flags fail loudly.
- New logic is covered by tests, including in-memory-vs-streaming equivalence.
