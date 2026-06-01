"""Train action-conditioned large-loss risk heads from saved transitions."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import torch
from torch import nn

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.mlflow_tracking import DEFAULT_EXPERIMENT_NAME, log_artifact, log_metrics, log_params, start_run
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays, save_checkpoint


RISK_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "terminal_rewards",
)


@dataclass(frozen=True)
class RiskTrainingConfig:
    threshold: float = -1.0
    batch_size: int = 2048
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    epochs: int = 1
    steps_per_epoch: Optional[int] = None
    positive_fraction: float = 0.5
    severity_weight: float = 0.2
    train_encoder: bool = True
    seed: int = 0
    device: str = "cpu"


@dataclass(frozen=True)
class RiskTrainingMetrics:
    epoch: int
    step: int
    loss: float
    probability_loss: float
    severity_loss: float
    batch_positive_rate: float
    positive_probability: float
    negative_probability: float
    severity_mae: float


def train_action_risk(
    data_paths: Sequence[Path],
    checkpoint_dir: Path,
    init_checkpoint: Path,
    config: RiskTrainingConfig,
    env_config: Optional[EnvConfig] = None,
    model_config: Optional[ModelConfig] = None,
    max_transitions: Optional[int] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
    report_output: Optional[Path] = None,
) -> list[RiskTrainingMetrics]:
    arrays = load_risk_arrays(data_paths, max_transitions=max_transitions)
    labels, severities = risk_targets(arrays, threshold=config.threshold)
    positive_indices = np.flatnonzero(labels > 0.5).astype(np.int64)
    negative_indices = np.flatnonzero(labels <= 0.5).astype(np.int64)
    if positive_indices.size == 0 or negative_indices.size == 0:
        raise ValueError(
            "balanced action-risk training needs both positive and negative large-loss rows; "
            f"positives={positive_indices.size} negatives={negative_indices.size}"
        )

    env_config = env_config or infer_env_config(arrays)
    model = PolicyValueNet(env_config, model_config or ModelConfig()).to(config.device)
    load_checkpoint(init_checkpoint, model)
    configure_trainable_parameters(model, train_encoder=config.train_encoder)
    optimizer = torch.optim.AdamW(
        [param for param in model.parameters() if param.requires_grad],
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )

    effective_batch = min(max(2, int(config.batch_size)), int(arrays["action_ids"].shape[0]))
    steps_per_epoch = config.steps_per_epoch or max(1, int(arrays["action_ids"].shape[0]) // effective_batch)
    rng = np.random.default_rng(config.seed)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)

    metrics: list[RiskTrainingMetrics] = []
    with start_run(
        enabled=mlflow_enabled,
        experiment_name=mlflow_experiment,
        tracking_uri=mlflow_tracking_uri,
        run_name=mlflow_run_name,
        tags={"stage": "training", "method": "balanced_action_risk"},
    ) as mlflow_run:
        if mlflow_run is not None:
            log_params(
                {
                    "method": "balanced_action_risk",
                    "data_paths": ",".join(str(path) for path in data_paths),
                    "checkpoint_dir": checkpoint_dir,
                    "init_checkpoint": init_checkpoint,
                    "transitions": int(arrays["action_ids"].shape[0]),
                    "positive_transitions": int(positive_indices.size),
                    "negative_transitions": int(negative_indices.size),
                    "positive_rate": float(np.mean(labels)),
                    "max_transitions": max_transitions,
                    **asdict(config),
                    **model_config_params(model_config or ModelConfig()),
                }
            )

        for epoch in range(1, config.epochs + 1):
            latest: Optional[RiskTrainingMetrics] = None
            for step in range(1, steps_per_epoch + 1):
                batch_indices = balanced_batch_indices(
                    positive_indices,
                    negative_indices,
                    batch_size=effective_batch,
                    positive_fraction=config.positive_fraction,
                    rng=rng,
                )
                metric = train_risk_step(model, optimizer, arrays, labels, severities, batch_indices, config)
                latest = RiskTrainingMetrics(epoch=epoch, step=step, **metric)
                metrics.append(latest)
                if mlflow_run is not None:
                    log_metrics(asdict(latest), step=(epoch - 1) * steps_per_epoch + step)
                if step == 1 or step % 20 == 0 or step == steps_per_epoch:
                    print(
                        f"epoch {epoch}/{config.epochs} step {step}/{steps_per_epoch} "
                        f"loss={latest.loss:.4f} prob={latest.probability_loss:.4f} "
                        f"sev={latest.severity_loss:.4f} pos={latest.batch_positive_rate:.3f} "
                        f"p_pos={latest.positive_probability:.3f} p_neg={latest.negative_probability:.3f} "
                        f"sev_mae={latest.severity_mae:.4f}",
                        flush=True,
                    )

            checkpoint_path = checkpoint_dir / f"epoch_{epoch:03d}.pt"
            save_checkpoint(checkpoint_path, model, optimizer, step=epoch)
            if mlflow_run is not None:
                log_artifact(checkpoint_path, artifact_path="checkpoints")
                if latest is not None:
                    log_metrics({"epoch_loss": latest.loss}, step=epoch)

    if report_output is not None:
        report_output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": 1,
            "method": "balanced_action_risk",
            "data_paths": [str(path) for path in data_paths],
            "checkpoint_dir": str(checkpoint_dir),
            "init_checkpoint": str(init_checkpoint),
            "transitions": int(arrays["action_ids"].shape[0]),
            "positive_transitions": int(positive_indices.size),
            "negative_transitions": int(negative_indices.size),
            "positive_rate": float(np.mean(labels)),
            "config": asdict(config),
            "metrics": [asdict(metric) for metric in metrics],
        }
        report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def load_risk_arrays(data_paths: Sequence[Path], max_transitions: Optional[int] = None) -> dict[str, np.ndarray]:
    loaded = [read_transition_arrays(path, keys=RISK_ARRAY_KEYS, limit=max_transitions) for path in data_paths]
    if not loaded:
        raise ValueError("at least one data path is required")
    if len(loaded) == 1:
        return loaded[0]
    return {
        key: _concat_with_padding([arrays[key] for arrays in loaded])
        for key in RISK_ARRAY_KEYS
    }


def infer_env_config(arrays: dict[str, np.ndarray]) -> EnvConfig:
    default = EnvConfig()
    scalar_features = max(default.scalar_features, int(arrays["scalars"].shape[1]))
    return EnvConfig(
        action_space_size=int(arrays["action_mask"].shape[1]),
        plane_shape=tuple(int(dim) for dim in arrays["planes"].shape[1:]),
        scalar_features=scalar_features,
    )


def risk_targets(arrays: dict[str, np.ndarray], threshold: float) -> tuple[np.ndarray, np.ndarray]:
    seats = arrays["seats"].astype(np.int64, copy=False)
    row_indices = np.arange(seats.shape[0])
    returns = arrays["terminal_rewards"][row_indices, seats].astype(np.float32, copy=False)
    labels = (returns <= float(threshold)).astype(np.float32)
    severities = np.maximum(float(threshold) - returns, 0.0).astype(np.float32)
    return labels, severities


def balanced_batch_indices(
    positive_indices: np.ndarray,
    negative_indices: np.ndarray,
    batch_size: int,
    positive_fraction: float,
    rng: np.random.Generator,
) -> np.ndarray:
    positive_count = int(round(max(0.0, min(1.0, positive_fraction)) * batch_size))
    positive_count = min(max(1, positive_count), batch_size - 1)
    negative_count = batch_size - positive_count
    positives = rng.choice(positive_indices, size=positive_count, replace=positive_indices.size < positive_count)
    negatives = rng.choice(negative_indices, size=negative_count, replace=negative_indices.size < negative_count)
    batch = np.concatenate([positives, negatives]).astype(np.int64, copy=False)
    rng.shuffle(batch)
    return batch


def configure_trainable_parameters(model: nn.Module, train_encoder: bool) -> None:
    for param in model.parameters():
        param.requires_grad = False
    for module_name in ("action_risk_probability_head", "action_risk_severity_head"):
        for param in getattr(model, module_name).parameters():
            param.requires_grad = True
    if not train_encoder:
        return
    for module_name in ("plane_stem", "plane_blocks", "plane_projection", "plane_head", "scalar_encoder", "trunk"):
        for param in getattr(model, module_name).parameters():
            param.requires_grad = True


def train_risk_step(
    model: PolicyValueNet,
    optimizer: torch.optim.Optimizer,
    arrays: dict[str, np.ndarray],
    labels: np.ndarray,
    severities: np.ndarray,
    indices: np.ndarray,
    config: RiskTrainingConfig,
) -> dict[str, float]:
    model.train()
    planes = torch.from_numpy(arrays["planes"][indices].astype(np.float32, copy=False)).to(config.device)
    scalars = torch.from_numpy(arrays["scalars"][indices].astype(np.float32, copy=False)).to(config.device)
    action_mask = torch.from_numpy(arrays["action_mask"][indices].astype(np.int8, copy=False)).to(config.device)
    action_ids = torch.from_numpy(arrays["action_ids"][indices].astype(np.int64, copy=False)).to(config.device)
    target_labels = torch.from_numpy(labels[indices].astype(np.float32, copy=False)).to(config.device)
    target_severities = torch.from_numpy(severities[indices].astype(np.float32, copy=False)).to(config.device)

    risk_logits, risk_severities = model.action_risk_predictions(planes, scalars, action_mask)
    logits = risk_logits.gather(1, action_ids.unsqueeze(1)).squeeze(1)
    severity = risk_severities.gather(1, action_ids.unsqueeze(1)).squeeze(1)
    probability_loss = nn.functional.binary_cross_entropy_with_logits(logits, target_labels)
    severity_loss = nn.functional.smooth_l1_loss(severity, target_severities)
    loss = probability_loss + float(config.severity_weight) * severity_loss

    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    nn.utils.clip_grad_norm_([param for param in model.parameters() if param.requires_grad], max_norm=5.0)
    optimizer.step()

    with torch.inference_mode():
        probabilities = torch.sigmoid(logits)
        positives = target_labels > 0.5
        negatives = ~positives
        positive_probability = probabilities[positives].mean() if positives.any() else torch.tensor(0.0, device=config.device)
        negative_probability = probabilities[negatives].mean() if negatives.any() else torch.tensor(0.0, device=config.device)
        severity_mae = torch.mean(torch.abs(severity - target_severities))
    return {
        "loss": float(loss.item()),
        "probability_loss": float(probability_loss.item()),
        "severity_loss": float(severity_loss.item()),
        "batch_positive_rate": float(target_labels.mean().item()),
        "positive_probability": float(positive_probability.item()),
        "negative_probability": float(negative_probability.item()),
        "severity_mae": float(severity_mae.item()),
    }


def _concat_with_padding(arrays: Sequence[np.ndarray]) -> np.ndarray:
    target_shape = tuple(max(array.shape[axis] for array in arrays) for axis in range(1, arrays[0].ndim))
    padded = []
    for array in arrays:
        pad_width = [(0, 0)]
        for current, target in zip(array.shape[1:], target_shape):
            if current > target:
                raise ValueError(f"cannot pad array shape {array.shape} down to target feature shape {target_shape}")
            pad_width.append((0, target - current))
        padded.append(np.pad(array, pad_width, mode="constant") if array.shape[1:] != target_shape else array)
    return np.concatenate(padded, axis=0)


def parse_data_paths(values: Sequence[str]) -> list[Path]:
    paths = [Path(value) for value in values]
    if not paths:
        raise ValueError("at least one --data path is required")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Train action-conditioned large-loss risk heads")
    parser.add_argument("--data", action="append", required=True, help="Sharded transition dataset. Repeat to mix data.")
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--init-checkpoint", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, default=None)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--steps-per-epoch", type=int, default=None)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--threshold", type=float, default=-1.0)
    parser.add_argument("--positive-fraction", type=float, default=0.5)
    parser.add_argument("--severity-weight", type=float, default=0.2)
    parser.add_argument("--freeze-encoder", action="store_true")
    parser.add_argument("--max-transitions", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--mlflow", action="store_true")
    parser.add_argument("--mlflow-tracking-uri", type=str, default=None)
    parser.add_argument("--mlflow-experiment", type=str, default=DEFAULT_EXPERIMENT_NAME)
    parser.add_argument("--mlflow-run-name", type=str, default=None)
    add_model_config_args(parser)
    args = parser.parse_args()

    train_action_risk(
        data_paths=parse_data_paths(args.data),
        checkpoint_dir=args.checkpoint_dir,
        init_checkpoint=args.init_checkpoint,
        config=RiskTrainingConfig(
            threshold=args.threshold,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            weight_decay=args.weight_decay,
            epochs=args.epochs,
            steps_per_epoch=args.steps_per_epoch,
            positive_fraction=args.positive_fraction,
            severity_weight=args.severity_weight,
            train_encoder=not args.freeze_encoder,
            seed=args.seed,
            device=args.device,
        ),
        model_config=model_config_from_args(args),
        max_transitions=args.max_transitions,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
        report_output=args.report_output,
    )


if __name__ == "__main__":
    main()
