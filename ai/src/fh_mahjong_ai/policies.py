from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import torch

from .action_catalog import action_label
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
