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
        self.policy_channels = channels  # 39: the stem consumes exactly these
        self.model_config = model_config

        trunk_in = model_config.plane_feature_dim + model_config.scalar_hidden_dim
        if model_config.event_window > 0:
            self.event_encoder = EventEncoder(model_config.event_embed_dim, model_config.event_hidden_dim)
            trunk_in += model_config.event_hidden_dim
        self.trunk = nn.Sequential(
            nn.Linear(trunk_in, model_config.trunk_hidden_dim),
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
        value_in = model_config.trunk_hidden_dim
        if model_config.privileged_critic:
            self.privileged_encoder = nn.Sequential(
                nn.Conv2d(12, 32, kernel_size=3, padding=1),
                nn.GELU(),
                nn.Flatten(start_dim=1),
                nn.Linear(32 * height * width, 128),
                nn.GELU(),
            )
            value_in += 128
        self.value_head = nn.Sequential(
            nn.Linear(value_in, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 1),
            nn.Tanh(),
        )
        if model_config.aux_heads:
            self.belief_head = nn.Linear(model_config.trunk_hidden_dim, 12 * 42)
            self.dealin_head = nn.Linear(model_config.trunk_hidden_dim, 1)
            self.rank_head = nn.Linear(model_config.trunk_hidden_dim, 5)
        self.large_loss_head = nn.Sequential(
            nn.Linear(model_config.trunk_hidden_dim, model_config.value_hidden_dim),
            nn.GELU(),
            nn.Linear(model_config.value_hidden_dim, 2),
        )
        self.action_risk_probability_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)
        self.action_risk_severity_head = nn.Linear(model_config.trunk_hidden_dim, env_config.action_space_size)

    @property
    def wants_events(self) -> bool:
        return self.model_config.event_window > 0

    def forward(self, planes: Tensor, scalars: Tensor, action_mask: Tensor,
                events: Tensor | None = None, event_lengths: Tensor | None = None) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars, events, event_lengths)

        logits = self.policy_head(features)
        masked_logits = logits.masked_fill(action_mask <= 0, torch.finfo(logits.dtype).min)
        value = self.value_head(self._value_features(features, planes)).squeeze(-1)
        return masked_logits, value

    def encode(self, planes: Tensor, scalars: Tensor, events: Tensor | None = None,
               event_lengths: Tensor | None = None) -> Tensor:
        policy_planes = planes[:, : self.policy_channels]
        plane_features = self.plane_head(self.plane_projection(self.plane_blocks(self.plane_stem(policy_planes))))
        expected_scalars = self.scalar_encoder[0].in_features
        if scalars.shape[1] < expected_scalars:
            scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
        elif scalars.shape[1] > expected_scalars:
            raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
        scalar_features = self.scalar_encoder(scalars)
        parts = [plane_features, scalar_features]
        if self.wants_events:
            if events is None or event_lengths is None:
                batch = planes.shape[0]
                event_features = torch.zeros(batch, self.model_config.event_hidden_dim,
                                             device=planes.device, dtype=plane_features.dtype)
            else:
                event_features = self.event_encoder(events, event_lengths)
            parts.append(event_features)
        return self.trunk(torch.cat(parts, dim=1))

    def _value_features(self, features: Tensor, planes: Tensor) -> Tensor:
        if not self.model_config.privileged_critic:
            return features
        if planes.shape[1] >= 51:
            priv = self.privileged_encoder(planes[:, self.policy_channels : self.policy_channels + 12])
        else:
            priv = torch.zeros(planes.shape[0], 128, device=planes.device, dtype=features.dtype)
        return torch.cat([features, priv], dim=1)

    def aux_predictions(self, features: Tensor) -> dict:
        return {
            "belief": self.belief_head(features).view(-1, 12, 42),
            "dealin": self.dealin_head(features).squeeze(-1),
            "rank": self.rank_head(features),
        }

    def q_values(self, planes: Tensor, scalars: Tensor, action_mask: Tensor) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        if isinstance(self.q_head, DuelingQHead):
            q_values = self.q_head(features, action_mask)
            value = self.value_head(self._value_features(features, planes)).squeeze(-1)
            return q_values, value
        q_values = self.q_head(features)
        masked_q_values = q_values.masked_fill(action_mask <= 0, torch.finfo(q_values.dtype).min)
        value = self.value_head(self._value_features(features, planes)).squeeze(-1)
        return masked_q_values, value

    def large_loss_predictions(self, planes: Tensor, scalars: Tensor, detach_features: bool = False) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        if detach_features:
            features = features.detach()
        risk_outputs = self.large_loss_head(features)
        probability_logits = risk_outputs[:, 0]
        severity = torch.nn.functional.softplus(risk_outputs[:, 1])
        return probability_logits, severity

    def action_risk_predictions(
        self,
        planes: Tensor,
        scalars: Tensor,
        action_mask: Tensor,
        detach_features: bool = False,
    ) -> tuple[Tensor, Tensor]:
        features = self.encode(planes, scalars)
        if detach_features:
            features = features.detach()
        probability_logits = self.action_risk_probability_head(features)
        severity = torch.nn.functional.softplus(self.action_risk_severity_head(features))
        masked_probability_logits = probability_logits.masked_fill(
            action_mask <= 0,
            torch.finfo(probability_logits.dtype).min,
        )
        masked_severity = severity.masked_fill(action_mask <= 0, 0.0)
        return masked_probability_logits, masked_severity

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


from .events import NUM_EVENT_TYPES as _NUM_EVENT_TYPES

assert _NUM_EVENT_TYPES == 8, "EventEncoder token layout assumes 8 event types — update NUM_TOKENS math"


class EventEncoder(nn.Module):
    """GRU over the packed public-event history (Spec B2b).

    Input: raw packed uint32 codec values as int64 [B, W] + lengths [B].
    Bit layout (events.py): type 0-3 | rel_seat 4-5 | face 6-11 |
    rel_from 12-13 | tsumogiri bit 14 | haitei bit 15.
    Token = (type*4 + rel_seat)*64 + face  in [0, 2048).
    """

    NUM_TOKENS = 8 * 4 * 64  # 2048; the 8 is events.NUM_EVENT_TYPES (asserted below)

    def __init__(self, embed_dim: int, hidden_dim: int) -> None:
        super().__init__()
        self.embedding = nn.Embedding(self.NUM_TOKENS, embed_dim)
        self.side_proj = nn.Linear(6, embed_dim)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)
        self.hidden_dim = hidden_dim

    def forward(self, events: Tensor, lengths: Tensor) -> Tensor:
        # Decode bits on-device (cheap, vectorized).
        # Masked to 3 bits (NUM_EVENT_TYPES=8): the wire format reserves a 4-bit
        # field, but only types 0-7 are ever produced. Folding stray high bits
        # keeps the embedding lookup in-bounds without altering any real event.
        ev_type = (events >> 0) & 0x7
        rel_seat = (events >> 4) & 0x3
        face = (events >> 6) & 0x3F
        rel_from = (events >> 12) & 0x3
        tsumogiri = ((events >> 14) & 0x1).float()
        haitei = ((events >> 15) & 0x1).float()
        tokens = (ev_type * 4 + rel_seat) * 64 + face
        side = torch.cat(
            [
                tsumogiri.unsqueeze(-1),
                haitei.unsqueeze(-1),
                torch.nn.functional.one_hot(rel_from, num_classes=4).float(),
            ],
            dim=-1,
        )
        x = self.embedding(tokens) + self.side_proj(side)
        out, _ = self.gru(x)  # [B, W, H] over the PADDED sequence
        # Gather the output at index length-1; zero-length rows -> zeros.
        batch = events.shape[0]
        idx = (lengths - 1).clamp(min=0).view(batch, 1, 1).expand(-1, 1, self.hidden_dim)
        gathered = out.gather(1, idx).squeeze(1)
        return gathered * (lengths > 0).float().unsqueeze(-1)


def infer_model_config(state_dict: dict[str, Tensor]) -> ModelConfig:
    """Recover the ModelConfig of a saved PolicyValueNet from its state dict.

    Checkpoints produced by different runs vary in depth/width/heads, and the
    architecture is fully determined by tensor shapes — loaders must not
    assume ModelConfig defaults.
    """
    if any(key.startswith(("event_encoder.", "privileged_encoder.", "belief_head.",
                           "dealin_head.", "rank_head.")) for key in state_dict):
        raise RuntimeError(
            "this checkpoint carries Spec B2b modules (event encoder / privileged critic / "
            "aux heads), which infer_model_config cannot reconstruct — checkpoint-backed "
            "serving and self-play for B2b models land in Spec B2c. Evaluate B2b checkpoints "
            "with fh-mj-evaluate and explicit --model-event-window/--model-privileged-critic/"
            "--model-aux-heads flags instead."
        )
    defaults = ModelConfig()
    channels = int(state_dict["plane_stem.0.weight"].shape[0])
    block_indices = {
        int(key.split(".")[1]) for key in state_dict if key.startswith("plane_blocks.")
    }
    attention_key = "plane_blocks.0.channel_attention.shared_mlp.0.weight"
    channel_attention = attention_key in state_dict
    if channel_attention:
        hidden = int(state_dict[attention_key].shape[0])
        channel_attention_ratio = max(1, channels // hidden)
    else:
        channel_attention_ratio = defaults.channel_attention_ratio
    dueling_q = "q_head.value_head.0.weight" in state_dict
    return ModelConfig(
        channels=channels,
        residual_blocks=max(block_indices) + 1 if block_indices else 0,
        plane_feature_dim=int(state_dict["plane_head.0.weight"].shape[0]),
        scalar_hidden_dim=int(state_dict["scalar_encoder.0.weight"].shape[0]),
        trunk_hidden_dim=int(state_dict["trunk.0.weight"].shape[0]),
        value_hidden_dim=int(state_dict["value_head.0.weight"].shape[0]),
        q_hidden_dim=int(state_dict["q_head.value_head.0.weight"].shape[0])
        if dueling_q
        else defaults.q_hidden_dim,
        pool_planes=int(state_dict["plane_head.0.weight"].shape[1]) == channels,
        channel_attention=channel_attention,
        channel_attention_ratio=channel_attention_ratio,
        dueling_q=dueling_q,
    )
