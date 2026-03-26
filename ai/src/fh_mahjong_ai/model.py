from __future__ import annotations

import torch
from torch import Tensor, nn

from .config import EnvConfig, ModelConfig


class PolicyValueNet(nn.Module):
    """Masked-action policy/value network for Mahjong observations."""

    def __init__(self, env_config: EnvConfig, model_config: ModelConfig) -> None:
        super().__init__()
        channels, _, _ = env_config.plane_shape

        self.plane_encoder = nn.Sequential(
            nn.Conv2d(channels, model_config.channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv2d(model_config.channels, model_config.channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.scalar_encoder = nn.Sequential(
            nn.Linear(env_config.scalar_features, model_config.scalar_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.scalar_hidden_dim, model_config.scalar_hidden_dim),
            nn.GELU(),
        )
        self.trunk = nn.Sequential(
            nn.Linear(model_config.channels + model_config.scalar_hidden_dim, model_config.trunk_hidden_dim),
            nn.GELU(),
        )
        self.policy_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        self.value_head = nn.Sequential(
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
            nn.Tanh(),
        )

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        plane_features = self.plane_encoder(planes).flatten(start_dim=1)
        scalar_features = self.scalar_encoder(scalars)
        features = self.trunk(torch.cat([plane_features, scalar_features], dim=1))

        logits = self.policy_head(features)
        masked_logits = logits.masked_fill(action_mask <= 0, torch.finfo(logits.dtype).min)
        value = self.value_head(features).squeeze(-1)
        return masked_logits, value
