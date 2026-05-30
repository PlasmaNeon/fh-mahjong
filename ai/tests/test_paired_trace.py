from __future__ import annotations

import numpy as np

from fh_mahjong_ai.paired_trace import first_divergence_index, summarize_observation, summarize_trace_pairs
from fh_mahjong_ai.types import Observation


def test_first_divergence_index_detects_action_change() -> None:
    assert first_divergence_index([5, 6, 7], [5, 8, 7]) == 1


def test_first_divergence_index_detects_length_change() -> None:
    assert first_divergence_index([5, 6], [5, 6, 7]) == 2
    assert first_divergence_index([5, 6], [5, 6]) is None


def test_summarize_observation_reports_legal_family_rates_and_scalars() -> None:
    mask = np.zeros(204, dtype=np.int8)
    mask[0] = 1
    mask[5] = 1
    mask[47] = 1
    scalars = np.zeros(50, dtype=np.float32)
    scalars[25] = 0.5
    scalars[48] = 0.25
    observation = Observation(
        seat=2,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=scalars,
        action_mask=mask,
        metadata={"decision_index": 9, "phase": 2, "active_player": 2},
    )

    summary = summarize_observation(observation)

    assert summary["decision_index"] == 9
    assert summary["legal_action_count"] == 3
    assert summary["legal_action_family_rates"] == {
        "discard": 1 / 3,
        "pass": 1 / 3,
        "pon": 1 / 3,
    }
    assert summary["scalars"]["overall_shanten"] == 0.5
    assert summary["scalars"]["self_bust_margin"] == 0.25


def test_summarize_trace_pairs_handles_terminal_length_divergence() -> None:
    report = summarize_trace_pairs(
        [
            {
                "left_reward": 0.0,
                "right_reward": 1.0,
                "reward_delta": 1.0,
                "first_divergence_index": 2,
                "first_divergence": {
                    "left": {
                        "action_family": "discard",
                        "action_label": "discard 1m",
                        "observation": {"scalars": {"overall_shanten": 0.1}},
                    },
                    "right": None,
                },
            }
        ]
    )

    assert report["summary"]["divergence_action_family_pairs"] == {"discard->missing": 1}


def test_summarize_trace_pairs_reports_high_risk_cases() -> None:
    report = summarize_trace_pairs(
        [
            {
                "seed": 534005,
                "seat": 0,
                "anchor_reward": -0.9,
                "candidate_reward": -1.4,
                "reward_delta": -0.5,
                "first_divergence_index": 12,
                "first_divergence": {
                    "left": {"action_id": 0, "action_label": "pass", "action_family": "pass"},
                    "right": {
                        "action_id": 47,
                        "action_label": "pon 1m",
                        "action_family": "pon",
                        "decision_index": 173,
                        "observation": {"scalars": {"rank_score": 0.5}},
                    },
                },
            }
        ],
        left_label="anchor",
        right_label="candidate",
        large_loss_threshold=-1.0,
    )

    summary = report["summary"]
    assert len(summary["candidate_large_loss_cases"]) == 1
    assert len(summary["new_candidate_large_loss_cases"]) == 1
    assert summary["candidate_large_loss_cases"][0]["candidate_action_label"] == "pon 1m"
    assert summary["candidate_large_loss_cases"][0]["decision_index"] == 173
    assert summary["worst_reward_delta_cases"][0]["seed"] == 534005
