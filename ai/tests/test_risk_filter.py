from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.risk_filter import (
    RiskCase,
    apply_risk_case_weights,
    load_risk_cases_from_paired_trace_reports,
)


def test_load_risk_cases_from_paired_trace_report_extracts_first_divergence(tmp_path: Path) -> None:
    report_path = tmp_path / "trace.json"
    report_path.write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": -0.5,
                        "candidate_reward": -1.25,
                        "reward_delta": -0.75,
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "right": {
                                "decision_index": 77,
                                "action_id": 47,
                                "action_label": "pon 1m",
                            }
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_risk_cases_from_paired_trace_reports([report_path], large_loss_threshold=-1.0)

    assert cases == [
        RiskCase(
            seed=100,
            seat=2,
            decision_index=77,
            action_id=47,
            action_label="pon 1m",
            reward=-1.25,
            baseline_reward=-0.5,
            reward_delta=-0.75,
            source="paired_trace",
            tags=("new_right_large_loss", "right_large_loss"),
        )
    ]


def test_apply_risk_case_weights_matches_seed_seat_decision_action() -> None:
    arrays = {
        "episode_index": np.asarray([0, 0, 5, 5], dtype=np.int64),
        "seats": np.asarray([0, 2, 2, 2], dtype=np.int16),
        "decision_indices": np.asarray([10, 76, 77, 78], dtype=np.int64),
        "action_ids": np.asarray([5, 47, 47, 48], dtype=np.int64),
    }
    case = RiskCase(seed=105, seat=2, decision_index=77, action_id=47)

    report = apply_risk_case_weights(arrays, [case], weight=4.0, dataset_start_seed=100)

    assert arrays["sample_weights"].tolist() == [1.0, 1.0, 4.0, 1.0]
    assert report.matched_cases == 1
    assert report.weighted_transitions == 1
    assert report.matched_by == {"seed_seat_decision": 1}


def test_apply_risk_case_weights_falls_back_to_seed_seat_action_without_decision_indices() -> None:
    arrays = {
        "episode_index": np.asarray([5, 5, 5], dtype=np.int64),
        "seats": np.asarray([2, 2, 1], dtype=np.int16),
        "action_ids": np.asarray([46, 47, 47], dtype=np.int64),
    }
    case = RiskCase(seed=105, seat=2, decision_index=77, action_id=47)

    report = apply_risk_case_weights(arrays, [case], weight=2.5, dataset_start_seed=100)

    assert arrays["sample_weights"].tolist() == [1.0, 2.5, 1.0]
    assert report.matched_by == {"seed_seat_action": 1}
