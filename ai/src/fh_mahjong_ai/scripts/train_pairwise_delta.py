"""Train a direct paired-trace candidate-anchor reward-delta predictor."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch

from fh_mahjong_ai.paired_trace_delta import (
    PairwiseDeltaNet,
    PairwiseSequenceDeltaNet,
    build_pairwise_delta_arrays,
    evaluate_pairwise_delta,
    score_paired_trace_delta,
)
from fh_mahjong_ai.storage import save_checkpoint


@dataclass(frozen=True)
class PairwiseDeltaTrainConfig:
    batch_size: int = 64
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    epochs: int = 1
    steps_per_epoch: int = 100
    validation_mod: int = 10
    validation_remainder: int = 0
    seed: int = 0
    device: str = "cpu"
    sequence_model: bool = False
    source_balanced_batches: bool = False
    worst_source_loss_weight: float = 0.0


def train_pairwise_delta(
    train_reports: Sequence[Path],
    checkpoint_dir: Path,
    config: PairwiseDeltaTrainConfig,
    eval_reports: dict[str, Path],
    report_output: Path | None = None,
    left_label: str = "anchor",
    right_label: str = "candidate",
    min_abs_delta: float = 0.0,
    guard_margins: Sequence[float] = (0.0,),
) -> dict[str, object]:
    arrays, metadata = build_pairwise_delta_arrays(
        train_reports,
        left_label=left_label,
        right_label=right_label,
        min_abs_delta=min_abs_delta,
        include_trajectory_context=True,
    )
    train_indices, validation_indices = episode_split_indices(
        arrays["episode_index"],
        validation_mod=config.validation_mod,
        validation_remainder=config.validation_remainder,
    )
    model_cls = PairwiseSequenceDeltaNet if config.sequence_model else PairwiseDeltaNet
    model = model_cls(scalar_features=int(arrays["scalars"].shape[1])).to(config.device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    rng = np.random.default_rng(config.seed)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    effective_batch = min(max(1, int(config.batch_size)), int(train_indices.size))
    history: list[dict[str, float | int]] = []
    loss_fn = torch.nn.MSELoss()

    for epoch in range(1, int(config.epochs) + 1):
        model.train()
        last_loss = 0.0
        for step in range(1, int(config.steps_per_epoch) + 1):
            batch_indices = sample_batch_indices(
                rng,
                train_indices,
                arrays["source_ids"],
                batch_size=effective_batch,
                source_balanced=config.source_balanced_batches,
            )
            scalars = torch.from_numpy(arrays["scalars"][batch_indices].astype(np.float32)).to(config.device)
            left_actions = torch.from_numpy(arrays["left_action_ids"][batch_indices].astype(np.int64)).to(config.device)
            right_actions = torch.from_numpy(arrays["right_action_ids"][batch_indices].astype(np.int64)).to(config.device)
            targets = torch.from_numpy(arrays["targets"][batch_indices].astype(np.float32)).to(config.device)
            source_ids = torch.from_numpy(arrays["source_ids"][batch_indices].astype(np.int64)).to(config.device)
            if config.sequence_model:
                sequences = torch.from_numpy(arrays["sequence_features"][batch_indices].astype(np.float32)).to(config.device)
                predictions = model(scalars, left_actions, right_actions, sequences)
            else:
                predictions = model(scalars, left_actions, right_actions)
            per_item_loss = torch.square(predictions - targets)
            loss = per_item_loss.mean()
            if config.worst_source_loss_weight > 0.0:
                source_losses = []
                for source_id in torch.unique(source_ids):
                    mask = source_ids == source_id
                    if torch.any(mask):
                        source_losses.append(per_item_loss[mask].mean())
                if source_losses:
                    loss = loss + float(config.worst_source_loss_weight) * torch.stack(source_losses).max()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            optimizer.step()
            last_loss = float(loss.detach().cpu().item())
            if step == 1 or step == int(config.steps_per_epoch) or step % 20 == 0:
                print(f"epoch {epoch}/{config.epochs} step {step}/{config.steps_per_epoch} loss={last_loss:.5f}", flush=True)

        train_metrics = evaluate_pairwise_delta(model, arrays, train_indices, device=config.device)
        validation_metrics = evaluate_pairwise_delta(model, arrays, validation_indices, device=config.device)
        source_validation = source_validation_metrics(model, arrays, validation_indices, device=config.device)
        history.append(
            {
                "epoch": epoch,
                "loss": last_loss,
                "train_mae": train_metrics.mae,
                "validation_mae": validation_metrics.mae,
                "validation_rmse": validation_metrics.rmse,
                "validation_correlation": validation_metrics.correlation,
                "worst_source_validation_mae": max(
                    (metrics["mae"] for metrics in source_validation.values()),
                    default=validation_metrics.mae,
                ),
            }
        )
        save_checkpoint(checkpoint_dir / f"epoch_{epoch:03d}.pt", model, optimizer=optimizer, step=epoch)
        print(
            f"--- epoch {epoch} train_mae={train_metrics.mae:.4f} "
            f"val_mae={validation_metrics.mae:.4f} val_corr={validation_metrics.correlation:.4f}",
            flush=True,
        )

    diagnostics: dict[str, object] = {}
    for name, path in eval_reports.items():
        diagnostics[name] = score_paired_trace_delta(
            path,
            model,
            device=config.device,
            left_label=left_label,
            right_label=right_label,
            guard_margins=guard_margins,
        )

    report = {
        "schema_version": 1,
        "method": "train_pairwise_delta",
        "config": asdict(config),
        "metadata": metadata,
        "train_reports": [str(path) for path in train_reports],
        "eval_reports": {name: str(path) for name, path in eval_reports.items()},
        "history": history,
        "source_validation": source_validation_metrics(model, arrays, validation_indices, device=config.device),
        "diagnostics": diagnostics,
        "checkpoint_dir": str(checkpoint_dir),
    }
    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def episode_split_indices(
    episode_index: np.ndarray,
    validation_mod: int = 10,
    validation_remainder: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    episodes = np.asarray(episode_index, dtype=np.int64)
    validation_mask = (episodes % int(validation_mod)) == int(validation_remainder)
    train_indices = np.flatnonzero(~validation_mask)
    validation_indices = np.flatnonzero(validation_mask)
    if train_indices.size == 0 or validation_indices.size == 0:
        raise ValueError("episode split produced an empty train or validation split")
    return train_indices.astype(np.int64), validation_indices.astype(np.int64)


def sample_batch_indices(
    rng: np.random.Generator,
    train_indices: np.ndarray,
    source_ids: np.ndarray,
    batch_size: int,
    source_balanced: bool = False,
) -> np.ndarray:
    if not source_balanced:
        return rng.choice(train_indices, size=batch_size, replace=train_indices.size < batch_size)
    source_values = np.unique(source_ids[train_indices])
    if source_values.size <= 1:
        return rng.choice(train_indices, size=batch_size, replace=train_indices.size < batch_size)
    per_source = max(1, int(np.ceil(batch_size / source_values.size)))
    pieces: list[np.ndarray] = []
    for source_value in source_values:
        candidates = train_indices[source_ids[train_indices] == source_value]
        if candidates.size == 0:
            continue
        pieces.append(rng.choice(candidates, size=per_source, replace=candidates.size < per_source))
    if not pieces:
        return rng.choice(train_indices, size=batch_size, replace=train_indices.size < batch_size)
    batch = np.concatenate(pieces).astype(np.int64)
    rng.shuffle(batch)
    if batch.size < batch_size:
        extra = rng.choice(train_indices, size=batch_size - batch.size, replace=train_indices.size < batch_size)
        batch = np.concatenate([batch, extra.astype(np.int64)])
        rng.shuffle(batch)
    return batch[:batch_size].astype(np.int64)


def source_validation_metrics(
    model: torch.nn.Module,
    arrays: dict[str, np.ndarray],
    validation_indices: np.ndarray,
    device: str = "cpu",
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for source_id in np.unique(arrays["source_ids"][validation_indices]):
        indices = validation_indices[arrays["source_ids"][validation_indices] == source_id]
        if indices.size == 0:
            continue
        metrics = evaluate_pairwise_delta(model, arrays, indices, device=device)
        result[str(int(source_id))] = {
            "rows": int(indices.size),
            "mae": metrics.mae,
            "rmse": metrics.rmse,
            "correlation": metrics.correlation,
        }
    return result


def parse_named_paths(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--eval-report must be formatted as name=/path/to/report.json")
        name, raw_path = value.split("=", 1)
        result[name] = Path(raw_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a paired-trace reward-delta predictor")
    parser.add_argument("--train-report", type=Path, action="append", required=True)
    parser.add_argument("--eval-report", type=str, action="append", default=[])
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="anchor")
    parser.add_argument("--right-label", type=str, default="candidate")
    parser.add_argument("--min-abs-delta", type=float, default=0.0)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--steps-per-epoch", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--validation-mod", type=int, default=10)
    parser.add_argument("--validation-remainder", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument(
        "--sequence-model",
        action="store_true",
        help="Use a compact GRU over visible pre-divergence prefix rows in addition to current scalars/actions.",
    )
    parser.add_argument(
        "--source-balanced-batches",
        action="store_true",
        help="Sample training batches approximately evenly from each train report source.",
    )
    parser.add_argument(
        "--worst-source-loss-weight",
        type=float,
        default=0.0,
        help="Add this weight times the maximum per-source batch MSE to the normal batch MSE.",
    )
    parser.add_argument("--guard-margin", type=float, action="append", default=[0.0, 0.05, 0.10])
    args = parser.parse_args()

    config = PairwiseDeltaTrainConfig(
        batch_size=args.batch_size,
        learning_rate=args.lr,
        weight_decay=args.weight_decay,
        epochs=args.epochs,
        steps_per_epoch=args.steps_per_epoch,
        validation_mod=args.validation_mod,
        validation_remainder=args.validation_remainder,
        seed=args.seed,
        device=args.device,
        sequence_model=bool(args.sequence_model),
        source_balanced_batches=bool(args.source_balanced_batches),
        worst_source_loss_weight=float(args.worst_source_loss_weight),
    )
    report = train_pairwise_delta(
        train_reports=args.train_report,
        checkpoint_dir=args.checkpoint_dir,
        config=config,
        eval_reports=parse_named_paths(args.eval_report),
        report_output=args.report_output,
        left_label=args.left_label,
        right_label=args.right_label,
        min_abs_delta=args.min_abs_delta,
        guard_margins=args.guard_margin,
    )
    print(f"Rows: {report['metadata']['stats']['rows']}")
    if report["history"]:
        final = report["history"][-1]
        print(f"Validation MAE:  {final['validation_mae']:.4f}")
        print(f"Validation Corr: {final['validation_correlation']:.4f}")
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
