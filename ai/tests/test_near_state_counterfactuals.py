from __future__ import annotations

import numpy as np
import pytest

from fh_mahjong_ai.near_state_counterfactuals import (
    action_mask_jaccard,
    extract_near_state_discard_cases,
    visible_scalar_distance,
)


def _step(action_id: int, action_mask: list[int], decision_index: int = 10) -> dict:
    scalars = {
        "overall_shanten": 0.25,
        "standard_shanten": 0.25,
        "ukeire": 0.5,
        "visible_score_potential": 0.4,
        "large_loss_margin": 0.7,
        "self_bust_margin": 0.8,
        "hand_progress": 0.3,
        "hands_remaining": 0.7,
        "public_threat": 0.2,
    }
    return {
        "decision_index": decision_index,
        "action_id": action_id,
        "action_label": f"discard {action_id}",
        "action_family": "discard",
        "observation": {
            "scalars": scalars,
            "arrays": {
                "planes": np.zeros((2, 3, 1), dtype=np.float32).tolist(),
                "scalars": np.zeros(58, dtype=np.float32).tolist(),
                "action_mask": action_mask,
            },
        },
    }


def test_visible_scalar_distance_reports_l1_and_linf() -> None:
    distance = visible_scalar_distance(
        {"overall_shanten": 0.1, "ukeire": 0.4},
        {"overall_shanten": 0.3, "ukeire": 0.5},
        scalar_names=("overall_shanten", "ukeire"),
    )

    assert distance["count"] == 2
    assert distance["l1_mean"] == pytest.approx(0.15)
    assert distance["linf"] == pytest.approx(0.2)


def test_action_mask_jaccard_compares_legal_sets() -> None:
    assert action_mask_jaccard(_step(2, [1, 0, 1]), _step(2, [1, 1, 1])) == 2 / 3


def test_extract_near_state_discard_cases_accepts_cross_legal_later_case() -> None:
    mask = [0] * 8
    mask[2] = 1
    mask[5] = 1
    report = {
        "left_label": "anchor",
        "right_label": "candidate",
        "pairs": [
            {
                "seed": 100,
                "seat": 1,
                "anchor_reward": 0.4,
                "candidate_reward": -1.2,
                "anchor_outcome": {"discarder_seat": -1},
                "candidate_outcome": {"discarder_seat": 1},
                "first_divergence_index": 3,
                "first_divergence": {
                    "left": _step(2, mask, decision_index=8),
                    "right": _step(5, mask, decision_index=8),
                },
                "divergences": [
                    {
                        "divergence_index": 3,
                        "left": _step(2, mask, decision_index=8),
                        "right": _step(5, mask, decision_index=8),
                    },
                    {
                        "divergence_index": 6,
                        "left": _step(2, mask, decision_index=12),
                        "right": _step(5, mask, decision_index=12),
                    },
                ],
            }
        ],
    }

    extracted = extract_near_state_discard_cases(report, divergence_source="later", large_loss_threshold=-1.0)

    assert extracted["summary"]["cases"] == 1
    assert extracted["summary"]["high_risk_cases"] == 1
    case = extracted["cases"][0]
    assert case["source"] == "later_aligned_disagreement"
    assert case["preferred_action_id"] == 2
    assert case["avoided_action_id"] == 5
    assert case["action_mask_jaccard"] == 1.0


def test_extract_near_state_discard_cases_rejects_cross_illegal_action() -> None:
    left_mask = [0] * 8
    left_mask[2] = 1
    right_mask = [0] * 8
    right_mask[5] = 1
    report = {
        "left_label": "anchor",
        "right_label": "candidate",
        "pairs": [
            {
                "seed": 100,
                "seat": 1,
                "anchor_reward": 0.4,
                "candidate_reward": -1.2,
                "anchor_outcome": {},
                "candidate_outcome": {},
                "first_divergence_index": 3,
                "first_divergence": {
                    "left": _step(2, left_mask),
                    "right": _step(5, right_mask),
                },
                "divergences": [
                    {
                        "divergence_index": 6,
                        "left": _step(2, left_mask),
                        "right": _step(5, right_mask),
                    }
                ],
            }
        ],
    }

    extracted = extract_near_state_discard_cases(report, divergence_source="later")

    assert extracted["summary"]["cases"] == 0
    assert extracted["summary"]["skipped"]["cross_illegal_action"] == 1
