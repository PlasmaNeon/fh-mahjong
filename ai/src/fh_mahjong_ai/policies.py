from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import torch

from .model import PolicyValueNet
from .types import Observation


@dataclass(slots=True)
class ActionChoice:
    action_id: int
    value: Optional[float] = None


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
