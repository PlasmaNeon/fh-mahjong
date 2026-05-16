from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.generate_data import generate_dataset
from fh_mahjong_ai.storage import read_transitions_jsonl


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
