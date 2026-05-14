"""Conservative offline Q-learning on saved Mahjong trajectories."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, OfflineQConfig, TrainConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl, save_checkpoint
from fh_mahjong_ai.trainer import OfflineQMetrics, OfflineQTrainer


def train_offline_q(
    data_path: Path,
    checkpoint_dir: Path,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    gamma: float = 0.99,
    conservative_weight: float = 0.1,
    bc_weight: float = 0.1,
    value_weight: float = 0.25,
    target_update_interval: int = 25,
    target_tau: float = 1.0,
    device: str = "cpu",
    log_interval: int = 10,
    init_checkpoint: Optional[Path] = None,
    resume: bool = False,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
) -> List[OfflineQMetrics]:
    """Train a masked-action Q head from fixed offline trajectory data."""
    transitions = read_transitions_jsonl(data_path)
    backfill_returns(transitions)

    buf = ReplayBuffer(capacity=len(transitions))
    buf.extend(transitions)

    env_config = EnvConfig()
    model_config = ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(device)
    target_model = PolicyValueNet(env_config, model_config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-4)

    start_epoch = 0
    if init_checkpoint is not None:
        load_checkpoint(init_checkpoint, model)

    if resume:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoints = sorted(checkpoint_dir.glob("epoch_*.pt"))
        if checkpoints:
            start_epoch = load_checkpoint(checkpoints[-1], model, optimizer)

    target_model.load_state_dict(model.state_dict())
    target_model.eval()

    train_config = TrainConfig(
        batch_size=min(batch_size, len(buf)),
        learning_rate=learning_rate,
        device=device,
    )
    q_config = OfflineQConfig(
        gamma=gamma,
        conservative_weight=conservative_weight,
        bc_weight=bc_weight,
        value_weight=value_weight,
        target_update_interval=target_update_interval,
        target_tau=target_tau,
    )
    trainer = OfflineQTrainer(model, target_model, optimizer, train_config, q_config)

    steps_per_epoch = max(1, len(buf) // batch_size)
    all_metrics: List[OfflineQMetrics] = []

    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "offline_q"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "offline_q",
                    "data_path": data_path,
                    "checkpoint_dir": checkpoint_dir,
                    "epochs": epochs,
                    "start_epoch": start_epoch,
                    "batch_size": train_config.batch_size,
                    "learning_rate": learning_rate,
                    "gamma": gamma,
                    "conservative_weight": conservative_weight,
                    "bc_weight": bc_weight,
                    "value_weight": value_weight,
                    "target_update_interval": target_update_interval,
                    "target_tau": target_tau,
                    "device": device,
                    "transitions": len(transitions),
                    "init_checkpoint": init_checkpoint,
                }
            )

        for epoch in range(start_epoch + 1, epochs + 1):
            epoch_loss = 0.0
            latest_metrics = None
            for step in range(1, steps_per_epoch + 1):
                metrics = trainer.train_step(buf)
                latest_metrics = metrics
                all_metrics.append(metrics)
                epoch_loss += metrics.loss

                global_step = (epoch - 1) * steps_per_epoch + step
                if global_step % target_update_interval == 0:
                    trainer.update_target_network()

                if global_step % log_interval == 0:
                    print(
                        f"epoch {epoch}/{epochs}  step {step}/{steps_per_epoch}  "
                        f"loss={metrics.loss:.4f}  td={metrics.td_loss:.4f}  "
                        f"cql={metrics.conservative_loss:.4f}  bc={metrics.bc_loss:.4f}  "
                        f"value={metrics.value_loss:.4f}"
                    )

            trainer.update_target_network()
            avg_loss = epoch_loss / steps_per_epoch
            print(f"--- epoch {epoch} avg_loss={avg_loss:.4f}")

            checkpoint_dir.mkdir(parents=True, exist_ok=True)
            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            save_checkpoint(
                checkpoint_path,
                model,
                optimizer,
                step=epoch,
            )
            if mlflow_run is not None and latest_metrics is not None:
                log_metrics(
                    {
                        "train": {
                            "avg_loss": avg_loss,
                            "last_loss": latest_metrics.loss,
                            "last_td_loss": latest_metrics.td_loss,
                            "last_conservative_loss": latest_metrics.conservative_loss,
                            "last_bc_loss": latest_metrics.bc_loss,
                            "last_value_loss": latest_metrics.value_loss,
                            "last_avg_q": latest_metrics.avg_q,
                            "last_avg_target": latest_metrics.avg_target,
                        }
                    },
                    step=epoch,
                )
                log_artifact(checkpoint_path, artifact_path="checkpoints")

        if mlflow_run is not None:
            print(f"MLflow run: {mlflow_run.info.run_id}")

    return all_metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train conservative offline Q model")
    parser.add_argument("--data", type=Path, required=True, help="JSONL trajectory data")
    parser.add_argument("--checkpoint-dir", type=Path, default=Path("checkpoints/offline_q"))
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--gamma", type=float, default=0.99)
    parser.add_argument("--conservative-weight", type=float, default=0.1)
    parser.add_argument("--bc-weight", type=float, default=0.1)
    parser.add_argument("--value-weight", type=float, default=0.25)
    parser.add_argument("--target-update-interval", type=int, default=25)
    parser.add_argument("--target-tau", type=float, default=1.0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--log-interval", type=int, default=10)
    parser.add_argument("--init-checkpoint", type=Path, default=None, help="Optional BC checkpoint to warm-start from")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--mlflow", action="store_true", help="Log training params, metrics, and artifacts to MLflow")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    args = parser.parse_args()

    print(f"Loading data from {args.data}...")
    metrics = train_offline_q(
        data_path=args.data,
        checkpoint_dir=args.checkpoint_dir,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        gamma=args.gamma,
        conservative_weight=args.conservative_weight,
        bc_weight=args.bc_weight,
        value_weight=args.value_weight,
        target_update_interval=args.target_update_interval,
        target_tau=args.target_tau,
        device=args.device,
        log_interval=args.log_interval,
        init_checkpoint=args.init_checkpoint,
        resume=args.resume,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
    )
    print(f"Training complete. Final loss: {metrics[-1].loss:.4f}")


if __name__ == "__main__":
    main()
