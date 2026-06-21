from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import torch

from .global_ev import ActionGlobalEVNet, GlobalEVNet, regression_metrics
from .paired_trace import SCALAR_NAMES, TRACE_CONTEXT_SCALAR_NAMES


def score_paired_trace_global_ev(
    report: dict[str, Any],
    model: GlobalEVNet | ActionGlobalEVNet,
    device: str = "cpu",
    left_label: Optional[str] = None,
    right_label: Optional[str] = None,
    max_cases: int = 12,
    action_conditioned: bool = False,
    guard_margins: Sequence[float] = (),
) -> dict[str, Any]:
    left_label = left_label or str(report.get("left_label", "left"))
    right_label = right_label or str(report.get("right_label", "right"))
    pairs = report.get("pairs", [])
    if not isinstance(pairs, list):
        raise ValueError("paired trace report must contain a list field named 'pairs'")

    rows: list[dict[str, Any]] = []
    for pair in pairs:
        row = score_pair_global_ev(
            pair,
            model,
            device=device,
            left_label=left_label,
            right_label=right_label,
            action_conditioned=action_conditioned,
        )
        if row is not None:
            rows.append(row)

    if not rows:
        raise ValueError(
            "no scoreable divergences found; rerun paired_trace with --include-observation-arrays"
        )

    predicted = np.asarray([row["predicted_delta"] for row in rows], dtype=np.float32)
    actual = np.asarray([row["actual_delta"] for row in rows], dtype=np.float32)
    metrics = regression_metrics(predicted, actual)
    actual_sign = np.sign(actual)
    predicted_sign = np.sign(predicted)
    nonzero = actual_sign != 0
    sign_accuracy = float(np.mean(predicted_sign[nonzero] == actual_sign[nonzero])) if np.any(nonzero) else 0.0
    harmful = [row for row in rows if row["actual_delta"] < 0.0]
    helpful = [row for row in rows if row["actual_delta"] > 0.0]
    predicted_harmful = [row for row in harmful if row["predicted_delta"] < 0.0]
    predicted_helpful = [row for row in helpful if row["predicted_delta"] > 0.0]

    by_family_pair = summarize_by_family_pair(rows)
    worst_mismatches = sorted(rows, key=lambda row: abs(row["prediction_error"]), reverse=True)[:max_cases]
    worst_false_positive = sorted(
        [row for row in rows if row["predicted_delta"] > 0.0 and row["actual_delta"] < 0.0],
        key=lambda row: row["predicted_delta"] - row["actual_delta"],
        reverse=True,
    )[:max_cases]

    return {
        "schema_version": 1,
        "method": "global_ev_first_divergence_diagnostics",
        "left_label": left_label,
        "right_label": right_label,
        "pairs": len(pairs),
        "scoreable_divergences": len(rows),
        "metrics": asdict(metrics),
        "sign_accuracy": sign_accuracy,
        "harmful_count": len(harmful),
        "harmful_predicted_harmful_rate": len(predicted_harmful) / len(harmful) if harmful else 0.0,
        "helpful_count": len(helpful),
        "helpful_predicted_helpful_rate": len(predicted_helpful) / len(helpful) if helpful else 0.0,
        "by_family_pair": by_family_pair,
        "guard_preflight": guard_preflight(rows, guard_margins),
        "worst_mismatches": [compact_row(row) for row in worst_mismatches],
        "worst_false_positive_cases": [compact_row(row) for row in worst_false_positive],
    }


def score_pair_global_ev(
    pair: dict[str, Any],
    model: GlobalEVNet | ActionGlobalEVNet,
    device: str,
    left_label: str,
    right_label: str,
    action_conditioned: bool = False,
) -> Optional[dict[str, Any]]:
    divergence = pair.get("first_divergence") or {}
    left_step = divergence.get("left") or divergence.get(left_label)
    right_step = divergence.get("right") or divergence.get(right_label)
    if not isinstance(left_step, dict) or not isinstance(right_step, dict):
        return None
    extra_scalars = trace_context_vector(pair)
    expected_scalars = expected_scalar_features(model)
    left_observation = observation_arrays(left_step, extra_scalars=extra_scalars, expected_scalars=expected_scalars)
    right_observation = observation_arrays(right_step, extra_scalars=extra_scalars, expected_scalars=expected_scalars)
    if left_observation is None or right_observation is None:
        return None

    if action_conditioned:
        left_ev, right_ev = predict_action_global_ev(
            model,
            [left_observation, right_observation],
            [int(left_step["action_id"]), int(right_step["action_id"])],
            device=device,
        )
    else:
        left_ev, right_ev = predict_global_ev(model, [left_observation, right_observation], device=device)
    actual_delta = float(pair[f"{right_label}_reward"]) - float(pair[f"{left_label}_reward"])
    predicted_delta = float(right_ev - left_ev)
    return {
        "seed": int(pair["seed"]),
        "seat": int(pair["seat"]),
        "first_divergence_index": pair.get("first_divergence_index"),
        "decision_index": right_step.get("decision_index", left_step.get("decision_index")),
        f"{left_label}_reward": float(pair[f"{left_label}_reward"]),
        f"{right_label}_reward": float(pair[f"{right_label}_reward"]),
        "actual_delta": actual_delta,
        f"{left_label}_global_ev": float(left_ev),
        f"{right_label}_global_ev": float(right_ev),
        "predicted_delta": predicted_delta,
        "prediction_error": predicted_delta - actual_delta,
        f"{left_label}_action_id": int(left_step["action_id"]),
        f"{left_label}_action_label": left_step.get("action_label"),
        f"{left_label}_action_family": left_step.get("action_family"),
        f"{right_label}_action_id": int(right_step["action_id"]),
        f"{right_label}_action_label": right_step.get("action_label"),
        f"{right_label}_action_family": right_step.get("action_family"),
        "family_pair": f"{left_step.get('action_family')}->{right_step.get('action_family')}",
        "scalars": scalar_context(right_step.get("observation") or left_step.get("observation") or {}),
    }


def observation_arrays(
    step: dict[str, Any],
    extra_scalars: Optional[np.ndarray] = None,
    expected_scalars: Optional[int] = None,
) -> Optional[tuple[np.ndarray, np.ndarray]]:
    observation = step.get("observation")
    if not isinstance(observation, dict):
        return None
    arrays = observation.get("arrays", observation)
    if not isinstance(arrays, dict):
        return None
    if "planes" not in arrays or "scalars" not in arrays:
        return None
    planes = np.asarray(arrays["planes"], dtype=np.float32)
    scalars = np.asarray(arrays["scalars"], dtype=np.float32).reshape(-1)
    if extra_scalars is not None and expected_scalars is not None and int(expected_scalars) > int(scalars.size):
        scalars = np.concatenate([scalars, extra_scalars.astype(np.float32, copy=False).reshape(-1)], axis=0)
        scalars = scalars[: int(expected_scalars)]
    return planes, scalars


def expected_scalar_features(model: GlobalEVNet | ActionGlobalEVNet) -> int:
    encoder = getattr(model, "scalar_encoder", None)
    if encoder is None:
        return 0
    return int(encoder[0].in_features)


def trace_context_vector(pair: dict[str, Any]) -> np.ndarray:
    raw = pair.get("pre_divergence_context")
    if not isinstance(raw, dict):
        raw = {}
    return np.asarray([float(raw.get(name, 0.0)) for name in TRACE_CONTEXT_SCALAR_NAMES], dtype=np.float32)


@torch.inference_mode()
def predict_global_ev(
    model: GlobalEVNet,
    observations: Sequence[tuple[np.ndarray, np.ndarray]],
    device: str,
) -> np.ndarray:
    planes = torch.from_numpy(np.stack([obs[0] for obs in observations]).astype(np.float32)).to(device)
    scalars = torch.from_numpy(np.stack([obs[1] for obs in observations]).astype(np.float32)).to(device)
    model.eval()
    return model(planes, scalars).detach().cpu().numpy().astype(np.float32)


@torch.inference_mode()
def predict_action_global_ev(
    model: ActionGlobalEVNet,
    observations: Sequence[tuple[np.ndarray, np.ndarray]],
    action_ids: Sequence[int],
    device: str,
) -> np.ndarray:
    planes = torch.from_numpy(np.stack([obs[0] for obs in observations]).astype(np.float32)).to(device)
    scalars = torch.from_numpy(np.stack([obs[1] for obs in observations]).astype(np.float32)).to(device)
    actions = torch.as_tensor(action_ids, dtype=torch.long, device=device)
    model.eval()
    return model(planes, scalars, actions).detach().cpu().numpy().astype(np.float32)


def scalar_context(observation: dict[str, Any]) -> dict[str, float]:
    raw = observation.get("scalars", {})
    if isinstance(observation.get("arrays"), dict):
        raw = observation["arrays"].get("scalars", raw)
    if isinstance(raw, dict):
        return {str(key): float(value) for key, value in raw.items() if isinstance(value, (int, float))}
    values = np.asarray(raw, dtype=np.float32).reshape(-1)
    return {
        name: float(values[index])
        for index, name in SCALAR_NAMES.items()
        if index < values.shape[0]
    }


def summarize_by_family_pair(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    counts = Counter(str(row["family_pair"]) for row in rows)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row["family_pair"])].append(row)
    result: dict[str, dict[str, float | int]] = {}
    for family_pair, items in buckets.items():
        actual = np.asarray([row["actual_delta"] for row in items], dtype=np.float32)
        predicted = np.asarray([row["predicted_delta"] for row in items], dtype=np.float32)
        result[family_pair] = {
            "count": counts[family_pair],
            "actual_delta_mean": float(np.mean(actual)),
            "predicted_delta_mean": float(np.mean(predicted)),
            "mae": float(np.mean(np.abs(predicted - actual))),
            "predicted_harmful_rate": float(np.mean(predicted < 0.0)),
            "actual_harmful_rate": float(np.mean(actual < 0.0)),
        }
    return dict(sorted(result.items(), key=lambda item: (-item[1]["count"], item[0])))


def guard_preflight(rows: Sequence[dict[str, Any]], margins: Sequence[float]) -> dict[str, dict[str, float | int]]:
    result: dict[str, dict[str, float | int]] = {}
    for margin in margins:
        threshold = float(margin)
        allowed = [row for row in rows if float(row["predicted_delta"]) >= threshold]
        blocked = [row for row in rows if float(row["predicted_delta"]) < threshold]
        harmful = [row for row in rows if float(row["actual_delta"]) < 0.0]
        harmful_allowed = [row for row in allowed if float(row["actual_delta"]) < 0.0]
        harmful_blocked = [row for row in blocked if float(row["actual_delta"]) < 0.0]
        actual_allowed_delta = float(np.sum([row["actual_delta"] for row in allowed], dtype=np.float64)) if allowed else 0.0
        result[f"{threshold:.4f}"] = {
            "margin": threshold,
            "allowed_count": len(allowed),
            "blocked_count": len(blocked),
            "allowed_rate": len(allowed) / len(rows) if rows else 0.0,
            "actual_allowed_delta_sum": actual_allowed_delta,
            "harmful_allowed_count": len(harmful_allowed),
            "harmful_blocked_count": len(harmful_blocked),
            "harmful_block_rate": len(harmful_blocked) / len(harmful) if harmful else 0.0,
        }
    return result


def action_ev_branch_cf_calibration(
    arrays: dict[str, np.ndarray],
    model: ActionGlobalEVNet,
    device: str = "cpu",
    batch_size: int = 4096,
    guard_margins: Sequence[float] = (0.0, -0.02, -0.05),
) -> dict[str, Any]:
    preferred = np.asarray(arrays["pairwise_preferred_action_ids"], dtype=np.int64)
    avoided = np.asarray(arrays["pairwise_avoided_action_ids"], dtype=np.int64)
    preferred_rewards = np.asarray(arrays["branch_preferred_rewards"], dtype=np.float32)
    avoided_rewards = np.asarray(arrays["branch_avoided_rewards"], dtype=np.float32)
    reward_gaps = preferred_rewards - avoided_rewards
    preferred_scores, avoided_scores = predict_branch_action_scores(
        arrays,
        model,
        preferred,
        avoided,
        device=device,
        batch_size=batch_size,
    )
    margins = preferred_scores - avoided_scores
    rows = [
        {
            "predicted_delta": float(margins[index]),
            "actual_delta": float(reward_gaps[index]),
            "family_pair": "preferred->avoided",
        }
        for index in range(int(preferred.shape[0]))
    ]
    return {
        "schema_version": 1,
        "method": "action_ev_branch_cf_calibration",
        "rows": int(preferred.shape[0]),
        "preferred_rate": float(np.mean(margins > 0.0)) if margins.size else 0.0,
        "tie_rate": float(np.mean(margins == 0.0)) if margins.size else 0.0,
        "mean_margin": float(np.mean(margins)) if margins.size else 0.0,
        "reward_gap": {
            "mean": float(np.mean(reward_gaps)) if reward_gaps.size else 0.0,
            "median": float(np.median(reward_gaps)) if reward_gaps.size else 0.0,
            "max": float(np.max(reward_gaps)) if reward_gaps.size else 0.0,
        },
        "reward_gap_weighted_preferred_rate": weighted_rate(margins > 0.0, reward_gaps),
        "reward_gap_weighted_mean_margin": weighted_mean(margins, reward_gaps),
        "by_reward_gap": reward_gap_buckets(margins, reward_gaps),
        "guard_preflight": guard_preflight(rows, guard_margins),
    }


@torch.inference_mode()
def predict_branch_action_scores(
    arrays: dict[str, np.ndarray],
    model: ActionGlobalEVNet,
    preferred_actions: np.ndarray,
    avoided_actions: np.ndarray,
    device: str,
    batch_size: int = 4096,
) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    preferred_scores: list[np.ndarray] = []
    avoided_scores: list[np.ndarray] = []
    total = int(preferred_actions.shape[0])
    effective_batch = max(1, int(batch_size))
    for start in range(0, total, effective_batch):
        end = min(start + effective_batch, total)
        planes = torch.from_numpy(arrays["planes"][start:end].astype(np.float32, copy=False)).to(device)
        scalars = torch.from_numpy(arrays["scalars"][start:end].astype(np.float32, copy=False)).to(device)
        preferred = torch.from_numpy(preferred_actions[start:end]).to(device)
        avoided = torch.from_numpy(avoided_actions[start:end]).to(device)
        preferred_scores.append(model(planes, scalars, preferred).detach().cpu().numpy())
        avoided_scores.append(model(planes, scalars, avoided).detach().cpu().numpy())
    return (
        np.concatenate(preferred_scores).astype(np.float32),
        np.concatenate(avoided_scores).astype(np.float32),
    )


def reward_gap_buckets(margins: np.ndarray, reward_gaps: np.ndarray) -> dict[str, dict[str, float | int]]:
    bucket_defs = (
        ("0.00-0.05", 0.0, 0.05),
        ("0.05-0.20", 0.05, 0.20),
        ("0.20-0.50", 0.20, 0.50),
        ("0.50+", 0.50, float("inf")),
    )
    report: dict[str, dict[str, float | int]] = {}
    for name, lower, upper in bucket_defs:
        mask = (reward_gaps >= lower) & (reward_gaps < upper)
        selected = margins[mask]
        report[name] = {
            "count": int(selected.size),
            "preferred_rate": float(np.mean(selected > 0.0)) if selected.size else 0.0,
            "mean_margin": float(np.mean(selected)) if selected.size else 0.0,
        }
    return report


def weighted_rate(values: np.ndarray, weights: np.ndarray) -> float:
    numeric = np.asarray(values, dtype=np.float32)
    numeric_weights = np.asarray(weights, dtype=np.float32)
    total = float(np.sum(numeric_weights))
    if total <= 1e-8:
        return float(np.mean(numeric)) if numeric.size else 0.0
    return float(np.sum(numeric * numeric_weights) / total)


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    numeric = np.asarray(values, dtype=np.float32)
    numeric_weights = np.asarray(weights, dtype=np.float32)
    total = float(np.sum(numeric_weights))
    if total <= 1e-8:
        return float(np.mean(numeric)) if numeric.size else 0.0
    return float(np.sum(numeric * numeric_weights) / total)


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: row[key]
        for key in (
            "seed",
            "seat",
            "first_divergence_index",
            "decision_index",
            "actual_delta",
            "predicted_delta",
            "prediction_error",
            "family_pair",
        )
        if key in row
    } | {
        "left_action_label": row.get("left_action_label") or row.get("anchor_action_label"),
        "right_action_label": row.get("right_action_label") or row.get("candidate_action_label"),
        "left_action_id": row.get("left_action_id") or row.get("anchor_action_id"),
        "right_action_id": row.get("right_action_id") or row.get("candidate_action_id"),
        "left_action_family": row.get("left_action_family") or row.get("anchor_action_family"),
        "right_action_family": row.get("right_action_family") or row.get("candidate_action_family"),
        "scalars": row.get("scalars", {}),
    }
