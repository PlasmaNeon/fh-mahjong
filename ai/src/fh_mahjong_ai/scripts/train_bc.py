"""Behavior cloning training on heuristic trajectory data."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint, read_transitions_jsonl, save_checkpoint
from fh_mahjong_ai.trainer import BehaviorCloningTrainer, TrainMetrics


def train_bc(
    data_path: Path,
    checkpoint_dir: Path,
    epochs: int = 10,
    batch_size: int = 64,
    learning_rate: float = 3e-4,
    device: str = "cpu",
    log_interval: int = 10,
    resume: bool = False,
) -> List[TrainMetrics]:
    """Run BC training and return collected metrics."""
    transitions = read_transitions_jsonl(data_path)
    backfill_returns(transitions)

    buf = ReplayBuffer(capacity=len(transitions))
    buf.extend(transitions)

    env_config = EnvConfig()
    model_config = ModelConfig()
    model = PolicyValueNet(env_config, model_config).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate, weight_decay=1e-4)

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
    )
    trainer = BehaviorCloningTrainer(model, optimizer, train_config)

    steps_per_epoch = max(1, len(buf) // batch_size)
    all_metrics: List[TrainMetrics] = []

    for epoch in range(start_epoch + 1, epochs + 1):
        epoch_loss = 0.0
        for step in range(1, steps_per_epoch + 1):
            metrics = trainer.train_step(buf)
            all_metrics.append(metrics)
            epoch_loss += metrics.loss

            global_step = (epoch - 1) * steps_per_epoch + step
            if global_step % log_interval == 0:
                print(
                    f"epoch {epoch}/{epochs}  step {step}/{steps_per_epoch}  "
                    f"loss={metrics.loss:.4f}  policy={metrics.policy_loss:.4f}  "
                    f"value={metrics.value_loss:.4f}"
                )

        avg_loss = epoch_loss / steps_per_epoch
        print(f"--- epoch {epoch} avg_loss={avg_loss:.4f}")

        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        save_checkpoint(
            checkpoint_dir / f"epoch_{epoch:03d}.pt",
            model, optimizer, step=epoch,
        )

    return all_metrics


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
    args = parser.parse_args()

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
    )
    print(f"Training complete. Final loss: {metrics[-1].loss:.4f}")


if __name__ == "__main__":
    main()
