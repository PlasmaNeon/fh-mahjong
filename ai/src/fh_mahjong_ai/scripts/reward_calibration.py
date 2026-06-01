"""Generate reward calibration diagnostics for an offline RL checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.reward_calibration import CALIBRATION_ARRAY_KEYS, CALIBRATION_FALLBACK_KEYS, compute_reward_calibration
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays


def reward_calibration_report(
    checkpoint: Path,
    data_path: Path,
    gamma: float = 0.99,
    large_loss_threshold: Optional[float] = None,
    large_loss_risk_mode: str = "auto",
    max_transitions: Optional[int] = None,
    batch_size: int = 4096,
    device: str = "cpu",
    report_output: Optional[Path] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
) -> dict:
    arrays = _read_calibration_arrays(data_path, max_transitions=max_transitions)
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(checkpoint, model)
    model.to(device)

    report = {
        "schema_version": 1,
        "checkpoint": str(checkpoint),
        "checkpoint_step": step,
        "data": str(data_path),
        "gamma": gamma,
        "large_loss_threshold": large_loss_threshold,
        "large_loss_risk_mode": large_loss_risk_mode,
        "max_transitions": max_transitions,
        "device": device,
        "calibration": compute_reward_calibration(
            model=model,
            arrays=arrays,
            gamma=gamma,
            batch_size=batch_size,
            device=device,
            large_loss_threshold=large_loss_threshold,
            large_loss_risk_mode=large_loss_risk_mode,
        ),
    }

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "reward_calibration"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "checkpoint": checkpoint,
                    "checkpoint_step": step,
                    "data": data_path,
                    "gamma": gamma,
                    "large_loss_threshold": large_loss_threshold,
                    "large_loss_risk_mode": large_loss_risk_mode,
                    "max_transitions": max_transitions,
                    "batch_size": batch_size,
                    "device": device,
                }
            )
            log_metrics({"calibration": report["calibration"]})

        if report_output is not None:
            report_output.parent.mkdir(parents=True, exist_ok=True)
            report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if mlflow_run is not None:
                log_artifact(report_output, artifact_path="reports")

        if mlflow_run is not None:
            print(f"MLflow run: {mlflow_run.info.run_id}")

    return report


def _read_calibration_arrays(data_path: Path, max_transitions: Optional[int]) -> dict:
    try:
        return read_transition_arrays(data_path, keys=CALIBRATION_ARRAY_KEYS, limit=max_transitions)
    except KeyError as exc:
        if "steps_to_done" not in str(exc):
            raise
        return read_transition_arrays(data_path, keys=CALIBRATION_FALLBACK_KEYS, limit=max_transitions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Report Q/value calibration against discounted terminal payout")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument(
        "--large-loss-threshold",
        type=float,
        default=None,
        help="Optional target threshold for large-loss probability/severity head calibration.",
    )
    parser.add_argument(
        "--large-loss-risk-mode",
        choices=("auto", "action", "state"),
        default="auto",
        help="Use action-conditioned risk heads, legacy state-only risk head, or auto-detect for large-loss calibration.",
    )
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=4096)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--mlflow", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    args = parser.parse_args()

    report = reward_calibration_report(
        checkpoint=args.checkpoint,
        data_path=args.data,
        gamma=args.gamma,
        large_loss_threshold=args.large_loss_threshold,
        large_loss_risk_mode=args.large_loss_risk_mode,
        max_transitions=args.max_transitions,
        batch_size=args.batch_size,
        device=args.device,
        report_output=args.report_output,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
    )
    calibration = report["calibration"]
    print(f"Transitions: {calibration['total_transitions']}")
    print(f"Q MAE:       {calibration['q_error']['mae']:.4f}")
    print(f"Q RMSE:      {calibration['q_error']['rmse']:.4f}")
    print(f"Q Bias:      {calibration['q_error']['bias']:.4f}")
    print(f"Q Corr:      {calibration['q_error']['correlation']:.4f}")
    print(f"Value MAE:   {calibration['value_error']['mae']:.4f}")
    if "large_loss_calibration" in calibration:
        large_loss = calibration["large_loss_calibration"]
        print(f"LL Rate:     {large_loss['positive_rate']:.4f}")
        print(f"LL Brier:    {large_loss['probability']['brier']:.4f}")
        print(f"LL AUC:      {large_loss['probability']['auc']:.4f}")
        print(f"LL Sev MAE:  {large_loss['severity']['mae']:.4f}")
    if args.report_output is not None:
        print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
