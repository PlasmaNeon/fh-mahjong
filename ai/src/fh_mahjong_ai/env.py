from __future__ import annotations

from typing import Optional

from .bridge import MahjongBridge, build_bridge
from .config import EnvConfig
from .types import Observation, StepResult


class MahjongEnv:
    """Thin environment wrapper around a Mahjong bridge implementation."""

    def __init__(self, config: EnvConfig, bridge: Optional[MahjongBridge] = None) -> None:
        self.config = config
        self.bridge = bridge or build_bridge(config)
        self.current_observation: Optional[Observation] = None

    def reset(self, seed: Optional[int] = None) -> Observation:
        self.current_observation = self.bridge.reset(seed=seed)
        return self.current_observation

    def step(self, action_id: int) -> StepResult:
        result = self.bridge.step(action_id)
        self.current_observation = result.observation
        return result

    def close(self) -> None:
        self.bridge.close()
