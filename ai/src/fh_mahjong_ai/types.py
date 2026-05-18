from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

FloatArray = np.ndarray
IntArray = np.ndarray


@dataclass
class Observation:
    seat: int
    planes: FloatArray
    scalars: FloatArray
    action_mask: IntArray
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def legal_actions(self) -> tuple[int, ...]:
        indices = np.flatnonzero(self.action_mask)
        return tuple(int(index) for index in indices.tolist())


@dataclass
class StepResult:
    observation: Observation
    rewards: FloatArray
    terminated: bool
    truncated: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class Transition:
    observation: Observation
    action_id: int
    rewards: FloatArray
    next_observation: Observation
    terminated: bool
    truncated: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class TrainBatch:
    planes: FloatArray
    scalars: FloatArray
    action_mask: IntArray
    action_ids: IntArray
    returns: FloatArray
    steps_to_done: IntArray
    next_planes: FloatArray
    next_scalars: FloatArray
    next_action_mask: IntArray
    rewards: FloatArray
    dones: FloatArray
