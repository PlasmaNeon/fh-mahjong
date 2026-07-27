from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.storage import (
    ShardedTransitionWriter,
    iter_observation_action_batches,
    load_checkpoint,
    read_transition_arrays,
    read_transitions,
    save_checkpoint,
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
    assert loaded[4].info["steps_to_done"] == 0
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


def test_read_transition_arrays_can_limit_rows(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    write_transitions_npz_shards(output_dir, _transitions(5), shard_size=2)

    arrays = read_transition_arrays(output_dir, keys=("planes", "action_ids"), limit=3)

    assert arrays["planes"].shape == (3, 39, 42, 1)
    assert arrays["action_ids"].tolist() == [5, 6, 7]


def test_npz_shards_include_steps_to_done(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    transitions = _transitions(3)
    for index, transition in enumerate(transitions):
        transition.info["episode_index"] = 7
        transition.terminated = index == 2
    write_transitions_npz_shards(output_dir, transitions, shard_size=3)

    arrays = read_transition_arrays(output_dir, keys=("steps_to_done",))

    assert arrays["steps_to_done"].tolist() == [2, 1, 0]


def test_iter_observation_action_batches_reads_npz_without_transition_objects(tmp_path: Path) -> None:
    output_dir = tmp_path / "npz"
    write_transitions_npz_shards(output_dir, _transitions(5), shard_size=4)

    batches = list(iter_observation_action_batches(output_dir, batch_size=3))

    assert [batch["action_ids"].shape[0] for batch in batches] == [3, 1, 1]
    assert batches[0]["planes"].shape == (3, 39, 42, 1)
    assert batches[0]["scalars"].shape == (3, 42)
    assert batches[0]["action_mask"].shape == (3, 204)


# ---------------------------------------------------------------------------
# Adversarial review round 8
# ---------------------------------------------------------------------------
#
# Finding (high): `save_checkpoint` wrote directly to its target path via a
# bare `torch.save(payload, path)` -- a crash (OOM kill, box preemption,
# power loss) mid-serialization leaves a torn/truncated file at that exact
# path. Every `iter_*.pt` this project writes (oracle.py's per-iteration
# checkpoints, ppo.py, and every train_*.py script) goes through this
# function, so a torn file could land at any of those paths. Fixed
# centrally (all callers pass a plain `path`; none read the destination
# path mid-write or otherwise depend on the old non-atomic behavior) by
# writing to a `.tmp` sibling and `os.replace`-ing it into place, mirroring
# oracle.py's existing `_atomic_torch_save` for `train_state.pt`.
def test_save_checkpoint_is_atomic_no_tmp_left_behind(tmp_path: Path, monkeypatch) -> None:
    import fh_mahjong_ai.storage as storage

    path = tmp_path / "iter_001.pt"
    model = torch.nn.Linear(4, 2)
    replace_calls = []
    real_replace = storage.os.replace

    def recording_replace(src, dst):
        # The final `os.replace` destination must already be a fully
        # written file at the time of the call -- i.e. `torch.save` targets
        # a tmp sibling, never `path` itself -- otherwise a crash between
        # `torch.save` and `os.replace` could never leave `path` untouched.
        assert Path(src) != Path(dst)
        assert Path(src).exists()
        replace_calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", recording_replace)

    save_checkpoint(path, model, step=3)

    assert replace_calls == [(path.with_name(path.name + ".tmp"), path)]
    assert path.exists()
    assert not (tmp_path / (path.name + ".tmp")).exists()
    assert list(tmp_path.glob("*.tmp")) == []
    step = load_checkpoint(path, torch.nn.Linear(4, 2))
    assert step == 3
