"""Evaluate action-conditioned global EV on exact branch-CF labels."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.global_ev import ActionGlobalEVNet, BRANCH_ACTION_EV_ARRAY_KEYS, BRANCH_ACTION_EV_OPTIONAL_ARRAY_KEYS
from fh_mahjong_ai.global_ev_diagnostics import action_ev_branch_cf_calibration
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibrate action EV against exact branch-CF labels")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--guard-margin", type=float, action="append", default=[0.0, -0.02, -0.05])
    parser.add_argument("--report-output", type=Path, required=True)
    add_model_config_args(parser)
    args = parser.parse_args()

    arrays = read_transition_arrays(
        args.data,
        keys=BRANCH_ACTION_EV_ARRAY_KEYS,
        optional_keys=BRANCH_ACTION_EV_OPTIONAL_ARRAY_KEYS,
        limit=args.max_transitions,
    )
    model = ActionGlobalEVNet(
        EnvConfig(scalar_features=int(arrays["scalars"].shape[1])),
        model_config_from_args(args),
    ).to(args.device)
    step = load_checkpoint(args.checkpoint, model)
    report = action_ev_branch_cf_calibration(
        arrays,
        model,
        device=args.device,
        batch_size=args.batch_size,
        guard_margins=args.guard_margin,
    )
    report["checkpoint"] = str(args.checkpoint)
    report["checkpoint_step"] = int(step)
    report["data"] = str(args.data)
    report["device"] = args.device
    report["max_transitions"] = args.max_transitions

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Rows:                         {report['rows']}")
    print(f"Preferred rate:               {report['preferred_rate']:.2%}")
    print(f"Reward-gap weighted preferred:{report['reward_gap_weighted_preferred_rate']:.2%}")
    print(f"Mean margin:                  {report['mean_margin']:.4f}")
    for margin, summary in report["guard_preflight"].items():
        print(
            f"Guard margin {margin}: allowed={summary['allowed_count']} "
            f"harmful_block_rate={summary['harmful_block_rate']:.2%} "
            f"actual_allowed_delta_sum={summary['actual_allowed_delta_sum']:.4f}"
        )
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
