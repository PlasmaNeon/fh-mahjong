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
from fh_mahjong_ai.risk_filter import (
    RiskCase,
    RiskWeightReport,
    apply_risk_case_weights,
    load_risk_cases_from_paired_trace_reports,
)
from fh_mahjong_ai.scripts.model_config_args import add_model_config_args, model_config_from_args, model_config_params
from fh_mahjong_ai.storage import load_checkpoint, read_transition_arrays, save_checkpoint


RISK_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "terminal_rewards",
    "episode_index",
)

OPTIONAL_RISK_ARRAY_KEYS = (
    "decision_indices",
    "sample_weights",
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_weights",
    "pairwise_reward_delta_targets",
)

PAIRWISE_ARRAY_KEYS = (
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_weights",
    "pairwise_reward_delta_targets",
)


@dataclass(frozen=True)
class RiskTrainingConfig:
    threshold: float = -1.0
    target_mode: str = "terminal"
    score_pressure_threshold: float = 0.6
    score_pressure_weight: float = 0.5
    batch_size: int = 2048
    learning_rate: float = 1e-4
    weight_decay: float = 1e-4
    epochs: int = 1
    steps_per_epoch: Optional[int] = None
    positive_fraction: float = 0.5
    severity_weight: float = 0.2
    paired_margin_weight: float = 0.0
    paired_severity_weight: float = 0.0
    paired_margin: float = 0.1
    paired_delta_scale: float = 1.0
    paired_delta_clip: float = 5.0
    paired_batch_fraction: float = 0.25
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
    paired_margin_loss: float
    paired_severity_loss: float
    batch_positive_rate: float
    positive_probability: float
    negative_probability: float
    severity_mae: float
    paired_count: int
    paired_delta_mae: float


def train_action_risk(
    data_paths: Sequence[Path],
    checkpoint_dir: Path,
    init_checkpoint: Path,
    config: RiskTrainingConfig,
    env_config: Optional[EnvConfig] = None,
    model_config: Optional[ModelConfig] = None,
    max_transitions: Optional[int] = None,
    risk_cases: Sequence[RiskCase] = (),
    risk_case_weight: float = 1.0,
    risk_dataset_start_seeds: Optional[Sequence[int]] = None,
    mlflow_enabled: bool = False,
    mlflow_tracking_uri: Optional[str] = None,
    mlflow_experiment: str = DEFAULT_EXPERIMENT_NAME,
    mlflow_run_name: Optional[str] = None,
    report_output: Optional[Path] = None,
) -> list[RiskTrainingMetrics]:
    arrays, risk_reports = load_risk_arrays(
        data_paths,
        max_transitions=max_transitions,
        risk_cases=risk_cases,
        risk_case_weight=risk_case_weight,
        risk_dataset_start_seeds=risk_dataset_start_seeds,
    )
    labels, severities = risk_targets(
        arrays,
        threshold=config.threshold,
        target_mode=config.target_mode,
        score_pressure_threshold=config.score_pressure_threshold,
        score_pressure_weight=config.score_pressure_weight,
    )
    positive_indices = np.flatnonzero(labels > 0.5).astype(np.int64)
    negative_indices = np.flatnonzero(labels <= 0.5).astype(np.int64)
    if positive_indices.size == 0 or negative_indices.size == 0:
        raise ValueError(
            "balanced action-risk training needs both positive and negative large-loss rows; "
            f"positives={positive_indices.size} negatives={negative_indices.size}"
        )

    paired_indices = np.flatnonzero(np.asarray(arrays.get("pairwise_weights", []), dtype=np.float32) > 0.0).astype(np.int64)

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
                    "risk_trace_cases": int(sum(report.cases for report in risk_reports)),
                    "risk_trace_matched_cases": int(sum(report.matched_cases for report in risk_reports)),
                    "paired_transitions": int(paired_indices.size),
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
                    batch_size=paired_balanced_batch_size(effective_batch, paired_indices, config),
                    positive_fraction=config.positive_fraction,
                    rng=rng,
                )
                batch_indices = append_paired_batch_indices(batch_indices, paired_indices, effective_batch, config, rng)
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
                        f"sev_mae={latest.severity_mae:.4f} paired={latest.paired_margin_loss:.4f}/{latest.paired_count}",
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
            "risk_reports": [asdict(report) for report in risk_reports],
            "paired_transitions": int(paired_indices.size),
            "config": asdict(config),
            "metrics": [asdict(metric) for metric in metrics],
        }
        report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


def load_risk_arrays(
    data_paths: Sequence[Path],
    max_transitions: Optional[int] = None,
    risk_cases: Sequence[RiskCase] = (),
    risk_case_weight: float = 1.0,
    risk_dataset_start_seeds: Optional[Sequence[int]] = None,
) -> tuple[dict[str, np.ndarray], list[RiskWeightReport]]:
    start_seeds = list(risk_dataset_start_seeds or [])
    loaded = []
    risk_reports: list[RiskWeightReport] = []
    for path_index, path in enumerate(data_paths):
        arrays = read_transition_arrays(
            path,
            keys=RISK_ARRAY_KEYS,
            optional_keys=OPTIONAL_RISK_ARRAY_KEYS,
            limit=max_transitions,
        )
        ensure_pairwise_arrays(arrays)
        if risk_cases:
            dataset_start_seed = start_seeds[path_index] if path_index < len(start_seeds) else None
            risk_reports.append(
                apply_risk_case_weights(
                    arrays,
                    risk_cases,
                    weight=risk_case_weight,
                    dataset_start_seed=dataset_start_seed,
                )
            )
        loaded.append(arrays)
    if not loaded:
        raise ValueError("at least one data path is required")
    if len(loaded) == 1:
        return loaded[0], risk_reports
    common_keys = set.intersection(*(set(arrays.keys()) for arrays in loaded))
    merge_keys = set(RISK_ARRAY_KEYS).union(PAIRWISE_ARRAY_KEYS).union(common_keys.intersection(OPTIONAL_RISK_ARRAY_KEYS))
    merged = {
        key: _concat_with_padding([arrays[key] for arrays in loaded])
        for key in sorted(merge_keys)
    }
    ensure_pairwise_arrays(merged)
    return merged, risk_reports


def ensure_pairwise_arrays(arrays: dict[str, np.ndarray]) -> None:
    rows = int(arrays["action_ids"].shape[0])
    arrays.setdefault("pairwise_preferred_action_ids", np.full(rows, -1, dtype=np.int64))
    arrays.setdefault("pairwise_avoided_action_ids", np.full(rows, -1, dtype=np.int64))
    arrays.setdefault("pairwise_weights", np.zeros(rows, dtype=np.float32))
    arrays.setdefault("pairwise_reward_delta_targets", np.zeros(rows, dtype=np.float32))


def infer_env_config(arrays: dict[str, np.ndarray]) -> EnvConfig:
    default = EnvConfig()
    scalar_features = max(default.scalar_features, int(arrays["scalars"].shape[1]))
    return EnvConfig(
        action_space_size=int(arrays["action_mask"].shape[1]),
        plane_shape=tuple(int(dim) for dim in arrays["planes"].shape[1:]),
        scalar_features=scalar_features,
    )


def risk_targets(
    arrays: dict[str, np.ndarray],
    threshold: float,
    target_mode: str = "terminal",
    score_pressure_threshold: float = 0.6,
    score_pressure_weight: float = 0.5,
) -> tuple[np.ndarray, np.ndarray]:
    seats = arrays["seats"].astype(np.int64, copy=False)
    row_indices = np.arange(seats.shape[0])
    returns = arrays["terminal_rewards"][row_indices, seats].astype(np.float32, copy=False)
    terminal_labels = returns <= float(threshold)
    severities = np.maximum(float(threshold) - returns, 0.0).astype(np.float32)
    normalized_mode = target_mode.lower()
    if normalized_mode == "terminal":
        labels = terminal_labels.astype(np.float32)
        return labels, severities
    if normalized_mode == "score_pressure":
        pressure = chongci_score_pressure(arrays)
        pressured_loss = (returns <= 0.0) & (pressure >= float(score_pressure_threshold))
        labels = (terminal_labels | pressured_loss).astype(np.float32)
        pressure_severity = np.maximum(-returns, 0.0).astype(np.float32) * pressure.astype(np.float32)
        severities = severities + float(score_pressure_weight) * pressure_severity
        return labels, severities.astype(np.float32, copy=False)
    raise ValueError(f"unsupported action-risk target_mode={target_mode!r}")


def chongci_score_pressure(arrays: dict[str, np.ndarray]) -> np.ndarray:
    scalars = arrays.get("scalars")
    rows = int(arrays["action_ids"].shape[0])
    if scalars is None or scalars.ndim != 2 or scalars.shape[1] <= 57:
        return np.zeros(rows, dtype=np.float32)
    is_chongci = scalars[:, 42].astype(np.float32, copy=False)
    hand_progress = scalars[:, 43].astype(np.float32, copy=False)
    leader_pressure = scalars[:, 46].astype(np.float32, copy=False)
    low_large_loss_margin = 1.0 - scalars[:, 47].astype(np.float32, copy=False)
    low_bust_margin = 1.0 - scalars[:, 48].astype(np.float32, copy=False)
    opponent_large_loss_pressure = scalars[:, 49].astype(np.float32, copy=False)
    public_threat = scalars[:, 57].astype(np.float32, copy=False)
    pressure = (
        0.35 * low_large_loss_margin
        + 0.20 * low_bust_margin
        + 0.15 * leader_pressure
        + 0.15 * opponent_large_loss_pressure
        + 0.10 * public_threat
        + 0.05 * hand_progress
    )
    pressure = np.clip(pressure, 0.0, 1.0)
    return (pressure * np.clip(is_chongci, 0.0, 1.0)).astype(np.float32, copy=False)
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


def paired_balanced_batch_size(
    batch_size: int,
    paired_indices: np.ndarray,
    config: RiskTrainingConfig,
) -> int:
    if paired_indices.size == 0 or (config.paired_margin_weight <= 0.0 and config.paired_severity_weight <= 0.0):
        return batch_size
    paired_count = int(round(max(0.0, min(1.0, config.paired_batch_fraction)) * batch_size))
    return max(2, batch_size - max(0, paired_count))


def append_paired_batch_indices(
    batch_indices: np.ndarray,
    paired_indices: np.ndarray,
    batch_size: int,
    config: RiskTrainingConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    if paired_indices.size == 0 or (config.paired_margin_weight <= 0.0 and config.paired_severity_weight <= 0.0):
        return batch_indices
    paired_count = max(1, batch_size - int(batch_indices.shape[0]))
    paired = rng.choice(paired_indices, size=paired_count, replace=paired_indices.size < paired_count)
    combined = np.concatenate([batch_indices, paired.astype(np.int64, copy=False)]).astype(np.int64, copy=False)
    rng.shuffle(combined)
    return combined


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
    paired_margin_loss, paired_severity_loss, paired_count, paired_delta_mae = pairwise_risk_losses(
        risk_logits,
        risk_severities,
        action_mask,
        arrays,
        indices,
        config,
    )
    loss = (
        probability_loss
        + float(config.severity_weight) * severity_loss
        + float(config.paired_margin_weight) * paired_margin_loss
        + float(config.paired_severity_weight) * paired_severity_loss
    )

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
        "paired_margin_loss": float(paired_margin_loss.item()),
        "paired_severity_loss": float(paired_severity_loss.item()),
        "batch_positive_rate": float(target_labels.mean().item()),
        "positive_probability": float(positive_probability.item()),
        "negative_probability": float(negative_probability.item()),
        "severity_mae": float(severity_mae.item()),
        "paired_count": paired_count,
        "paired_delta_mae": paired_delta_mae,
    }


def pairwise_risk_losses(
    risk_logits: torch.Tensor,
    risk_severities: torch.Tensor,
    action_mask: torch.Tensor,
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    config: RiskTrainingConfig,
) -> tuple[torch.Tensor, torch.Tensor, int, float]:
    zero = risk_logits.new_zeros(())
    preferred_action_ids = torch.from_numpy(
        arrays["pairwise_preferred_action_ids"][indices].astype(np.int64, copy=False)
    ).to(config.device)
    avoided_action_ids = torch.from_numpy(arrays["pairwise_avoided_action_ids"][indices].astype(np.int64, copy=False)).to(
        config.device
    )
    pairwise_weights = torch.from_numpy(arrays["pairwise_weights"][indices].astype(np.float32, copy=False)).to(config.device)
    reward_deltas = torch.from_numpy(
        arrays["pairwise_reward_delta_targets"][indices].astype(np.float32, copy=False)
    ).to(config.device)

    valid = (
        (pairwise_weights > 0.0)
        & (preferred_action_ids >= 0)
        & (avoided_action_ids >= 0)
        & (preferred_action_ids != avoided_action_ids)
    )
    action_count = risk_logits.shape[1]
    valid &= preferred_action_ids < action_count
    valid &= avoided_action_ids < action_count
    if action_mask.numel() > 0:
        rows = torch.arange(risk_logits.shape[0], device=risk_logits.device)
        preferred_legal = action_mask[rows, torch.clamp(preferred_action_ids, min=0, max=action_count - 1)] > 0
        avoided_legal = action_mask[rows, torch.clamp(avoided_action_ids, min=0, max=action_count - 1)] > 0
        valid &= preferred_legal & avoided_legal

    count = int(valid.sum().item())
    if count == 0:
        return zero, zero, 0, 0.0

    selected_logits = risk_logits[valid]
    selected_severities = risk_severities[valid]
    selected_preferred = preferred_action_ids[valid]
    selected_avoided = avoided_action_ids[valid]
    selected_weights = pairwise_weights[valid].to(dtype=risk_logits.dtype, device=risk_logits.device)
    scale = max(float(config.paired_delta_scale), 1e-6)
    delta_targets = torch.clamp(reward_deltas[valid] / scale, min=0.0, max=float(config.paired_delta_clip))

    preferred_logits = selected_logits.gather(1, selected_preferred.unsqueeze(1)).squeeze(1)
    avoided_logits = selected_logits.gather(1, selected_avoided.unsqueeze(1)).squeeze(1)
    risk_gap = avoided_logits - preferred_logits
    margin_targets = float(config.paired_margin) + delta_targets
    margin_losses = torch.relu(margin_targets - risk_gap)

    preferred_severity = selected_severities.gather(1, selected_preferred.unsqueeze(1)).squeeze(1)
    avoided_severity = selected_severities.gather(1, selected_avoided.unsqueeze(1)).squeeze(1)
    severity_gap = avoided_severity - preferred_severity
    severity_losses = nn.functional.smooth_l1_loss(severity_gap, delta_targets, reduction="none")

    margin_loss = weighted_mean(margin_losses, selected_weights)
    severity_loss = weighted_mean(severity_losses, selected_weights)
    with torch.inference_mode():
        paired_delta_mae = torch.mean(torch.abs(severity_gap - delta_targets))
    return margin_loss, severity_loss, count, float(paired_delta_mae.item())


def weighted_mean(values: torch.Tensor, weights: torch.Tensor) -> torch.Tensor:
    weights = weights.to(dtype=values.dtype, device=values.device)
    return torch.sum(values * weights) / torch.clamp(torch.sum(weights), min=1e-6)


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
    parser.add_argument(
        "--target-mode",
        choices=("terminal", "score_pressure"),
        default="terminal",
        help="Risk target definition. score_pressure adds visible Chongci match-pressure positives.",
    )
    parser.add_argument("--score-pressure-threshold", type=float, default=0.6)
    parser.add_argument("--score-pressure-weight", type=float, default=0.5)
    parser.add_argument("--positive-fraction", type=float, default=0.5)
    parser.add_argument("--severity-weight", type=float, default=0.2)
    parser.add_argument("--paired-trace-report", action="append", type=Path, default=[])
    parser.add_argument(
        "--paired-dataset-start-seed",
        action="append",
        type=int,
        default=[],
        help="Dataset start seed for each --data path, used to map paired trace seeds to episode_index.",
    )
    parser.add_argument("--paired-trace-right-label", type=str, default="candidate")
    parser.add_argument("--paired-trace-left-label", type=str, default="anchor")
    parser.add_argument("--paired-trace-weight", type=float, default=1.0)
    parser.add_argument("--paired-trace-worst-delta-count", type=int, default=0)
    parser.add_argument("--paired-margin-weight", type=float, default=0.0)
    parser.add_argument("--paired-severity-weight", type=float, default=0.0)
    parser.add_argument("--paired-margin", type=float, default=0.1)
    parser.add_argument("--paired-delta-scale", type=float, default=1.0)
    parser.add_argument("--paired-delta-clip", type=float, default=5.0)
    parser.add_argument("--paired-batch-fraction", type=float, default=0.25)
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
    risk_cases = load_risk_cases_from_paired_trace_reports(
        args.paired_trace_report,
        right_label=args.paired_trace_right_label,
        left_label=args.paired_trace_left_label,
        large_loss_threshold=args.threshold,
        worst_delta_count=args.paired_trace_worst_delta_count,
    ) if args.paired_trace_report else []

    train_action_risk(
        data_paths=parse_data_paths(args.data),
        checkpoint_dir=args.checkpoint_dir,
        init_checkpoint=args.init_checkpoint,
        config=RiskTrainingConfig(
            threshold=args.threshold,
            target_mode=args.target_mode,
            score_pressure_threshold=args.score_pressure_threshold,
            score_pressure_weight=args.score_pressure_weight,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            weight_decay=args.weight_decay,
            epochs=args.epochs,
            steps_per_epoch=args.steps_per_epoch,
            positive_fraction=args.positive_fraction,
            severity_weight=args.severity_weight,
            paired_margin_weight=args.paired_margin_weight,
            paired_severity_weight=args.paired_severity_weight,
            paired_margin=args.paired_margin,
            paired_delta_scale=args.paired_delta_scale,
            paired_delta_clip=args.paired_delta_clip,
            paired_batch_fraction=args.paired_batch_fraction,
            train_encoder=not args.freeze_encoder,
            seed=args.seed,
            device=args.device,
        ),
        model_config=model_config_from_args(args),
        max_transitions=args.max_transitions,
        risk_cases=risk_cases,
        risk_case_weight=args.paired_trace_weight,
        risk_dataset_start_seeds=args.paired_dataset_start_seed,
        mlflow_enabled=args.mlflow,
        mlflow_tracking_uri=args.mlflow_tracking_uri,
        mlflow_experiment=args.mlflow_experiment,
        mlflow_run_name=args.mlflow_run_name,
        report_output=args.report_output,
    )


if __name__ == "__main__":
    main()
