from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EnvConfig:
    action_space_size: int = 204
    plane_shape: tuple[int, int, int] = (39, 42, 1)
    scalar_features: int = 50
    max_steps_per_episode: int = 256
    bridge_kind: str = "go"
    seed: int = 1
    learning_seats: tuple[int, ...] = (0,)
    auto_play_heuristics: bool = True
    bridge_library_path: Optional[Path] = None
    match_mode: str = "classic"
    chongci_starting_score: int = 2000
    chongci_bust_threshold: int = 0
    chongci_max_hands: int = 50


@dataclass
class ModelConfig:
    channels: int = 96
    residual_blocks: int = 2
    plane_feature_dim: int = 256
    scalar_hidden_dim: int = 128
    trunk_hidden_dim: int = 256
    value_hidden_dim: int = 128
    q_hidden_dim: int = 256
    pool_planes: bool = False
    channel_attention: bool = False
    channel_attention_ratio: int = 16
    dueling_q: bool = True


@dataclass
class TrainConfig:
    batch_size: int = 64
    learning_rate: float = 3e-4
    weight_decay: float = 1e-4
    max_grad_norm: float = 5.0
    device: str = "cpu"
    seed: int = 0


@dataclass
class OfflineQConfig:
    gamma: float = 0.99
    conservative_weight: float = 0.1
    bc_weight: float = 0.1
    value_weight: float = 0.25
    target_update_interval: int = 25
    target_tau: float = 1.0


@dataclass
class DiscreteIQLConfig:
    gamma: float = 0.99
    target_mode: str = "mc"
    expectile: float = 0.7
    temperature: float = 1.0
    max_weight: float = 20.0
    q_weight: float = 1.0
    value_weight: float = 1.0
    policy_weight: float = 1.0
    bc_weight: float = 1.0
    cql_weight: float = 0.0
    target_update_interval: int = 25
    target_tau: float = 0.005
    large_loss_threshold: Optional[float] = None
    large_loss_penalty: float = 0.0
    large_loss_weight: float = 1.0
    pairwise_weight: float = 0.0
    pairwise_margin: float = 0.0
    pairwise_q_weight: float = 0.0
    pairwise_q_margin: float = 0.0
    large_loss_aux_weight: float = 0.0
    large_loss_severity_weight: float = 0.0
    large_loss_aux_detach: bool = False


@dataclass
class AdvantageWeightedBCConfig:
    temperature: float = 1.0
    max_weight: float = 20.0
    value_weight: float = 0.25


@dataclass
class SelfPlayConfig:
    episodes_per_iteration: int = 32
    checkpoint_dir: Path = Path("checkpoints")
    replay_dir: Path = Path("replays")
    deterministic_eval: bool = True
