from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import torch
from torch import Tensor, nn

from .config import EnvConfig, ModelConfig
from .model import ResidualBlock


GLOBAL_EV_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_ids",
    "terminal_rewards",
    "episode_index",
)

GLOBAL_EV_OPTIONAL_ARRAY_KEYS = (
    "decision_indices",
    "sample_weights",
)

BRANCH_ACTION_EV_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "branch_preferred_rewards",
    "branch_avoided_rewards",
    "episode_index",
)

BRANCH_ACTION_EV_OPTIONAL_ARRAY_KEYS = (
    "decision_indices",
    "pairwise_reward_delta_targets",
)


@dataclass(frozen=True)
class GlobalEVMetrics:
    count: int
    mae: float
    rmse: float
    bias: float
    correlation: float
    target_mean: float
    prediction_mean: float


class GlobalEVNet(nn.Module):
    """Visible-state predictor for final match expected value."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig) -> None:
        super().__init__()
        channels, height, width = env_config.plane_shape
        self.plane_stem = nn.Sequential(
            nn.Conv2d(channels, model_config.channels, kernel_size=3, padding=1),
            nn.GELU(),
        )
        self.plane_blocks = nn.Sequential(
            *[
                ResidualBlock(
                    model_config.channels,
                    channel_attention=model_config.channel_attention,
                    attention_ratio=model_config.channel_attention_ratio,
                )
                for _ in range(model_config.residual_blocks)
            ]
        )
        if model_config.pool_planes:
            plane_projection_dim = model_config.channels
            self.plane_projection = nn.Sequential(
                nn.AdaptiveAvgPool2d((1, 1)),
                nn.Flatten(start_dim=1),
            )
        else:
            plane_projection_dim = model_config.channels * height * width
            self.plane_projection = nn.Flatten(start_dim=1)
        self.plane_head = nn.Sequential(
            nn.Linear(plane_projection_dim, model_config.plane_feature_dim),
            nn.GELU(),
        )
        self.scalar_encoder = nn.Sequential(
            nn.Linear(env_config.scalar_features, model_config.scalar_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.scalar_hidden_dim, model_config.scalar_hidden_dim),
            nn.GELU(),
        )
        self.head = nn.Sequential(
            nn.Linear(model_config.plane_feature_dim + model_config.scalar_hidden_dim, model_config.trunk_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
        )

    def forward(self, planes: Tensor, scalars: Tensor) -> Tensor:
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(planes))))
        expected_scalars = self.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        scalar_features = self.scalar_encoder(scalars)
        return self.head(torch.cat([plane_features, scalar_features], dim=1)).squeeze(-1)


class ActionGlobalEVNet(nn.Module):
    """Visible-state/action predictor for final match expected value."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig) -> None:
        super().__init__()
        channels, height, width = env_config.plane_shape
        self.plane_stem = nn.Sequential(
            nn.Conv2d(channels, model_config.channels, kernel_size=3, padding=1),
            nn.GELU(),
        )
        self.plane_blocks = nn.Sequential(
            *[
                ResidualBlock(
                    model_config.channels,
                    channel_attention=model_config.channel_attention,
                    attention_ratio=model_config.channel_attention_ratio,
                )
                for _ in range(model_config.residual_blocks)
            ]
        )
        if model_config.pool_planes:
            plane_projection_dim = model_config.channels
            self.plane_projection = nn.Sequential(
                nn.AdaptiveAvgPool2d((1, 1)),
                nn.Flatten(start_dim=1),
            )
        else:
            plane_projection_dim = model_config.channels * height * width
            self.plane_projection = nn.Flatten(start_dim=1)
        self.plane_head = nn.Sequential(
            nn.Linear(plane_projection_dim, model_config.plane_feature_dim),
            nn.GELU(),
        )
        self.scalar_encoder = nn.Sequential(
            nn.Linear(env_config.scalar_features, model_config.scalar_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.scalar_hidden_dim, model_config.scalar_hidden_dim),
            nn.GELU(),
        )
        action_embedding_dim = min(64, max(8, model_config.scalar_hidden_dim // 2))
        self.action_embedding = nn.Embedding(env_config.action_space_size, action_embedding_dim)
        self.head = nn.Sequential(
            nn.Linear(
                model_config.plane_feature_dim + model_config.scalar_hidden_dim + action_embedding_dim,
                model_config.trunk_hidden_dim,
            ),
            nn.GELU(),
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
        )

    def forward(self, planes: Tensor, scalars: Tensor, action_ids: Tensor) -> Tensor:
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(planes))))
        expected_scalars = self.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        scalar_features = self.scalar_encoder(scalars)
        action_features = self.action_embedding(action_ids.to(dtype=torch.long))
        return self.head(torch.cat([plane_features, scalar_features, action_features], dim=1)).squeeze(-1)


def global_ev_targets(arrays: dict[str, np.ndarray]) -> np.ndarray:
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    rewards = np.asarray(arrays["terminal_rewards"], dtype=np.float32)
    if rewards.ndim != 2 or rewards.shape[1] < 4:
        raise ValueError("terminal_rewards must have shape [N, 4]")
    if seats.shape[0] != rewards.shape[0]:
        raise ValueError("seats and terminal_rewards must have the same row count")
    return rewards[np.arange(rewards.shape[0]), seats].astype(np.float32)


def branch_action_ev_arrays(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Expand exact branch-CF rows into action-conditioned EV samples."""
    seats = np.asarray(arrays["seats"], dtype=np.int16)
    planes = np.asarray(arrays["planes"], dtype=np.float32)
    scalars = np.asarray(arrays["scalars"], dtype=np.float32)
    preferred_actions = np.asarray(arrays["pairwise_preferred_action_ids"], dtype=np.int64)
    avoided_actions = np.asarray(arrays["pairwise_avoided_action_ids"], dtype=np.int64)
    preferred_rewards = np.asarray(arrays["branch_preferred_rewards"], dtype=np.float32)
    avoided_rewards = np.asarray(arrays["branch_avoided_rewards"], dtype=np.float32)
    if preferred_actions.shape != avoided_actions.shape:
        raise ValueError("preferred and avoided action arrays must have matching shape")
    if preferred_rewards.shape != avoided_rewards.shape or preferred_rewards.shape[0] != preferred_actions.shape[0]:
        raise ValueError("branch reward arrays must match pairwise action row count")

    row_count = int(preferred_actions.shape[0])
    expanded_rewards = np.zeros((row_count * 2, 4), dtype=np.float32)
    expanded_seats = np.repeat(seats, 2).astype(np.int16)
    expanded_rewards[np.arange(0, row_count * 2, 2), seats.astype(np.int64)] = preferred_rewards
    expanded_rewards[np.arange(1, row_count * 2, 2), seats.astype(np.int64)] = avoided_rewards
    result = {
        "seats": expanded_seats,
        "planes": np.repeat(planes, 2, axis=0).astype(np.float32),
        "scalars": np.repeat(scalars, 2, axis=0).astype(np.float32),
        "action_ids": np.column_stack([preferred_actions, avoided_actions]).reshape(-1).astype(np.int64),
        "terminal_rewards": expanded_rewards,
        "episode_index": np.repeat(np.asarray(arrays["episode_index"], dtype=np.int64), 2).astype(np.int64),
        "branch_role_ids": np.tile(np.asarray([1, 0], dtype=np.int8), row_count),
    }
    if "decision_indices" in arrays:
        result["decision_indices"] = np.repeat(np.asarray(arrays["decision_indices"], dtype=np.int64), 2)
    if "pairwise_reward_delta_targets" in arrays:
        result["pairwise_reward_delta_targets"] = np.repeat(
            np.asarray(arrays["pairwise_reward_delta_targets"], dtype=np.float32),
            2,
        )
    return result


def episode_split_indices(
    episode_index: np.ndarray,
    validation_mod: int = 10,
    validation_remainder: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    episodes = np.asarray(episode_index, dtype=np.int64)
    if episodes.ndim != 1:
        raise ValueError("episode_index must be a 1D array")
    if episodes.size == 0:
        raise ValueError("cannot split an empty dataset")
    if validation_mod <= 1:
        raise ValueError("validation_mod must be greater than 1")
    validation_mask = np.mod(episodes, int(validation_mod)) == int(validation_remainder)
    train_indices = np.flatnonzero(~validation_mask).astype(np.int64)
    validation_indices = np.flatnonzero(validation_mask).astype(np.int64)
    if train_indices.size == 0 or validation_indices.size == 0:
        cutoff = max(1, int(0.9 * episodes.size))
        train_indices = np.arange(0, cutoff, dtype=np.int64)
        validation_indices = np.arange(cutoff, episodes.size, dtype=np.int64)
    if validation_indices.size == 0:
        validation_indices = train_indices[-1:].copy()
        train_indices = train_indices[:-1]
    if train_indices.size == 0:
        raise ValueError("not enough rows to create train and validation splits")
    return train_indices, validation_indices


def regression_metrics(predictions: np.ndarray, targets: np.ndarray) -> GlobalEVMetrics:
    pred = np.asarray(predictions, dtype=np.float64)
    target = np.asarray(targets, dtype=np.float64)
    if pred.shape != target.shape:
        raise ValueError("predictions and targets must have matching shape")
    if pred.size == 0:
        raise ValueError("cannot score zero predictions")
    errors = pred - target
    pred_std = float(np.std(pred))
    target_std = float(np.std(target))
    if pred_std == 0.0 or target_std == 0.0:
        correlation = 0.0
    else:
        correlation = float(np.corrcoef(pred, target)[0, 1])
        if not np.isfinite(correlation):
            correlation = 0.0
    return GlobalEVMetrics(
        count=int(pred.size),
        mae=float(np.mean(np.abs(errors))),
        rmse=float(np.sqrt(np.mean(np.square(errors)))),
        bias=float(np.mean(errors)),
        correlation=correlation,
        target_mean=float(np.mean(target)),
        prediction_mean=float(np.mean(pred)),
    )


def constant_baseline_metrics(train_targets: np.ndarray, validation_targets: np.ndarray) -> GlobalEVMetrics:
    """Score the validation split against the train-set mean predictor."""
    train = np.asarray(train_targets, dtype=np.float32)
    validation = np.asarray(validation_targets, dtype=np.float32)
    if train.size == 0 or validation.size == 0:
        raise ValueError("train and validation targets must both be non-empty")
    predictions = np.full(validation.shape, float(np.mean(train)), dtype=np.float32)
    return regression_metrics(predictions, validation)


def concatenate_array_sets(array_sets: Sequence[dict[str, np.ndarray]]) -> dict[str, np.ndarray]:
    if not array_sets:
        raise ValueError("at least one array set is required")
    keys = set(array_sets[0].keys())
    for arrays in array_sets[1:]:
        keys &= set(arrays.keys())
    return {key: np.concatenate([arrays[key] for arrays in array_sets], axis=0) for key in sorted(keys)}
