from __future__ import annotations

import json
from pathlib import Path

from fh_mahjong_ai.checkpoint_manifest import load_checkpoint_manifest, resolve_checkpoint_path


def _manifest(path: Path) -> Path:
    payload = {
        "schema_version": 1,
        "current_reward_trained_best": {
            "id": "reward",
            "method": "iql",
            "checkpoint_path": "/tmp/reward.pt",
        },
        "fallbacks": [
            {
                "id": "bc",
                "method": "bc",
                "checkpoint_path": "/tmp/bc.pt",
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_checkpoint_manifest_and_resolve_ids(tmp_path: Path) -> None:
    manifest = load_checkpoint_manifest(_manifest(tmp_path / "best.json"))

    assert manifest.current.id == "reward"
    assert resolve_checkpoint_path(manifest) == Path("/tmp/reward.pt")
    assert resolve_checkpoint_path(manifest, checkpoint_id="fallback") == Path("/tmp/bc.pt")
    assert resolve_checkpoint_path(manifest, checkpoint_id="bc") == Path("/tmp/bc.pt")


def test_checkpoint_override_wins(tmp_path: Path) -> None:
    manifest = load_checkpoint_manifest(_manifest(tmp_path / "best.json"))

    assert resolve_checkpoint_path(manifest, checkpoint_override=Path("/override.pt")) == Path("/override.pt")
