from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import torch

from .types import Observation, Transition


def save_checkpoint(path: Path, model: torch.nn.Module, optimizer: Optional[torch.optim.Optimizer] = None, step: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model.state_dict(), "step": step}
    if optimizer is not None:
        payload["optimizer"] = optimizer.state_dict()
    torch.save(payload, path)


def load_checkpoint(path: Path, model: torch.nn.Module, optimizer: Optional[torch.optim.Optimizer] = None) -> int:
    payload = torch.load(path, map_location="cpu")
    model.load_state_dict(payload["model"])
    if optimizer is not None and "optimizer" in payload:
        optimizer.load_state_dict(payload["optimizer"])
    return int(payload.get("step", 0))


def write_transitions_jsonl(path: Path, transitions: Iterable[Transition]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for transition in transitions:
            handle.write(json.dumps(_transition_to_dict(transition)) + "\n")


def read_transitions_jsonl(path: Path) -> list[Transition]:
    transitions: list[Transition] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            transitions.append(_transition_from_dict(json.loads(line)))
    return transitions


def _transition_to_dict(transition: Transition) -> dict[str, object]:
    return {
        "observation": _observation_to_dict(transition.observation),
        "action_id": transition.action_id,
        "rewards": transition.rewards.tolist(),
        "next_observation": _observation_to_dict(transition.next_observation),
        "terminated": transition.terminated,
        "truncated": transition.truncated,
        "info": _sanitize_info(transition.info),
    }


def _sanitize_info(info: dict) -> dict:
    """Convert any numpy arrays in an info dict to plain Python lists."""
    result = {}
    for key, value in info.items():
        result[key] = value.tolist() if isinstance(value, np.ndarray) else value
    return result


def _transition_from_dict(payload: dict[str, object]) -> Transition:
    from .types import Transition

    return Transition(
        observation=_observation_from_dict(payload["observation"]),
        action_id=int(payload["action_id"]),
        rewards=np.asarray(payload["rewards"], dtype=np.float32),
        next_observation=_observation_from_dict(payload["next_observation"]),
        terminated=bool(payload["terminated"]),
        truncated=bool(payload.get("truncated", False)),
        info=dict(payload.get("info", {})),
    )


def _observation_to_dict(observation: Observation) -> dict[str, object]:
    return {
        "seat": observation.seat,
        "planes": observation.planes.tolist(),
        "scalars": observation.scalars.tolist(),
        "action_mask": observation.action_mask.tolist(),
        "metadata": observation.metadata,
    }


def _observation_from_dict(payload: dict[str, object]) -> Observation:
    return Observation(
        seat=int(payload["seat"]),
        planes=np.asarray(payload["planes"], dtype=np.float32),
        scalars=np.asarray(payload["scalars"], dtype=np.float32),
        action_mask=np.asarray(payload["action_mask"], dtype=np.int8),
        metadata=dict(payload.get("metadata", {})),
    )
