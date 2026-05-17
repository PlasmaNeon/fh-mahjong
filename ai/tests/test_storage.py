from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.storage import (
    ShardedTransitionWriter,
    iter_observation_action_batches,
    read_transition_arrays,
    read_transitions,
    write_transitions_jsonl,
    write_transitions_npz_shards,
)
from fh_mahjong_ai.types import Observation, Transition


def _observation(seed: int, seat: int = 0) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:12] = 1
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=rng.standard_normal(42).astype(np.float32),
        action_mask=mask,
    )


def _transitions(count: int = 5) -> list[Transition]:
    transitions = []
    for index in range(count):
        transitions.append(
            Transition(
                observation=_observation(index, seat=index % 4),
                action_id=5 + index,
                rewards=np.asarray([1, -1, 0, 0], dtype=np.float32),
                next_observation=_observation(index + 100, seat=(index + 1) % 4),
                terminated=index == count - 1,
                truncated=False,
                info={
                    "episode_index": index // 2,
                    "terminal_rewards": np.asarray([2, -2, 0, 0], dtype=np.float32),
                    "terminal_outcome": {
                        "is_draw": False,
                        "winner_seat": 0,
                        "win_type": 6,
                        "discarder_seat": 1,
                        "total_score": 4,
                        "payouts": [],
                    },
                },
            )
        )
    return transitions


def test_read_transitions_auto_supports_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "data.jsonl"
    write_transitions_jsonl(path, _transitions(3))

    loaded = read_transitions(path)

    assert len(loaded) == 3
    assert loaded[1].action_id == 6


def test_npz_shards_round_trip(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    source = _transitions(5)
    manifest = write_transitions_npz_shards(output_dir, source, shard_size=2)

    loaded = read_transitions(output_dir)
    manifest_payload = json.loads((output_dir / "manifest.json").read_text())

    assert manifest["transitions"] == 5
    assert [shard["transitions"] for shard in manifest_payload["shards"]] == [2, 2, 1]
    assert len(loaded) == 5
    assert loaded[4].terminated
    assert loaded[3].info["episode_index"] == 1
    np.testing.assert_allclose(loaded[0].info["terminal_rewards"], [2, -2, 0, 0])
    assert loaded[0].info["terminal_outcome"]["winner_seat"] == 0
    assert loaded[0].info["terminal_outcome"]["win_type"] == 6
    np.testing.assert_allclose(loaded[2].observation.planes, source[2].observation.planes)


def test_incremental_npz_writer_flushes_across_calls(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"

    writer = ShardedTransitionWriter(output_dir, shard_size=3)
    writer.write_many(_transitions(2))
    writer.write_many(_transitions(3))
    manifest = writer.close()

    loaded = read_transitions(output_dir)

    assert manifest["transitions"] == 5
    assert [shard["transitions"] for shard in manifest["shards"]] == [3, 2]
    assert len(loaded) == 5
    assert (output_dir / "manifest.json").exists()


def test_read_transition_arrays_can_select_keys(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    write_transitions_npz_shards(output_dir, _transitions(5), shard_size=2)

    arrays = read_transition_arrays(output_dir, keys=("planes", "action_ids"))

    assert set(arrays) == {"planes", "action_ids"}
    assert arrays["planes"].shape == (5, 39, 42, 1)
    assert arrays["action_ids"].tolist() == [5, 6, 7, 8, 9]


def test_iter_observation_action_batches_reads_npz_without_transition_objects(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    write_transitions_npz_shards(output_dir, _transitions(5), shard_size=4)

    batches = list(iter_observation_action_batches(output_dir, batch_size=3))

    assert [batch["action_ids"].shape[0] for batch in batches] == [3, 1, 1]
    assert batches[0]["planes"].shape == (3, 39, 42, 1)
    assert batches[0]["scalars"].shape == (3, 42)
    assert batches[0]["action_mask"].shape == (3, 204)
