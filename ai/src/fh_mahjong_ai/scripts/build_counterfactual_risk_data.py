"""CLI for building action-risk shards; reusable helpers live in counterfactual_data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# Keep the historical imports available to external scripts and notebooks.
from fh_mahjong_ai.counterfactual_data import (
    build_counterfactual_risk_arrays,
    selected_divergences,
    write_counterfactual_shard,
)


__all__ = [
    "build_counterfactual_risk_arrays",
    "selected_divergences",
    "write_counterfactual_shard",
    "main",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build direct counterfactual action-risk shards")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="anchor")
    parser.add_argument("--right-label", type=str, default="candidate")
    parser.add_argument("--large-loss-threshold", type=float, default=-1.0)
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--high-risk-only", action="store_true")
    parser.add_argument(
        "--preferred-policy",
        type=str,
        default=None,
        help=(
            "Keep only counterfactual rows where this report policy label is the preferred side. "
            "For example, use promoted_anchor to reinforce the promoted policy against rejected candidates."
        ),
    )
    parser.add_argument(
        "--preferred-action-family",
        type=str,
        default=None,
        help="Keep only counterfactual rows whose preferred action family matches this value.",
    )
    parser.add_argument(
        "--avoided-action-family",
        type=str,
        default=None,
        help="Keep only counterfactual rows whose avoided action family matches this value.",
    )
    parser.add_argument(
        "--training-target-policy",
        choices=("avoided", "preferred"),
        default="avoided",
        help=(
            "Choose which side supplies action_ids and terminal_rewards. "
            "Use avoided for risk/negative examples and preferred for teacher-policy distillation examples."
        ),
    )
    parser.add_argument(
        "--divergence-source",
        choices=("first", "later", "all"),
        default="first",
        help=(
            "Which paired-trace disagreements to convert. first is strict same-state counterfactual; "
            "later/all are aligned disagreements for risk calibration only."
        ),
    )
    args = parser.parse_args()

    arrays, metadata = build_counterfactual_risk_arrays(
        args.report,
        left_label=args.left_label,
        right_label=args.right_label,
        large_loss_threshold=args.large_loss_threshold,
        min_reward_gap=args.min_reward_gap,
        high_risk_only=args.high_risk_only,
        preferred_policy=args.preferred_policy,
        preferred_action_family=args.preferred_action_family,
        avoided_action_family=args.avoided_action_family,
        training_target_policy=args.training_target_policy,
        divergence_source=args.divergence_source,
    )
    manifest = write_counterfactual_shard(args.output_dir, arrays, metadata)
    print(json.dumps(manifest["counterfactual"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
