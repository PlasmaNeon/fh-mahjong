"""CLI for online self-play PPO fine-tuning."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig, train_ppo
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    parser = argparse.ArgumentParser(description="Online self-play PPO fine-tuning")
    parser.add_argument("--init-checkpoint", type=Path, required=True, help="Anchor checkpoint to warm-start (policy+value) and freeze as opponent")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--matches-per-iter", type=int, default=16)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-eps", type=float, default=0.2)
    parser.add_argument("--entropy-coef", type=float, default=0.01)
    parser.add_argument("--value-coef", type=float, default=0.5)
    parser.add_argument("--ppo-epochs", type=int, default=4)
    parser.add_argument("--minibatch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--sample-temperature", type=float, default=1.0)
    parser.add_argument("--eval-interval", type=int, default=5)
    parser.add_argument("--eval-seeds", type=int, default=80)
    parser.add_argument("--eval-start-seed", type=int, default=870000)
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    parser.add_argument("--max-steps-per-episode", type=int, default=4000)
    parser.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    parser.add_argument("--bridge-lib", type=str, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--no-eval", action="store_true")
    add_model_config_args(parser)
    args = parser.parse_args()

    env_config = EnvConfig(
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
    )
    config = PPOConfig(
        iterations=args.iterations, matches_per_iter=args.matches_per_iter,
        gamma=args.gamma, gae_lambda=args.gae_lambda, clip_eps=args.clip_eps,
        entropy_coef=args.entropy_coef, value_coef=args.value_coef,
        ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size, lr=args.lr,
        max_grad_norm=args.max_grad_norm, sample_temperature=args.sample_temperature,
        eval_interval=args.eval_interval, eval_seeds=args.eval_seeds,
        eval_start_seed=args.eval_start_seed, match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode, device=args.device,
    )
    history = train_ppo(
        env_config=env_config, model_config=model_config_from_args(args),
        init_checkpoint=args.init_checkpoint, checkpoint_dir=args.checkpoint_dir,
        config=config, base_seed=args.base_seed, run_eval=not args.no_eval,
    )
    print(f"PPO finished: {len(history)} iterations; checkpoints in {args.checkpoint_dir}")


if __name__ == "__main__":
    main()
