from __future__ import annotations

import numpy as np
import torch
from torch import Tensor, nn

from fh_mahjong_ai.policies import GuardedQPolicy, RiskGuardedPolicy, TailConstrainedCandidatePolicy
from fh_mahjong_ai.types import Observation


class FixedHeadsModel(nn.Module):
    def __init__(
        self,
        logits: dict[int, float],
        q_values: dict[int, float],
        risk_logits: dict[int, float] | None = None,
        risk_severities: dict[int, float] | None = None,
    ) -> None:
        super().__init__()
        self._logits = logits
        self._q_values = q_values
        self._risk_logits = risk_logits or {}
        self._risk_severities = risk_severities or {}

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

    def action_risk_predictions(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        logits = torch.full_like(action_mask, torch.finfo(torch.float32).min, dtype=torch.float32)
        severities = torch.zeros_like(action_mask, dtype=torch.float32)
        for action_id, value in self._risk_logits.items():
            logits[:, action_id] = value
        for action_id, value in self._risk_severities.items():
            severities[:, action_id] = value
        logits = logits.masked_fill(action_mask <= 0, torch.finfo(torch.float32).min)
        severities = severities.masked_fill(action_mask <= 0, 0.0)
        return logits, severities


def _observation() -> Observation:
    mask = np.zeros(204, dtype=np.int8)
    mask[5] = 1
    mask[6] = 1
    mask[7] = 1
    return Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(50, dtype=np.float32),
        action_mask=mask,
    )


def test_guarded_q_policy_uses_candidate_when_margin_clears_threshold() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={6: 10.0, 7: 0.0}, q_values={5: 1.0, 6: 1.8, 7: 9.0})
    policy = GuardedQPolicy(anchor, candidate, min_q_margin=0.5)

    choice = policy.choose(_observation())

    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["source"] == "candidate"
    assert choice.info["anchor_action_label"] == "discard 1m"
    assert choice.info["candidate_action_label"] == "discard 2m"


def test_guarded_q_policy_falls_back_to_anchor_below_threshold() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={6: 10.0}, q_values={5: 1.0, 6: 1.4})
    policy = GuardedQPolicy(anchor, candidate, min_q_margin=0.5)

    choice = policy.choose(_observation())

    assert choice.action_id == 5
    assert choice.info is not None
    assert choice.info["source"] == "anchor"


def test_tail_constrained_policy_allows_candidate_when_q_improves_without_extra_risk() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={6: 10.0}, q_values={5: 1.0, 6: 1.5})
    risk = FixedHeadsModel(logits={}, q_values={}, risk_logits={5: 0.0, 6: -1.0})
    policy = TailConstrainedCandidatePolicy(
        anchor,
        candidate,
        risk,
        min_q_margin=0.25,
        max_risk_increase=0.0,
    )

    choice = policy.choose(_observation())

    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["source"] == "candidate"
    assert choice.info["q_pass"] is True
    assert choice.info["risk_pass"] is True
    assert choice.info["candidate_risk"] < choice.info["anchor_risk"]


def test_tail_constrained_policy_blocks_candidate_when_large_loss_risk_increases() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={6: 10.0}, q_values={5: 1.0, 6: 2.0})
    risk = FixedHeadsModel(logits={}, q_values={}, risk_logits={5: -1.0, 6: 1.0})
    policy = TailConstrainedCandidatePolicy(
        anchor,
        candidate,
        risk,
        min_q_margin=0.25,
        max_risk_increase=0.0,
    )

    choice = policy.choose(_observation())

    assert choice.action_id == 5
    assert choice.info is not None
    assert choice.info["source"] == "anchor"
    assert choice.info["q_pass"] is True
    assert choice.info["risk_pass"] is False
    assert choice.info["candidate_risk"] > choice.info["anchor_risk"]


def test_tail_constrained_policy_allows_family_specific_risk_tolerance() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0}, q_values={})
    candidate = FixedHeadsModel(logits={6: 10.0}, q_values={5: 1.0, 6: 2.0})
    risk = FixedHeadsModel(logits={}, q_values={}, risk_logits={5: -1.0, 6: -0.95})
    policy = TailConstrainedCandidatePolicy(
        anchor,
        candidate,
        risk,
        min_q_margin=0.25,
        max_risk_increase=0.0,
        max_risk_increase_by_family={"discard": 0.02},
    )

    choice = policy.choose(_observation())

    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["source"] == "candidate"
    assert choice.info["candidate_action_family"] == "discard"
    assert choice.info["allowed_risk_increase"] == 0.02
    assert 0.0 < choice.info["risk_increase"] <= 0.02


def test_risk_guarded_policy_switches_to_lower_risk_policy_near_action() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 9.0, 7: 0.0}, q_values={})
    risk = FixedHeadsModel(
        logits={},
        q_values={},
        risk_logits={5: 2.0, 6: -2.0, 7: -3.0},
        risk_severities={5: 1.0, 6: 0.2, 7: 0.1},
    )
    policy = RiskGuardedPolicy(
        anchor,
        risk,
        anchor_risk_threshold=0.7,
        candidate_risk_threshold=0.2,
        min_risk_reduction=0.5,
        max_policy_logit_gap=2.0,
    )

    choice = policy.choose(_observation())

    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["source"] == "risk_guard"
    assert choice.info["chosen_action_id"] == 6
    assert choice.info["risk_reduction"] > 0.5


def test_risk_guarded_policy_keeps_anchor_when_safe_action_too_far_from_policy() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 0.0, 7: 9.5}, q_values={})
    risk = FixedHeadsModel(logits={}, q_values={}, risk_logits={5: 2.0, 6: -2.0, 7: 1.5})
    policy = RiskGuardedPolicy(
        anchor,
        risk,
        anchor_risk_threshold=0.7,
        candidate_risk_threshold=0.2,
        min_risk_reduction=0.5,
        max_policy_logit_gap=2.0,
    )

    choice = policy.choose(_observation())

    assert choice.action_id == 5
    assert choice.info is not None
    assert choice.info["source"] == "anchor"


def test_risk_guarded_policy_can_choose_policy_nearest_lower_risk_action() -> None:
    anchor = FixedHeadsModel(logits={5: 10.0, 6: 9.5, 7: 8.5}, q_values={})
    risk = FixedHeadsModel(
        logits={},
        q_values={},
        risk_logits={5: 2.0, 6: -1.0, 7: -3.0},
        risk_severities={5: 0.9, 6: 0.3, 7: 0.1},
    )
    lowest_risk = RiskGuardedPolicy(
        anchor,
        risk,
        anchor_risk_threshold=0.7,
        candidate_risk_threshold=0.4,
        min_risk_reduction=0.4,
        max_policy_logit_gap=2.0,
        selection_mode="lowest_risk",
    )
    policy_nearest = RiskGuardedPolicy(
        anchor,
        risk,
        anchor_risk_threshold=0.7,
        candidate_risk_threshold=0.4,
        min_risk_reduction=0.4,
        max_policy_logit_gap=2.0,
        selection_mode="policy_nearest",
    )

    assert lowest_risk.choose(_observation()).action_id == 7
    choice = policy_nearest.choose(_observation())
    assert choice.action_id == 6
    assert choice.info is not None
    assert choice.info["selection_mode"] == "policy_nearest"
