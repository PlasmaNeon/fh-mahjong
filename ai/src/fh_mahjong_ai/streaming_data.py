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
