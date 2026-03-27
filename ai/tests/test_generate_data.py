from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.generate_data import generate_dataset


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
    assert stats["episodes"] == 2
    assert stats["transitions"] > 0

    # Verify JSONL is loadable
    lines = output.read_text().strip().split("\n")
    assert len(lines) == stats["transitions"]
    first = json.loads(lines[0])
    assert "observation" in first
    assert "action_id" in first
