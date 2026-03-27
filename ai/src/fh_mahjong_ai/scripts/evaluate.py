"""Evaluate a trained checkpoint against baselines."""
from __future__ import annotations

import argparse
from pathlib import Path

import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.evaluate import compute_action_agreement, evaluate_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a trained model")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to .pt checkpoint")
    parser.add_argument("--data", type=Path, default=None, help="JSONL data for offline eval")
    parser.add_argument("--online-episodes", type=int, default=0, help="Number of online episodes (0 = skip)")
    parser.add_argument("--start-seed", type=int, default=1000, help="Starting seed for online eval")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--device", type=str, default="cpu", help="Device")
    args = parser.parse_args()

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(args.checkpoint, model)
    model.to(args.device)
    print(f"Loaded checkpoint from epoch {step}")

    if args.data is not None:
        print(f"\n--- Offline Evaluation (action agreement) ---")
        transitions = read_transitions_jsonl(args.data)
        report = compute_action_agreement(model, transitions, device=args.device)
        print(f"  Transitions:     {report['total_transitions']}")
        print(f"  Agreement:       {report['agreement_rate']:.2%}")
        print(f"  Top-3 Agreement: {report['top3_agreement_rate']:.2%}")

    if args.online_episodes > 0:
        print(f"\n--- Online Evaluation ({args.online_episodes} episodes) ---")
        seeds = list(range(args.start_seed, args.start_seed + args.online_episodes))
        report = evaluate_online(
            model=model,
            episodes=args.online_episodes,
            seeds=seeds,
            bridge_kind="go",
            bridge_library_path=args.bridge_lib,
            device=args.device,
        )
        print(f"  Episodes:    {report['episodes']}")
        print(f"  Avg Reward:  {report['avg_reward']}")
        print(f"  Wins:        {report['win_count']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
