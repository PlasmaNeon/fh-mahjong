from __future__ import annotations

import json
from functools import partial
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import numpy as np
from torch.utils.data import DataLoader, IterableDataset, get_worker_info

from .buffer import _DEFAULT_PLACEMENT_VALUES, train_batch_from_arrays
from .storage import SHARDED_TRANSITIONS_MANIFEST
from .types import TrainBatch


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
                    # Copy each row so it does not retain a view into the full shard
                    # array; otherwise buffered rows keep entire shards alive and
                    # memory grows unbounded (worker OOM).
                    row = {k: np.array(cols[k][int(r)], copy=True) for k in present}
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
