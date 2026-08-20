"""CLI for online self-play PPO fine-tuning."""
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.mlflow_tracking import (
    DEFAULT_EXPERIMENT_NAME,
    log_artifact,
    log_metrics,
    log_params,
    start_run,
)
from fh_mahjong_ai.ppo import PPOConfig, train_ppo
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args

_MLFLOW_METRIC_KEYS = (
    "policy_loss", "value_loss", "entropy", "approx_kl", "clip_fraction",
    "mean_reward", "steps", "pool_size", "rollout_truncations",
    "eval_mean_reward", "eval_mean_reward_ci95",
    "eval_large_loss_rate", "eval_mean_placement", "eval_mean_placement_ci95",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Online self-play PPO fine-tuning")
    parser.add_argument("--init-checkpoint", type=Path, required=True, help="Anchor checkpoint to warm-start (policy+value) and freeze as opponent")
    parser.add_argument("--grp-checkpoint", type=Path, default=None,
                        help="Frozen GlobalEVNet GRP checkpoint; reward becomes the placement-value delta")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--matches-per-iter", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=1,
                        help="parallel rollout workers (1 = sequential)")
    parser.add_argument("--pool-max-size", type=int, default=1,
                        help="opponent pool size: anchor + past-self snapshots (1 = single anchor)")
    parser.add_argument("--pool-snapshot-interval", type=int, default=10,
                        help="add a learner snapshot to the opponent pool every N iterations")
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
    parser.add_argument("--mlflow", action="store_true",
                        help="Log PPO params, per-iteration metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
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
        max_steps_per_episode=args.max_steps_per_episode, num_workers=args.num_workers,
        pool_max_size=args.pool_max_size, pool_snapshot_interval=args.pool_snapshot_interval,
        grp_checkpoint=args.grp_checkpoint,
        device=args.device,
    )
    # Optional observability must never abort an expensive training run. Guard
    # every MLflow call: on the first failure (timeout, server outage, SQLite
    # lock, artifact-store error) warn once and disable further tracking, but let
    # training continue to completion.
    tracking = {"on": False}

    def _safe_mlflow(action) -> None:
        if not tracking["on"]:
            return
        try:
            action()
        except Exception as exc:  # noqa: BLE001 - tracking must not crash training
            tracking["on"] = False
            print(
                f"warning: MLflow logging failed ({exc!r}); disabling tracking "
                f"for the rest of the run",
                file=sys.stderr,
            )

    def _mlflow_callback(metrics: dict) -> None:
        numeric = {
            key: float(metrics[key])
            for key in _MLFLOW_METRIC_KEYS
            if isinstance(metrics.get(key), (int, float))
        }
        _safe_mlflow(lambda: log_metrics(numeric, step=int(metrics.get("iteration", 0))))

    # Start/finish the MLflow run defensively: run creation and finalization talk
    # to the tracking backend and can fail (server down, SQLite lock). Init
    # failure must fall back to an untracked run (training still starts);
    # finalization failure must not crash a run that already finished. Real
    # training errors from train_ppo still propagate.
    mlflow_cm = None
    mlflow_run = None
    if args.mlflow:
        try:
            mlflow_cm = start_run(
                enabled=True,
                experiment_name=args.mlflow_experiment,
                tracking_uri=args.mlflow_tracking_uri,
                run_name=args.mlflow_run_name,
                tags={"algo": "ppo", "match_mode": args.match_mode},
            )
            mlflow_run = mlflow_cm.__enter__()
        except Exception as exc:  # noqa: BLE001 - tracking init must not block training
            print(
                f"warning: MLflow init failed ({exc!r}); continuing without tracking",
                file=sys.stderr,
            )
            mlflow_cm = None
            mlflow_run = None
    tracking["on"] = mlflow_run is not None

    try:
        if mlflow_run is not None:
            _safe_mlflow(lambda: log_params({
                **asdict(config),
                "init_checkpoint": str(args.init_checkpoint),
                "base_seed": args.base_seed,
                "bridge_kind": args.bridge_kind,
                "run_eval": not args.no_eval,
            }))
        history = train_ppo(
            env_config=env_config, model_config=model_config_from_args(args),
            init_checkpoint=args.init_checkpoint, checkpoint_dir=args.checkpoint_dir,
            config=config, base_seed=args.base_seed, run_eval=not args.no_eval,
            iteration_callback=_mlflow_callback if mlflow_run is not None else None,
        )
        # train_ppo persists history.json atomically after every iteration, so it is
        # already on disk (and survives interruptions) by the time we get here.
        history_path = args.checkpoint_dir / "history.json"
        if mlflow_run is not None:
            _safe_mlflow(lambda: log_artifact(history_path, artifact_path="reports"))
            final_ckpt = args.checkpoint_dir / f"iter_{len(history):03d}.pt"
            if final_ckpt.exists():
                _safe_mlflow(lambda: log_artifact(final_ckpt, artifact_path="checkpoints"))
            run_id = getattr(getattr(mlflow_run, "info", None), "run_id", None)
            if run_id:
                print(f"MLflow run: {run_id}")
    finally:
        if mlflow_cm is not None:
            # Pass the in-flight exception (if any) so a crashed training run is
            # finalized as FAILED, not FINISHED; still tolerate a backend error
            # during finalization itself.
            try:
                mlflow_cm.__exit__(*sys.exc_info())
            except Exception as exc:  # noqa: BLE001 - finalization must not crash a finished run
                print(
                    f"warning: MLflow finalization failed ({exc!r})",
                    file=sys.stderr,
                )

    print(
        f"PPO finished: {len(history)} iterations; checkpoints in {args.checkpoint_dir}; "
        f"history written to {history_path}"
    )


if __name__ == "__main__":
    main()
