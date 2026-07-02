"""Checkpoint-backed inference helpers for serving Mahjong actions."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import torch

from .action_catalog import action_family
from .bridge import build_bridge
from .checkpoint_manifest import DEFAULT_MANIFEST_PATH, load_checkpoint_manifest, resolve_checkpoint_path
from .config import EnvConfig
from .model import PolicyValueNet, infer_model_config
from .storage import load_checkpoint
from .types import Observation


@dataclass(frozen=True)
class ServedAction:
    action_id: int
    value: float
    checkpoint_path: str
    checkpoint_step: int
    greedy_action_id: int = -1
    sampling_applied: bool = False
    sampled_from_greedy: bool = False


class CheckpointPolicy:
    """PolicyValueNet checkpoint wrapper for visible-observation inference."""

    def __init__(
        self,
        model: PolicyValueNet,
        checkpoint_path: Path,
        checkpoint_step: int,
        device: str = "cpu",
        sample_temperature: float = 0.0,
        sample_top_k: int = 0,
        sample_action_family: str = "all",
        seed: int = 1,
    ) -> None:
        self.model = model
        self.checkpoint_path = checkpoint_path
        self.checkpoint_step = checkpoint_step
        self.device = device
        self.sample_temperature = max(0.0, float(sample_temperature))
        self.sample_top_k = max(0, int(sample_top_k))
        self.sample_action_family = str(sample_action_family or "all")
        self._rng = np.random.default_rng(seed)
        self.model.eval()

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint_path: Path,
        device: str = "cpu",
        sample_temperature: float = 0.0,
        sample_top_k: int = 0,
        sample_action_family: str = "all",
        seed: int = 1,
    ) -> "CheckpointPolicy":
        # Architecture varies across promoted checkpoints (e.g. residual-block
        # depth); recover it from the saved tensors instead of assuming defaults.
        saved_state = torch.load(checkpoint_path, map_location="cpu")["model"]
        model = PolicyValueNet(EnvConfig(), infer_model_config(saved_state))
        step = load_checkpoint(checkpoint_path, model)
        model.to(device)
        return cls(
            model=model,
            checkpoint_path=checkpoint_path,
            checkpoint_step=step,
            device=device,
            sample_temperature=sample_temperature,
            sample_top_k=sample_top_k,
            sample_action_family=sample_action_family,
            seed=seed,
        )

    @torch.inference_mode()
    def choose(self, observation: Observation) -> ServedAction:
        legal_actions = observation.legal_actions
        if not legal_actions:
            raise ValueError("observation has no legal actions")

        planes = torch.from_numpy(observation.planes).unsqueeze(0).to(self.device)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(self.device)
        expected_scalars = self.model.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(self.device)
        logits, value = self.model(planes, scalars, action_mask)
        greedy_action_id = int(torch.argmax(logits, dim=1).item())
        sampling_actions = self._sampling_actions(legal_actions)
        sampling_applied = self.sample_temperature > 0.0 and bool(sampling_actions)
        if self.sample_temperature > 0.0 and sampling_actions:
            legal_actions = sampling_actions
            candidate_actions = np.asarray(legal_actions, dtype=np.int64)
            legal_logits = logits[0, legal_actions].detach().cpu().numpy().astype(np.float64)
            if self.sample_top_k > 0 and legal_logits.size > self.sample_top_k:
                top_indices = np.argpartition(-legal_logits, self.sample_top_k - 1)[: self.sample_top_k]
                top_indices = top_indices[np.argsort(-legal_logits[top_indices])]
                candidate_actions = candidate_actions[top_indices]
                legal_logits = legal_logits[top_indices]
            scaled = legal_logits / self.sample_temperature
            scaled -= float(np.max(scaled))
            probabilities = np.exp(scaled)
            probabilities /= float(np.sum(probabilities))
            action_id = int(self._rng.choice(candidate_actions, p=probabilities))
        else:
            action_id = greedy_action_id
        if action_id not in legal_actions:
            raise ValueError(f"model selected illegal action_id={action_id}; legal={legal_actions}")
        return ServedAction(
            action_id=action_id,
            value=float(value.item()),
            checkpoint_path=str(self.checkpoint_path),
            checkpoint_step=self.checkpoint_step,
            greedy_action_id=greedy_action_id,
            sampling_applied=sampling_applied,
            sampled_from_greedy=sampling_applied and action_id != greedy_action_id,
        )

    def _sampling_actions(self, legal_actions: list[int]) -> list[int]:
        if self.sample_action_family in {"", "all", "*"}:
            return list(legal_actions)
        if all(action_family(action_id) == self.sample_action_family for action_id in legal_actions):
            return list(legal_actions)
        return []


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
