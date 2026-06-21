"""Q/policy ranking diagnostics for tensor-bearing paired traces."""
from __future__ import annotations

from collections import Counter
from typing import Any, Sequence

import numpy as np
import torch

from .action_catalog import action_family, action_label
from .paired_trace import counterfactual_label_from_pair


def score_paired_trace_q_rank(
    report: dict[str, Any],
    model: torch.nn.Module,
    device: str = "cpu",
    batch_size: int = 512,
    left_label: str | None = None,
    right_label: str | None = None,
    large_loss_threshold: float | None = None,
    min_reward_gap: float = 0.0,
    divergence_source: str = "first",
) -> dict[str, Any]:
    """Score checkpoint Q/policy ranking on paired-trace divergence labels.

    The report must have been generated with ``--include-observation-arrays`` so
    every scored divergence carries visible planes/scalars/action_mask arrays.
    """
    if divergence_source not in {"first", "all"}:
        raise ValueError("divergence_source must be 'first' or 'all'")
    left = left_label or str(report.get("left_label", "left"))
    right = right_label or str(report.get("right_label", "right"))
    rows = extract_paired_trace_rank_rows(
        report,
        left_label=left,
        right_label=right,
        large_loss_threshold=large_loss_threshold,
        min_reward_gap=min_reward_gap,
        divergence_source=divergence_source,
    )
    scores = evaluate_rank_rows(rows, model=model, device=device, batch_size=batch_size)
    return summarize_rank_rows(
        rows,
        scores,
        left_label=left,
        right_label=right,
        device=device,
        min_reward_gap=min_reward_gap,
        divergence_source=divergence_source,
    )


def extract_paired_trace_rank_rows(
    report: dict[str, Any],
    left_label: str = "left",
    right_label: str = "right",
    large_loss_threshold: float | None = None,
    min_reward_gap: float = 0.0,
    divergence_source: str = "first",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pair_index, pair in enumerate(report.get("pairs", [])):
        divergences = _divergences_for_pair(pair, divergence_source=divergence_source)
        for divergence in divergences:
            label = counterfactual_label_from_pair(
                pair,
                left_label=left_label,
                right_label=right_label,
                large_loss_threshold=large_loss_threshold,
                divergence=divergence,
            )
            if label is None:
                continue
            if float(label["reward_gap"]) < float(min_reward_gap):
                continue
            observation = _observation_arrays_for_label(divergence, label, left_label, right_label)
            if observation is None:
                continue
            rows.append(
                {
                    **label,
                    "pair_index": int(pair_index),
                    "planes": observation["planes"],
                    "scalars": observation["scalars"],
                    "action_mask": observation["action_mask"],
                }
            )
    return rows


def evaluate_rank_rows(
    rows: Sequence[dict[str, Any]],
    model: torch.nn.Module,
    device: str = "cpu",
    batch_size: int = 512,
) -> dict[str, np.ndarray]:
    if not rows:
        empty_float = np.asarray([], dtype=np.float32)
        empty_int = np.asarray([], dtype=np.int64)
        return {
            "policy_preferred": empty_float,
            "policy_avoided": empty_float,
            "q_preferred": empty_float,
            "q_avoided": empty_float,
            "policy_argmax": empty_int,
            "q_argmax": empty_int,
        }

    preferred = np.asarray([row["preferred_action_id"] for row in rows], dtype=np.int64)
    avoided = np.asarray([row["avoided_action_id"] for row in rows], dtype=np.int64)
    policy_preferred: list[np.ndarray] = []
    policy_avoided: list[np.ndarray] = []
    q_preferred: list[np.ndarray] = []
    q_avoided: list[np.ndarray] = []
    policy_argmax: list[np.ndarray] = []
    q_argmax: list[np.ndarray] = []
    effective_batch_size = max(1, int(batch_size))
    model.eval()
    with torch.inference_mode():
        for start in range(0, len(rows), effective_batch_size):
            end = min(start + effective_batch_size, len(rows))
            planes = torch.from_numpy(np.asarray([row["planes"] for row in rows[start:end]], dtype=np.float32)).to(device)
            scalars = torch.from_numpy(np.asarray([row["scalars"] for row in rows[start:end]], dtype=np.float32)).to(device)
            mask = torch.from_numpy(np.asarray([row["action_mask"] for row in rows[start:end]], dtype=np.int8)).to(device)
            preferred_actions = torch.from_numpy(preferred[start:end]).to(device)
            avoided_actions = torch.from_numpy(avoided[start:end]).to(device)
            logits, _ = model(planes, scalars, mask)
            q_values, _ = model.q_values(planes, scalars, mask)
            policy_preferred.append(logits.gather(1, preferred_actions.unsqueeze(1)).squeeze(1).cpu().numpy())
            policy_avoided.append(logits.gather(1, avoided_actions.unsqueeze(1)).squeeze(1).cpu().numpy())
            q_preferred.append(q_values.gather(1, preferred_actions.unsqueeze(1)).squeeze(1).cpu().numpy())
            q_avoided.append(q_values.gather(1, avoided_actions.unsqueeze(1)).squeeze(1).cpu().numpy())
            policy_argmax.append(torch.argmax(logits, dim=1).cpu().numpy())
            q_argmax.append(torch.argmax(q_values, dim=1).cpu().numpy())

    return {
        "policy_preferred": np.concatenate(policy_preferred).astype(np.float32),
        "policy_avoided": np.concatenate(policy_avoided).astype(np.float32),
        "q_preferred": np.concatenate(q_preferred).astype(np.float32),
        "q_avoided": np.concatenate(q_avoided).astype(np.float32),
        "policy_argmax": np.concatenate(policy_argmax).astype(np.int64),
        "q_argmax": np.concatenate(q_argmax).astype(np.int64),
    }


def summarize_rank_rows(
    rows: Sequence[dict[str, Any]],
    scores: dict[str, np.ndarray],
    left_label: str = "left",
    right_label: str = "right",
    device: str = "cpu",
    min_reward_gap: float = 0.0,
    divergence_source: str = "first",
) -> dict[str, Any]:
    preferred = np.asarray([row["preferred_action_id"] for row in rows], dtype=np.int64)
    avoided = np.asarray([row["avoided_action_id"] for row in rows], dtype=np.int64)
    reward_gaps = np.asarray([row["reward_gap"] for row in rows], dtype=np.float32)
    policy_margins = scores["policy_preferred"] - scores["policy_avoided"]
    q_margins = scores["q_preferred"] - scores["q_avoided"]
    return {
        "schema_version": 1,
        "left_label": left_label,
        "right_label": right_label,
        "device": device,
        "divergence_source": divergence_source,
        "min_reward_gap": float(min_reward_gap),
        "rows": len(rows),
        "reward_gap": _summary(reward_gaps),
        "preferred_policy_counts": dict(sorted(Counter(str(row["preferred_policy"]) for row in rows).items())),
        "avoided_policy_counts": dict(sorted(Counter(str(row["avoided_policy"]) for row in rows).items())),
        "family_pair_counts": _family_pair_counts(preferred, avoided),
        "policy_logits": _margin_summary(policy_margins, reward_gaps),
        "q_values": _margin_summary(q_margins, reward_gaps),
        "argmax": {
            "policy_preferred_action_rate": _rate(scores["policy_argmax"] == preferred),
            "policy_avoided_action_rate": _rate(scores["policy_argmax"] == avoided),
            "q_preferred_action_rate": _rate(scores["q_argmax"] == preferred),
            "q_avoided_action_rate": _rate(scores["q_argmax"] == avoided),
        },
        "examples": {
            "highest_gap_q_misrank": _examples(rows, q_margins, condition=q_margins < 0.0),
            "highest_gap_policy_misrank": _examples(rows, policy_margins, condition=policy_margins < 0.0),
        },
    }


def _divergences_for_pair(pair: dict[str, Any], divergence_source: str) -> list[dict[str, Any]]:
    if divergence_source == "all":
        divergences = [item for item in pair.get("divergences", []) if isinstance(item, dict)]
        if divergences:
            return divergences
    divergence = pair.get("first_divergence")
    return [divergence] if isinstance(divergence, dict) else []


def _observation_arrays_for_label(
    divergence: dict[str, Any],
    label: dict[str, Any],
    left_label: str,
    right_label: str,
) -> dict[str, Any] | None:
    preferred_step = _step_for_policy(divergence, str(label["preferred_policy"]), left_label, right_label)
    avoided_step = _step_for_policy(divergence, str(label["avoided_policy"]), left_label, right_label)
    for step in (preferred_step, avoided_step):
        arrays = ((step or {}).get("observation") or {}).get("arrays")
        if not isinstance(arrays, dict):
            continue
        if {"planes", "scalars", "action_mask"} <= set(arrays):
            return arrays
    return None


def _step_for_policy(
    divergence: dict[str, Any],
    policy: str,
    left_label: str,
    right_label: str,
) -> dict[str, Any] | None:
    if policy == left_label:
        return divergence.get("left") or divergence.get(left_label)
    if policy == right_label:
        return divergence.get("right") or divergence.get(right_label)
    return divergence.get(policy)


def _margin_summary(margins: np.ndarray, reward_gaps: np.ndarray) -> dict[str, Any]:
    positive = margins > 0.0
    negative = margins < 0.0
    return {
        "count": int(margins.size),
        "preferred_rate": _rate(positive),
        "misrank_rate": _rate(negative),
        "tie_rate": _rate(margins == 0.0),
        "mean_margin": float(np.mean(margins)) if margins.size else 0.0,
        "reward_gap_weighted_preferred_rate": _weighted_rate(positive, reward_gaps),
        "reward_gap_weighted_misrank_rate": _weighted_rate(negative, reward_gaps),
        "reward_gap_weighted_mean_margin": _weighted_mean(margins, reward_gaps),
    }


def _summary(values: np.ndarray) -> dict[str, Any]:
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)) if values.size else 0.0,
        "median": float(np.median(values)) if values.size else 0.0,
        "max": float(np.max(values)) if values.size else 0.0,
        "sum": float(np.sum(values)) if values.size else 0.0,
    }


def _family_pair_counts(preferred: np.ndarray, avoided: np.ndarray) -> dict[str, int]:
    counts = Counter()
    for preferred_action, avoided_action in zip(preferred.tolist(), avoided.tolist()):
        counts[f"{action_family(int(preferred_action))}_over_{action_family(int(avoided_action))}"] += 1
    return dict(sorted(counts.items()))


def _examples(rows: Sequence[dict[str, Any]], margins: np.ndarray, condition: np.ndarray, limit: int = 10) -> list[dict[str, Any]]:
    indexes = [index for index, keep in enumerate(condition.tolist()) if keep]
    indexes.sort(key=lambda index: float(rows[index]["reward_gap"]), reverse=True)
    examples = []
    for index in indexes[:limit]:
        row = rows[index]
        examples.append(
            {
                "seed": row.get("seed"),
                "seat": row.get("seat"),
                "decision_index": row.get("decision_index"),
                "reward_gap": float(row["reward_gap"]),
                "margin": float(margins[index]),
                "preferred_action_id": int(row["preferred_action_id"]),
                "preferred_action_label": action_label(int(row["preferred_action_id"])),
                "avoided_action_id": int(row["avoided_action_id"]),
                "avoided_action_label": action_label(int(row["avoided_action_id"])),
                "preferred_policy": row.get("preferred_policy"),
                "avoided_policy": row.get("avoided_policy"),
                "tags": row.get("tags", []),
            }
        )
    return examples


def _rate(mask: np.ndarray) -> float:
    return float(np.mean(mask)) if mask.size else 0.0


def _weighted_rate(mask: np.ndarray, weights: np.ndarray) -> float:
    if not mask.size:
        return 0.0
    total = float(np.sum(weights))
    if total <= 0.0:
        return _rate(mask)
    return float(np.sum(weights * mask.astype(np.float32)) / total)


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    if not values.size:
        return 0.0
    total = float(np.sum(weights))
    if total <= 0.0:
        return float(np.mean(values))
    return float(np.sum(values * weights) / total)
