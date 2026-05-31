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
        self.trunk = nn.Sequential(
            nn.Linear(
                model_config.plane_feature_dim + model_config.scalar_hidden_dim,
                model_config.trunk_hidden_dim,
            ),
            nn.GELU(),
        )
        self.policy_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        if model_config.dueling_q:
            self.q_head = DuelingQHead(
                model_config.trunk_hidden_dim,
                env_config.action_space_size,
                model_config.q_hidden_dim,
            )
        else:
            self.q_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        self.value_head = nn.Sequential(
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
            nn.Tanh(),
        )
        self.large_loss_head = nn.Sequential(
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 2),
        )

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)

        logits = self.policy_head(features)
        masked_logits = logits.masked_fill(action_mask <= 0, torch.finfo(logits.dtype).min)
        value = self.value_head(features).squeeze(-1)
        return masked_logits, value

    def encode(self, planes: Tensor, scalars: Tensor) -> Tensor:
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(planes))))
        expected_scalars = self.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        scalar_features = self.scalar_encoder(scalars)
        return self.trunk(torch.cat([plane_features, scalar_features], dim=1))

    def q_values(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        if isinstance(self.q_head, DuelingQHead):
            q_values = self.q_head(features, action_mask)
            value = self.value_head(features).squeeze(-1)
            return q_values, value
        q_values = self.q_head(features)
        masked_q_values = q_values.masked_fill(action_mask <= 0, torch.finfo(q_values.dtype).min)
        value = self.value_head(features).squeeze(-1)
        return masked_q_values, value

    def large_loss_predictions(self, planes: Tensor, scalars: Tensor, detach_features: bool = False) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        if detach_features:
            features = features.detach()
        risk_outputs = self.large_loss_head(features)
        probability_logits = risk_outputs[:, 0]
        severity = torch.nn.functional.softplus(risk_outputs[:, 1])
        return probability_logits, severity

    def initialize_q_head_from_policy(self) -> None:
        """Warm-start the critic head from a BC policy checkpoint."""
        if isinstance(self.q_head, DuelingQHead):
            self.q_head.initialize_advantage_from_policy(self.policy_head)
            return
        with torch.no_grad():
            self.q_head.weight.copy_(self.policy_head.weight)
            self.q_head.bias.copy_(self.policy_head.bias)


class ChannelAttention2d(nn.Module):
    """Mortal-style channel attention over semantic tile planes."""

    def __init__(self, channels: int, ratio: int = 16) -> None:
        super().__init__()
        hidden = max(1, channels // max(1, ratio))
        self.shared_mlp = nn.Sequential(
            nn.Linear(channels, hidden),
            nn.GELU(),
            nn.Linear(hidden, channels),
        )

    def forward(self, inputs: Tensor) -> Tensor:
        avg_out = self.shared_mlp(inputs.mean(dim=(-2, -1)))
        max_out = self.shared_mlp(inputs.amax(dim=(-2, -1)))
        weights = torch.sigmoid(avg_out + max_out).unsqueeze(-1).unsqueeze(-1)
        return inputs * weights


class ResidualBlock(nn.Module):
    """Small no-pooling residual block for semantic tile planes."""

    def __init__(self, channels: int, channel_attention: bool = False, attention_ratio: int = 16) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
        )
        self.channel_attention = ChannelAttention2d(channels, attention_ratio) if channel_attention else nn.Identity()

    def forward(self, inputs: Tensor) -> Tensor:
        return torch.nn.functional.gelu(inputs + self.channel_attention(self.layers(inputs)))


class DuelingQHead(nn.Module):
    """Masked dueling action-value head for discrete offline RL."""

    def __init__(self, trunk_dim: int, action_space_size: int, hidden_dim: int) -> None:
        super().__init__()
        self.value_head = nn.Sequential(
            nn.Linear(trunk_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, 1),
        )
        self.advantage_head = nn.Sequential(
            nn.Linear(trunk_dim, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, action_space_size),
        )

    def forward(self, features: Tensor, action_mask: Tensor) -> Tensor:
        legal = action_mask > 0
        value = self.value_head(features)
        advantage = self.advantage_head(features)
        legal_count = legal.sum(dim=-1, keepdim=True).clamp_min(1)
        advantage_mean = advantage.masked_fill(~legal, 0.0).sum(dim=-1, keepdim=True) / legal_count
        q_values = value + advantage - advantage_mean
        return q_values.masked_fill(~legal, torch.finfo(q_values.dtype).min)

    def initialize_advantage_from_policy(self, policy_head: nn.Linear) -> None:
        final_layer = self.advantage_head[-1]
        if not isinstance(final_layer, nn.Linear):
            return
        with torch.no_grad():
            if final_layer.weight.shape == policy_head.weight.shape:
                final_layer.weight.copy_(policy_head.weight)
                final_layer.bias.copy_(policy_head.bias)
