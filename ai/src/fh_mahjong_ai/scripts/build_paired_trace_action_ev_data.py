"""Build action-EV shards from paired-trace first-divergence outcome deltas."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh_mahjong_ai.paired_trace_action_ev import build_paired_trace_action_ev_arrays
from fh_mahjong_ai.scripts.build_counterfactual_risk_data import write_counterfactual_shard


def main() -> None:
    parser = argparse.ArgumentParser(description="Build paired-trace action-EV training shards")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="anchor")
    parser.add_argument("--right-label", type=str, default="candidate")
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument(
        "--action-family",
        type=str,
        default=None,
        help="Keep only rows where both preferred and avoided first-divergence actions are in this family.",
    )
    parser.add_argument(
        "--divergence-source",
        choices=("first", "later", "all"),
        default="first",
        help="Use first strict divergence by default; later/all are aligned by trace index only.",
    )
    parser.add_argument(
        "--include-trajectory-context",
        action="store_true",
        help="Append pre-divergence history summary scalars recorded by paired_trace.py.",
    )
    args = parser.parse_args()

    arrays, metadata = build_paired_trace_action_ev_arrays(
        report_path=args.report,
        left_label=args.left_label,
        right_label=args.right_label,
        min_reward_gap=args.min_reward_gap,
        action_family=args.action_family,
        divergence_source=args.divergence_source,
        include_trajectory_context=args.include_trajectory_context,
    )
    manifest = write_counterfactual_shard(args.output_dir, arrays, metadata)
    print(json.dumps(manifest["counterfactual"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
