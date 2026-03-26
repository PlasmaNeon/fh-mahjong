from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class EnvConfig:
    action_space_size: int = 128
    plane_shape: tuple[int, int, int] = (48, 34, 1)
    scalar_features: int = 32
    max_steps_per_episode: int = 256
    bridge_kind: str = "mock"
    seed: int = 1


@dataclass
class ModelConfig:
    channels: int = 96
    scalar_hidden_dim: int = 128
    trunk_hidden_dim: int = 256
    value_hidden_dim: int = 128


@dataclass
class TrainConfig:
    batch_size: int = 64
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    max_grad_norm: float = 5.0
    device: str = "cpu"


@dataclass
class SelfPlayConfig:
    episodes_per_iteration: int = 32
    checkpoint_dir: Path = Path("checkpoints")
    replay_dir: Path = Path("replays")
    deterministic_eval: bool = True
