"""Write detailed failure-slice diagnostics for branch-CF calibration reports."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fh_mahjong_ai.scripts.branch_cf_calibration import compute_branch_cf_calibration


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze branch-CF rows where policy/Q/risk disagree with labels")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    report = compute_branch_cf_calibration(
        checkpoint=args.checkpoint,
        data_path=args.data,
        batch_size=args.batch_size,
        device=args.device,
        max_transitions=args.max_transitions,
    )
    diagnostics: dict[str, Any] = {
        "schema_version": 1,
        "checkpoint": report["checkpoint"],
        "checkpoint_step": report["checkpoint_step"],
        "data": report["data"],
        "device": report["device"],
        "rows": report["rows"],
        "policy_logits": report["policy_logits"],
        "q_values": report["q_values"],
        "argmax": report["argmax"],
        "diagnostics": report["diagnostics"],
    }
    if "action_risk_probability_lower_is_better" in report:
        diagnostics["action_risk_probability_lower_is_better"] = report["action_risk_probability_lower_is_better"]

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    q_misrank = diagnostics["diagnostics"]["segments"]["q_misrank"]
    high_gap_q_misrank = diagnostics["diagnostics"]["segments"]["high_gap_q_misrank"]
    print(f"Rows:                  {diagnostics['rows']}")
    print(f"Q misrank rows:        {q_misrank['count']} ({q_misrank['rate']:.2%})")
    print(f"High-gap Q misranks:   {high_gap_q_misrank['count']} ({high_gap_q_misrank['rate']:.2%})")
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
