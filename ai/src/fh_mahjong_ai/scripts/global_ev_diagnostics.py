"""Score paired-trace first divergences with a frozen global EV model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.global_ev import ActionGlobalEVNet, GlobalEVNet
from fh_mahjong_ai.global_ev_diagnostics import score_paired_trace_global_ev
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.storage import load_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose paired first divergences with global EV")
    parser.add_argument("--global-ev-checkpoint", type=Path, required=True)
    parser.add_argument("--paired-trace-report", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="anchor")
    parser.add_argument("--right-label", type=str, default="candidate")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument(
        "--action-conditioned",
        action="store_true",
        help="Load an EV(state, action_id) checkpoint and compare first-divergence actions.",
    )
    parser.add_argument("--max-cases", type=int, default=12)
    parser.add_argument(
        "--guard-margin",
        type=float,
        action="append",
        default=[0.0, -0.02, -0.05],
        help=(
            "Candidate action is allowed when predicted candidate-anchor EV delta is at least this margin. "
            "Repeat for multiple preflight thresholds."
        ),
    )
    parser.add_argument("--report-output", type=Path, required=True)
    add_model_config_args(parser)
    args = parser.parse_args()

    model_config = model_config_from_args(args)
    scalar_features = checkpoint_scalar_features(args.global_ev_checkpoint)
    model = (
        ActionGlobalEVNet(EnvConfig(scalar_features=scalar_features), model_config)
        if args.action_conditioned
        else GlobalEVNet(EnvConfig(scalar_features=scalar_features), model_config)
    ).to(args.device)
    step = load_checkpoint(args.global_ev_checkpoint, model)
    report = json.loads(args.paired_trace_report.read_text(encoding="utf-8"))
    diagnostics = score_paired_trace_global_ev(
        report,
        model,
        device=args.device,
        left_label=args.left_label,
        right_label=args.right_label,
        max_cases=args.max_cases,
        action_conditioned=args.action_conditioned,
        guard_margins=args.guard_margin,
    )
    diagnostics["global_ev_checkpoint"] = str(args.global_ev_checkpoint)
    diagnostics["global_ev_checkpoint_step"] = int(step)
    diagnostics["paired_trace_report"] = str(args.paired_trace_report)
    diagnostics["device"] = args.device

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Scoreable divergences: {diagnostics['scoreable_divergences']}")
    print(f"MAE:                   {diagnostics['metrics']['mae']:.4f}")
    print(f"Correlation:           {diagnostics['metrics']['correlation']:.4f}")
    print(f"Sign accuracy:         {diagnostics['sign_accuracy']:.2%}")
    print(f"Harmful recall:        {diagnostics['harmful_predicted_harmful_rate']:.2%}")
    for margin, summary in diagnostics["guard_preflight"].items():
        print(
            f"Guard margin {margin}: allowed={summary['allowed_count']} "
            f"harmful_block_rate={summary['harmful_block_rate']:.2%} "
            f"actual_allowed_delta_sum={summary['actual_allowed_delta_sum']:.4f}"
        )
    print(f"Report saved to {args.report_output}")


def checkpoint_scalar_features(path: Path) -> int:
    payload = torch.load(path, map_location="cpu")
    weight = payload.get("model", {}).get("scalar_encoder.0.weight")
    if weight is None:
        return EnvConfig().scalar_features
    return int(weight.shape[1])


if __name__ == "__main__":
    main()
