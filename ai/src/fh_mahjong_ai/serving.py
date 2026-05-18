"""Checkpoint-backed inference helpers for serving Mahjong actions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import torch

from .bridge import build_bridge
from .checkpoint_manifest import DEFAULT_MANIFEST_PATH, load_checkpoint_manifest, resolve_checkpoint_path
from .config import EnvConfig, ModelConfig
from .model import PolicyValueNet
from .storage import load_checkpoint
from .types import Observation


@dataclass(frozen=True)
class ServedAction:
    action_id: int
    value: float
    checkpoint_path: str
    checkpoint_step: int


class CheckpointPolicy:
    """PolicyValueNet checkpoint wrapper for visible-observation inference."""

    def __init__(self, model: PolicyValueNet, checkpoint_path: Path, checkpoint_step: int, device: str = "cpu") -> None:
        self.model = model
        self.checkpoint_path = checkpoint_path
        self.checkpoint_step = checkpoint_step
        self.device = device
        self.model.eval()

    @classmethod
    def from_checkpoint(cls, checkpoint_path: Path, device: str = "cpu") -> "CheckpointPolicy":
        model = PolicyValueNet(EnvConfig(), ModelConfig())
        step = load_checkpoint(checkpoint_path, model)
        model.to(device)
        return cls(model=model, checkpoint_path=checkpoint_path, checkpoint_step=step, device=device)

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ServedAction:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)
        logits, value = self.model(planes, scalars, action_mask)
        action_id = int(torch.argmax(logits, dim=1).item())
        if action_id not in legal_actions:
            raise ValueError(f"model selected illegal action_id={action_id}; legal={legal_actions}")
        return ServedAction(
            action_id=action_id,
            value=float(value.item()),
            checkpoint_path=str(self.checkpoint_path),
            checkpoint_step=self.checkpoint_step,
        )


def load_policy_from_manifest(
    manifest_path: Path = DEFAULT_MANIFEST_PATH,
    checkpoint_id: str = "current",
    checkpoint_override: Optional[Path] = None,
    device: str = "cpu",
) -> CheckpointPolicy:
    manifest = load_checkpoint_manifest(manifest_path)
    checkpoint_path = resolve_checkpoint_path(
        manifest=manifest,
        checkpoint_id=checkpoint_id,
        checkpoint_override=checkpoint_override,
    )
    return CheckpointPolicy.from_checkpoint(checkpoint_path, device=device)


def run_bridge_serving_smoke(
    policy: CheckpointPolicy,
    episodes: int = 4,
    start_seed: int = 1,
    bridge_kind: str = "mock",
    bridge_library_path: Optional[Path] = None,
    max_decisions: int = 512,
) -> dict[str, int]:
    """Step a served policy through a bridge so Go/mock legality validates actions."""
    completed = 0
    decisions = 0
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=max_decisions,
    )
    bridge = build_bridge(config)
    try:
        for offset in range(max(0, int(episodes))):
            observation = bridge.reset(seed=start_seed + offset)
            reset_result = bridge.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                completed += 1
                continue
            while True:
                action = policy.choose(observation)
                decisions += 1
                result = bridge.step(action.action_id)
                if result.terminated or result.truncated:
                    completed += 1
                    break
                observation = result.observation
    finally:
        bridge.close()
    return {"episodes": completed, "decisions": decisions}
