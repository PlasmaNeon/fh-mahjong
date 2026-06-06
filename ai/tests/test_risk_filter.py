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
                            "left": {
                                "decision_index": 77,
                                "action_id": 46,
                                "action_label": "pass",
                            },
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
            baseline_action_id=46,
            baseline_action_label="pass",
            reward=-1.25,
            baseline_reward=-0.5,
            reward_delta=-0.75,
            source="paired_trace",
            tags=("new_right_large_loss", "right_large_loss"),
        )
    ]


def test_load_risk_cases_from_paired_trace_report_extracts_counterfactual_labels(tmp_path: Path) -> None:
    report_path = tmp_path / "trace.json"
    report_path.write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_reward": -0.5,
                        "reward_delta": -0.75,
                        "anchor_outcome": {"discarder_seat": -1},
                        "candidate_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 46,
                                "action_label": "pass",
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                            },
                        },
                    },
                    {
                        "seed": 101,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_reward": 0.24,
                        "reward_delta": -0.01,
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {"decision_index": 77, "action_id": 46, "action_label": "pass"},
                            "right": {"decision_index": 77, "action_id": 5, "action_label": "discard 1m"},
                        },
                    },
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_risk_cases_from_paired_trace_reports(
        [report_path],
        large_loss_threshold=-1.0,
        include_large_losses=False,
        include_new_large_losses=False,
        include_counterfactual_labels=True,
        min_counterfactual_reward_gap=0.1,
    )

    assert cases == [
        RiskCase(
            seed=100,
            seat=2,
            decision_index=77,
            action_id=5,
            action_label="discard 1m",
            baseline_action_id=46,
            baseline_action_label="pass",
            reward=-0.5,
            baseline_reward=0.25,
            reward_delta=-0.75,
            source="paired_trace_counterfactual",
            tags=("avoided_deal_in", "counterfactual", "new_deal_in", "worse_reward"),
        )
    ]


def test_load_risk_cases_from_paired_trace_report_uses_report_labels(tmp_path: Path) -> None:
    report_path = tmp_path / "trace.json"
    report_path.write_text(
        json.dumps(
            {
                "left_label": "anchor",
                "right_label": "candidate_t054_w075",
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_t054_w075_reward": -0.5,
                        "reward_delta": -0.75,
                        "anchor_outcome": {"discarder_seat": -1},
                        "candidate_t054_w075_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 46,
                                "action_label": "pass",
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                            },
                        },
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    cases = load_risk_cases_from_paired_trace_reports(
        [report_path],
        large_loss_threshold=-1.0,
        include_large_losses=False,
        include_new_large_losses=False,
        include_counterfactual_labels=True,
        min_counterfactual_reward_gap=0.1,
    )

    assert cases == [
        RiskCase(
            seed=100,
            seat=2,
            decision_index=77,
            action_id=5,
            action_label="discard 1m",
            baseline_action_id=46,
            baseline_action_label="pass",
            reward=-0.5,
            baseline_reward=0.25,
            reward_delta=-0.75,
            source="paired_trace_counterfactual",
            tags=("avoided_deal_in", "counterfactual", "new_deal_in", "worse_reward"),
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
    assert arrays["risk_case_matches"].tolist() == [False, False, True, False]
    assert arrays["pairwise_weights"].tolist() == [0.0, 0.0, 0.0, 0.0]


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


def test_apply_risk_case_weights_adds_pairwise_preference_labels() -> None:
    arrays = {
        "episode_index": np.asarray([5, 5, 5], dtype=np.int64),
        "seats": np.asarray([2, 2, 2], dtype=np.int16),
        "decision_indices": np.asarray([76, 77, 78], dtype=np.int64),
        "action_ids": np.asarray([46, 47, 48], dtype=np.int64),
    }
    case = RiskCase(
        seed=105,
        seat=2,
        decision_index=77,
        action_id=47,
        baseline_action_id=46,
    )

    report = apply_risk_case_weights(arrays, [case], weight=1.0, dataset_start_seed=100)

    assert arrays["sample_weights"].tolist() == [1.0, 1.0, 1.0]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [-1, 46, -1]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [-1, 47, -1]
    assert arrays["pairwise_weights"].tolist() == [0.0, 1.0, 0.0]
    assert arrays["pairwise_reward_delta_targets"].tolist() == [0.0, 0.0, 0.0]
    assert arrays["risk_case_matches"].tolist() == [False, True, False]
    assert report.pairwise_cases == 1
    assert report.pairwise_transitions == 1


def test_apply_risk_case_weights_adds_pairwise_reward_delta_targets() -> None:
    arrays = {
        "episode_index": np.asarray([5], dtype=np.int64),
        "seats": np.asarray([2], dtype=np.int16),
        "decision_indices": np.asarray([77], dtype=np.int64),
        "action_ids": np.asarray([47], dtype=np.int64),
    }
    case = RiskCase(
        seed=105,
        seat=2,
        decision_index=77,
        action_id=47,
        baseline_action_id=46,
        reward=-1.25,
        baseline_reward=-0.5,
    )

    report = apply_risk_case_weights(arrays, [case], weight=1.0, dataset_start_seed=100)

    assert arrays["pairwise_reward_delta_targets"].tolist() == [0.75]
    assert report.pairwise_delta_mean == 0.75
    assert report.pairwise_delta_max == 0.75
