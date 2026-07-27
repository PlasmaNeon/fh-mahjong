"""CLI for Spec B2b training: event history + privileged critic + auxiliary
heads, warm-started from the 39ch champion."""
from __future__ import annotations
import argparse
from dataclasses import replace
from pathlib import Path
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig, default_num_workers
from fh_mahjong_ai.oracle import train_b2b
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args


def main() -> None:
    p = argparse.ArgumentParser(description="Spec B2b training (event GRU + privileged critic + aux heads)")
    p.add_argument("--champion", type=Path, default=None,
                   help="39ch champion checkpoint to warm-start from; required unless "
                        "--resume-from-state is given (the resume path builds the model from "
                        "the state file and never touches --champion)")
    p.add_argument("--checkpoint-dir", type=Path, required=True)
    p.add_argument("--iterations", type=int, default=50)
    p.add_argument("--matches-per-iter", type=int, default=256)
    p.add_argument("--num-workers", type=int, default=None,
                   help="parallel B2b rollout workers (1 = sequential); default is "
                        "min(core-aware, --matches-per-iter) since rollout throughput is "
                        "core-bound and extra workers beyond the match count sit idle")
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
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--privileged-critic", dest="privileged_critic", action="store_true", default=True,
                   help="train a privileged-info critic branch (default: on)")
    p.add_argument("--no-privileged-critic", dest="privileged_critic", action="store_false")
    p.add_argument("--aux-heads", dest="aux_heads", action="store_true", default=True,
                   help="train the belief/deal-in/rank auxiliary heads (default: on)")
    p.add_argument("--no-aux-heads", dest="aux_heads", action="store_false")
    p.add_argument("--model-growth-blocks", type=int, default=0,
                   help="deep16-rezero capacity growth: stack this many ReZero residual "
                        "blocks onto --champion (which must then be a complete post-B2b "
                        "anchor checkpoint, not the raw 39ch champion the default (0) "
                        "surgery path expects); 0 = disabled (default)")
    p.add_argument("--train-state-every", type=int, default=5,
                   help="write <checkpoint-dir>/train_state.pt (model + optimizer + RNG + "
                        "next-iteration) every N iterations, and always at completion, so "
                        "a multi-day lap survives a box restart; 0 disables it")
    p.add_argument("--resume-from-state", type=Path, default=None,
                   help="resume a previous run from a train_state.pt written by "
                        "--train-state-every: skips the --champion/--model-growth-blocks "
                        "warm-start (the model comes from the state file), validates that "
                        "every config flag matches what the state was saved under, and "
                        "continues iteration numbering + history.json from where it left off")
    p.add_argument("--force-history-reset", action="store_true", default=False,
                   help="DANGEROUS: skip the check that checkpoint_dir's existing iter_*.pt "
                        "artifacts all belong to the same run_id as the resuming state file. "
                        "This check now runs on EVERY --resume-from-state (not only when "
                        "history.json is missing or corrupt) -- it inspects every iter_*.pt in "
                        "checkpoint_dir, including ones this resume is about to overwrite, "
                        "since a foreign checkpoint there is still evidence of a wrong "
                        "directory. The flag name predates this and now covers both cases: "
                        "the missing/corrupt-history recovery path AND a resume with an "
                        "otherwise valid, matching history.json that still has a foreign "
                        "artifact sitting in checkpoint_dir. Only the artifact-lineage check "
                        "is skipped -- config/base_seed mismatches still raise. Use ONLY when "
                        "you have manually confirmed checkpoint_dir holds this run's own "
                        "checkpoints, never to force a resume into a directory that might "
                        "belong to a different run")
    add_model_config_args(p)
    args = p.parse_args()
    if args.champion is None and args.resume_from_state is None:
        p.error("--champion is required unless --resume-from-state is given")
    num_workers = args.num_workers
    if num_workers is None:
        num_workers = min(default_num_workers(), args.matches_per_iter)
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           oracle_observation=True, event_history_window=args.event_window)
    config = PPOConfig(iterations=args.iterations, matches_per_iter=args.matches_per_iter,
                       gamma=args.gamma, lr=args.lr, entropy_coef=args.entropy_coef,
                       ppo_epochs=args.ppo_epochs, minibatch_size=args.minibatch_size,
                       max_grad_norm=args.max_grad_norm, match_mode=args.match_mode,
                       max_steps_per_episode=args.max_steps_per_episode, device=args.device,
                       num_workers=num_workers)
    base_model_config = model_config_from_args(args)
    model_config = replace(base_model_config, event_window=args.event_window,
                          privileged_critic=args.privileged_critic, aux_heads=args.aux_heads,
                          growth_blocks=args.model_growth_blocks)
    train_b2b(env_config=env_config, model_config=model_config, champion_checkpoint=args.champion,
             checkpoint_dir=args.checkpoint_dir, config=config, base_seed=args.base_seed,
             growth_blocks=args.model_growth_blocks, train_state_every=args.train_state_every,
             resume_from_state=args.resume_from_state, force_history_reset=args.force_history_reset)


if __name__ == "__main__":
    main()
