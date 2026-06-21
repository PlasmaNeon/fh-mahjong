"""CLI for Q/policy ranking diagnostics on tensor-bearing paired traces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.paired_trace_q_diagnostics import score_paired_trace_q_rank
from fh_mahjong_ai.storage import load_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Score Q/policy ranking on paired-trace divergence labels")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--paired-trace-report", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default=None)
    parser.add_argument("--right-label", type=str, default=None)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--divergence-source", choices=("first", "all"), default="first")
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    checkpoint_step = load_checkpoint(args.checkpoint, model)
    model.to(args.device)
    report = json.loads(args.paired_trace_report.read_text(encoding="utf-8"))
    diagnostics = score_paired_trace_q_rank(
        report,
        model=model,
        device=args.device,
        batch_size=args.batch_size,
        left_label=args.left_label,
        right_label=args.right_label,
        large_loss_threshold=args.large_loss_threshold,
        min_reward_gap=args.min_reward_gap,
        divergence_source=args.divergence_source,
    )
    diagnostics["checkpoint"] = str(args.checkpoint)
    diagnostics["checkpoint_step"] = int(checkpoint_step)
    diagnostics["paired_trace_report"] = str(args.paired_trace_report)

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rows:                  {diagnostics['rows']}")
    print(f"Policy preferred rate: {diagnostics['policy_logits']['preferred_rate']:.2%}")
    print(f"Q preferred rate:      {diagnostics['q_values']['preferred_rate']:.2%}")
    print(f"Q misrank rate:        {diagnostics['q_values']['misrank_rate']:.2%}")
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
