from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .config import EnvConfig
from .types import Observation, StepResult


class BridgeError(RuntimeError):
    """Raised when the environment bridge cannot satisfy a request."""


class MahjongBridge(ABC):
    """Interface implemented by any Go-backed or mock Mahjong environment bridge."""

    def __init__(self, config: EnvConfig) -> None:
        self.config = config

    @abstractmethod
    def reset(self, seed: Optional[int] = None) -> Observation:
        raise NotImplementedError

    @abstractmethod
    def step(self, action_id: int) -> StepResult:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


@dataclass
class MockState:
    step_index: int = 0
    current_seat: int = 0


class MockMahjongBridge(MahjongBridge):
    """Random-but-deterministic placeholder used until the Go RL bridge exists."""

    def __init__(self, config: EnvConfig) -> None:
        super().__init__(config)
        self._state = MockState()
        self._rng = np.random.default_rng(config.seed)
        self._current_observation: Optional[Observation] = None

    def reset(self, seed: Optional[int] = None) -> Observation:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._state = MockState()
        self._current_observation = self._observe()
        return self._current_observation

    def step(self, action_id: int) -> StepResult:
        if self._current_observation is None:
            raise BridgeError("mock bridge must be reset before step()")
        if action_id not in self._current_observation.legal_actions:
            raise BridgeError(
                f"illegal mock action {action_id}; legal={self._current_observation.legal_actions}"
            )

        self._state.step_index += 1
        self._state.current_seat = (self._state.current_seat + 1) % 4

        terminated = self._state.step_index >= self.config.max_steps_per_episode
        rewards = np.zeros(4, dtype=np.float32)
        if terminated:
            rewards = self._rng.normal(loc=0.0, scale=1.0, size=4).astype(np.float32)

        next_observation = self._observe()
        self._current_observation = next_observation
        return StepResult(
            observation=next_observation,
            rewards=rewards,
            terminated=terminated,
            info={"mock_action": action_id, "step_index": self._state.step_index},
        )

    def close(self) -> None:
        return None

    def _observe(self) -> Observation:
        channels, height, width = self.config.plane_shape
        planes = self._rng.random((channels, height, width), dtype=np.float32)
        scalars = self._rng.random((self.config.scalar_features,), dtype=np.float32)
        action_mask = np.zeros((self.config.action_space_size,), dtype=np.int8)

        legal_count = int(self._rng.integers(low=4, high=min(12, self.config.action_space_size)))
        legal_indices = self._rng.choice(self.config.action_space_size, size=legal_count, replace=False)
        action_mask[legal_indices] = 1

        return Observation(
            seat=self._state.current_seat,
            planes=planes,
            scalars=scalars,
            action_mask=action_mask,
            metadata={"step_index": self._state.step_index, "bridge": "mock"},
        )


class UnimplementedGoBridge(MahjongBridge):
    """Placeholder for the real Go bridge."""

    def reset(self, seed: Optional[int] = None) -> Observation:
        raise BridgeError("Go Mahjong bridge is not implemented yet")

    def step(self, action_id: int) -> StepResult:
        raise BridgeError("Go Mahjong bridge is not implemented yet")

    def close(self) -> None:
        return None


def build_bridge(config: EnvConfig) -> MahjongBridge:
    if config.bridge_kind == "mock":
        return MockMahjongBridge(config)
    if config.bridge_kind == "go":
        return UnimplementedGoBridge(config)
    raise BridgeError(f"unknown bridge kind: {config.bridge_kind}")
