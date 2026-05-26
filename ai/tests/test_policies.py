from __future__ import annotations

import numpy as np
import torch
from torch import Tensor, nn

from fh_mahjong_ai.policies import GuardedQPolicy
from fh_mahjong_ai.types import Observation


class FixedHeadsModel(nn.Module):
    def __init__(self, logits: dict[int, float], q_values: dict[int, float]) -> None:
        super().__init__()
        self._logits = logits
        self._q_values = q_values

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        logits = torch.full_like(action_mask, torch.finfo(torch.float32).min, dtype=torch.float32)
        for action_id, value in self._logits.items():
            logits[:, action_id] = value
        logits = logits.masked_fill(action_mask <= 0, torch.finfo(torch.float32).min)
        return logits, torch.zeros((action_mask.shape[0],), dtype=torch.float32)

    def q_values(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        values = torch.full_like(action_mask, torch.finfo(torch.float32).min, dtype=torch.float32)
        for action_id, value in self._q_values.items():
            values[:, action_id] = value
        values = values.masked_fill(action_mask <= 0, torch.finfo(torch.float32).min)
        return values, torch.zeros((action_mask.shape[0],), dtype=torch.float32)


def _observation() -> Observation:
    mask = np.zeros(204, dtype=np.int8)
    mask[5] = 1
    mask[6] = 1
    return Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(50, dtype=np.float32),
        action_mask=mask,
    )


def test_guarded_q_policy_uses_candidate_when_margin_clears_threshold() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={}, q_values={5: 1.0, 6: 1.8})
    policy = GuardedQPolicy(anchor, candidate, min_q_margin=0.5)

    choice = policy.choose(_observation())

    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["source"] == "candidate"
    assert choice.info["anchor_action_label"] == "discard 1m"
    assert choice.info["candidate_action_label"] == "discard 2m"


def test_guarded_q_policy_falls_back_to_anchor_below_threshold() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={}, q_values={5: 1.0, 6: 1.4})
    policy = GuardedQPolicy(anchor, candidate, min_q_margin=0.5)

    choice = policy.choose(_observation())

    assert choice.action_id == 5
    assert choice.info is not None
    assert choice.info["source"] == "anchor"
