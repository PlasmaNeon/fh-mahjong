# Streaming IQL Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in streaming replay buffer (PyTorch `IterableDataset` + `DataLoader`) so IQL can train on sharded self-play datasets larger than RAM, wired into `fh-mj-train-iql` and `fh-mj-selfplay-loop`.

**Architecture:** Extract `ArrayReplayBuffer.sample`'s per-index field logic into a shared `train_batch_from_arrays(...)` so the streaming collate reuses the *exact* same logic (equivalence by construction). A `TransitionIterableDataset` streams per-row samples from `.npz` shards (per-epoch shard shuffle + bounded shuffle buffer, multi-worker shard partitioning); `StreamingReplayBuffer` wraps a `DataLoader` and exposes the same `.sample(batch_size)`/`__len__` as `ArrayReplayBuffer`, so `DiscreteIQLTrainer` and the IQL math are untouched.

**Tech Stack:** Python 3.12 (uv), PyTorch (`torch.utils.data`), NumPy, the `fh_mahjong_ai` package, pytest.

**Spec:** `worklog/specs/2026-06-23-streaming-iql-training-design.md`

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `ai/src/fh_mahjong_ai/buffer.py` | Replay buffers | Extract `train_batch_from_arrays(...)`; `ArrayReplayBuffer.sample` delegates to it |
| `ai/src/fh_mahjong_ai/streaming_data.py` | Shard index, `IterableDataset`, collate, `StreamingReplayBuffer` | Create |
| `ai/src/fh_mahjong_ai/scripts/train_iql.py` | IQL CLI | `--stream` + buffer construction + scope guard |
| `ai/src/fh_mahjong_ai/selfplay_loop.py` | Loop | `LoopConfig.stream_training` + pass-through |
| `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py` | Loop CLI | `--stream-training` etc. |
| `ai/tests/test_streaming_data.py` | Tests | Create |
| `ai/AGENTS.md` | Docs | Document module + flags |

Commands run from repo root with `uv run --project ai ...`.

---

## Task 1: Extract `train_batch_from_arrays` (DRY refactor)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/buffer.py`
- Test: `ai/tests/test_buffer.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_buffer.py`:

```python
def test_train_batch_from_arrays_matches_indices() -> None:
    from fh_mahjong_ai.buffer import train_batch_from_arrays

    arrays = {
        "seats": np.asarray([0, 1], dtype=np.int64),
        "planes": np.zeros((2, 39, 42, 1), dtype=np.float32),
        "scalars": np.zeros((2, 58), dtype=np.float32),
        "action_mask": np.ones((2, 204), dtype=np.int8),
        "action_ids": np.asarray([3, 7], dtype=np.int64),
        "steps_to_done": np.asarray([1, 0], dtype=np.int32),
        "terminal_rewards": np.asarray([[1.0, -1.0, 0.0, 0.0], [0.2, 0.8, -0.5, -0.5]], dtype=np.float32),
        "rewards": np.zeros((2, 4), dtype=np.float32),
        "terminated": np.asarray([False, True], dtype=np.bool_),
        "truncated": np.asarray([False, False], dtype=np.bool_),
        "next_planes": np.zeros((2, 39, 42, 1), dtype=np.float32),
        "next_scalars": np.zeros((2, 58), dtype=np.float32),
        "next_action_mask": np.ones((2, 204), dtype=np.int8),
        "sample_weights": np.asarray([1.0, 2.0], dtype=np.float32),
    }
    batch = train_batch_from_arrays(arrays, np.asarray([0, 1]), reward_shaping="raw")
    assert batch.action_ids.tolist() == [3, 7]
    assert batch.returns.tolist() == [1.0, 0.8]      # terminal_rewards[i, seat_i]
    assert batch.dones.tolist() == [0.0, 1.0]
    assert batch.sample_weights.tolist() == [1.0, 2.0]

    shaped = train_batch_from_arrays(arrays, np.asarray([0, 1]), reward_shaping="placement")
    # row0 seat0 best -> 1.0 ; row1 seat1 best -> 1.0
    assert shaped.returns.tolist() == [1.0, 1.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_buffer.py -k train_batch_from_arrays -q`
Expected: FAIL with `ImportError: cannot import name 'train_batch_from_arrays'`.

- [ ] **Step 3: Add the shared function and delegate from `ArrayReplayBuffer.sample`**

In `ai/src/fh_mahjong_ai/buffer.py`, add this module-level function (place it just above the `ArrayReplayBuffer` class):

```python
def train_batch_from_arrays(
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    reward_shaping: str = "raw",
    placement_values: tuple = _DEFAULT_PLACEMENT_VALUES,
) -> TrainBatch:
    """Build a TrainBatch from a shard-style arrays dict at the given row indices.

    Shared by ArrayReplayBuffer.sample and the streaming collate so both produce
    identical batches.
    """
    indices = np.asarray(indices, dtype=np.int64)
    batch_size = int(indices.shape[0])
    seats = arrays["seats"][indices].astype(np.int64, copy=False)

    if reward_shaping == "placement":
        full_terminal = arrays["terminal_rewards"][indices].astype(np.float32, copy=False)
        shaped = placement_shaped_returns(full_terminal, placement_values)
        returns = shaped[np.arange(batch_size), seats].astype(np.float32, copy=False)
    else:
        returns = arrays["terminal_rewards"][indices, seats].astype(np.float32, copy=False)

    steps_to_done = (
        arrays["steps_to_done"][indices].astype(np.int32, copy=False)
        if "steps_to_done" in arrays
        else np.zeros(batch_size, dtype=np.int32)
    )
    rewards = (
        arrays["rewards"][indices, seats].astype(np.float32, copy=False)
        if "rewards" in arrays
        else np.zeros(batch_size, dtype=np.float32)
    )
    dones = (
        np.logical_or(arrays["terminated"][indices], arrays["truncated"][indices]).astype(np.float32)
        if "terminated" in arrays and "truncated" in arrays
        else np.zeros(batch_size, dtype=np.float32)
    )
    sample_weights = (
        arrays["sample_weights"][indices].astype(np.float32, copy=False)
        if "sample_weights" in arrays
        else np.ones(batch_size, dtype=np.float32)
    )

    def _opt_ids(key):
        return (
            arrays[key][indices].astype(np.int64, copy=False)
            if key in arrays
            else np.full(batch_size, -1, dtype=np.int64)
        )

    def _opt_f32(key):
        return (
            arrays[key][indices].astype(np.float32, copy=False)
            if key in arrays
            else np.zeros(batch_size, dtype=np.float32)
        )

    return TrainBatch(
        planes=arrays["planes"][indices].astype(np.float32, copy=False),
        scalars=arrays["scalars"][indices].astype(np.float32, copy=False),
        action_mask=arrays["action_mask"][indices].astype(np.int8, copy=False),
        action_ids=arrays["action_ids"][indices].astype(np.int64, copy=False),
        returns=returns,
        steps_to_done=steps_to_done,
        next_planes=arrays["next_planes"][indices].astype(np.float32, copy=False)
        if "next_planes" in arrays
        else np.empty((batch_size, 0), dtype=np.float32),
        next_scalars=arrays["next_scalars"][indices].astype(np.float32, copy=False)
        if "next_scalars" in arrays
        else np.empty((batch_size, 0), dtype=np.float32),
        next_action_mask=arrays["next_action_mask"][indices].astype(np.int8, copy=False)
        if "next_action_mask" in arrays
        else np.empty((batch_size, 0), dtype=np.int8),
        rewards=rewards,
        dones=dones,
        sample_weights=sample_weights,
        pairwise_preferred_action_ids=_opt_ids("pairwise_preferred_action_ids"),
        pairwise_avoided_action_ids=_opt_ids("pairwise_avoided_action_ids"),
        pairwise_weights=_opt_f32("pairwise_weights"),
        pairwise_reward_delta_targets=_opt_f32("pairwise_reward_delta_targets"),
    )
```

Then replace the body of `ArrayReplayBuffer.sample` after the index selection (everything from `seats = self.arrays["seats"]...` down to the final `return TrainBatch(...)`) with:

```python
        rng = np.random.default_rng(seed)
        positions = rng.choice(len(self), size=batch_size, replace=False)
        indices = self.indices[positions]
        return train_batch_from_arrays(self.arrays, indices, self.reward_shaping, self.placement_values)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_buffer.py -q`
Expected: PASS (existing buffer tests + the new one — the refactor preserves behavior).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/buffer.py ai/tests/test_buffer.py
git commit -m "refactor(buffer): extract train_batch_from_arrays shared by buffer + streaming"
```

---

## Task 2: `build_shard_index`

**Files:**
- Create: `ai/src/fh_mahjong_ai/streaming_data.py`
- Test: `ai/tests/test_streaming_data.py`

- [ ] **Step 1: Write the failing test**

Create `ai/tests/test_streaming_data.py`:

```python
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.storage import write_transitions_npz_shards
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0) -> Observation:
    return Observation(
        seat=seat,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(58, dtype=np.float32),
        action_mask=np.ones(204, dtype=np.int8),
    )


def _transitions(n: int, start: int = 0) -> list[Transition]:
    out = []
    for i in range(n):
        idx = start + i
        out.append(
            Transition(
                observation=_obs(idx % 4),
                action_id=idx,
                rewards=np.asarray([0, 0, 0, 0], dtype=np.float32),
                next_observation=_obs(idx % 4),
                terminated=(i == n - 1),
                info={"episode_index": idx, "terminal_rewards": np.asarray([1, -1, 0, 0], dtype=np.float32)},
            )
        )
    return out


def _make_shards(tmp_path: Path, n: int, name: str, start: int = 0) -> Path:
    d = tmp_path / name
    write_transitions_npz_shards(d, _transitions(n, start), shard_size=4)
    return d


def test_build_shard_index_counts_rows_across_dirs(tmp_path: Path):
    from fh_mahjong_ai.streaming_data import build_shard_index

    d1 = _make_shards(tmp_path, 10, "a", start=0)
    d2 = _make_shards(tmp_path, 6, "b", start=100)
    shards, total = build_shard_index([d1, d2])
    assert total == 16
    assert sum(rows for _, rows in shards) == 16
    assert all(rows > 0 for _, rows in shards)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k build_shard_index -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.streaming_data'`.

- [ ] **Step 3: Implement `build_shard_index`**

Create `ai/src/fh_mahjong_ai/streaming_data.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np

from .storage import SHARDED_TRANSITIONS_MANIFEST


def build_shard_index(data_paths: Sequence[Path]) -> Tuple[List[Tuple[Path, int]], int]:
    """Enumerate (shard_path, n_rows) across sharded dirs; returns (index, total)."""
    index: List[Tuple[Path, int]] = []
    for raw in data_paths:
        directory = Path(raw)
        manifest_path = directory / SHARDED_TRANSITIONS_MANIFEST
        if not manifest_path.exists():
            raise FileNotFoundError(f"no sharded manifest at {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for shard in manifest.get("shards", []):
            shard_path = directory / str(shard["path"])
            index.append((shard_path, int(shard["transitions"])))
    if not index:
        raise ValueError(f"no shards found in {list(data_paths)}")
    total = sum(rows for _, rows in index)
    return index, total
```

Confirm the manifest filename constant exists: `grep -n "SHARDED_TRANSITIONS_MANIFEST" ai/src/fh_mahjong_ai/storage.py` (it is used by `read_transition_arrays`). If the per-shard transition count key differs from `"transitions"`, read it from the manifest written by `write_transitions_npz_shards` and adjust the key accordingly.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k build_shard_index -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/streaming_data.py ai/tests/test_streaming_data.py
git commit -m "feat(streaming): shard index over sharded transition datasets"
```

---

## Task 3: `TransitionIterableDataset` + `collate_transitions`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/streaming_data.py`
- Test: `ai/tests/test_streaming_data.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_streaming_data.py`:

```python
def test_iterable_dataset_yields_every_row_once_single_worker(tmp_path: Path):
    from fh_mahjong_ai.streaming_data import TransitionIterableDataset

    d = _make_shards(tmp_path, 10, "a", start=0)
    ds = TransitionIterableDataset([d], shuffle_buffer=3, seed=0)
    action_ids = sorted(int(s["action_ids"]) for s in ds)
    assert action_ids == list(range(10))  # every row exactly once, no dup/drop


def test_collate_builds_trainbatch(tmp_path: Path):
    from fh_mahjong_ai.streaming_data import TransitionIterableDataset, collate_transitions

    d = _make_shards(tmp_path, 8, "a", start=0)
    ds = TransitionIterableDataset([d], shuffle_buffer=2, seed=0)
    samples = list(ds)[:4]
    batch = collate_transitions(samples)
    assert batch.planes.shape == (4, 39, 42, 1)
    assert batch.action_ids.shape == (4,)
    assert batch.returns.shape == (4,)
    assert batch.next_planes.shape == (4, 39, 42, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k "iterable_dataset or collate" -q`
Expected: FAIL with `ImportError: cannot import name 'TransitionIterableDataset'`.

- [ ] **Step 3: Implement the dataset and collate**

Append to `ai/src/fh_mahjong_ai/streaming_data.py` (add imports at top: `from typing import Dict, Iterator, Optional`; `import torch`; `from torch.utils.data import IterableDataset, get_worker_info`; `from .buffer import train_batch_from_arrays, _DEFAULT_PLACEMENT_VALUES`; `from .types import TrainBatch`):

```python
# Per-row fields carried from a shard into collate. Full per-seat vectors
# (terminal_rewards, rewards) are kept so train_batch_from_arrays computes the
# acting-seat return/reward identically to the in-memory buffer.
_ROW_KEYS = (
    "seats", "planes", "scalars", "action_mask", "action_ids", "steps_to_done",
    "terminal_rewards", "rewards", "terminated", "truncated",
    "next_planes", "next_scalars", "next_action_mask", "sample_weights",
)


class TransitionIterableDataset(IterableDataset):
    """Streams per-transition samples from sharded .npz datasets.

    One full pass (__iter__) yields every row exactly once with local shuffling.
    """

    def __init__(
        self,
        data_paths: Sequence[Path],
        shuffle_buffer: int = 50000,
        seed: int = 0,
    ) -> None:
        super().__init__()
        self.index, self.total = build_shard_index(data_paths)
        self.shuffle_buffer = max(1, int(shuffle_buffer))
        self.seed = int(seed)
        self._epoch = 0

    def __len__(self) -> int:
        return self.total

    def _shards_for_worker(self) -> List[Tuple[Path, int]]:
        info = get_worker_info()
        if info is None:
            return list(self.index)
        return [s for i, s in enumerate(self.index) if i % info.num_workers == info.id]

    def __iter__(self) -> Iterator[Dict[str, np.ndarray]]:
        info = get_worker_info()
        worker_id = 0 if info is None else info.id
        rng = np.random.default_rng(self.seed + self._epoch * 1000 + worker_id)
        self._epoch += 1

        shards = self._shards_for_worker()
        order = rng.permutation(len(shards))
        buffer: List[Dict[str, np.ndarray]] = []

        def _emit_random() -> Dict[str, np.ndarray]:
            j = int(rng.integers(len(buffer)))
            buffer[j], buffer[-1] = buffer[-1], buffer[j]
            return buffer.pop()

        for shard_pos in order:
            shard_path, _ = shards[int(shard_pos)]
            with np.load(shard_path, allow_pickle=False) as loaded:
                present = [k for k in _ROW_KEYS if k in loaded.files]
                cols = {k: loaded[k] for k in present}
                n = cols["action_ids"].shape[0]
                for r in rng.permutation(n):
                    row = {k: cols[k][int(r)] for k in present}
                    buffer.append(row)
                    if len(buffer) >= self.shuffle_buffer:
                        yield _emit_random()
        while buffer:
            yield _emit_random()


def collate_transitions(
    samples: Sequence[Dict[str, np.ndarray]],
    reward_shaping: str = "raw",
    placement_values: tuple = _DEFAULT_PLACEMENT_VALUES,
) -> TrainBatch:
    """Stack per-row samples into a TrainBatch via the shared array logic."""
    keys = samples[0].keys()
    arrays = {k: np.stack([s[k] for s in samples]) for k in keys}
    return train_batch_from_arrays(arrays, np.arange(len(samples)), reward_shaping, placement_values)
```

Note: `terminated`/`truncated` are stacked as bool arrays; `train_batch_from_arrays` consumes them via `np.logical_or`, so collate needs no special-casing.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k "iterable_dataset or collate" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/streaming_data.py ai/tests/test_streaming_data.py
git commit -m "feat(streaming): IterableDataset (shuffle buffer, per-row) + collate"
```

---

## Task 4: `StreamingReplayBuffer`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/streaming_data.py`
- Test: `ai/tests/test_streaming_data.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_streaming_data.py`:

```python
def test_streaming_replay_buffer_sample_contract_and_epoch_wrap(tmp_path: Path):
    from fh_mahjong_ai.streaming_data import StreamingReplayBuffer

    d = _make_shards(tmp_path, 12, "a", start=0)
    buf = StreamingReplayBuffer([d], batch_size=4, shuffle_buffer=3, num_workers=0, seed=0)
    assert len(buf) == 12
    seen = []
    for _ in range(6):  # 6 batches of 4 = 2 epochs; must not raise at epoch boundary
        batch = buf.sample(4)
        assert batch.action_ids.shape == (4,)
        seen.extend(int(a) for a in batch.action_ids.tolist())
    # first epoch (first 3 batches) covers all 12 rows exactly once
    assert sorted(seen[:12]) == list(range(12))


def test_streaming_equivalence_with_array_buffer_returns(tmp_path: Path):
    from fh_mahjong_ai.buffer import ArrayReplayBuffer
    from fh_mahjong_ai.storage import read_transition_arrays
    from fh_mahjong_ai.streaming_data import StreamingReplayBuffer

    d = _make_shards(tmp_path, 8, "a", start=0)
    arrays = read_transition_arrays(d)
    # in-memory placement returns for every row, keyed by action_id
    mem = ArrayReplayBuffer(arrays=arrays, indices=np.arange(8), reward_shaping="placement")
    mem_batch = mem.sample(8, seed=1)
    mem_by_action = dict(zip(mem_batch.action_ids.tolist(), [round(float(r), 5) for r in mem_batch.returns.tolist()]))

    buf = StreamingReplayBuffer([d], batch_size=8, shuffle_buffer=8, num_workers=0, seed=0, reward_shaping="placement")
    s_batch = buf.sample(8)
    s_by_action = dict(zip(s_batch.action_ids.tolist(), [round(float(r), 5) for r in s_batch.returns.tolist()]))
    assert s_by_action == mem_by_action
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k "streaming_replay or equivalence" -q`
Expected: FAIL with `ImportError: cannot import name 'StreamingReplayBuffer'`.

- [ ] **Step 3: Implement `StreamingReplayBuffer`**

Append to `ai/src/fh_mahjong_ai/streaming_data.py` (add `from functools import partial` and `from torch.utils.data import DataLoader` to imports):

```python
class StreamingReplayBuffer:
    """Disk-streaming replay buffer with the ArrayReplayBuffer .sample/__len__ API."""

    def __init__(
        self,
        data_paths: Sequence[Path],
        batch_size: int,
        shuffle_buffer: int = 50000,
        num_workers: int = 2,
        seed: int = 0,
        reward_shaping: str = "raw",
        placement_values: tuple = _DEFAULT_PLACEMENT_VALUES,
    ) -> None:
        self.batch_size = int(batch_size)
        self._dataset = TransitionIterableDataset(data_paths, shuffle_buffer=shuffle_buffer, seed=seed)
        self._loader = DataLoader(
            self._dataset,
            batch_size=self.batch_size,
            num_workers=int(num_workers),
            collate_fn=partial(
                collate_transitions,
                reward_shaping=reward_shaping,
                placement_values=tuple(placement_values),
            ),
            drop_last=True,
        )
        self._iter: Optional[Iterator[TrainBatch]] = None

    def __len__(self) -> int:
        return len(self._dataset)

    def sample(self, batch_size: int, seed: Optional[int] = None) -> TrainBatch:
        if batch_size != self.batch_size:
            raise ValueError(
                f"StreamingReplayBuffer is fixed at batch_size={self.batch_size}, got {batch_size}"
            )
        if self._iter is None:
            self._iter = iter(self._loader)
        try:
            return next(self._iter)
        except StopIteration:
            self._iter = iter(self._loader)  # next epoch (reshuffled)
            return next(self._iter)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -k "streaming_replay or equivalence" -q`
Expected: PASS.

- [ ] **Step 5: Run the whole streaming test module**

Run: `uv run --project ai pytest ai/tests/test_streaming_data.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/streaming_data.py ai/tests/test_streaming_data.py
git commit -m "feat(streaming): StreamingReplayBuffer with .sample/__len__ via DataLoader"
```

---

## Task 5: Wire `--stream` into `fh-mj-train-iql`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_iql.py`
- Test: `ai/tests/test_iql.py`

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_iql.py` (it already imports `train_iql`, `EnvConfig`, `ModelConfig`, `write_transitions_npz_shards`, and has a `_transitions` helper — reuse them):

```python
def test_train_iql_stream_runs_and_saves(tmp_path: Path) -> None:
    env_config = EnvConfig()
    shard_dir = tmp_path / "shards"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_npz_shards(shard_dir, _transitions(16, env_config), shard_size=8)

    metrics = train_iql(
        data_path=shard_dir,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=4,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
        stream=True,
        stream_shuffle_buffer=8,
        stream_workers=0,
    )
    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_train_iql_stream_rejects_pairwise(tmp_path: Path) -> None:
    env_config = EnvConfig()
    shard_dir = tmp_path / "shards"
    write_transitions_npz_shards(shard_dir, _transitions(8, env_config), shard_size=8)
    with pytest.raises(ValueError, match="stream"):
        train_iql(
            data_path=shard_dir,
            checkpoint_dir=tmp_path / "ck",
            epochs=1,
            batch_size=4,
            device="cpu",
            stream=True,
            pairwise_data_paths=[shard_dir],
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_iql.py -k "stream" -q`
Expected: FAIL with `TypeError: train_iql() got an unexpected keyword argument 'stream'`.

- [ ] **Step 3: Add params, scope guard, and buffer construction**

In `ai/src/fh_mahjong_ai/scripts/train_iql.py`:

1. Add an import near the top: `from fh_mahjong_ai.streaming_data import StreamingReplayBuffer`.

2. Add params to the `train_iql(...)` signature (next to `reward_shaping`/`placement_values`):

```python
    stream: bool = False,
    stream_shuffle_buffer: int = 50000,
    stream_workers: int = 2,
```

3. Immediately after `data_paths = normalize_data_paths(data_path)` and the existing `pairwise_paths`/`target_mode` checks, add the scope guard and streaming construction. Replace the existing `buf, transition_count, dataset_transition_counts = load_iql_replay_buffer(...)` call site with:

```python
    if stream:
        if pairwise_paths or risk_trace_reports:
            raise ValueError("--stream does not support --pairwise-data or risk-trace options")
        buf = StreamingReplayBuffer(
            data_paths,
            batch_size=batch_size,
            shuffle_buffer=stream_shuffle_buffer,
            num_workers=stream_workers,
            seed=0,
            reward_shaping=reward_shaping,
            placement_values=tuple(placement_values),
        )
        transition_count = len(buf)
        dataset_transition_counts = [transition_count]
    else:
        buf, transition_count, dataset_transition_counts = load_iql_replay_buffer(
            data_paths,
            max_transitions=max_transitions,
            risk_cases=risk_cases,
            risk_weight=risk_trace_weight,
            risk_dataset_start_seeds=risk_trace_dataset_start_seeds,
            apply_risk_cases=bool(risk_cases)
            and (risk_trace_weight > 1.0 or pairwise_weight > 0.0 or pairwise_q_weight > 0.0),
            pairwise_replay_multiplier=pairwise_replay_multiplier,
            pairwise_data_paths=pairwise_paths,
            pairwise_data_min_reward_gap=pairwise_data_min_reward_gap,
            risk_filter_datasets=risk_trace_filter_datasets,
            risk_context_radius=risk_trace_context_radius,
            reward_shaping=reward_shaping,
            placement_values=placement_values,
        )
```

(Keep the existing `load_iql_replay_buffer(...)` arguments exactly as they currently are in the file; only move them into the `else` branch. The `risk_cases = load_risk_cases_from_paired_trace_reports(...)` line stays before this block.)

4. In `main()`, add CLI args near `--reward-shaping`:

```python
    parser.add_argument("--stream", action="store_true", help="Stream batches from sharded data (memory-bounded; large datasets)")
    parser.add_argument("--stream-shuffle-buffer", type=int, default=50000)
    parser.add_argument("--stream-workers", type=int, default=2)
```

and forward them in the `train_iql(...)` call:

```python
        stream=args.stream,
        stream_shuffle_buffer=args.stream_shuffle_buffer,
        stream_workers=args.stream_workers,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_iql.py -k "stream" -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full IQL module**

Run: `uv run --project ai pytest ai/tests/test_iql.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_iql.py ai/tests/test_iql.py
git commit -m "feat(iql): --stream memory-bounded training via StreamingReplayBuffer"
```

---

## Task 6: Wire `--stream-training` into the loop

**Files:**
- Modify: `ai/src/fh_mahjong_ai/selfplay_loop.py`, `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py`
- Test: `ai/tests/test_selfplay_loop.py`

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_selfplay_loop.py` (reuse its `_tiny_env_model`, `save_checkpoint`, `PolicyValueNet`, `LoopConfig`, `run_loop`):

```python
def test_run_loop_streaming_training(tmp_path: Path):
    env, model_cfg = _tiny_env_model()
    init = tmp_path / "init.pt"
    save_checkpoint(init, PolicyValueNet(env, model_cfg))

    cfg = LoopConfig(
        run_dir=tmp_path / "run",
        fixed_init=str(init),
        base_data=[],
        initial_best=str(init),
        iterations=1,
        episodes_per_iter=3,
        screen_seeds=2,
        confirm_seeds=2,
        epochs=1,
        batch_size=4,
        match_mode="classic",
        device="cpu",
        bridge_kind="mock",
        max_steps_per_episode=None,
        seat_policy_template=["0=random", "1=random", "2=random", "3=random"],
        stream_training=True,
        stream_shuffle_buffer=8,
        stream_workers=0,
    )
    ledger = run_loop(cfg, env, model_cfg)
    assert ledger.iteration == 1
    assert (cfg.run_dir / "ledger.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k streaming_training -q`
Expected: FAIL with `TypeError` for unexpected `stream_training`.

- [ ] **Step 3: Add config fields and pass-through**

In `ai/src/fh_mahjong_ai/selfplay_loop.py`:

1. Add to `LoopConfig` (near `generation` fields, before `thresholds`):

```python
    stream_training: bool = False
    stream_shuffle_buffer: int = 50000
    stream_workers: int = 2
```

2. In `run_iteration`, in the `train_iql(...)` call, add:

```python
        stream=config.stream_training,
        stream_shuffle_buffer=config.stream_shuffle_buffer,
        stream_workers=config.stream_workers,
```

In `ai/src/fh_mahjong_ai/scripts/selfplay_loop.py`:

3. Add CLI args (near the other loop flags):

```python
    parser.add_argument("--stream-training", action="store_true")
    parser.add_argument("--stream-shuffle-buffer", type=int, default=50000)
    parser.add_argument("--stream-workers", type=int, default=2)
```

4. Pass them into the `LoopConfig(...)` construction:

```python
        stream_training=args.stream_training,
        stream_shuffle_buffer=args.stream_shuffle_buffer,
        stream_workers=args.stream_workers,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -k streaming_training -q`
Expected: PASS.

- [ ] **Step 5: Run the full loop module**

Run: `uv run --project ai pytest ai/tests/test_selfplay_loop.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/selfplay_loop.py ai/src/fh_mahjong_ai/scripts/selfplay_loop.py ai/tests/test_selfplay_loop.py
git commit -m "feat(selfplay-loop): --stream-training opt-in memory-bounded training"
```

---

## Task 7: Docs + full-suite gate

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Document the module and flags**

In `ai/AGENTS.md`, add a Key Files bullet near `selfplay_loop.py`:

```markdown
- **src/fh_mahjong_ai/streaming_data.py** — Memory-bounded streaming replay for IQL: `build_shard_index`, a PyTorch `TransitionIterableDataset` (per-epoch shard shuffle + bounded shuffle buffer, multi-worker shard partitioning), `collate_transitions`, and `StreamingReplayBuffer` (same `.sample`/`__len__` as `ArrayReplayBuffer`, backed by a `DataLoader`). Lets `fh-mj-train-iql --stream` / `fh-mj-selfplay-loop --stream-training` train on datasets larger than RAM; one epoch sees every row once. Reuses `buffer.train_batch_from_arrays` so streamed and in-memory batches are identical. Does not support the pairwise/risk-trace auxiliary paths (raises if combined).
```

Add a tests bullet:

```markdown
- **tests/test_streaming_data.py** — Tests for the shard index, epoch completeness (every row once, single- and multi-worker), in-memory-vs-streaming batch equivalence, the `.sample()` epoch-wrap contract, and the `--stream` pairwise scope guard.
```

- [ ] **Step 2: Run the full Python suite**

Run: `uv run --project ai pytest ai/tests -q`
Expected: all PASS.

- [ ] **Step 3: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document streaming_data module and --stream flags"
```

---

## Self-Review Notes

- **Spec coverage:** `IterableDataset`+`DataLoader` (Tasks 3-4); every-row-per-epoch (Task 3 + test); same `.sample`/`__len__` interface (Task 4); opt-in `--stream`/`--stream-training` default off (Tasks 5-6); scope guard error (Task 5); per-row reconstruction reuse via `train_batch_from_arrays` (Task 1) → equivalence test (Task 4); multi-worker partitioning (Task 3); memory bounded by shuffle buffer (design, exercised with `shuffle_buffer` < dataset in tests).
- **No Go changes, no storage-format change, no IQL-math change** — only buffer construction and a DRY refactor.
- **Type consistency:** `train_batch_from_arrays(arrays, indices, reward_shaping, placement_values)` is defined in Task 1 and called identically in `ArrayReplayBuffer.sample` and `collate_transitions` (Task 3); `StreamingReplayBuffer(data_paths, batch_size, shuffle_buffer, num_workers, seed, reward_shaping, placement_values)` defined in Task 4 and constructed with the same kwargs in Task 5; loop fields `stream_training`/`stream_shuffle_buffer`/`stream_workers` consistent across Tasks 5-6.
- **Manifest key risk (flagged in Task 2):** if `write_transitions_npz_shards`'s manifest uses a different per-shard count key than `"transitions"`, Task 2 Step 3 says to adjust — verify against `storage.py` when implementing.
