"""Evaluate a trained checkpoint against baselines."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement_from_batches, evaluate_duplicate_seats, evaluate_online
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import iter_observation_action_batches, load_checkpoint


def write_evaluation_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_seed_windows(values: list[str], episodes: int, start_seed: int) -> list[int]:
    if not values:
        return list(range(start_seed, start_seed + episodes))
    seeds: list[int] = []
    for value in values:
        if ":" in value:
            start_text, count_text = value.split(":", 1)
            start = int(start_text)
            count = int(count_text)
        else:
            start = int(value)
            count = episodes
        seeds.extend(range(start, start + count))
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--data", type=Path, default=None, help="JSONL data for offline eval")
    parser.add_argument("--online-episodes", type=int, default=0, help="Number of online episodes (0 = skip)")
    parser.add_argument("--start-seed", type=int, default=1000, help="Starting seed for online eval")
    parser.add_argument(
        "--seed-window",
        action="append",
        default=[],
        help="Start seed or start:count. Repeat for non-contiguous online eval windows.",
    )
    parser.add_argument("--duplicate-seats", action="store_true", help="Rotate the agent through all four seats")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="classic", help="Simulator match mode")
    parser.add_argument("--chongci-starting-score", type=int, default=2000, help="Chongci starting score")
    parser.add_argument("--chongci-bust-threshold", type=int, default=0, help="Chongci bust threshold")
    parser.add_argument("--chongci-max-hands", type=int, default=50, help="Chongci hand cap")
    parser.add_argument(
        "--max-steps-per-episode",
        type=int,
        default=None,
        help="Bridge decision cap per online episode; defaults to EnvConfig",
    )
    parser.add_argument(
        "--large-loss-threshold",
        type=float,
        default=None,
        help="Reward threshold for large-loss reporting; defaults by match mode",
    )
    parser.add_argument("--device", type=str, default="cpu", help="Device")
    parser.add_argument("--offline-batch-size", type=int, default=4096, help="Batch size for offline action-agreement inference")
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--mlflow", action="store_true", help="Log inference/evaluation params, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    model_config = model_config_from_args(args)
    model = PolicyValueNet(EnvConfig(), model_config)
    step = load_checkpoint(args.checkpoint, model)
    model.to(args.device)
    print(f"Loaded checkpoint from epoch {step}")

    final_report: dict[str, Any] = {
        "schema_version": 1,
        "checkpoint": str(args.checkpoint),
        "checkpoint_step": step,
        "data": str(args.data) if args.data else None,
        "device": args.device,
        "match_mode": args.match_mode,
        "model_config": model_config_params(model_config),
        "chongci_config": {
            "starting_score": args.chongci_starting_score,
            "bust_threshold": args.chongci_bust_threshold,
            "max_hands": args.chongci_max_hands,
        }
        if args.match_mode == "chongci"
        else None,
        "offline": None,
        "online": None,
    }

    with start_run(
        enabled=args.mlflow,
        experiment_name=args.mlflow_experiment,
        tracking_uri=args.mlflow_tracking_uri,
        run_name=args.mlflow_run_name,
        tags={"stage": "inference_evaluation"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "checkpoint": args.checkpoint,
                    "checkpoint_step": step,
                    "data": args.data,
                    "device": args.device,
                    "offline_batch_size": args.offline_batch_size,
                    "online_episodes": args.online_episodes,
                    "start_seed": args.start_seed,
                    "duplicate_seats": args.duplicate_seats,
                    "bridge_library_path": args.bridge_lib,
                    "match_mode": args.match_mode,
                    "chongci_starting_score": args.chongci_starting_score,
                    "chongci_bust_threshold": args.chongci_bust_threshold,
                    "chongci_max_hands": args.chongci_max_hands,
                    "max_steps_per_episode": args.max_steps_per_episode,
                    "large_loss_threshold": args.large_loss_threshold,
                    **model_config_params(model_config),
                }
            )

        if args.data is not None:
            print(f"\n--- Offline Evaluation (action agreement) ---")
            offline_report = compute_action_agreement_from_batches(
                model,
                iter_observation_action_batches(args.data, args.offline_batch_size),
                device=args.device,
            )
            final_report["offline"] = offline_report
            print(f"  Transitions:     {offline_report['total_transitions']}")
            print(f"  Agreement:       {offline_report['agreement_rate']:.2%}")
            print(f"  Top-3 Agreement: {offline_report['top3_agreement_rate']:.2%}")
            print("  Action Families:")
            for family, family_report in offline_report["family_agreement"].items():
                print(
                    f"    {family}: n={family_report['total']} "
                    f"top1={family_report['agreement_rate']:.2%} "
                    f"top3={family_report['top3_agreement_rate']:.2%}"
                )
            if mlflow_run is not None:
                log_metrics({"offline": offline_report})

        if args.online_episodes > 0:
            print(f"\n--- Online Evaluation ({args.online_episodes} episodes) ---")
            seeds = parse_seed_windows(args.seed_window, args.online_episodes, args.start_seed)
            if args.duplicate_seats:
                online_report = evaluate_duplicate_seats(
                    model=model,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    device=args.device,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=args.max_steps_per_episode,
                )
            else:
                online_report = evaluate_online(
                    model=model,
                    episodes=args.online_episodes,
                    seeds=seeds,
                    bridge_kind="go",
                    bridge_library_path=args.bridge_lib,
                    device=args.device,
                    large_loss_threshold=args.large_loss_threshold,
                    match_mode=args.match_mode,
                    chongci_starting_score=args.chongci_starting_score,
                    chongci_bust_threshold=args.chongci_bust_threshold,
                    chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=args.max_steps_per_episode,
                )
            final_report["online"] = online_report
            print(f"  Match Mode:  {online_report['match_mode']}")
            print(f"  Episodes:    {online_report['episodes']}")
            print(f"  Avg Reward:  {online_report['avg_reward']}")
            print(
                f"  Reward > 0:  {online_report['positive_reward_count']} "
                f"({online_report['positive_reward_rate']:.2%})"
            )
            if args.match_mode == "classic":
                print(f"  Wins:        {online_report['win_count']}")
                print(f"  Win Rate:    {online_report['win_rate']:.2%}")
            else:
                print("  Win Rate:    reward-positive compatibility metric; use Reward > 0 for Chongci")
            print(f"  Large Loss:  {online_report['large_loss_rate']:.2%}")
            if online_report.get("round_outcome_rates"):
                print("  Round Outcomes:")
                for name, rate in online_report["round_outcome_rates"].items():
                    count = online_report.get("round_outcome_counts", {}).get(name, 0)
                    print(f"    {name}: n={count} rate={rate:.2%}")
            if mlflow_run is not None:
                log_metrics({"online": online_report})

        if args.report_output is not None:
            write_evaluation_report(args.report_output, final_report)
            print(f"Report saved to {args.report_output}")

        if mlflow_run is not None:
            log_artifact(args.checkpoint, artifact_path="checkpoints")
            log_artifact(args.report_output, artifact_path="reports")
            print(f"MLflow run: {mlflow_run.info.run_id}")

    print("\nDone.")


if __name__ == "__main__":
    main()
