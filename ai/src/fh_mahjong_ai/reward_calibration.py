"""Reward calibration diagnostics for offline Mahjong RL checkpoints."""
from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np
import torch
from torch import nn

from .data import compute_steps_to_done
from .evaluate import action_family, reward_summary
from .trainer import discounted_terminal_returns


CALIBRATION_ARRAY_KEYS = (
    "seats",
    "planes",
    "scalars",
    "action_mask",
    "action_ids",
    "terminal_rewards",
    "steps_to_done",
    "episode_index",
    "terminated",
    "truncated",
)

CALIBRATION_FALLBACK_KEYS = tuple(key for key in CALIBRATION_ARRAY_KEYS if key != "steps_to_done")


def add_steps_to_done_if_missing(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    if "steps_to_done" not in arrays:
        arrays["steps_to_done"] = compute_steps_to_done(
            arrays["episode_index"],
            np.logical_or(arrays["terminated"], arrays["truncated"]),
        )
    return arrays


def compute_reward_calibration(
    model: nn.Module,
    arrays: dict[str, np.ndarray],
    gamma: float = 0.99,
    batch_size: int = 4096,
    device: str = "cpu",
    large_loss_threshold: float | None = None,
    large_loss_risk_mode: str = "auto",
) -> dict[str, Any]:
    """Compare critic/value predictions against discounted terminal round payout."""
    arrays = add_steps_to_done_if_missing(arrays)
    total = int(arrays["action_ids"].shape[0])
    effective_batch_size = max(1, int(batch_size))
    model.eval()

    targets: list[np.ndarray] = []
    terminal_returns: list[np.ndarray] = []
    q_predictions: list[np.ndarray] = []
    value_predictions: list[np.ndarray] = []
    policy_predictions: list[np.ndarray] = []
    q_predictions_argmax: list[np.ndarray] = []
    action_ids_all: list[np.ndarray] = []
    risk_probabilities: list[np.ndarray] = []
    risk_severities: list[np.ndarray] = []

    with torch.inference_mode():
        for start in range(0, total, effective_batch_size):
            end = min(start + effective_batch_size, total)
            seats = arrays["seats"][start:end].astype(np.int64, copy=False)
            row_indices = np.arange(start, end)
            action_ids = arrays["action_ids"][start:end].astype(np.int64, copy=False)
            returns = arrays["terminal_rewards"][row_indices, seats].astype(np.float32, copy=False)
            steps_to_done = arrays["steps_to_done"][start:end].astype(np.int32, copy=False)

            planes = torch.from_numpy(arrays["planes"][start:end].astype(np.float32, copy=False)).to(device)
            scalars = torch.from_numpy(arrays["scalars"][start:end].astype(np.float32, copy=False)).to(device)
            mask = torch.from_numpy(arrays["action_mask"][start:end].astype(np.int8, copy=False)).to(device)
            action_tensor = torch.from_numpy(action_ids).to(device)
            return_tensor = torch.from_numpy(returns).to(device)
            steps_tensor = torch.from_numpy(steps_to_done).to(device)

            logits, values = model(planes, scalars, mask)
            q_values, _ = model.q_values(planes, scalars, mask)
            dataset_q = q_values.gather(1, action_tensor.unsqueeze(1)).squeeze(1)
            target = discounted_terminal_returns(return_tensor, steps_tensor, gamma)
            if large_loss_threshold is not None and _supports_risk_mode(model, large_loss_risk_mode):
                risk_logits, severity = _risk_predictions_for_mode(
                    model,
                    planes,
                    scalars,
                    mask,
                    action_tensor,
                    large_loss_risk_mode,
                )
                risk_probabilities.append(torch.sigmoid(risk_logits).cpu().numpy())
                risk_severities.append(severity.cpu().numpy())

            targets.append(target.cpu().numpy())
            terminal_returns.append(returns.copy())
            q_predictions.append(dataset_q.cpu().numpy())
            value_predictions.append(values.cpu().numpy())
            policy_predictions.append(torch.argmax(logits, dim=1).cpu().numpy())
            q_predictions_argmax.append(torch.argmax(q_values, dim=1).cpu().numpy())
            action_ids_all.append(action_ids.copy())

    target_array = np.concatenate(targets).astype(np.float32)
    terminal_return_array = np.concatenate(terminal_returns).astype(np.float32)
    q_array = np.concatenate(q_predictions).astype(np.float32)
    value_array = np.concatenate(value_predictions).astype(np.float32)
    policy_actions = np.concatenate(policy_predictions).astype(np.int64)
    q_actions = np.concatenate(q_predictions_argmax).astype(np.int64)
    action_ids = np.concatenate(action_ids_all).astype(np.int64)

    error = q_array - target_array
    value_error = value_array - target_array
    report = {
        "total_transitions": total,
        "gamma": gamma,
        "target": reward_summary(target_array.tolist()),
        "q_prediction": reward_summary(q_array.tolist()),
        "value_prediction": reward_summary(value_array.tolist()),
        "q_error": _error_summary(error, target_array, q_array),
        "value_error": _error_summary(value_error, target_array, value_array),
        "policy_agreement_rate": float(np.mean(policy_actions == action_ids)) if total else 0.0,
        "q_argmax_agreement_rate": float(np.mean(q_actions == action_ids)) if total else 0.0,
        "by_action_family": _family_report(action_ids, target_array, q_array, value_array, policy_actions, q_actions),
        "by_target_sign": _target_sign_report(target_array, q_array, value_array),
    }
    if large_loss_threshold is not None and risk_probabilities:
        probability_array = np.concatenate(risk_probabilities).astype(np.float32)
        severity_array = np.concatenate(risk_severities).astype(np.float32)
        report["large_loss_calibration"] = _large_loss_report(
            terminal_return_array,
            probability_array,
            severity_array,
            threshold=float(large_loss_threshold),
            action_ids=action_ids,
        )
        report["large_loss_calibration"]["risk_mode"] = _resolved_risk_mode(model, large_loss_risk_mode)
    return report


def _supports_risk_mode(model: nn.Module, mode: str) -> bool:
    resolved = _resolved_risk_mode(model, mode)
    if resolved == "action":
        return hasattr(model, "action_risk_predictions")
    if resolved == "state":
        return hasattr(model, "large_loss_predictions")
    return False


def _resolved_risk_mode(model: nn.Module, mode: str) -> str:
    normalized = mode.lower()
    if normalized not in {"auto", "action", "state"}:
        raise ValueError(f"unsupported large loss risk mode: {mode!r}")
    if normalized == "auto":
        return "action" if hasattr(model, "action_risk_predictions") else "state"
    return normalized


def _risk_predictions_for_mode(
    model: nn.Module,
    planes: torch.Tensor,
    scalars: torch.Tensor,
    action_mask: torch.Tensor,
    action_ids: torch.Tensor,
    mode: str,
) -> tuple[torch.Tensor, torch.Tensor]:
    resolved = _resolved_risk_mode(model, mode)
    if resolved == "action":
        risk_logits, severity = model.action_risk_predictions(planes, scalars, action_mask)
        return (
            risk_logits.gather(1, action_ids.unsqueeze(1)).squeeze(1),
            severity.gather(1, action_ids.unsqueeze(1)).squeeze(1),
        )
    if resolved == "state":
        return model.large_loss_predictions(planes, scalars)
    raise ValueError(f"unsupported large loss risk mode: {mode!r}")


def _large_loss_report(
    target: np.ndarray,
    probability: np.ndarray,
    severity_prediction: np.ndarray,
    threshold: float,
    action_ids: np.ndarray | None = None,
) -> dict[str, Any]:
    labels = target <= float(threshold)
    label_float = labels.astype(np.float32)
    severity_target = np.maximum(float(threshold) - target, 0.0).astype(np.float32)
    probability = np.clip(probability.astype(np.float32), 1e-6, 1.0 - 1e-6)
    severity_prediction = severity_prediction.astype(np.float32)
    severity_error = severity_prediction - severity_target
    report = {
        "threshold": float(threshold),
        "count": int(target.size),
        "positive_count": int(np.count_nonzero(labels)),
        "positive_rate": float(np.mean(label_float)) if target.size else 0.0,
        "probability": {
            "mean": float(np.mean(probability)) if probability.size else 0.0,
            "positive_mean": _masked_mean(probability, labels),
            "negative_mean": _masked_mean(probability, ~labels),
            "brier": float(np.mean(np.square(probability - label_float))) if probability.size else 0.0,
            "binary_cross_entropy": float(
                -np.mean(label_float * np.log(probability) + (1.0 - label_float) * np.log(1.0 - probability))
            )
            if probability.size
            else 0.0,
            "auc": _binary_auc(label_float, probability),
        },
        "severity": {
            "target_mean": float(np.mean(severity_target)) if severity_target.size else 0.0,
            "prediction_mean": float(np.mean(severity_prediction)) if severity_prediction.size else 0.0,
            "mae": float(np.mean(np.abs(severity_error))) if severity_error.size else 0.0,
            "rmse": float(np.sqrt(np.mean(np.square(severity_error)))) if severity_error.size else 0.0,
            "bias": float(np.mean(severity_error)) if severity_error.size else 0.0,
        },
        "risk_bands": _risk_band_report(label_float, probability, severity_target),
    }
    if action_ids is not None:
        report["by_action_family"] = _large_loss_family_report(
            action_ids,
            labels,
            label_float,
            probability,
            severity_target,
            severity_prediction,
        )
    return report


def _masked_mean(values: np.ndarray, mask: np.ndarray) -> float:
    if int(np.count_nonzero(mask)) == 0:
        return 0.0
    return float(np.mean(values[mask]))


def _binary_auc(labels: np.ndarray, scores: np.ndarray) -> float:
    positive_count = int(np.count_nonzero(labels > 0.5))
    negative_count = int(labels.size - positive_count)
    if positive_count == 0 or negative_count == 0:
        return 0.0
    order = np.argsort(scores, kind="mergesort")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, scores.size + 1, dtype=np.float64)

    sorted_scores = scores[order]
    start = 0
    while start < scores.size:
        end = start + 1
        while end < scores.size and sorted_scores[end] == sorted_scores[start]:
            end += 1
        if end - start > 1:
            average_rank = float(np.mean(ranks[order[start:end]]))
            ranks[order[start:end]] = average_rank
        start = end

    positive_rank_sum = float(np.sum(ranks[labels > 0.5]))
    return float((positive_rank_sum - positive_count * (positive_count + 1) / 2.0) / (positive_count * negative_count))


def _risk_band_report(labels: np.ndarray, probability: np.ndarray, severity_target: np.ndarray) -> dict[str, dict[str, float]]:
    bands = {
        "0.00-0.25": (0.0, 0.25),
        "0.25-0.50": (0.25, 0.50),
        "0.50-0.75": (0.50, 0.75),
        "0.75-1.00": (0.75, 1.000001),
    }
    report: dict[str, dict[str, float]] = {}
    for name, (low, high) in bands.items():
        mask = (probability >= low) & (probability < high)
        count = int(np.count_nonzero(mask))
        if count == 0:
            report[name] = {"count": 0, "large_loss_rate": 0.0, "avg_probability": 0.0, "avg_severity": 0.0}
            continue
        report[name] = {
            "count": count,
            "large_loss_rate": float(np.mean(labels[mask])),
            "avg_probability": float(np.mean(probability[mask])),
            "avg_severity": float(np.mean(severity_target[mask])),
        }
    return report


def _large_loss_family_report(
    action_ids: np.ndarray,
    labels: np.ndarray,
    label_float: np.ndarray,
    probability: np.ndarray,
    severity_target: np.ndarray,
    severity_prediction: np.ndarray,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, action_id in enumerate(action_ids.tolist()):
        buckets[action_family(int(action_id))].append(index)

    report: dict[str, dict[str, Any]] = {}
    for family, indices in sorted(buckets.items()):
        idx = np.asarray(indices, dtype=np.int64)
        family_labels = labels[idx]
        family_label_float = label_float[idx]
        family_probability = probability[idx]
        family_severity_target = severity_target[idx]
        family_severity_prediction = severity_prediction[idx]
        severity_error = family_severity_prediction - family_severity_target
        report[family] = {
            "count": int(idx.size),
            "positive_count": int(np.count_nonzero(family_labels)),
            "positive_rate": float(np.mean(family_label_float)) if idx.size else 0.0,
            "probability": {
                "mean": float(np.mean(family_probability)) if idx.size else 0.0,
                "positive_mean": _masked_mean(family_probability, family_labels),
                "negative_mean": _masked_mean(family_probability, ~family_labels),
                "brier": float(np.mean(np.square(family_probability - family_label_float))) if idx.size else 0.0,
                "auc": _binary_auc(family_label_float, family_probability),
            },
            "severity": {
                "target_mean": float(np.mean(family_severity_target)) if idx.size else 0.0,
                "prediction_mean": float(np.mean(family_severity_prediction)) if idx.size else 0.0,
                "mae": float(np.mean(np.abs(severity_error))) if idx.size else 0.0,
                "bias": float(np.mean(severity_error)) if idx.size else 0.0,
            },
        }
    return report


def _error_summary(error: np.ndarray, target: np.ndarray, prediction: np.ndarray) -> dict[str, float]:
    if error.size == 0:
        return {"mae": 0.0, "rmse": 0.0, "bias": 0.0, "correlation": 0.0}
    correlation = 0.0
    if float(np.std(target)) > 0.0 and float(np.std(prediction)) > 0.0:
        correlation = float(np.corrcoef(target, prediction)[0, 1])
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(np.square(error)))),
        "bias": float(np.mean(error)),
        "correlation": correlation,
    }


def _family_report(
    action_ids: np.ndarray,
    target: np.ndarray,
    q_prediction: np.ndarray,
    value_prediction: np.ndarray,
    policy_actions: np.ndarray,
    q_actions: np.ndarray,
) -> dict[str, dict[str, float]]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, action_id in enumerate(action_ids.tolist()):
        buckets[action_family(int(action_id))].append(index)

    report: dict[str, dict[str, float]] = {}
    for family, indices in sorted(buckets.items()):
        idx = np.asarray(indices, dtype=np.int64)
        q_error = q_prediction[idx] - target[idx]
        value_error = value_prediction[idx] - target[idx]
        report[family] = {
            "count": int(idx.size),
            "target_mean": float(np.mean(target[idx])),
            "q_mean": float(np.mean(q_prediction[idx])),
            "q_mae": float(np.mean(np.abs(q_error))),
            "q_bias": float(np.mean(q_error)),
            "value_mean": float(np.mean(value_prediction[idx])),
            "value_mae": float(np.mean(np.abs(value_error))),
            "policy_agreement_rate": float(np.mean(policy_actions[idx] == action_ids[idx])),
            "q_argmax_agreement_rate": float(np.mean(q_actions[idx] == action_ids[idx])),
        }
    return report


def _target_sign_report(target: np.ndarray, q_prediction: np.ndarray, value_prediction: np.ndarray) -> dict[str, dict[str, float]]:
    masks = {
        "negative": target < 0,
        "zero": target == 0,
        "positive": target > 0,
    }
    report: dict[str, dict[str, float]] = {}
    for name, mask in masks.items():
        count = int(np.count_nonzero(mask))
        if count == 0:
            report[name] = {"count": 0, "target_mean": 0.0, "q_mean": 0.0, "value_mean": 0.0}
            continue
        report[name] = {
            "count": count,
            "target_mean": float(np.mean(target[mask])),
            "q_mean": float(np.mean(q_prediction[mask])),
            "value_mean": float(np.mean(value_prediction[mask])),
        }
    return report
