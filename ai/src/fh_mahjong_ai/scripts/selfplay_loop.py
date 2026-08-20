"""CLI for the Chongci self-play improvement loop."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args
from fh_mahjong_ai.selfplay_loop import GateThresholds, LoopConfig, run_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Chongci self-play improvement loop")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--fixed-init", type=str, required=True, help="Frozen init checkpoint for every candidate")
    parser.add_argument("--initial-best", type=str, required=True, help="Starting current-best checkpoint")
    parser.add_argument("--base-data", type=str, action="append", default=[], help="Repeatable accumulated base dataset dirs")
    parser.add_argument("--iterations", type=int, default=5)
    parser.add_argument("--episodes-per-iter", type=int, default=300)
    parser.add_argument("--start-seed", type=int, default=810000)
    parser.add_argument("--seed-stride", type=int, default=10000)
    parser.add_argument("--screen-seeds", type=int, default=80)
    parser.add_argument("--confirm-seeds", type=int, default=240)
    parser.add_argument("--eval-start-seed", type=int, default=870000)
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--patience", type=int, default=3)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    parser.add_argument("--bridge-lib", type=str, default=None)
    parser.add_argument("--max-steps-per-episode", type=int, default=4000)
    parser.add_argument(
        "--seat-policy-template",
        nargs="+",
        default=["0=checkpoint:{best}", "1=checkpoint:{best}", "3=random"],
    )
    parser.add_argument("--screen-margin", type=float, default=0.05)
    parser.add_argument("--large-loss-eps", type=float, default=0.0)
    parser.add_argument("--positive-eps", type=float, default=0.02)
    parser.add_argument("--stream-training", action="store_true")
    parser.add_argument("--stream-shuffle-buffer", type=int, default=50000)
    parser.add_argument("--stream-workers", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    add_model_config_args(parser)
    args = parser.parse_args()

    env_config = EnvConfig(
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
    )
    model_config = model_config_from_args(args)

    config = LoopConfig(
        run_dir=args.run_dir,
        fixed_init=args.fixed_init,
        base_data=list(args.base_data),
        initial_best=args.initial_best,
        iterations=args.iterations,
        episodes_per_iter=args.episodes_per_iter,
        start_seed=args.start_seed,
        seed_stride=args.seed_stride,
        screen_seeds=args.screen_seeds,
        confirm_seeds=args.confirm_seeds,
        eval_start_seed=args.eval_start_seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        patience=args.patience,
        match_mode=args.match_mode,
        device=args.device,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        max_steps_per_episode=args.max_steps_per_episode,
        seat_policy_template=list(args.seat_policy_template),
        stream_training=args.stream_training,
        stream_shuffle_buffer=args.stream_shuffle_buffer,
        stream_workers=args.stream_workers,
        thresholds=GateThresholds(
            screen_margin=args.screen_margin,
            large_loss_eps=args.large_loss_eps,
            positive_eps=args.positive_eps,
        ),
    )
    ledger = run_loop(config, env_config, model_config, resume=args.resume)
    print(f"loop finished at iteration {ledger.iteration}; current best = {ledger.current_best}")


if __name__ == "__main__":
    main()
