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
) -> dict[str, Any]:
    """Compare critic/value predictions against discounted terminal round payout."""
    arrays = add_steps_to_done_if_missing(arrays)
    total = int(arrays["action_ids"].shape[0])
    effective_batch_size = max(1, int(batch_size))
    model.eval()

    targets: list[np.ndarray] = []
    q_predictions: list[np.ndarray] = []
    value_predictions: list[np.ndarray] = []
    policy_predictions: list[np.ndarray] = []
    q_predictions_argmax: list[np.ndarray] = []
    action_ids_all: list[np.ndarray] = []

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

            targets.append(target.cpu().numpy())
            q_predictions.append(dataset_q.cpu().numpy())
            value_predictions.append(values.cpu().numpy())
            policy_predictions.append(torch.argmax(logits, dim=1).cpu().numpy())
            q_predictions_argmax.append(torch.argmax(q_values, dim=1).cpu().numpy())
            action_ids_all.append(action_ids.copy())

    target_array = np.concatenate(targets).astype(np.float32)
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
