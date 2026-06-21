from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.targeted_branch_cf_diagnostics import targeted_branch_cf_diagnostics


def test_targeted_branch_cf_diagnostics_reports_left_right_action_quality(tmp_path: Path) -> None:
    shard_dir = tmp_path / "targeted"
    shard_dir.mkdir()
    np.savez(
        shard_dir / "transitions-00000.npz",
        pairwise_preferred_action_ids=np.asarray([8, 9, 10], dtype=np.int64),
        pairwise_avoided_action_ids=np.asarray([1, 2, 3], dtype=np.int64),
        pairwise_reward_delta_targets=np.asarray([0.5, 0.25, 1.0], dtype=np.float32),
        action_ids=np.asarray([1, 2, 3], dtype=np.int64),
        branch_left_action_ids=np.asarray([8, 2, 5], dtype=np.int64),
        branch_right_action_ids=np.asarray([1, 9, 10], dtype=np.int64),
        branch_target_actual_deltas=np.asarray([-0.5, -0.25, -1.0], dtype=np.float32),
        branch_target_predicted_deltas=np.asarray([0.2, 0.1, -0.1], dtype=np.float32),
    )
    (shard_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "npz_shards",
                "compressed": False,
                "shard_size": 3,
                "transitions": 3,
                "shards": [{"path": "transitions-00000.npz", "transitions": 3}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = targeted_branch_cf_diagnostics([shard_dir])

    assert report["combined"]["rows"] == 3
    assert report["combined"]["left_policy"]["preferred_match_count"] == 1
    assert report["combined"]["left_policy"]["avoided_match_count"] == 1
    assert report["combined"]["right_policy"]["preferred_match_count"] == 2
    assert report["combined"]["right_policy"]["avoided_match_count"] == 1
    dataset = report["datasets"][0]
    assert dataset["target_actual_delta"]["count"] == 3
    assert dataset["right_policy"]["preferred_match_reward_gap"]["count"] == 2
