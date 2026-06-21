from __future__ import annotations

import numpy as np
import pytest
import torch
from torch import nn

from fh_mahjong_ai.paired_trace_q_diagnostics import (
    extract_paired_trace_rank_rows,
    score_paired_trace_q_rank,
)


class TinyRankModel(nn.Module):
    def forward(
        self,
        planes: torch.Tensor,
        scalars: torch.Tensor,
        action_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        del planes, scalars
        logits = torch.full_like(action_mask, -10.0, dtype=torch.float32)
        logits[:, 5] = 1.0
        logits[:, 6] = 3.0
        return logits, torch.zeros(action_mask.shape[0], dtype=torch.float32)

    def q_values(
        self,
        planes: torch.Tensor,
        scalars: torch.Tensor,
        action_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        del planes, scalars
        q_values = torch.full_like(action_mask, -10.0, dtype=torch.float32)
        q_values[:, 5] = 4.0
        q_values[:, 6] = 2.0
        return q_values, torch.zeros(action_mask.shape[0], dtype=torch.float32)


def test_extract_paired_trace_rank_rows_uses_tensor_divergence_arrays() -> None:
    report = _report()

    rows = extract_paired_trace_rank_rows(
        report,
        left_label="anchor",
        right_label="candidate",
        min_reward_gap=0.05,
    )

    assert len(rows) == 1
    assert rows[0]["preferred_policy"] == "anchor"
    assert rows[0]["avoided_policy"] == "candidate"
    assert rows[0]["preferred_action_id"] == 5
    assert rows[0]["avoided_action_id"] == 6
    assert np.asarray(rows[0]["action_mask"]).shape == (204,)


def test_score_paired_trace_q_rank_reports_policy_and_q_disagreement() -> None:
    diagnostics = score_paired_trace_q_rank(
        _report(),
        model=TinyRankModel(),
        left_label="anchor",
        right_label="candidate",
        min_reward_gap=0.05,
    )

    assert diagnostics["rows"] == 1
    assert diagnostics["policy_logits"]["preferred_rate"] == pytest.approx(0.0)
    assert diagnostics["policy_logits"]["misrank_rate"] == pytest.approx(1.0)
    assert diagnostics["q_values"]["preferred_rate"] == pytest.approx(1.0)
    assert diagnostics["q_values"]["misrank_rate"] == pytest.approx(0.0)
    assert diagnostics["argmax"]["policy_avoided_action_rate"] == pytest.approx(1.0)
    assert diagnostics["argmax"]["q_preferred_action_rate"] == pytest.approx(1.0)


def _report() -> dict:
    mask = np.zeros(204, dtype=np.int8)
    mask[5] = 1
    mask[6] = 1
    arrays = {
        "planes": np.zeros((39, 42, 1), dtype=np.float32).tolist(),
        "scalars": np.zeros(58, dtype=np.float32).tolist(),
        "action_mask": mask.tolist(),
    }
    return {
        "left_label": "anchor",
        "right_label": "candidate",
        "pairs": [
            {
                "seed": 1,
                "seat": 0,
                "anchor_reward": 1.0,
                "candidate_reward": 0.25,
                "reward_delta": -0.75,
                "first_divergence_index": 3,
                "first_divergence": {
                    "divergence_index": 3,
                    "left": {
                        "action_id": 5,
                        "action_label": "discard 1m",
                        "action_family": "discard",
                        "decision_index": 9,
                        "observation": {"arrays": arrays},
                    },
                    "right": {
                        "action_id": 6,
                        "action_label": "discard 2m",
                        "action_family": "discard",
                        "decision_index": 9,
                        "observation": {"arrays": arrays},
                    },
                },
            }
        ],
    }
