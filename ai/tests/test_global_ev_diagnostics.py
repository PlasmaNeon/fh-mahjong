from __future__ import annotations

import numpy as np
import pytest
import torch
from torch import nn

from fh_mahjong_ai.global_ev_diagnostics import score_paired_trace_global_ev
from fh_mahjong_ai.global_ev_diagnostics import action_ev_branch_cf_calibration


class SumScalarEV(nn.Module):
    def forward(self, planes: torch.Tensor, scalars: torch.Tensor) -> torch.Tensor:
        del planes
        return scalars[:, 0]


class ActionIdEV(nn.Module):
    def forward(self, planes: torch.Tensor, scalars: torch.Tensor, action_ids: torch.Tensor) -> torch.Tensor:
        del planes, scalars
        return action_ids.to(dtype=torch.float32) / 10.0


def _step(action_id: int, family: str, scalar0: float) -> dict:
    scalars = np.zeros(58, dtype=np.float32)
    scalars[0] = scalar0
    scalars[46] = 0.25
    return {
        "action_id": action_id,
        "action_label": f"{family} {action_id}",
        "action_family": family,
        "decision_index": 17,
        "observation": {
            "arrays": {
                "planes": np.zeros((39, 42, 1), dtype=np.float32).tolist(),
                "scalars": scalars.tolist(),
                "action_mask": np.ones(204, dtype=np.int8).tolist(),
            },
            "scalars": {"leader_pressure": float(scalars[46])},
        },
    }


def test_score_paired_trace_global_ev_reports_delta_accuracy() -> None:
    report = {
        "pairs": [
            {
                "seed": 1,
                "seat": 0,
                "anchor_reward": 0.4,
                "candidate_reward": -0.6,
                "first_divergence_index": 3,
                "first_divergence": {
                    "left": _step(5, "discard", 0.8),
                    "right": _step(0, "pass", 0.1),
                },
            },
            {
                "seed": 2,
                "seat": 1,
                "anchor_reward": -0.2,
                "candidate_reward": 0.3,
                "first_divergence_index": 4,
                "first_divergence": {
                    "left": _step(6, "discard", -0.1),
                    "right": _step(47, "pon", 0.4),
                },
            },
        ]
    }

    diagnostics = score_paired_trace_global_ev(
        report,
        SumScalarEV(),
        left_label="anchor",
        right_label="candidate",
        guard_margins=[0.0],
    )

    assert diagnostics["scoreable_divergences"] == 2
    assert diagnostics["sign_accuracy"] == 1.0
    assert diagnostics["harmful_predicted_harmful_rate"] == 1.0
    assert diagnostics["helpful_predicted_helpful_rate"] == 1.0
    assert diagnostics["guard_preflight"]["0.0000"]["allowed_count"] == 1
    assert diagnostics["guard_preflight"]["0.0000"]["harmful_block_rate"] == 1.0
    assert diagnostics["by_family_pair"]["discard->pass"]["count"] == 1
    assert diagnostics["worst_mismatches"][0]["scalars"]["leader_pressure"] == pytest.approx(0.25)
    assert diagnostics["worst_mismatches"][0]["left_action_id"] in {5, 6}
    assert diagnostics["worst_mismatches"][0]["right_action_id"] in {0, 47}
    assert diagnostics["worst_mismatches"][0]["left_action_family"] == "discard"
    assert diagnostics["worst_mismatches"][0]["right_action_family"] in {"pass", "pon"}


def test_score_paired_trace_action_global_ev_can_rank_same_state_actions() -> None:
    report = {
        "pairs": [
            {
                "seed": 1,
                "seat": 0,
                "anchor_reward": 0.0,
                "candidate_reward": 0.5,
                "first_divergence_index": 3,
                "first_divergence": {
                    "left": _step(1, "discard", 0.0),
                    "right": _step(9, "discard", 0.0),
                },
            }
        ]
    }

    diagnostics = score_paired_trace_global_ev(
        report,
        ActionIdEV(),
        left_label="anchor",
        right_label="candidate",
        action_conditioned=True,
        guard_margins=[0.0],
    )

    assert diagnostics["scoreable_divergences"] == 1
    assert diagnostics["sign_accuracy"] == 1.0
    assert diagnostics["helpful_predicted_helpful_rate"] == 1.0
    assert diagnostics["guard_preflight"]["0.0000"]["allowed_count"] == 1


def test_score_paired_trace_global_ev_requires_observation_arrays() -> None:
    report = {
        "pairs": [
            {
                "seed": 1,
                "seat": 0,
                "anchor_reward": 0.4,
                "candidate_reward": -0.6,
                "first_divergence": {
                    "left": {"action_id": 5, "action_family": "discard", "observation": {"scalars": {}}},
                    "right": {"action_id": 0, "action_family": "pass", "observation": {"scalars": {}}},
                },
            }
        ]
    }

    with pytest.raises(ValueError, match="include-observation-arrays"):
        score_paired_trace_global_ev(
            report,
            SumScalarEV(),
            left_label="anchor",
            right_label="candidate",
        )


def test_action_ev_branch_cf_calibration_reports_preferred_rate() -> None:
    arrays = {
        "planes": np.zeros((2, 39, 42, 1), dtype=np.float32),
        "scalars": np.zeros((2, 58), dtype=np.float32),
        "pairwise_preferred_action_ids": np.asarray([9, 1], dtype=np.int64),
        "pairwise_avoided_action_ids": np.asarray([1, 9], dtype=np.int64),
        "branch_preferred_rewards": np.asarray([1.0, 0.5], dtype=np.float32),
        "branch_avoided_rewards": np.asarray([0.0, 0.0], dtype=np.float32),
    }

    report = action_ev_branch_cf_calibration(
        arrays,
        ActionIdEV(),
        guard_margins=[0.0],
    )

    assert report["rows"] == 2
    assert report["preferred_rate"] == 0.5
    assert report["reward_gap"]["mean"] == pytest.approx(0.75)
    assert report["guard_preflight"]["0.0000"]["allowed_count"] == 1
