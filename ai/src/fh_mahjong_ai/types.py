from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

FloatArray = np.ndarray
IntArray = np.ndarray


@dataclass(slots=True)
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


@dataclass(slots=True)
class StepResult:
    observation: Observation
    rewards: FloatArray
    terminated: bool
    truncated: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Transition:
    observation: Observation
    action_id: int
    rewards: FloatArray
    next_observation: Observation
    terminated: bool
    truncated: bool = False
    info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrainBatch:
    planes: FloatArray
    scalars: FloatArray
    action_mask: IntArray
    action_ids: IntArray
    returns: FloatArray
