from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .paired_trace import TRACE_CONTEXT_SCALAR_NAMES, counterfactual_label_from_pair


def build_paired_trace_action_ev_arrays(
    report_path: Path,
    left_label: str = "anchor",
    right_label: str = "candidate",
    min_reward_gap: float = 0.0,
    action_family: str | None = None,
    divergence_source: str = "first",
    include_trajectory_context: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if divergence_source not in {"first", "later", "all"}:
        raise ValueError("divergence_source must be 'first', 'later', or 'all'")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_left_label = str(report.get("left_label") or left_label)
    report_right_label = str(report.get("right_label") or right_label)
    rows: list[dict[str, Any]] = []
    skipped_missing_arrays = 0
    skipped_same_reward = 0
    skipped_reward_gap = 0
    skipped_action_family = 0

    for pair in report.get("pairs", []):
        for divergence in selected_divergences(pair, divergence_source=divergence_source):
            label = counterfactual_label_from_pair(
                pair,
                left_label=report_left_label,
                right_label=report_right_label,
                divergence=divergence,
                divergence_index=divergence.get("divergence_index"),
            )
            if label is None:
                skipped_same_reward += 1
                continue
            if float(label["reward_gap"]) < float(min_reward_gap):
                skipped_reward_gap += 1
                continue
            if action_family is not None and (
                str(label["preferred_action_family"]) != action_family
                or str(label["avoided_action_family"]) != action_family
            ):
                skipped_action_family += 1
                continue
            preferred_policy = str(label["preferred_policy"])
            preferred_step = (
                divergence.get("right" if preferred_policy == report_right_label else "left")
                or divergence.get(preferred_policy)
                or {}
            )
            arrays = (preferred_step.get("observation") or {}).get("arrays")
            if not arrays:
                skipped_missing_arrays += 1
                continue
            rows.append({"label": label, "arrays": arrays, "pair": pair})

    if not rows:
        raise ValueError(
            "no paired-trace action-EV rows with observation arrays were found; "
            "rerun paired_trace with --include-observation-arrays"
        )

    planes = np.stack([np.asarray(row["arrays"]["planes"], dtype=np.float32) for row in rows]).astype(np.float32)
    scalars = np.stack([np.asarray(row["arrays"]["scalars"], dtype=np.float32) for row in rows]).astype(np.float32)
    if include_trajectory_context:
        context_scalars = np.stack([trace_context_vector(row["pair"]) for row in rows]).astype(np.float32)
        scalars = np.concatenate([scalars, context_scalars], axis=1)
    action_mask = np.stack([np.asarray(row["arrays"]["action_mask"], dtype=np.int8) for row in rows]).astype(np.int8)
    seats = np.asarray([int(row["label"]["seat"]) for row in rows], dtype=np.int16)
    preferred_action_ids = np.asarray([int(row["label"]["preferred_action_id"]) for row in rows], dtype=np.int64)
    avoided_action_ids = np.asarray([int(row["label"]["avoided_action_id"]) for row in rows], dtype=np.int64)
    preferred_rewards = np.asarray([float(row["label"]["preferred_reward"]) for row in rows], dtype=np.float32)
    avoided_rewards = np.asarray([float(row["label"]["avoided_reward"]) for row in rows], dtype=np.float32)
    terminal_rewards = np.zeros((len(rows), 4), dtype=np.float32)
    terminal_rewards[np.arange(len(rows)), seats.astype(np.int64)] = avoided_rewards
    labels = [row["label"] for row in rows]
    payload = {
        "seats": seats,
        "planes": planes,
        "scalars": scalars,
        "action_mask": action_mask,
        "action_ids": avoided_action_ids,
        "decision_indices": np.asarray(
            [int(label["decision_index"] if label["decision_index"] is not None else index) for index, label in enumerate(labels)],
            dtype=np.int64,
        ),
        "episode_index": np.asarray([int(label["seed"]) for label in labels], dtype=np.int64),
        "terminal_rewards": terminal_rewards,
        "rewards": np.zeros((len(rows), 4), dtype=np.float32),
        "next_planes": planes.copy(),
        "next_scalars": scalars.copy(),
        "next_action_mask": action_mask.copy(),
        "terminated": np.zeros(len(rows), dtype=np.bool_),
        "truncated": np.zeros(len(rows), dtype=np.bool_),
        "steps_to_done": np.zeros(len(rows), dtype=np.int32),
        "sample_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_preferred_action_ids": preferred_action_ids,
        "pairwise_avoided_action_ids": avoided_action_ids,
        "pairwise_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_reward_delta_targets": preferred_rewards - avoided_rewards,
        "branch_preferred_rewards": preferred_rewards,
        "branch_avoided_rewards": avoided_rewards,
        "branch_left_action_ids": np.asarray(
            [
                int(label["preferred_action_id"] if label["preferred_policy"] == report_left_label else label["avoided_action_id"])
                for label in labels
            ],
            dtype=np.int64,
        ),
        "branch_right_action_ids": np.asarray(
            [
                int(label["preferred_action_id"] if label["preferred_policy"] == report_right_label else label["avoided_action_id"])
                for label in labels
            ],
            dtype=np.int64,
        ),
        "branch_target_actual_deltas": np.asarray(
            [
                float(label["preferred_reward"] - label["avoided_reward"])
                if label["preferred_policy"] == report_right_label
                else float(label["avoided_reward"] - label["preferred_reward"])
                for label in labels
            ],
            dtype=np.float32,
        ),
        "branch_target_predicted_deltas": np.full(len(rows), np.nan, dtype=np.float32),
    }
    metadata = {
        "source": "paired_trace_first_divergence_action_ev",
        "source_report": str(report_path),
        "rows": len(rows),
        "left_label": report_left_label,
        "right_label": report_right_label,
        "min_reward_gap": float(min_reward_gap),
        "action_family_filter": action_family,
        "divergence_source": divergence_source,
        "include_trajectory_context": bool(include_trajectory_context),
        "trajectory_context_scalar_names": list(TRACE_CONTEXT_SCALAR_NAMES) if include_trajectory_context else [],
        "skipped_missing_arrays": skipped_missing_arrays,
        "skipped_same_reward": skipped_same_reward,
        "skipped_reward_gap": skipped_reward_gap,
        "skipped_action_family": skipped_action_family,
        "mean_reward_gap": float(np.mean(payload["pairwise_reward_delta_targets"])),
        "max_reward_gap": float(np.max(payload["pairwise_reward_delta_targets"])),
        "preferred_policy_counts": dict(sorted(Counter(str(label["preferred_policy"]) for label in labels).items())),
        "avoided_policy_counts": dict(sorted(Counter(str(label["avoided_policy"]) for label in labels).items())),
        "preferred_family_counts": dict(sorted(Counter(str(label["preferred_action_family"]) for label in labels).items())),
        "avoided_family_counts": dict(sorted(Counter(str(label["avoided_action_family"]) for label in labels).items())),
    }
    return payload, metadata


def trace_context_vector(pair: dict[str, Any]) -> np.ndarray:
    raw = pair.get("pre_divergence_context")
    if not isinstance(raw, dict):
        raw = {}
    return np.asarray([float(raw.get(name, 0.0)) for name in TRACE_CONTEXT_SCALAR_NAMES], dtype=np.float32)


def selected_divergences(pair: dict[str, Any], divergence_source: str = "first") -> list[dict[str, Any]]:
    first = pair.get("first_divergence")
    first_index = pair.get("first_divergence_index")
    if divergence_source == "first":
        if not first:
            return []
        payload = dict(first)
        if first_index is not None and "divergence_index" not in payload:
            payload["divergence_index"] = int(first_index)
        return [payload]

    divergences = [dict(item) for item in pair.get("divergences", []) if isinstance(item, dict)]
    if not divergences and first:
        payload = dict(first)
        if first_index is not None and "divergence_index" not in payload:
            payload["divergence_index"] = int(first_index)
        divergences = [payload]
    if divergence_source == "all":
        return divergences

    return [
        divergence
        for divergence in divergences
        if divergence.get("divergence_index") is not None
        and first_index is not None
        and int(divergence["divergence_index"]) != int(first_index)
    ]
