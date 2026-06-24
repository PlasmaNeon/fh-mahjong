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


def test_iterable_dataset_rows_own_their_data_not_shard_views(tmp_path: Path):
    # Regression: rows must be copies, not views into the loaded shard array,
    # or buffered rows keep whole shards alive and a worker OOMs.
    from fh_mahjong_ai.streaming_data import TransitionIterableDataset

    d = _make_shards(tmp_path, 8, "a", start=0)
    ds = TransitionIterableDataset([d], shuffle_buffer=2, seed=0)
    for s in ds:
        assert s["planes"].base is None  # owns its data (copy), not a shard view
        assert s["next_planes"].base is None
        break
