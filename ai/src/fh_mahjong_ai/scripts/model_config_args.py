from __future__ import annotations

import argparse

from fh_mahjong_ai.config import ModelConfig


def add_model_config_args(parser: argparse.ArgumentParser) -> None:
    defaults = ModelConfig()
    parser.add_argument("--model-channels", type=int, default=defaults.channels)
    parser.add_argument("--model-residual-blocks", type=int, default=defaults.residual_blocks)
    parser.add_argument("--model-plane-feature-dim", type=int, default=defaults.plane_feature_dim)
    parser.add_argument("--model-scalar-hidden-dim", type=int, default=defaults.scalar_hidden_dim)
    parser.add_argument("--model-trunk-hidden-dim", type=int, default=defaults.trunk_hidden_dim)
    parser.add_argument("--model-value-hidden-dim", type=int, default=defaults.value_hidden_dim)
    parser.add_argument("--model-q-hidden-dim", type=int, default=defaults.q_hidden_dim)
    parser.add_argument("--model-pool-planes", action="store_true", default=defaults.pool_planes)
    parser.add_argument("--model-channel-attention", action="store_true", default=defaults.channel_attention)
    parser.add_argument("--model-channel-attention-ratio", type=int, default=defaults.channel_attention_ratio)
    parser.add_argument("--model-no-dueling-q", action="store_true")
    parser.add_argument("--model-event-window", type=int, default=defaults.event_window)
    parser.add_argument("--model-privileged-critic", action="store_true", default=defaults.privileged_critic)
    parser.add_argument("--model-aux-heads", action="store_true", default=defaults.aux_heads)


def model_config_from_args(args: argparse.Namespace) -> ModelConfig:
    return ModelConfig(
        channels=args.model_channels,
        residual_blocks=args.model_residual_blocks,
        plane_feature_dim=args.model_plane_feature_dim,
        scalar_hidden_dim=args.model_scalar_hidden_dim,
        trunk_hidden_dim=args.model_trunk_hidden_dim,
        value_hidden_dim=args.model_value_hidden_dim,
        q_hidden_dim=args.model_q_hidden_dim,
        pool_planes=args.model_pool_planes,
        channel_attention=args.model_channel_attention,
        channel_attention_ratio=args.model_channel_attention_ratio,
        dueling_q=not args.model_no_dueling_q,
        event_window=args.model_event_window,
        privileged_critic=args.model_privileged_critic,
        aux_heads=args.model_aux_heads,
    )


def model_config_params(model_config: ModelConfig) -> dict[str, object]:
    return {
        "model_channels": model_config.channels,
        "model_residual_blocks": model_config.residual_blocks,
        "model_plane_feature_dim": model_config.plane_feature_dim,
        "model_scalar_hidden_dim": model_config.scalar_hidden_dim,
        "model_trunk_hidden_dim": model_config.trunk_hidden_dim,
        "model_value_hidden_dim": model_config.value_hidden_dim,
        "model_q_hidden_dim": model_config.q_hidden_dim,
        "model_pool_planes": model_config.pool_planes,
        "model_channel_attention": model_config.channel_attention,
        "model_channel_attention_ratio": model_config.channel_attention_ratio,
        "model_dueling_q": model_config.dueling_q,
        "model_event_window": model_config.event_window,
        "model_privileged_critic": model_config.privileged_critic,
        "model_aux_heads": model_config.aux_heads,
        "model_growth_blocks": model_config.growth_blocks,
    }
