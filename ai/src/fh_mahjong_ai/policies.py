from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import torch

from .action_catalog import action_family, action_label
from .model import PolicyValueNet
from .types import Observation


@dataclass
class ActionChoice:
    action_id: int
    value: Optional[float] = None
    info: Optional[dict[str, Any]] = None


class RandomMaskedPolicy:
    def __init__(self, seed: int = 1) -> None:
        self._rng = np.random.default_rng(seed)

    def choose(self, observation: Observation) -> ActionChoice:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")
        action_id = int(self._rng.choice(legal_actions))
        return ActionChoice(action_id=action_id)


class TorchGreedyPolicy:
    def __init__(self, model: PolicyValueNet, device: str = "cpu") -> None:
        self.model = model
        self.device = device

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ActionChoice:
        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)

        logits, value = self.model(planes, scalars, action_mask)
        action_id = int(torch.argmax(logits, dim=1).item())
        return ActionChoice(action_id=action_id, value=float(value.item()))


class GuardedQPolicy:
    """Use a candidate policy only when its Q estimate clears the anchor action by a margin."""

    def __init__(
        self,
        anchor_model: PolicyValueNet,
        candidate_model: PolicyValueNet,
        min_q_margin: float = 0.0,
        device: str = "cpu",
    ) -> None:
        self.anchor_model = anchor_model
        self.candidate_model = candidate_model
        self.min_q_margin = float(min_q_margin)
        self.device = device

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ActionChoice:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)

        anchor_logits, anchor_value = self.anchor_model(planes, scalars, action_mask)
        candidate_logits, candidate_policy_value = self.candidate_model(planes, scalars, action_mask)
        candidate_q_values, candidate_value = self.candidate_model.q_values(planes, scalars, action_mask)

        anchor_action = int(torch.argmax(anchor_logits, dim=1).item())
        candidate_action = int(torch.argmax(candidate_logits, dim=1).item())
        candidate_q = float(candidate_q_values[0, candidate_action].item())
        anchor_q = float(candidate_q_values[0, anchor_action].item())
        q_margin = candidate_q - anchor_q

        if candidate_action == anchor_action:
            chosen_action = anchor_action
            source = "same"
        elif q_margin >= self.min_q_margin:
            chosen_action = candidate_action
            source = "candidate"
        else:
            chosen_action = anchor_action
            source = "anchor"

        return ActionChoice(
            action_id=chosen_action,
            value=float(candidate_value.item()),
            info={
                "source": source,
                "anchor_action_id": anchor_action,
                "anchor_action_label": action_label(anchor_action),
                "candidate_action_id": candidate_action,
                "candidate_action_label": action_label(candidate_action),
                "chosen_action_label": action_label(chosen_action),
                "candidate_q": candidate_q,
                "anchor_action_q": anchor_q,
                "q_margin": q_margin,
                "anchor_value": float(anchor_value.item()),
                "candidate_policy_value": float(candidate_policy_value.item()),
                "candidate_value": float(candidate_value.item()),
                "min_q_margin": self.min_q_margin,
            },
        )


class TailConstrainedCandidatePolicy:
    """Use candidate actions only when Q improves and predicted large-loss risk does not increase."""

    def __init__(
        self,
        anchor_model: PolicyValueNet,
        candidate_model: PolicyValueNet,
        risk_model: PolicyValueNet,
        min_q_margin: float = 0.0,
        max_risk_increase: float = 0.0,
        max_risk_increase_by_family: Optional[dict[str, float]] = None,
        max_candidate_risk: Optional[float] = None,
        severity_weight: float = 0.0,
        device: str = "cpu",
    ) -> None:
        self.anchor_model = anchor_model
        self.candidate_model = candidate_model
        self.risk_model = risk_model
        self.min_q_margin = float(min_q_margin)
        self.max_risk_increase = float(max_risk_increase)
        self.max_risk_increase_by_family = {
            str(family): float(value)
            for family, value in (max_risk_increase_by_family or {}).items()
        }
        self.max_candidate_risk = float(max_candidate_risk) if max_candidate_risk is not None else None
        self.severity_weight = float(severity_weight)
        self.device = device

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ActionChoice:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)

        anchor_logits, anchor_value = self.anchor_model(planes, scalars, action_mask)
        candidate_logits, candidate_policy_value = self.candidate_model(planes, scalars, action_mask)
        candidate_q_values, candidate_value = self.candidate_model.q_values(planes, scalars, action_mask)
        risk_logits, risk_severities = self.risk_model.action_risk_predictions(planes, scalars, action_mask)
        risk_probabilities = torch.sigmoid(risk_logits)

        anchor_action = int(torch.argmax(anchor_logits, dim=1).item())
        candidate_action = int(torch.argmax(candidate_logits, dim=1).item())
        candidate_family = action_family(candidate_action)
        allowed_risk_increase = self.max_risk_increase_by_family.get(candidate_family, self.max_risk_increase)
        candidate_q = float(candidate_q_values[0, candidate_action].item())
        anchor_q = float(candidate_q_values[0, anchor_action].item())
        q_margin = candidate_q - anchor_q

        anchor_risk = float(risk_probabilities[0, anchor_action].item())
        candidate_risk = float(risk_probabilities[0, candidate_action].item())
        anchor_severity = float(risk_severities[0, anchor_action].item())
        candidate_severity = float(risk_severities[0, candidate_action].item())
        anchor_tail_score = anchor_risk + self.severity_weight * anchor_severity
        candidate_tail_score = candidate_risk + self.severity_weight * candidate_severity
        risk_increase = candidate_risk - anchor_risk
        tail_score_increase = candidate_tail_score - anchor_tail_score

        q_pass = q_margin >= self.min_q_margin
        risk_pass = risk_increase <= allowed_risk_increase
        severity_pass = tail_score_increase <= allowed_risk_increase
        max_risk_pass = self.max_candidate_risk is None or candidate_risk <= self.max_candidate_risk

        if candidate_action == anchor_action:
            chosen_action = anchor_action
            source = "same"
        elif q_pass and risk_pass and severity_pass and max_risk_pass:
            chosen_action = candidate_action
            source = "candidate"
        else:
            chosen_action = anchor_action
            source = "anchor"

        chosen_risk = float(risk_probabilities[0, chosen_action].item())
        chosen_severity = float(risk_severities[0, chosen_action].item())
        return ActionChoice(
            action_id=chosen_action,
            value=float(candidate_value.item()),
            info={
                "source": source,
                "anchor_action_id": anchor_action,
                "anchor_action_label": action_label(anchor_action),
                "candidate_action_id": candidate_action,
                "candidate_action_label": action_label(candidate_action),
                "candidate_action_family": candidate_family,
                "chosen_action_id": chosen_action,
                "chosen_action_label": action_label(chosen_action),
                "candidate_q": candidate_q,
                "anchor_action_q": anchor_q,
                "q_margin": q_margin,
                "anchor_risk": anchor_risk,
                "candidate_risk": candidate_risk,
                "chosen_risk": chosen_risk,
                "risk_reduction": anchor_risk - chosen_risk,
                "risk_increase": risk_increase,
                "anchor_severity": anchor_severity,
                "candidate_severity": candidate_severity,
                "chosen_severity": chosen_severity,
                "tail_score_increase": tail_score_increase,
                "anchor_value": float(anchor_value.item()),
                "candidate_policy_value": float(candidate_policy_value.item()),
                "candidate_value": float(candidate_value.item()),
                "min_q_margin": self.min_q_margin,
                "max_risk_increase": self.max_risk_increase,
                "allowed_risk_increase": allowed_risk_increase,
                "max_risk_increase_by_family": self.max_risk_increase_by_family,
                "max_candidate_risk": self.max_candidate_risk,
                "severity_weight": self.severity_weight,
                "q_pass": q_pass,
                "risk_pass": risk_pass,
                "severity_pass": severity_pass,
                "max_risk_pass": max_risk_pass,
            },
        )


class RiskGuardedPolicy:
    """Keep an anchor policy unless a risk critic finds a lower-risk legal substitute."""

    def __init__(
        self,
        anchor_model: PolicyValueNet,
        risk_model: PolicyValueNet,
        anchor_risk_threshold: float = 0.6,
        candidate_risk_threshold: float = 0.45,
        min_risk_reduction: float = 0.1,
        max_policy_logit_gap: float = 3.0,
        severity_weight: float = 0.0,
        selection_mode: str = "lowest_risk",
        device: str = "cpu",
    ) -> None:
        self.anchor_model = anchor_model
        self.risk_model = risk_model
        self.anchor_risk_threshold = float(anchor_risk_threshold)
        self.candidate_risk_threshold = float(candidate_risk_threshold)
        self.min_risk_reduction = float(min_risk_reduction)
        self.max_policy_logit_gap = float(max_policy_logit_gap)
        self.severity_weight = float(severity_weight)
        if selection_mode not in {"lowest_risk", "policy_nearest"}:
            raise ValueError("selection_mode must be 'lowest_risk' or 'policy_nearest'")
        self.selection_mode = selection_mode
        self.device = device

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ActionChoice:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)

        anchor_logits, anchor_value = self.anchor_model(planes, scalars, action_mask)
        risk_logits, risk_severities = self.risk_model.action_risk_predictions(planes, scalars, action_mask)
        risk_probabilities = torch.sigmoid(risk_logits)

        anchor_action = int(torch.argmax(anchor_logits, dim=1).item())
        anchor_risk = float(risk_probabilities[0, anchor_action].item())
        anchor_severity = float(risk_severities[0, anchor_action].item())
        anchor_logit = float(anchor_logits[0, anchor_action].item())
        chosen_action = anchor_action
        source = "anchor"

        if anchor_risk >= self.anchor_risk_threshold:
            legal = torch.nonzero(action_mask[0] > 0, as_tuple=False).flatten()
            legal_risks = risk_probabilities[0, legal]
            legal_severities = risk_severities[0, legal]
            legal_logits = anchor_logits[0, legal]
            logit_gap = anchor_logit - legal_logits
            risk_reduction = anchor_risk - legal_risks
            allowed = (
                (legal_risks <= self.candidate_risk_threshold)
                & (risk_reduction >= self.min_risk_reduction)
                & (logit_gap <= self.max_policy_logit_gap)
            )
            if bool(allowed.any().item()):
                risk_score = legal_risks + self.severity_weight * legal_severities
                if self.selection_mode == "policy_nearest":
                    ranking_score = (logit_gap + 0.01 * risk_score).masked_fill(
                        ~allowed,
                        torch.finfo(logit_gap.dtype).max,
                    )
                else:
                    ranking_score = risk_score.masked_fill(~allowed, torch.finfo(risk_score.dtype).max)
                best_index = int(torch.argmin(ranking_score).item())
                chosen_action = int(legal[best_index].item())
                if chosen_action != anchor_action:
                    source = "risk_guard"

        chosen_risk = float(risk_probabilities[0, chosen_action].item())
        chosen_severity = float(risk_severities[0, chosen_action].item())
        return ActionChoice(
            action_id=chosen_action,
            value=float(anchor_value.item()),
            info={
                "source": source,
                "anchor_action_id": anchor_action,
                "anchor_action_label": action_label(anchor_action),
                "chosen_action_id": chosen_action,
                "chosen_action_label": action_label(chosen_action),
                "anchor_risk": anchor_risk,
                "chosen_risk": chosen_risk,
                "anchor_severity": anchor_severity,
                "chosen_severity": chosen_severity,
                "risk_reduction": anchor_risk - chosen_risk,
                "anchor_risk_threshold": self.anchor_risk_threshold,
                "candidate_risk_threshold": self.candidate_risk_threshold,
                "min_risk_reduction": self.min_risk_reduction,
                "max_policy_logit_gap": self.max_policy_logit_gap,
                "selection_mode": self.selection_mode,
            },
        )
