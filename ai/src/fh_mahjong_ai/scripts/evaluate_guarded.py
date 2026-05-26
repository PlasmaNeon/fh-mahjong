"""Evaluate a Q-guarded reward checkpoint against an anchor policy."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import evaluate_duplicate_seats_policy
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import GuardedQPolicy
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import load_checkpoint


def load_model(checkpoint: Path, device: str, model_config: ModelConfig) -> tuple[PolicyValueNet, int]:
    model = PolicyValueNet(EnvConfig(), model_config)
    step = load_checkpoint(checkpoint, model)
    model.to(device)
    model.eval()
    return model, step


def write_report(path: Path, report: dict[str, Any]) -> None:
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
    parser = argparse.ArgumentParser(description="Evaluate a Q-margin guarded reward checkpoint")
    parser.add_argument("--anchor-checkpoint", type=Path, required=True)
    parser.add_argument("--candidate-checkpoint", type=Path, required=True)
    parser.add_argument(
        "--q-margin",
        type=float,
        action="append",
        default=[],
        help="Minimum candidate Q advantage over the anchor action. Repeat for a sweep.",
    )
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--start-seed", type=int, default=1000)
    parser.add_argument(
        "--seed-window",
        action="append",
        default=[],
        help="Start seed or start:count. Repeat for non-contiguous duplicate windows.",
    )
    parser.add_argument("--seats", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--bridge-lib", type=Path, default=None)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--max-steps-per-episode", type=int, default=20000)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--report-output", type=Path, required=True)
    add_model_config_args(parser)
    args = parser.parse_args()

    model_config = model_config_from_args(args)
    anchor_model, anchor_step = load_model(args.anchor_checkpoint, args.device, model_config)
    candidate_model, candidate_step = load_model(args.candidate_checkpoint, args.device, model_config)
    seeds = parse_seed_windows(args.seed_window, episodes=args.episodes, start_seed=args.start_seed)
    margins = args.q_margin or [0.0]

    reports: dict[str, Any] = {}
    for margin in margins:
        print(f"\n--- Guarded evaluation q_margin={margin:.4f} ---", flush=True)
        report = evaluate_duplicate_seats_policy(
            policy_factory=lambda _seat, selected_margin=margin: GuardedQPolicy(
                anchor_model=anchor_model,
                candidate_model=candidate_model,
                min_q_margin=selected_margin,
                device=args.device,
            ),
            seeds=seeds,
            seats=args.seats,
            bridge_kind="go",
            bridge_library_path=args.bridge_lib,
            large_loss_threshold=args.large_loss_threshold,
            match_mode=args.match_mode,
            chongci_starting_score=args.chongci_starting_score,
            chongci_bust_threshold=args.chongci_bust_threshold,
            chongci_max_hands=args.chongci_max_hands,
            max_steps_per_episode=args.max_steps_per_episode,
        )
        reports[str(margin)] = report
        print(
            f"episodes={report['episodes']} mean={report['mean_reward']:.4f} "
            f"positive={report['positive_reward_rate']:.2%} "
            f"large_loss={report['large_loss_rate']:.2%} "
            f"choices={report['policy_choice_rates']}",
            flush=True,
        )

    final_report = {
        "schema_version": 1,
        "anchor_checkpoint": str(args.anchor_checkpoint),
        "anchor_step": anchor_step,
        "candidate_checkpoint": str(args.candidate_checkpoint),
        "candidate_step": candidate_step,
        "model_config": model_config_params(model_config),
        "seeds": seeds,
        "seats": args.seats,
        "match_mode": args.match_mode,
        "chongci_config": {
            "starting_score": args.chongci_starting_score,
            "bust_threshold": args.chongci_bust_threshold,
            "max_hands": args.chongci_max_hands,
        }
        if args.match_mode == "chongci"
        else None,
        "reports_by_margin": reports,
    }
    write_report(args.report_output, final_report)
    print(f"\nReport saved to {args.report_output}")


if __name__ == "__main__":
    main()
