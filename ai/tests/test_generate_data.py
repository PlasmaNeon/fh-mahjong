from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.bridge import BridgeError
from fh_mahjong_ai.scripts import generate_data
from fh_mahjong_ai.scripts.generate_data import DEFAULT_CHUNK_SIZE, generate_dataset
from fh_mahjong_ai.storage import read_transitions, read_transitions_jsonl


def test_generate_dataset_mock(tmp_path: Path) -> None:
    output = tmp_path / "data.jsonl"
    stats = generate_dataset(
        episodes=2,
        start_seed=1,
        output_path=output,
        bridge_kind="mock",
        bridge_library_path=None,
    )

    assert output.exists()
    manifest = output.with_suffix(".manifest.json")
    assert manifest.exists()
    assert stats["episodes"] == 2
    assert stats["transitions"] > 0
    assert stats["manifest_path"] == str(manifest)

    # Verify JSONL is loadable
    lines = output.read_text().strip().split("\n")
    assert len(lines) == stats["transitions"]
    first = json.loads(lines[0])
    assert "observation" in first
    assert "action_id" in first

    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["schema_version"] == 1
    assert manifest_payload["dataset"]["start_seed"] == 1
    assert manifest_payload["dataset"]["end_seed"] == 2
    assert manifest_payload["dataset"]["transitions"] == stats["transitions"]
    assert manifest_payload["source"]["policy"] == "mock_random_masked"
    assert manifest_payload["environment"]["action_space_size"] == 204


def test_generate_dataset_mock_chunked_uses_global_episode_indices(tmp_path: Path) -> None:
    output = tmp_path / "chunked.jsonl"
    stats = generate_dataset(
        episodes=5,
        start_seed=10,
        output_path=output,
        bridge_kind="mock",
        bridge_library_path=None,
        chunk_size=2,
    )

    transitions = read_transitions_jsonl(output)
    episode_indices = {int(t.info["episode_index"]) for t in transitions}

    assert stats["episodes"] == 5
    assert stats["chunk_size"] == 2
    assert [chunk["episodes"] for chunk in stats["chunks"]] == [2, 2, 1]
    assert episode_indices == {0, 1, 2, 3, 4}

    manifest_payload = json.loads(output.with_suffix(".manifest.json").read_text())
    assert manifest_payload["dataset"]["chunk_size"] == 2
    assert len(manifest_payload["dataset"]["chunks"]) == 3


def test_generate_dataset_auto_chunks_large_episode_counts(tmp_path: Path) -> None:
    # Regression for the silent zero-transition bug: a large episode count must
    # auto-chunk into bounded per-call payloads (never one oversized bridge
    # call) and still yield transitions + a non-empty manifest.
    output = tmp_path / "data.jsonl"
    stats = generate_dataset(
        episodes=40,
        start_seed=1,
        output_path=output,
        bridge_kind="mock",
        bridge_library_path=None,
    )

    # No explicit chunk_size -> capped default, so 40 episodes span 2 chunks.
    assert DEFAULT_CHUNK_SIZE == 20
    assert stats["chunk_size"] == 20
    assert [chunk["episodes"] for chunk in stats["chunks"]] == [20, 20]
    assert stats["transitions"] > 0

    manifest = output.with_suffix(".manifest.json")
    assert manifest.exists()
    manifest_payload = json.loads(manifest.read_text())
    assert manifest_payload["dataset"]["transitions"] == stats["transitions"]
    assert manifest_payload["dataset"]["transitions"] > 0
    assert manifest_payload["dataset"]["episodes"] == 40


def test_generate_dataset_raises_when_chunk_returns_no_transitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulates the oversized-payload bridge failure where the Go bridge return
    # is silently truncated to empty. The generator must fail loudly instead of
    # writing an empty manifest and reporting success.
    class _EmptyBridge:
        def generate_heuristic_trajectories(self, episodes: int, start_seed: int = 1):
            return []

        def close(self) -> None:
            return None

    monkeypatch.setattr(generate_data, "build_bridge", lambda config: _EmptyBridge())

    output = tmp_path / "data.jsonl"
    with pytest.raises(BridgeError, match="0 transitions"):
        generate_dataset(
            episodes=4,
            start_seed=1,
            output_path=output,
            bridge_kind="go",
            bridge_library_path=None,
        )

    # No success manifest should be written for a failed generation.
    assert not output.with_suffix(".manifest.json").exists()


def test_generate_dataset_mock_can_write_npz_shards(tmp_path: Path) -> None:
    output = tmp_path / "npz-data"
    stats = generate_dataset(
        episodes=3,
        start_seed=20,
        output_path=output,
        bridge_kind="mock",
        bridge_library_path=None,
        chunk_size=1,
        output_format="npz_shards",
        shard_size=2,
    )

    transitions = read_transitions(output)
    manifest_payload = json.loads((output / "manifest.json").read_text())
    dataset_manifest = json.loads((tmp_path / "npz-data.manifest.json").read_text())

    assert stats["output_format"] == "npz_shards"
    assert stats["transitions"] == len(transitions)
    assert stats["shard_manifest_path"] == str(output / "manifest.json")
    assert manifest_payload["format"] == "npz_shards"
    assert all(shard["transitions"] <= 2 for shard in manifest_payload["shards"])
    assert dataset_manifest["dataset"]["format"] == "npz_shards"
    assert dataset_manifest["dataset"]["shard_manifest_path"] == str(output / "manifest.json")


def test_seed_mod_4_rule_keeps_exactly_one_seat_per_episode(tmp_path: Path) -> None:
    out = tmp_path / "data.jsonl"
    manifest = tmp_path / "manifest.json"
    stats = generate_dataset(
        episodes=8,
        start_seed=1_300_000,
        output_path=out,
        manifest_path=manifest,
        bridge_kind="mock",
        output_format="jsonl",
        learning_seat_rule="seed-mod-4",
    )
    transitions = read_transitions(out)
    by_episode: dict[int, set[int]] = {}
    for t in transitions:
        by_episode.setdefault(int(t.info["episode_index"]), set()).add(int(t.observation.seat))
    for ep, seats in by_episode.items():
        assert seats == {ep % 4}, (ep, seats)  # seed = 1_300_000 + ep, base = 1_300_000
    m = json.loads(manifest.read_text())
    assert m["dataset"]["learning_seat_rule"] == "seed-mod-4"
    assert m["dataset"]["seat_rule_base_seed"] == 1_300_000
    assert sum(m["dataset"]["per_seat_transitions"].values()) == len(transitions) == stats["transitions"]
    assert m["dataset"]["chunks"][0]["transitions_before_seat_filter"] >= m["dataset"]["chunks"][0]["transitions"]


def test_default_rule_all_is_unchanged(tmp_path: Path) -> None:
    out = tmp_path / "data.jsonl"
    generate_dataset(
        episodes=2,
        start_seed=7,
        output_path=out,
        manifest_path=tmp_path / "m.json",
        bridge_kind="mock",
        output_format="jsonl",
    )
    m = json.loads((tmp_path / "m.json").read_text())
    assert m["dataset"]["learning_seat_rule"] == "all"
    assert "transitions_before_seat_filter" in m["dataset"]["chunks"][0]


def test_unknown_seat_rule_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="learning_seat_rule"):
        generate_dataset(
            episodes=1,
            start_seed=0,
            output_path=tmp_path / "d.jsonl",
            manifest_path=tmp_path / "m.json",
            bridge_kind="mock",
            output_format="jsonl",
            learning_seat_rule="bogus",
        )
