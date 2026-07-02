"""CLI for Phase-2 self-play feature-dropout oracle training."""
from __future__ import annotations
import argparse
from pathlib import Path
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig, default_num_workers
from fh_mahjong_ai.oracle import train_selfplay_oracle
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    p = argparse.ArgumentParser(description="Phase-2 self-play feature-dropout oracle training")
    p.add_argument("--anchor-checkpoint", type=Path, required=True, help="39ch anchor to warm-start from")
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--iterations", type=int, default=50)
    p.add_argument("--matches-per-iter", type=int, default=256)
    p.add_argument("--num-workers", type=int, default=default_num_workers(),
                   help="parallel self-play rollout workers (1 = sequential); default is "
                        "core-aware (rollout throughput is core-bound, not memory-bound)")
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--entropy-coef", type=float, default=0.0)
    p.add_argument("--ppo-epochs", type=int, default=2)
    p.add_argument("--minibatch-size", type=int, default=256)
    p.add_argument("--max-grad-norm", type=float, default=0.5)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--base-seed", type=int, default=0)
    add_model_config_args(p)
    args = p.parse_args()
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           oracle_observation=True)
    config = PPOConfig(iterations=args.iterations, matches_per_iter=args.matches_per_iter,
                       gamma=args.gamma, lr=args.lr, entropy_coef=args.entropy_coef,
                       ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size,
                       max_grad_norm=args.max_grad_norm, match_mode=args.match_mode,
                       max_steps_per_episode=args.max_steps_per_episode, device=args.device,
                       num_workers=args.num_workers)
    train_selfplay_oracle(env_config=env_config, model_config=model_config_from_args(args),
                          anchor_checkpoint=args.anchor_checkpoint, checkpoint_dir=args.checkpoint_dir,
                          config=config, base_seed=args.base_seed, run_eval=False)


if __name__ == "__main__":
    main()
