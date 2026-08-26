"""Behavior cloning training on heuristic trajectory data."""
from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
from pathlib import Path
from typing import Any, List, Optional

import numpy as np
import torch

from fh_mahjong_ai.buffer import ArrayReplayBuffer, ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.data import backfill_returns, split_train_validation
from fh_mahjong_ai.evaluate import compute_action_agreement, compute_action_agreement_from_batches
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import is_sharded_transition_dataset, load_checkpoint, model_config_metadata, read_transition_arrays, read_transitions, save_checkpoint
from fh_mahjong_ai.offline_trainers import BehaviorCloningTrainer, TrainMetrics

BC_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "episode_index",
    "terminal_rewards",
)


def train_bc(
    data_path: Path,
    checkpoint_dir: Path,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    device: str = "cpu",
    log_interval: int = 10,
    resume: bool = False,
    validation_fraction: float = 0.2,
    split_seed: int = 0,
    report_path: Optional[Path] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
    validation_batch_size: int = 4096,
    model_config: Optional[ModelConfig] = None,
    patience: Optional[int] = None,
    min_delta: float = 1e-4,
    min_epochs: int = 1,
) -> List[TrainMetrics]:
    """Run BC training and return collected metrics."""
    if patience is not None and patience < 1:
        raise ValueError("--patience must be >= 1")
    if min_delta < 0:
        raise ValueError("--min-delta must be >= 0")
    if min_epochs < 1:
        raise ValueError("--min-epochs must be >= 1")

    torch.manual_seed(split_seed)
    validation_arrays: Optional[dict[str, np.ndarray]] = None
    validation_indices: Optional[np.ndarray] = None
    validation_transitions = []

    if is_sharded_transition_dataset(data_path):
        arrays = read_transition_arrays(data_path, keys=BC_ARRAY_KEYS)
        train_indices, validation_indices = split_array_train_validation(
            arrays["episode_index"],
            validation_fraction=validation_fraction,
            seed=split_seed,
        )
        total_transitions = int(arrays["action_ids"].shape[0])
        train_count = int(train_indices.size)
        validation_count = int(validation_indices.size)
        validation_arrays = arrays
        buf = ArrayReplayBuffer(arrays=arrays, indices=train_indices)
    else:
        transitions = read_transitions(data_path)
        backfill_returns(transitions)
        train_transitions, validation_transitions = split_train_validation(
            transitions,
            validation_fraction=validation_fraction,
            seed=split_seed,
        )
        total_transitions = len(transitions)
        train_count = len(train_transitions)
        validation_count = len(validation_transitions)
        buf = ReplayBuffer(capacity=len(train_transitions))
        buf.extend(train_transitions)

    if len(buf) == 0:
        raise ValueError(f"no training transitions found in {data_path}")

    if patience is not None and validation_count == 0:
        raise ValueError("--patience requires a validation split")

    env_config = EnvConfig()
    if model_config is None:
        model_config = ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)

    start_epoch = 0
    if resume:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoints = sorted(checkpoint_dir.glob("epoch_*.pt"))
        if checkpoints:
            start_epoch = load_checkpoint(checkpoints[-1], model, optimizer)

    train_config = TrainConfig(
        batch_size=min(batch_size, len(buf)),
        learning_rate=learning_rate,
        device=device,
        seed=split_seed,
    )
    trainer = BehaviorCloningTrainer(model, optimizer, train_config)

    steps_per_epoch = max(1, len(buf) // batch_size)
    all_metrics: List[TrainMetrics] = []
    report: dict[str, Any] = {
        "schema_version": 1,
        "method": "behavior_cloning",
        "data_path": str(data_path),
        "checkpoint_dir": str(checkpoint_dir),
        "total_transitions": total_transitions,
        "train_transitions": train_count,
        "validation_transitions": validation_count,
        "validation_fraction": validation_fraction,
        "split_seed": split_seed,
        "batch_size": train_config.batch_size,
        "validation_batch_size": validation_batch_size,
        "learning_rate": learning_rate,
        "device": device,
        "model_config": model_config_metadata(model_config),
        "epochs": [],
    }

    best_ce = float("inf")
    best_epoch: Optional[int] = None
    patience_ref = float("inf")
    stale = 0
    stopped_early = False
    epochs_run = 0

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "behavior_cloning"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "behavior_cloning",
                    "data_path": data_path,
                    "checkpoint_dir": checkpoint_dir,
                    "epochs": epochs,
                    "start_epoch": start_epoch,
                    "batch_size": train_config.batch_size,
                    "validation_batch_size": validation_batch_size,
                    "learning_rate": learning_rate,
                    "weight_decay": train_config.weight_decay,
                    "validation_fraction": validation_fraction,
                    "split_seed": split_seed,
                    "device": device,
                    "total_transitions": total_transitions,
                    "train_transitions": train_count,
                    "validation_transitions": validation_count,
                    **model_config_params(model_config),
                }
            )

        for epoch in range(start_epoch + 1, epochs + 1):
            epoch_loss = 0.0
            epoch_policy_loss = 0.0
            epoch_value_loss = 0.0
            for step in range(1, steps_per_epoch + 1):
                metrics = trainer.train_step(buf)
                all_metrics.append(metrics)
                epoch_loss += metrics.loss
                epoch_policy_loss += metrics.policy_loss
                epoch_value_loss += metrics.value_loss

                global_step = (epoch - 1) * steps_per_epoch + step
                if global_step % log_interval == 0:
                    print(
                        f"epoch {epoch}/{epochs}  step {step}/{steps_per_epoch}  "
                        f"loss={metrics.loss:.4f}  policy={metrics.policy_loss:.4f}  "
                        f"value={metrics.value_loss:.4f}"
                    )

            avg_loss = epoch_loss / steps_per_epoch
            epoch_report: dict[str, Any] = {
                "epoch": epoch,
                "avg_loss": avg_loss,
                "avg_policy_loss": epoch_policy_loss / steps_per_epoch,
                "avg_value_loss": epoch_value_loss / steps_per_epoch,
            }
            # BC trains event-enabled configs with events=None (zeroed event
            # features, per spec B2b/4.3), so validating under that same
            # zeroed condition is a faithful measure of what BC learned --
            # NOT a valid metric for an event-trained (PPO) checkpoint. See
            # compute_action_agreement_from_batches's docstring.
            wants_events = bool(getattr(model, "wants_events", False))
            if validation_count:
                if validation_arrays is not None and validation_indices is not None:
                    validation_report = compute_action_agreement_from_batches(
                        model,
                        iter_array_observation_action_batches(
                            validation_arrays,
                            validation_indices,
                            validation_batch_size,
                        ),
                        device=device,
                        allow_zero_events=wants_events,
                    )
                else:
                    validation_report = compute_action_agreement(
                        model,
                        validation_transitions,
                        device=device,
                        batch_size=validation_batch_size,
                        allow_zero_events=wants_events,
                    )
                epoch_report["validation"] = validation_report
                epoch_report["validation_events"] = "zeroed" if wants_events else "none"
                print(
                    f"--- epoch {epoch} avg_loss={avg_loss:.4f}  "
                    f"val_top1={validation_report['agreement_rate']:.2%}  "
                    f"val_top3={validation_report['top3_agreement_rate']:.2%}"
                )
            else:
                epoch_report["validation"] = None
                epoch_report["validation_events"] = None
                print(f"--- epoch {epoch} avg_loss={avg_loss:.4f}")

            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            save_checkpoint(
                checkpoint_path,
                model, optimizer, step=epoch,
                metadata={
                    "model_config": model_config_metadata(model_config),
                    "method": "behavior_cloning",
                },
            )
            epoch_report["checkpoint_path"] = str(checkpoint_path)
            report["epochs"].append(epoch_report)

            epochs_run = epoch
            val_ce = (epoch_report["validation"] or {}).get("mean_cross_entropy")
            if val_ce is not None:
                # Selection (best_epoch) is the literal argmin over validation CE.
                # Stopping (stale/patience) is gated on a min_delta-significant
                # improvement, tracked separately so a sub-min_delta improvement
                # can still win selection without resetting the patience clock.
                if val_ce < best_ce:
                    best_ce, best_epoch = float(val_ce), epoch
                    if patience is not None:
                        # Refresh best.pt right after this epoch's checkpoint is
                        # saved so an interrupted run always leaves a current
                        # best.pt behind, not just a run that reaches the end
                        # of the loop. Copy-then-rename so a reader never
                        # observes a partially written best.pt.
                        best_pt_dst = checkpoint_dir / "best.pt"
                        best_pt_tmp = checkpoint_dir / "best.pt.tmp"
                        shutil.copyfile(checkpoint_path, best_pt_tmp)
                        os.replace(best_pt_tmp, best_pt_dst)
                if val_ce < patience_ref - min_delta:
                    patience_ref, stale = float(val_ce), 0
                else:
                    stale += 1
                if patience is not None and epoch >= min_epochs and stale >= patience:
                    stopped_early = True

            report["stopped_early"] = stopped_early
            report["epochs_run"] = epochs_run
            report["best_epoch"] = best_epoch
            report["best_validation_cross_entropy"] = best_ce if best_epoch is not None else None

            if report_path is not None:
                write_training_report(report_path, report)

            if mlflow_run is not None:
                log_metrics(
                    {
                        "train": {
                            "avg_loss": epoch_report["avg_loss"],
                            "avg_policy_loss": epoch_report["avg_policy_loss"],
                            "avg_value_loss": epoch_report["avg_value_loss"],
                        },
                        "validation": epoch_report["validation"] or {},
                    },
                    step=epoch,
                )
                log_artifact(checkpoint_path, artifact_path="checkpoints")

            if stopped_early:
                print(
                    f"--- early stop at epoch {epoch}: no val CE improvement >= {min_delta} "
                    f"for {patience} epochs (best epoch {best_epoch})"
                )
                break

        if mlflow_run is not None:
            log_artifact(report_path, artifact_path="reports")
            print(f"MLflow run: {mlflow_run.info.run_id}")

    if patience is not None and best_epoch is not None:
        # best.pt is refreshed in-loop as soon as best_epoch changes (above);
        # this is a no-op guard for callers that mutate checkpoint_dir between
        # the last in-loop refresh and return (e.g. tests, `--resume` chains).
        # filecmp.cmp(shallow=False) compares sizes first and only reads both
        # files when sizes match, so the common (already-refreshed) case never
        # pays for a full byte compare.
        best_checkpoint_path = checkpoint_dir / f"epoch_{best_epoch:03d}.pt"
        best_pt_path = checkpoint_dir / "best.pt"
        if not (best_pt_path.exists() and filecmp.cmp(best_pt_path, best_checkpoint_path, shallow=False)):
            best_pt_tmp = checkpoint_dir / "best.pt.tmp"
            shutil.copyfile(best_checkpoint_path, best_pt_tmp)
            os.replace(best_pt_tmp, best_pt_path)

    return all_metrics


def write_training_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def split_array_train_validation(
    episode_indices: np.ndarray,
    validation_fraction: float = 0.2,
    seed: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    if validation_fraction < 0.0 or validation_fraction >= 1.0:
        raise ValueError("validation_fraction must be in [0.0, 1.0)")

    unique_episodes = np.unique(episode_indices)
    if unique_episodes.size <= 1 or validation_fraction == 0.0:
        return np.arange(episode_indices.shape[0], dtype=np.int64), np.asarray([], dtype=np.int64)

    rng = np.random.default_rng(seed)
    shuffled = unique_episodes.copy()
    rng.shuffle(shuffled)
    validation_count = int(round(unique_episodes.size * validation_fraction))
    validation_count = min(max(validation_count, 1), unique_episodes.size - 1)
    validation_episodes = set(int(index) for index in shuffled[:validation_count])

    validation_mask = np.asarray([int(index) in validation_episodes for index in episode_indices], dtype=bool)
    all_indices = np.arange(episode_indices.shape[0], dtype=np.int64)
    return all_indices[~validation_mask], all_indices[validation_mask]


def iter_array_observation_action_batches(
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    batch_size: int,
):
    effective_batch_size = max(1, int(batch_size))
    for start in range(0, indices.size, effective_batch_size):
        selected = indices[start : start + effective_batch_size]
        yield {
            "planes": arrays["planes"][selected],
            "scalars": arrays["scalars"][selected],
            "action_mask": arrays["action_mask"][selected],
            "action_ids": arrays["action_ids"][selected],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train behavior cloning model")
    parser.add_argument("--data", type=Path, required=True, help="JSONL trajectory data")
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("checkpoints/bc"))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--log-interval", type=int, default=10)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--validation-batch-size", type=int, default=4096, help="Batch size for validation inference")
    parser.add_argument("--split-seed", type=int, default=0)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--mlflow", action="store_true", help="Log training params, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    parser.add_argument("--patience", type=int, default=None,
                         help="Stop after this many epochs without validation CE improvement")
    parser.add_argument("--min-delta", type=float, default=1e-4,
                         help="Minimum validation CE decrease to count as an improvement")
    parser.add_argument("--min-epochs", type=int, default=1,
                         help="Minimum epochs to run before early stopping can trigger")
    add_model_config_args(parser)
    args = parser.parse_args()

    if args.patience is not None and args.patience < 1:
        parser.error("--patience must be >= 1")
    if args.min_delta < 0:
        parser.error("--min-delta must be >= 0")
    if args.min_epochs < 1:
        parser.error("--min-epochs must be >= 1")

    report_output = args.report_output or args.checkpoint_dir / "training_report.json"
    print(f"Loading data from {args.data}...")
    metrics = train_bc(
        data_path=args.data,
        checkpoint_dir=args.checkpoint_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        device=args.device,
        log_interval=args.log_interval,
        resume=args.resume,
        validation_fraction=args.validation_fraction,
        split_seed=args.split_seed,
        report_path=report_output,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
        validation_batch_size=args.validation_batch_size,
        model_config=model_config_from_args(args),
        patience=args.patience,
        min_delta=args.min_delta,
        min_epochs=args.min_epochs,
    )
    print(f"Training complete. Final loss: {metrics[-1].loss:.4f}")
    print(f"Report saved to {report_output}")


if __name__ == "__main__":
    main()
