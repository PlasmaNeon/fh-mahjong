from __future__ import annotations

import re

import torch
from torch import Tensor, nn

from .config import EnvConfig, ModelConfig

# Optional-head prefixes load_checkpoint already treats as backward/forward
# compatible (strict=False); the cross-check below must not flag them.
_COMPATIBLE_OPTIONAL_PREFIXES = (
    "q_head.", "large_loss_head.", "action_risk_probability_head.", "action_risk_severity_head.",
)
_B2B_MODULE_PREFIXES = (
    "event_encoder.", "privileged_encoder.", "belief_head.", "dealin_head.", "rank_head.",
)
_GROWTH_MODULE_PREFIX = "growth."
_GROWTH_ALPHA_RE = re.compile(r"^growth\.([^.]+)\.alpha$")


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
            self.event_encoder = EventEncoder(
                model_config.event_embed_dim,
                model_config.event_hidden_dim,
                model_config.event_output_dim,
            )
            trunk_in += self.event_encoder.output_dim
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
        # deep16-rezero: constructed last so that, at growth_blocks=0 (empty Sequential,
        # zero new state_dict keys), every module above consumes RNG identically to
        # before this feature existed. Applied functionally right after the legacy
        # residual stack in encode() below.
        self.growth = nn.Sequential(
            *[
                ReZeroResidualBlock(
                    model_config.channels,
                    channel_attention=model_config.channel_attention,
                    attention_ratio=model_config.channel_attention_ratio,
                )
                for _ in range(model_config.growth_blocks)
            ]
        )

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
        plane_trunk = self.growth(self.plane_blocks(self.plane_stem(policy_planes)))
        plane_features = self.plane_head(self.plane_projection(plane_trunk))
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
                event_features = torch.zeros(batch, self.event_encoder.output_dim,
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


class ReZeroResidualBlock(nn.Module):
    """ReZero-style residual block: x + alpha * attn(F(x)), alpha a learned scalar init to 0.

    No trailing activation (unlike ResidualBlock): with alpha starting at exactly 0,
    this makes the block an exact identity at init regardless of F's random weights,
    so stacking these for capacity growth is dormant until training moves alpha.
    """

    def __init__(self, channels: int, channel_attention: bool = False, attention_ratio: int = 16) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
            nn.GELU(),
            nn.Conv2d(channels, channels, kernel_size=3, padding=1),
        )
        self.channel_attention = ChannelAttention2d(channels, attention_ratio) if channel_attention else nn.Identity()
        self.alpha = nn.Parameter(torch.zeros(()))

    def forward(self, inputs: Tensor) -> Tensor:
        return inputs + self.alpha * self.channel_attention(self.layers(inputs))


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

    def __init__(self, embed_dim: int, hidden_dim: int, output_dim: int = 0) -> None:
        super().__init__()
        self.embedding = nn.Embedding(self.NUM_TOKENS, embed_dim)
        self.side_proj = nn.Linear(6, embed_dim)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)
        self.hidden_dim = hidden_dim
        # output_dim == 0 or == hidden_dim both collapse to "no projection"
        # (dormant): the widening lap's step-zero invariant is that
        # event_output_dim equal to event_hidden_dim is indistinguishable
        # from the default, down to the state_dict itself.
        self.output_proj: nn.Linear | None = None
        if output_dim not in (0, hidden_dim):
            self.output_proj = nn.Linear(hidden_dim, output_dim)

    @property
    def output_dim(self) -> int:
        return self.output_proj.out_features if self.output_proj is not None else self.hidden_dim

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
        result = gathered * (lengths > 0).float().unsqueeze(-1)
        if self.output_proj is not None:
            result = self.output_proj(result)
        return result


def _first_effective_block_attention_key(residual_blocks: int) -> str:
    """The state-dict key of the `ChannelAttention2d.shared_mlp` inside
    whichever block actually runs FIRST in `encode()`'s
    `self.growth(self.plane_blocks(self.plane_stem(...)))` chain.

    `ResidualBlock` (in `plane_blocks`) and `ReZeroResidualBlock` (in
    `growth`) both build their attention submodule the same way (a
    `ChannelAttention2d` at `<prefix>.channel_attention`), so whichever stack
    contributes the first block is where attention/its bottleneck width must
    be read from. When `residual_blocks > 0`, `plane_blocks.0` runs first;
    otherwise (a residual-free architecture, e.g. adversarial round 2,
    Finding 2: `residual_blocks=0` with `growth_blocks>0`) `growth.0` is the
    first — and only — place attention can appear. Reading `plane_blocks.0`
    unconditionally previously derived `channel_attention=False` for any
    residual-free checkpoint regardless of what `growth.0` actually carried,
    causing a valid attention+growth checkpoint's own metadata to be
    rejected."""
    prefix = "plane_blocks.0" if residual_blocks > 0 else "growth.0"
    return f"{prefix}.channel_attention.shared_mlp.0.weight"


def _shape_inferred_fields(state_dict: dict[str, Tensor]) -> dict:
    """Fields recoverable purely from tensor shapes.

    This covers legacy (pre-B2b) checkpoints in full, and B2b checkpoints
    partially: `event_embed_dim`/`event_hidden_dim`/`privileged_critic`/
    `aux_heads` are shape-derived, but `event_window` is NOT — no weight
    tensor encodes the max event-history length (the GRU is length-agnostic),
    so callers reconstructing a B2b checkpoint must overlay `event_window`
    (and, for robustness, the other three B2b flags) from metadata.
    """
    defaults = ModelConfig()
    channels = int(state_dict["plane_stem.0.weight"].shape[0])
    block_indices = {
        int(key.split(".")[1]) for key in state_dict if key.startswith("plane_blocks.")
    }
    residual_blocks = max(block_indices) + 1 if block_indices else 0
    attention_key = _first_effective_block_attention_key(residual_blocks)
    channel_attention = attention_key in state_dict
    if channel_attention:
        hidden = int(state_dict[attention_key].shape[0])
        channel_attention_ratio = max(1, channels // hidden)
    else:
        channel_attention_ratio = defaults.channel_attention_ratio
    dueling_q = "q_head.value_head.0.weight" in state_dict
    fields = dict(
        channels=channels,
        residual_blocks=residual_blocks,
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
        privileged_critic="privileged_encoder.0.weight" in state_dict,
        aux_heads="belief_head.weight" in state_dict,
    )
    if "event_encoder.embedding.weight" in state_dict:
        fields["event_embed_dim"] = int(state_dict["event_encoder.embedding.weight"].shape[1])
    if "event_encoder.gru.weight_ih_l0" in state_dict:
        fields["event_hidden_dim"] = int(state_dict["event_encoder.gru.weight_ih_l0"].shape[0]) // 3
    return fields


def _derive_growth_blocks(state_dict: dict[str, Tensor]) -> int:
    """Derive the deep16-rezero growth-block count from `growth.{i}.alpha` keys.

    Every `ReZeroResidualBlock` carries exactly one `alpha` parameter (plus
    conv/attention tensors under the same numeric index), so counting alpha
    keys — rather than every key under the `growth.` prefix — avoids
    double-counting a single block's other tensors. This is intentionally
    NOT folded into `_shape_inferred_fields`: unlike every other shape-derived
    field, a checkpoint carrying `growth.*` keys must still be rejected
    up front when there is no usable metadata (see `infer_model_config`'s
    `has_growth_keys` fail-closed branch) rather than silently shape-inferred,
    so this helper is only ever consulted once metadata is already known to
    be present.

    Indices must form the contiguous set `0..N-1`. A non-integer token or a
    gap means the state dict itself is malformed or tampered with, so this
    fails closed instead of guessing at a block count.
    """
    indices: list[int] = []
    for key in state_dict:
        match = _GROWTH_ALPHA_RE.match(key)
        if match is None:
            continue
        token = match.group(1)
        if not token.isdigit():
            raise RuntimeError(
                f"growth block index {token!r} in state dict key {key!r} is not a "
                "valid non-negative integer -- state dict appears malformed or tampered"
            )
        indices.append(int(token))
    if not indices:
        return 0
    indices.sort()
    if indices != list(range(len(indices))):
        raise RuntimeError(
            "growth.*.alpha indices are not the contiguous set 0..N-1: found "
            f"{indices} -- state dict appears malformed or tampered"
        )
    return len(indices)


def _effective_attention_hidden(channels: int, ratio: int) -> int:
    """The attention bottleneck width `ChannelAttention2d.__init__` actually
    constructs for a given (channels, ratio) pair. Must match that formula
    exactly (see `ChannelAttention2d.__init__` above): multiple ratios can
    floor to the same hidden width, so the raw ratio is not what a shape
    cross-check can recover or compare."""
    return max(1, channels // max(1, ratio))


def _verify_metadata_matches_shapes(config: ModelConfig, state_dict: dict[str, Tensor]) -> None:
    """Cross-check every metadata-claimed field that is ALSO derivable from
    `state_dict`'s tensor shapes, cheaply (no allocation) and BEFORE any
    `PolicyValueNet` is constructed (adversarial round 20, Finding 1b).

    `ModelConfig.__post_init__` bounds every dimension, but a bounded value
    can still be a lie: metadata claiming `channels=128` when the checkpoint
    was actually saved with `channels=96` is within bounds yet would build
    the wrong (still non-trivially large) net for nothing, and — more
    importantly — a value near the cap that happens to match no real
    checkpoint is still real memory. `_shape_inferred_fields` already knows
    how to read every one of these fields straight off tensor shapes (no
    model construction involved); reusing it here means a mismatch is
    caught before `infer_model_config` ever calls `PolicyValueNet(...)` for
    its later, more expensive, `_cross_check_shapes` comparison.

    Not every metadata field this compares against is unique, though (round
    26): `channel_attention_ratio` is never read by `ChannelAttention2d` when
    `channel_attention` is False, and distinct ratios can floor to the same
    effective hidden width (`_effective_attention_hidden`) when it is True;
    `q_hidden_dim` is never read when `dueling_q` is False. Comparing those
    raw fields unconditionally rejects a model's own honestly-saved metadata.
    Skip `channel_attention_ratio`/`q_hidden_dim` themselves and instead
    compare the effective attention width whenever attention is on — the
    quantity that actually determines the constructed architecture.
    """
    shape_fields = _shape_inferred_fields(state_dict)
    shape_fields.pop("channel_attention_ratio", None)
    if not config.dueling_q:
        shape_fields.pop("q_hidden_dim", None)

    mismatched = {
        field: (getattr(config, field), shape_value)
        for field, shape_value in shape_fields.items()
        if getattr(config, field) != shape_value
    }

    if config.channel_attention:
        claimed_hidden = _effective_attention_hidden(config.channels, config.channel_attention_ratio)
        attention_key = _first_effective_block_attention_key(config.residual_blocks)
        if attention_key in state_dict:
            actual_hidden = int(state_dict[attention_key].shape[0])
            if claimed_hidden != actual_hidden:
                mismatched["channel_attention_effective_hidden"] = (claimed_hidden, actual_hidden)

    # deep16-rezero (Task 3): `growth_blocks` is derivable from state-dict
    # keys (`_derive_growth_blocks`, contiguous `growth.{i}.alpha` count) just
    # like the fields above, but is intentionally kept out of
    # `_shape_inferred_fields` (see that helper's docstring) so a checkpoint
    # with no usable metadata still fails closed instead of being silently
    # shape-inferred. Metadata is known present here (this function only runs
    # when it is), so cross-check the claim against the derived count now —
    # BEFORE `PolicyValueNet` is ever constructed — catching both a doctored
    # over-claim (metadata says 5, checkpoint has 3) and a doctored
    # under-claim (metadata says 0 but the checkpoint actually carries
    # `growth.*` tensors).
    derived_growth_blocks = _derive_growth_blocks(state_dict)
    if config.growth_blocks != derived_growth_blocks:
        mismatched["growth_blocks"] = (config.growth_blocks, derived_growth_blocks)

    if mismatched:
        raise RuntimeError(
            "infer_model_config shape cross-check failed before construction: metadata "
            "claims ModelConfig fields that do not match the checkpoint's tensor shapes "
            f"(field: (claimed, shape_derived))={mismatched}"
        )


def _reconstruct_env_config(state_dict: dict[str, Tensor], model_config: ModelConfig) -> EnvConfig:
    """Rebuild just enough EnvConfig to instantiate a shape-matching throwaway
    PolicyValueNet for the cross-check below. Only tensor-shape-relevant
    fields matter here (input channel count, scalar count, action space,
    and the plane height*width area when it actually appears in a weight
    shape) — this is not the env the checkpoint was trained under."""
    input_channels = int(state_dict["plane_stem.0.weight"].shape[1])
    scalar_features = int(state_dict["scalar_encoder.0.weight"].shape[1])
    action_space_size = int(state_dict["policy_head.weight"].shape[0])
    if not model_config.pool_planes:
        area = int(state_dict["plane_head.0.weight"].shape[1]) // max(1, model_config.channels)
    elif model_config.privileged_critic and "privileged_encoder.3.weight" in state_dict:
        area = int(state_dict["privileged_encoder.3.weight"].shape[1]) // 32
    else:
        area = 42
    return EnvConfig(
        plane_shape=(input_channels, max(1, area), 1),
        scalar_features=scalar_features,
        action_space_size=action_space_size,
    )


def _cross_check_shapes(state_dict: dict[str, Tensor], reference_state: dict[str, Tensor]) -> None:
    given_keys = set(state_dict)
    ref_keys = set(reference_state)

    # A prefix is only exempt when the *entire* optional head is absent on one
    # side (the legitimate "older checkpoint predates this head" case). If both
    # sides carry keys under the prefix but the key sets differ (e.g. a
    # doctored `dueling_q` flag reconstructs DuelingQHead vs plain nn.Linear
    # under the same "q_head." prefix), that is a real architecture mismatch
    # and must not be exempted.
    exempt_prefixes = tuple(
        prefix
        for prefix in _COMPATIBLE_OPTIONAL_PREFIXES
        if not any(k.startswith(prefix) for k in given_keys)
        or not any(k.startswith(prefix) for k in ref_keys)
    )

    missing = sorted(k for k in ref_keys - given_keys if not k.startswith(exempt_prefixes))
    unexpected = sorted(k for k in given_keys - ref_keys if not k.startswith(exempt_prefixes))
    mismatched = sorted(
        key for key in given_keys & ref_keys
        if tuple(state_dict[key].shape) != tuple(reference_state[key].shape)
    )
    if missing or unexpected or mismatched:
        raise RuntimeError(
            "infer_model_config shape cross-check failed: the reconstructed ModelConfig does "
            "not reproduce the checkpoint's tensor shapes "
            f"(missing={missing}, unexpected={unexpected}, mismatched={mismatched})"
        )


def infer_model_config(state_dict: dict[str, Tensor], metadata: dict | None = None) -> ModelConfig:
    """Recover the ModelConfig of a saved PolicyValueNet from its state dict.

    Checkpoints produced by different runs vary in depth/width/heads, and the
    architecture is not always fully determined by tensor shapes — B2b's
    `event_window` in particular is invisible to every weight tensor. `metadata`
    (the checkpoint's saved `metadata` dict, if any) is consulted first:

    1. `metadata["model_config"]` (a complete ModelConfig, saved by newer
       B2b/B2c/deep16-rezero training paths) is authoritative if present.
    2. Otherwise `metadata["b2b"]` (the four-flag block older B2b checkpoints
       carry) overlays `event_window`/`privileged_critic`/`aux_heads`/
       `residual_blocks`; every other field is still shape-inferred (this
       predates deep16-rezero, so `growth_blocks` is never overlaid here —
       it stays whatever `_shape_inferred_fields` doesn't set, i.e. the
       ModelConfig default of 0).
    3. Otherwise, if the state dict carries no B2b modules and no
       deep16-rezero `growth.*` keys, everything is shape-inferred (the
       pre-B2b legacy path).
    4. Otherwise (B2b modules and/or `growth.*` keys present, no usable
       metadata) this raises — `event_window` cannot be recovered from
       shapes alone, and `growth_blocks`, while shape-derivable in
       principle, is deliberately still required to come from metadata (see
       `_derive_growth_blocks`'s docstring) so a stripped-metadata grown
       checkpoint fails with an explicit, clearly-messaged rejection instead
       of the generic shape-cross-check error it would otherwise hit deeper
       in `_cross_check_shapes`.

    In every case the reconstructed config is cross-checked by instantiating
    a throwaway PolicyValueNet and comparing its state dict's keys/shapes
    against `state_dict`; any mismatch raises. When metadata is present,
    `_verify_metadata_matches_shapes` additionally cross-checks every
    metadata field that IS derivable from shapes (including
    `growth_blocks`, via `_derive_growth_blocks`) BEFORE that throwaway
    `PolicyValueNet` is ever constructed.
    """
    metadata = metadata or {}
    has_b2b_modules = any(key.startswith(_B2B_MODULE_PREFIXES) for key in state_dict)
    has_growth_keys = any(key.startswith(_GROWTH_MODULE_PREFIX) for key in state_dict)

    model_config_meta = metadata.get("model_config")
    b2b_meta = metadata.get("b2b")
    if isinstance(model_config_meta, dict):
        config = ModelConfig(**model_config_meta)
    elif isinstance(b2b_meta, dict):
        fields = _shape_inferred_fields(state_dict)
        fields.update(
            event_window=int(b2b_meta["event_window"]),
            privileged_critic=bool(b2b_meta["privileged_critic"]),
            aux_heads=bool(b2b_meta["aux_heads"]),
            residual_blocks=int(b2b_meta["residual_blocks"]),
        )
        config = ModelConfig(**fields)
    elif has_b2b_modules or has_growth_keys:
        reasons = []
        if has_b2b_modules:
            reasons.append("Spec B2b modules (event encoder / privileged critic / aux heads)")
        if has_growth_keys:
            reasons.append("deep16-rezero growth blocks (growth.*)")
        raise RuntimeError(
            "this checkpoint carries " + " and ".join(reasons) + " but no usable metadata "
            "(\"model_config\" or \"b2b\"), so infer_model_config cannot reconstruct its "
            "ModelConfig from shapes alone. Re-save the checkpoint with metadata "
            "(save_checkpoint(..., metadata={\"model_config\": model_config_metadata(config)})), "
            "or evaluate it with fh-mj-evaluate and explicit --model-event-window/"
            "--model-privileged-critic/--model-aux-heads/--model-growth-blocks flags instead."
        )
    else:
        config = ModelConfig(**_shape_inferred_fields(state_dict))

    if isinstance(model_config_meta, dict) or isinstance(b2b_meta, dict):
        # Round 20, Finding 1b: metadata (either the whole-config or the
        # b2b-flag-overlay form) can claim fields that ARE derivable from
        # `state_dict`'s tensor shapes — `channels`, `residual_blocks`, etc.
        # Check those cheaply, without allocating anything, BEFORE the
        # throwaway `PolicyValueNet` below is ever constructed. The
        # shape-inferred-only branch above needs no such check: every field
        # it used already came from these same shapes.
        _verify_metadata_matches_shapes(config, state_dict)

    env_config = _reconstruct_env_config(state_dict, config)
    reference_state = PolicyValueNet(env_config, config).state_dict()
    _cross_check_shapes(state_dict, reference_state)
    return config
