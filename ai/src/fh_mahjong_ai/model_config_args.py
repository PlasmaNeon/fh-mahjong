from __future__ import annotations

import argparse

from fh_mahjong_ai.config import ModelConfig


def add_model_config_args(parser: argparse.ArgumentParser) -> None:
    defaults = ModelConfig()
    parser.add_argument("--model-channels", type=int, default=defaults.channels)
    parser.add_argument("--model-residual-blocks", type=int, default=defaults.residual_blocks)
    parser.add_argument("--model-kernel-width", type=int, choices=(1, 3), default=defaults.kernel_width,
                        help="conv kernel width over the plane axis: 3 = historical 3x3 "
                             "(default), 1 = Mortal-style (3,1) 1-D kernels")
    parser.add_argument("--model-trunk-rezero", action="store_true", default=defaults.trunk_rezero,
                        help="build every main residual block as a ReZero block "
                             "(x + alpha*F(x), alpha init 0, no trailing GELU) so deep "
                             "trunks start as the identity; mortal-scale-scratch Amendment 3")
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
    parser.add_argument("--model-event-hidden-dim", type=int, default=defaults.event_hidden_dim,
                        help="event-GRU hidden width (gru-width lap); only used on the "
                             "explicit-flag ModelConfig path, i.e. when the checkpoint carries "
                             "no usable metadata")
    parser.add_argument("--model-event-output-dim", type=int, default=defaults.event_output_dim,
                        help="event-encoder output-projection width; 0 (default) = equal to "
                             "--model-event-hidden-dim (no projection, dormant); only used on "
                             "the explicit-flag ModelConfig path")
    parser.add_argument("--model-privileged-critic", action="store_true", default=defaults.privileged_critic)
    parser.add_argument("--model-aux-heads", action="store_true", default=defaults.aux_heads)


def model_config_from_args(args: argparse.Namespace, *, event_window: int | None = None) -> ModelConfig:
    """Build a `ModelConfig` from parsed CLI args in ONE construction.

    `event_window` overrides `args.model_event_window` -- callers that have
    a separate, more-authoritative event-window value (e.g. `train_b2b.py`'s
    own `--event-window`, which is NOT the same flag as `--model-event-window`)
    must pass it here rather than constructing a `ModelConfig` from
    `args.model_event_window` first and `dataclasses.replace`-ing the
    effective window in afterward. Adversarial round 6, high finding: that
    two-step pattern builds an INTERMEDIATE `ModelConfig` with whatever
    `--model-event-window` defaults to (0) while `--model-event-output-dim`
    may already be nonzero on the CLI -- `ModelConfig.__post_init__`'s round-2
    rejection (`event_output_dim != 0` requires `event_window != 0`) fires on
    that intermediate object before the `replace()` ever runs, so the
    documented resume recipe (which carries the widened
    `--model-event-hidden-dim`/`--model-event-output-dim` alongside
    `--event-window`, not `--model-event-window`) raised unconditionally.
    Threading the effective window into this single constructor call means
    no invalid intermediate `ModelConfig` is ever built.
    """
    return ModelConfig(
        channels=args.model_channels,
        residual_blocks=args.model_residual_blocks,
        kernel_width=args.model_kernel_width,
        trunk_rezero=args.model_trunk_rezero,
        plane_feature_dim=args.model_plane_feature_dim,
        scalar_hidden_dim=args.model_scalar_hidden_dim,
        trunk_hidden_dim=args.model_trunk_hidden_dim,
        value_hidden_dim=args.model_value_hidden_dim,
        q_hidden_dim=args.model_q_hidden_dim,
        pool_planes=args.model_pool_planes,
        channel_attention=args.model_channel_attention,
        channel_attention_ratio=args.model_channel_attention_ratio,
        dueling_q=not args.model_no_dueling_q,
        event_window=args.model_event_window if event_window is None else event_window,
        event_hidden_dim=args.model_event_hidden_dim,
        event_output_dim=args.model_event_output_dim,
        privileged_critic=args.model_privileged_critic,
        aux_heads=args.model_aux_heads,
    )


def model_config_params(model_config: ModelConfig) -> dict[str, object]:
    return {
        "model_channels": model_config.channels,
        "model_residual_blocks": model_config.residual_blocks,
        "model_kernel_width": model_config.kernel_width,
        "model_trunk_rezero": model_config.trunk_rezero,
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
        "model_event_hidden_dim": model_config.event_hidden_dim,
        "model_event_output_dim": model_config.event_output_dim,
        "model_privileged_critic": model_config.privileged_critic,
        "model_aux_heads": model_config.aux_heads,
        "model_growth_blocks": model_config.growth_blocks,
    }
