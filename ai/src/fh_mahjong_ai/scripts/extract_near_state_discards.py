"""Extract high-confidence near-state discard counterfactuals from paired traces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh_mahjong_ai.near_state_counterfactuals import extract_near_state_discard_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract near-state discard-vs-discard paired trace cases")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default=None)
    parser.add_argument("--right-label", type=str, default=None)
    parser.add_argument("--divergence-source", choices=("first", "later", "all"), default="later")
    parser.add_argument("--large-loss-threshold", type=float, default=-1.0)
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--max-decision-index-gap", type=int, default=0)
    parser.add_argument("--max-scalar-l1", type=float, default=0.10)
    parser.add_argument("--max-scalar-linf", type=float, default=0.25)
    parser.add_argument("--min-action-mask-jaccard", type=float, default=0.95)
    args = parser.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    extracted = extract_near_state_discard_cases(
        report,
        left_label=args.left_label,
        right_label=args.right_label,
        divergence_source=args.divergence_source,
        large_loss_threshold=args.large_loss_threshold,
        min_reward_gap=args.min_reward_gap,
        max_decision_index_gap=args.max_decision_index_gap,
        max_scalar_l1=args.max_scalar_l1,
        max_scalar_linf=args.max_scalar_linf,
        min_action_mask_jaccard=args.min_action_mask_jaccard,
    )
    extracted["source_report"] = str(args.report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(extracted, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = extracted["summary"]
    print(f"Cases:      {summary['cases']}")
    print(f"High risk:  {summary['high_risk_cases']}")
    print(f"Output:     {args.output}")


if __name__ == "__main__":
    main()
