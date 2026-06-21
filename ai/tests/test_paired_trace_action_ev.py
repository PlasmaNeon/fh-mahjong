from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.paired_trace_action_ev import build_paired_trace_action_ev_arrays


def _step(action_id: int, family: str, decision_index: int = 17) -> dict:
    return {
        "action_id": action_id,
        "action_label": f"{family} {action_id}",
        "action_family": family,
        "decision_index": decision_index,
        "observation": {
            "arrays": {
                "planes": np.full((39, 42, 1), float(action_id), dtype=np.float32).tolist(),
                "scalars": np.full(58, 0.25, dtype=np.float32).tolist(),
                "action_mask": np.ones(204, dtype=np.int8).tolist(),
            }
        },
    }


def test_build_paired_trace_action_ev_arrays_uses_actual_reward_winner(tmp_path: Path) -> None:
    report = {
        "left_label": "anchor",
        "right_label": "candidate",
        "pairs": [
            {
                "seed": 123,
                "seat": 2,
                "anchor_reward": -0.4,
                "candidate_reward": 0.3,
                "first_divergence_index": 5,
                "first_divergence": {
                    "left": _step(8, "discard"),
                    "right": _step(9, "discard"),
                },
                "pre_divergence_context": {
                    "trace_context_available": 1.0,
                    "trace_divergence_step_2000": 0.5,
                },
            }
        ],
    }
    report_path = tmp_path / "trace.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    arrays, metadata = build_paired_trace_action_ev_arrays(report_path)

    assert metadata["rows"] == 1
    assert metadata["preferred_policy_counts"] == {"candidate": 1}
    assert arrays["pairwise_preferred_action_ids"].tolist() == [9]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [8]
    np.testing.assert_allclose(arrays["branch_preferred_rewards"], np.asarray([0.3], dtype=np.float32))
    np.testing.assert_allclose(arrays["branch_avoided_rewards"], np.asarray([-0.4], dtype=np.float32))
    np.testing.assert_allclose(arrays["pairwise_reward_delta_targets"], np.asarray([0.7], dtype=np.float32))
    assert arrays["episode_index"].tolist() == [123]
    assert arrays["decision_indices"].tolist() == [17]
    assert arrays["branch_left_action_ids"].tolist() == [8]
    assert arrays["branch_right_action_ids"].tolist() == [9]
    np.testing.assert_allclose(arrays["branch_target_actual_deltas"], np.asarray([0.7], dtype=np.float32))

    context_arrays, context_metadata = build_paired_trace_action_ev_arrays(
        report_path,
        include_trajectory_context=True,
    )
    assert context_metadata["include_trajectory_context"] is True
    assert context_arrays["scalars"].shape[1] > arrays["scalars"].shape[1]
    assert context_arrays["scalars"][0, arrays["scalars"].shape[1]] == 1.0


def test_build_paired_trace_action_ev_arrays_can_filter_action_family(tmp_path: Path) -> None:
    report = {
        "pairs": [
            {
                "seed": 1,
                "seat": 0,
                "anchor_reward": 0.5,
                "candidate_reward": -0.1,
                "first_divergence_index": 1,
                "first_divergence": {"left": _step(5, "discard"), "right": _step(80, "pon")},
            }
        ]
    }
    report_path = tmp_path / "trace.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(ValueError, match="no paired-trace action-EV rows"):
        build_paired_trace_action_ev_arrays(report_path, action_family="discard")
