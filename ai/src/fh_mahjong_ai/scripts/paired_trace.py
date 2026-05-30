"""Compare two checkpoints on paired online traces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.paired_trace import compare_policy_traces
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.storage import load_checkpoint


def load_model(checkpoint: Path, device: str, model_config: ModelConfig) -> PolicyValueNet:
    model = PolicyValueNet(EnvConfig(), model_config)
    step = load_checkpoint(checkpoint, model)
    model.to(device)
    model.eval()
    print(f"Loaded {checkpoint} from epoch {step}")
    return model


def parse_seed_windows(values: list[str], episodes: int) -> list[int]:
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
    parser = argparse.ArgumentParser(description="Compare two checkpoints with paired online traces")
    parser.add_argument("--left-checkpoint", type=Path, required=True)
    parser.add_argument("--right-checkpoint", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="left")
    parser.add_argument("--right-label", type=str, default="right")
    parser.add_argument(
        "--seed-window",
        action="append",
        default=[],
        help="Start seed or start:count. Repeat for multiple windows.",
    )
    parser.add_argument("--episodes", type=int, default=20, help="Default count for seed windows without ':count'")
    parser.add_argument("--seats", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--bridge-lib", type=Path, default=None)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--max-steps-per-episode", type=int, default=20000)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--worst-delta-count", type=int, default=8)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--progress-interval", type=int, default=8)
    parser.add_argument("--report-output", type=Path, required=True)
    add_model_config_args(parser)
    args = parser.parse_args()

    seed_windows = args.seed_window or ["1000"]
    seeds = parse_seed_windows(seed_windows, episodes=args.episodes)
    model_config = model_config_from_args(args)
    left_model = load_model(args.left_checkpoint, args.device, model_config)
    right_model = load_model(args.right_checkpoint, args.device, model_config)
    progress_interval = max(0, int(args.progress_interval))

    def progress(completed: int, total: int, seed: int, seat: int) -> None:
        if progress_interval and (completed == 1 or completed % progress_interval == 0 or completed == total):
            print(f"Completed {completed}/{total} trace pairs; last seed={seed} seat={seat}", flush=True)

    report = compare_policy_traces(
        left_model=left_model,
        right_model=right_model,
        seeds=seeds,
        seats=args.seats,
        left_label=args.left_label,
        right_label=args.right_label,
        bridge_library_path=str(args.bridge_lib) if args.bridge_lib is not None else None,
        device=args.device,
        match_mode=args.match_mode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        max_steps_per_episode=args.max_steps_per_episode,
        large_loss_threshold=args.large_loss_threshold,
        worst_delta_count=args.worst_delta_count,
        progress_callback=progress,
    )
    report["left_checkpoint"] = str(args.left_checkpoint)
    report["right_checkpoint"] = str(args.right_checkpoint)
    report["seeds"] = seeds
    report["seats"] = args.seats
    report["match_mode"] = args.match_mode
    report["device"] = args.device

    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = report["summary"]
    print(f"Pairs:              {summary['episodes']}")
    print(f"Divergence rate:    {summary['divergence_rate']:.2%}")
    print(f"{args.right_label} better: {summary[f'{args.right_label}_better_rate']:.2%}")
    print(f"Mean delta:         {summary['reward_delta']['mean']:.4f}")
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
