from __future__ import annotations

import torch
from torch import Tensor, nn

from .config import EnvConfig, ModelConfig


class PolicyValueNet(nn.Module):
    """Masked-action policy/value network for Mahjong observations."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig) -> None:
        super().__init__()
        channels, height, width = env_config.plane_shape

        self.plane_stem = nn.Sequential(
            nn.Conv2d(channels, model_config.channels, kernel_size=3, padding=1),
            nn.GELU(),
        )
        self.plane_blocks = nn.Sequential(
            *[ResidualBlock(model_config.channels) for _ in range(model_config.residual_blocks)]
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
        self.trunk = nn.Sequential(
            nn.Linear(
                model_config.plane_feature_dim + model_config.scalar_hidden_dim,
                model_config.trunk_hidden_dim,
            ),
            nn.GELU(),
        )
        self.policy_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        self.q_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        self.value_head = nn.Sequential(
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
            nn.Tanh(),
        )

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)

        logits = self.policy_head(features)
        masked_logits = logits.masked_fill(action_mask <= 0, torch.finfo(logits.dtype).min)
        value = self.value_head(features).squeeze(-1)
        return masked_logits, value

    def encode(self, planes: Tensor, scalars: Tensor) -> Tensor:
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(planes))))
        scalar_features = self.scalar_encoder(scalars)
        return self.trunk(torch.cat([plane_features, scalar_features], dim=1))

    def q_values(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        q_values = self.q_head(features)
        masked_q_values = q_values.masked_fill(action_mask <= 0, torch.finfo(q_values.dtype).min)
        value = self.value_head(features).squeeze(-1)
        return masked_q_values, value

    def initialize_q_head_from_policy(self) -> None:
        """Warm-start the critic head from a BC policy checkpoint."""
        with torch.no_grad():
            self.q_head.weight.copy_(self.policy_head.weight)
            self.q_head.bias.copy_(self.policy_head.bias)


class ResidualBlock(nn.Module):
    """Small no-pooling residual block for semantic tile planes."""

    def __init__(self, channels: int) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        return torch.nn.functional.gelu(inputs + self.layers(inputs))
