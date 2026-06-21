from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import Tensor, nn

from .config import EnvConfig
from .global_ev import GlobalEVMetrics, regression_metrics
from .paired_trace import TRACE_CONTEXT_SCALAR_NAMES, TRACE_SEQUENCE_FEATURE_NAMES, TRACE_SEQUENCE_LENGTH


PAIRWISE_DELTA_ARRAY_KEYS = (
    "scalars",
    "sequence_features",
    "left_action_ids",
    "right_action_ids",
    "targets",
    "episode_index",
    "seats",
    "source_ids",
)


@dataclass(frozen=True)
class PairwiseDeltaBuildStats:
    rows: int
    skipped_missing_divergence: int
    skipped_missing_arrays: int
    skipped_small_delta: int
    target_mean: float
    target_min: float
    target_max: float


class PairwiseDeltaNet(nn.Module):
    """Predict candidate-anchor final reward delta for one paired divergence."""

    def __init__(
        self,
        scalar_features: int,
        action_space_size: int = EnvConfig().action_space_size,
        scalar_hidden_dim: int = 128,
        action_embedding_dim: int = 32,
        hidden_dim: int = 256,
    ) -> None:
        super().__init__()
        self.scalar_encoder = nn.Sequential(
            nn.Linear(int(scalar_features), scalar_hidden_dim),
            nn.GELU(),
            nn.Linear(scalar_hidden_dim, scalar_hidden_dim),
            nn.GELU(),
        )
        self.action_embedding = nn.Embedding(int(action_space_size), int(action_embedding_dim))
        self.head = nn.Sequential(
            nn.Linear(scalar_hidden_dim + action_embedding_dim * 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(self, scalars: Tensor, left_action_ids: Tensor, right_action_ids: Tensor) -> Tensor:
        scalar_features = self.scalar_encoder(scalars)
        left_action = self.action_embedding(left_action_ids.to(dtype=torch.long))
        right_action = self.action_embedding(right_action_ids.to(dtype=torch.long))
        action_delta = right_action - left_action
        features = torch.cat([scalar_features, left_action, right_action, action_delta], dim=1)
        return self.head(features).squeeze(-1)


class PairwiseSequenceDeltaNet(nn.Module):
    """Predict candidate-anchor reward delta from current state plus visible history."""

    uses_sequence_features = True

    def __init__(
        self,
        scalar_features: int,
        sequence_features: int = len(TRACE_SEQUENCE_FEATURE_NAMES),
        action_space_size: int = EnvConfig().action_space_size,
        scalar_hidden_dim: int = 128,
        sequence_hidden_dim: int = 64,
        action_embedding_dim: int = 32,
        hidden_dim: int = 256,
    ) -> None:
        super().__init__()
        self.scalar_encoder = nn.Sequential(
            nn.Linear(int(scalar_features), scalar_hidden_dim),
            nn.GELU(),
            nn.Linear(scalar_hidden_dim, scalar_hidden_dim),
            nn.GELU(),
        )
        self.sequence_encoder = nn.GRU(
            input_size=int(sequence_features),
            hidden_size=int(sequence_hidden_dim),
            batch_first=True,
        )
        self.action_embedding = nn.Embedding(int(action_space_size), int(action_embedding_dim))
        self.head = nn.Sequential(
            nn.Linear(scalar_hidden_dim + sequence_hidden_dim + action_embedding_dim * 3, hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, 1),
        )

    def forward(
        self,
        scalars: Tensor,
        left_action_ids: Tensor,
        right_action_ids: Tensor,
        sequence_features: Tensor,
    ) -> Tensor:
        scalar_features = self.scalar_encoder(scalars)
        _, hidden = self.sequence_encoder(sequence_features)
        sequence_features_encoded = hidden[-1]
        left_action = self.action_embedding(left_action_ids.to(dtype=torch.long))
        right_action = self.action_embedding(right_action_ids.to(dtype=torch.long))
        action_delta = right_action - left_action
        features = torch.cat(
            [scalar_features, sequence_features_encoded, left_action, right_action, action_delta],
            dim=1,
        )
        return self.head(features).squeeze(-1)


def build_pairwise_delta_arrays(
    report_paths: Sequence[Path],
    left_label: str = "anchor",
    right_label: str = "candidate",
    min_abs_delta: float = 0.0,
    include_trajectory_context: bool = True,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped_missing_divergence = 0
    skipped_missing_arrays = 0
    skipped_small_delta = 0
    report_summaries: list[dict[str, Any]] = []

    for source_id, report_path in enumerate(report_paths):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_left_label = str(report.get("left_label") or left_label)
        report_right_label = str(report.get("right_label") or right_label)
        before = len(rows)
        for pair in report.get("pairs", []):
            divergence = pair.get("first_divergence") or {}
            left_step = divergence.get("left") or divergence.get(report_left_label)
            right_step = divergence.get("right") or divergence.get(report_right_label)
            if not isinstance(left_step, dict) or not isinstance(right_step, dict):
                skipped_missing_divergence += 1
                continue
            arrays = (left_step.get("observation") or {}).get("arrays")
            if not isinstance(arrays, dict) or "scalars" not in arrays:
                skipped_missing_arrays += 1
                continue
            target = float(pair[f"{report_right_label}_reward"]) - float(pair[f"{report_left_label}_reward"])
            if abs(target) < float(min_abs_delta):
                skipped_small_delta += 1
                continue
            scalars = np.asarray(arrays["scalars"], dtype=np.float32).reshape(-1)
            if include_trajectory_context:
                scalars = np.concatenate([scalars, trace_context_vector(pair)], axis=0)
            rows.append(
                {
                    "scalars": scalars.astype(np.float32),
                    "sequence_features": trace_sequence_matrix(pair),
                    "left_action_id": int(left_step["action_id"]),
                    "right_action_id": int(right_step["action_id"]),
                    "target": float(target),
                    "episode_index": int(pair["seed"]),
                    "seat": int(pair["seat"]),
                    "source_id": int(source_id),
                    "source_report": str(report_path),
                }
            )
        report_summaries.append({"path": str(report_path), "rows": len(rows) - before})

    if not rows:
        raise ValueError("no paired-trace delta rows with observation arrays were found")

    targets = np.asarray([row["target"] for row in rows], dtype=np.float32)
    arrays = {
        "scalars": np.stack([row["scalars"] for row in rows]).astype(np.float32),
        "sequence_features": np.stack([row["sequence_features"] for row in rows]).astype(np.float32),
        "left_action_ids": np.asarray([row["left_action_id"] for row in rows], dtype=np.int64),
        "right_action_ids": np.asarray([row["right_action_id"] for row in rows], dtype=np.int64),
        "targets": targets,
        "episode_index": np.asarray([row["episode_index"] for row in rows], dtype=np.int64),
        "seats": np.asarray([row["seat"] for row in rows], dtype=np.int16),
        "source_ids": np.asarray([row["source_id"] for row in rows], dtype=np.int16),
    }
    stats = PairwiseDeltaBuildStats(
        rows=len(rows),
        skipped_missing_divergence=skipped_missing_divergence,
        skipped_missing_arrays=skipped_missing_arrays,
        skipped_small_delta=skipped_small_delta,
        target_mean=float(np.mean(targets)),
        target_min=float(np.min(targets)),
        target_max=float(np.max(targets)),
    )
    metadata = {
        "source": "paired_trace_pairwise_delta",
        "reports": report_summaries,
        "source_reports": [str(path) for path in report_paths],
        "left_label": left_label,
        "right_label": right_label,
        "min_abs_delta": float(min_abs_delta),
        "include_trajectory_context": bool(include_trajectory_context),
        "trajectory_context_scalar_names": list(TRACE_CONTEXT_SCALAR_NAMES) if include_trajectory_context else [],
        "trace_sequence_length": TRACE_SEQUENCE_LENGTH,
        "trace_sequence_feature_names": list(TRACE_SEQUENCE_FEATURE_NAMES),
        "stats": asdict(stats),
    }
    return arrays, metadata


def score_paired_trace_delta(
    report_path: Path,
    model: PairwiseDeltaNet,
    device: str = "cpu",
    left_label: str = "anchor",
    right_label: str = "candidate",
    guard_margins: Sequence[float] = (0.0,),
) -> dict[str, Any]:
    arrays, metadata = build_pairwise_delta_arrays(
        [report_path],
        left_label=left_label,
        right_label=right_label,
        min_abs_delta=0.0,
        include_trajectory_context=True,
    )
    predictions = predict_pairwise_delta(model, arrays, device=device)
    targets = arrays["targets"].astype(np.float32)
    metrics = regression_metrics(predictions, targets)
    actual_sign = np.sign(targets)
    predicted_sign = np.sign(predictions)
    nonzero = actual_sign != 0
    sign_accuracy = float(np.mean(predicted_sign[nonzero] == actual_sign[nonzero])) if np.any(nonzero) else 0.0
    harmful = targets < 0.0
    harmful_predicted_harmful = np.logical_and(harmful, predictions < 0.0)
    return {
        "schema_version": 1,
        "method": "paired_trace_pairwise_delta_diagnostics",
        "paired_trace_report": str(report_path),
        "metadata": metadata,
        "scoreable_divergences": int(targets.shape[0]),
        "metrics": asdict(metrics),
        "sign_accuracy": sign_accuracy,
        "harmful_count": int(np.count_nonzero(harmful)),
        "harmful_predicted_harmful_rate": (
            float(np.count_nonzero(harmful_predicted_harmful) / np.count_nonzero(harmful))
            if np.any(harmful)
            else 0.0
        ),
        "guard_preflight": guard_preflight(predictions, targets, guard_margins),
    }


@torch.inference_mode()
def predict_pairwise_delta(model: PairwiseDeltaNet, arrays: dict[str, np.ndarray], device: str = "cpu") -> np.ndarray:
    model.eval()
    scalars = torch.from_numpy(arrays["scalars"].astype(np.float32)).to(device)
    left_actions = torch.from_numpy(arrays["left_action_ids"].astype(np.int64)).to(device)
    right_actions = torch.from_numpy(arrays["right_action_ids"].astype(np.int64)).to(device)
    if getattr(model, "uses_sequence_features", False):
        sequences = torch.from_numpy(arrays["sequence_features"].astype(np.float32)).to(device)
        prediction = model(scalars, left_actions, right_actions, sequences)
    else:
        prediction = model(scalars, left_actions, right_actions)
    return prediction.detach().cpu().numpy().astype(np.float32)


def evaluate_pairwise_delta(
    model: PairwiseDeltaNet,
    arrays: dict[str, np.ndarray],
    indices: np.ndarray,
    device: str = "cpu",
) -> GlobalEVMetrics:
    subset = {
        "scalars": arrays["scalars"][indices],
        "sequence_features": arrays["sequence_features"][indices],
        "left_action_ids": arrays["left_action_ids"][indices],
        "right_action_ids": arrays["right_action_ids"][indices],
    }
    predictions = predict_pairwise_delta(model, subset, device=device)
    targets = arrays["targets"][indices].astype(np.float32)
    return regression_metrics(predictions, targets)


def guard_preflight(
    predictions: np.ndarray,
    targets: np.ndarray,
    margins: Sequence[float],
) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    harmful = targets < 0.0
    for margin in margins:
        threshold = float(margin)
        allowed = predictions >= threshold
        blocked = ~allowed
        harmful_allowed = np.logical_and(harmful, allowed)
        harmful_blocked = np.logical_and(harmful, blocked)
        result[f"{threshold:.4f}"] = {
            "margin": threshold,
            "allowed_count": int(np.count_nonzero(allowed)),
            "blocked_count": int(np.count_nonzero(blocked)),
            "allowed_rate": float(np.mean(allowed)) if targets.size else 0.0,
            "actual_allowed_delta_sum": float(np.sum(targets[allowed], dtype=np.float64)) if np.any(allowed) else 0.0,
            "harmful_allowed_count": int(np.count_nonzero(harmful_allowed)),
            "harmful_blocked_count": int(np.count_nonzero(harmful_blocked)),
            "harmful_block_rate": (
                float(np.count_nonzero(harmful_blocked) / np.count_nonzero(harmful))
                if np.any(harmful)
                else 0.0
            ),
        }
    return result


def trace_context_vector(pair: dict[str, Any]) -> np.ndarray:
    raw = pair.get("pre_divergence_context")
    if not isinstance(raw, dict):
        raw = {}
    return np.asarray([float(raw.get(name, 0.0)) for name in TRACE_CONTEXT_SCALAR_NAMES], dtype=np.float32)


def trace_sequence_matrix(pair: dict[str, Any]) -> np.ndarray:
    sequence = pair.get("pre_divergence_sequence")
    matrix = np.zeros((TRACE_SEQUENCE_LENGTH, len(TRACE_SEQUENCE_FEATURE_NAMES)), dtype=np.float32)
    if not isinstance(sequence, list):
        return matrix
    tail = sequence[-TRACE_SEQUENCE_LENGTH:]
    start = TRACE_SEQUENCE_LENGTH - len(tail)
    for offset, step in enumerate(tail):
        if not isinstance(step, dict):
            continue
        features = step.get("features")
        if not isinstance(features, dict):
            continue
        matrix[start + offset] = np.asarray(
            [float(features.get(name, 0.0)) for name in TRACE_SEQUENCE_FEATURE_NAMES],
            dtype=np.float32,
        )
    return matrix
