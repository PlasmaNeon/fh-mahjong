"""Near-state discard counterfactual extraction from paired traces."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .evaluate import reward_summary
from .paired_trace import counterfactual_label_from_pair
from .scripts.build_counterfactual_risk_data import selected_divergences


COMPARABLE_SCALARS = (
    "overall_shanten",
    "standard_shanten",
    "seven_pairs_shanten",
    "independence_shanten",
    "ukeire",
    "best_discard_post_shanten",
    "best_discard_ukeire",
    "best_discard_route_delta",
    "wild_count",
    "visible_score_potential",
    "discard_danger_range",
    "hand_progress",
    "hands_remaining",
    "rank_score",
    "leader_pressure",
    "large_loss_margin",
    "self_bust_margin",
    "opponent_large_loss_pressure",
    "score_ratio",
    "net_score_progress",
    "next_rank_pressure",
    "lower_rank_cushion",
    "public_threat",
)


def extract_near_state_discard_cases(
    report: dict[str, Any],
    left_label: str | None = None,
    right_label: str | None = None,
    divergence_source: str = "later",
    large_loss_threshold: float = -1.0,
    min_reward_gap: float = 0.0,
    max_decision_index_gap: int = 0,
    max_scalar_l1: float = 0.10,
    max_scalar_linf: float = 0.25,
    min_action_mask_jaccard: float = 0.95,
    scalar_names: Sequence[str] = COMPARABLE_SCALARS,
) -> dict[str, Any]:
    """Filter paired traces to high-confidence discard-vs-discard near-state cases."""
    if divergence_source not in {"first", "later", "all"}:
        raise ValueError("divergence_source must be 'first', 'later', or 'all'")
    report_left_label = str(report.get("left_label") or left_label or "left")
    report_right_label = str(report.get("right_label") or right_label or "right")
    cases: list[dict[str, Any]] = []
    skipped = Counter()

    for pair in report.get("pairs", []):
        for divergence in selected_divergences(pair, divergence_source=divergence_source):
            label = counterfactual_label_from_pair(
                pair,
                left_label=report_left_label,
                right_label=report_right_label,
                large_loss_threshold=large_loss_threshold,
                divergence=divergence,
                divergence_index=divergence.get("divergence_index"),
            )
            if label is None:
                skipped["unlabeled_or_same_reward"] += 1
                continue
            if float(label["reward_gap"]) < float(min_reward_gap):
                skipped["reward_gap"] += 1
                continue
            if label["preferred_action_family"] != "discard" or label["avoided_action_family"] != "discard":
                skipped["not_discard_vs_discard"] += 1
                continue
            left_step = _step_for_policy(divergence, report_left_label, "left")
            right_step = _step_for_policy(divergence, report_right_label, "right")
            if not left_step or not right_step:
                skipped["missing_step"] += 1
                continue
            if not _has_observation_arrays(left_step) or not _has_observation_arrays(right_step):
                skipped["missing_arrays"] += 1
                continue

            preferred_step = left_step if label["preferred_policy"] == report_left_label else right_step
            avoided_step = left_step if label["avoided_policy"] == report_left_label else right_step
            preferred_action = int(label["preferred_action_id"])
            avoided_action = int(label["avoided_action_id"])

            legality = {
                "preferred_action_legal_in_preferred_observation": _action_legal(preferred_step, preferred_action),
                "avoided_action_legal_in_preferred_observation": _action_legal(preferred_step, avoided_action),
                "preferred_action_legal_in_avoided_observation": _action_legal(avoided_step, preferred_action),
                "avoided_action_legal_in_avoided_observation": _action_legal(avoided_step, avoided_action),
            }
            if not all(legality.values()):
                skipped["cross_illegal_action"] += 1
                continue

            decision_gap = abs(
                int(preferred_step.get("decision_index", 0)) - int(avoided_step.get("decision_index", 0))
            )
            if decision_gap > int(max_decision_index_gap):
                skipped["decision_index_gap"] += 1
                continue

            scalar_distance = visible_scalar_distance(
                _named_scalars(preferred_step),
                _named_scalars(avoided_step),
                scalar_names=scalar_names,
            )
            if scalar_distance["l1_mean"] > float(max_scalar_l1):
                skipped["scalar_l1"] += 1
                continue
            if scalar_distance["linf"] > float(max_scalar_linf):
                skipped["scalar_linf"] += 1
                continue

            mask_jaccard = action_mask_jaccard(preferred_step, avoided_step)
            if mask_jaccard < float(min_action_mask_jaccard):
                skipped["action_mask_jaccard"] += 1
                continue

            cases.append(
                {
                    **label,
                    "source": (
                        "first_divergence"
                        if label.get("divergence_index") == label.get("first_divergence_index")
                        else "later_aligned_disagreement"
                    ),
                    "decision_index_gap": decision_gap,
                    "scalar_distance": scalar_distance,
                    "action_mask_jaccard": mask_jaccard,
                    "legality": legality,
                    "preferred_policy_scores": action_score_for_step(preferred_step, preferred_action, avoided_action),
                    "avoided_policy_scores": action_score_for_step(avoided_step, preferred_action, avoided_action),
                }
            )

    return {
        "schema_version": 1,
        "source_report": report.get("source_report"),
        "left_label": report_left_label,
        "right_label": report_right_label,
        "divergence_source": divergence_source,
        "filters": {
            "large_loss_threshold": float(large_loss_threshold),
            "min_reward_gap": float(min_reward_gap),
            "max_decision_index_gap": int(max_decision_index_gap),
            "max_scalar_l1": float(max_scalar_l1),
            "max_scalar_linf": float(max_scalar_linf),
            "min_action_mask_jaccard": float(min_action_mask_jaccard),
            "scalar_names": list(scalar_names),
        },
        "summary": summarize_near_state_cases(cases, skipped),
        "cases": cases,
    }


def summarize_near_state_cases(cases: Sequence[dict[str, Any]], skipped: Counter[str]) -> dict[str, Any]:
    reward_gaps = [float(case["reward_gap"]) for case in cases]
    high_risk = [case for case in cases if bool(case.get("is_high_risk"))]
    source_counts = Counter(str(case.get("source")) for case in cases)
    preferred_policy_counts = Counter(str(case.get("preferred_policy")) for case in cases)
    avoided_policy_counts = Counter(str(case.get("avoided_policy")) for case in cases)
    return {
        "cases": len(cases),
        "high_risk_cases": len(high_risk),
        "source_counts": dict(sorted(source_counts.items())),
        "preferred_policy_counts": dict(sorted(preferred_policy_counts.items())),
        "avoided_policy_counts": dict(sorted(avoided_policy_counts.items())),
        "reward_gap": reward_summary(reward_gaps),
        "skipped": dict(sorted(skipped.items())),
    }


def visible_scalar_distance(
    preferred_scalars: dict[str, float],
    avoided_scalars: dict[str, float],
    scalar_names: Sequence[str] = COMPARABLE_SCALARS,
) -> dict[str, Any]:
    diffs: list[float] = []
    missing: list[str] = []
    for name in scalar_names:
        if name not in preferred_scalars or name not in avoided_scalars:
            missing.append(str(name))
            continue
        diffs.append(abs(float(preferred_scalars[name]) - float(avoided_scalars[name])))
    if not diffs:
        return {"count": 0, "l1_mean": float("inf"), "linf": float("inf"), "missing": missing}
    array = np.asarray(diffs, dtype=np.float32)
    return {
        "count": int(array.size),
        "l1_mean": float(np.mean(array)),
        "linf": float(np.max(array)),
        "missing": missing,
    }


def action_mask_jaccard(left_step: dict[str, Any], right_step: dict[str, Any]) -> float:
    left_mask = _action_mask(left_step)
    right_mask = _action_mask(right_step)
    if left_mask is None or right_mask is None:
        return 0.0
    left_legal = left_mask > 0
    right_legal = right_mask > 0
    union = np.logical_or(left_legal, right_legal)
    union_count = int(np.count_nonzero(union))
    if union_count == 0:
        return 1.0
    intersection = np.logical_and(left_legal, right_legal)
    return float(np.count_nonzero(intersection) / union_count)


def action_score_for_step(step: dict[str, Any], preferred_action_id: int, avoided_action_id: int) -> dict[str, Any]:
    scores = step.get("action_scores") or {}
    return {
        "chosen_action_id": scores.get("chosen_action_id"),
        "preferred_policy_logit": _score_lookup(scores.get("top_policy_logits", []), preferred_action_id),
        "avoided_policy_logit": _score_lookup(scores.get("top_policy_logits", []), avoided_action_id),
        "preferred_q": _score_lookup(scores.get("top_q", []), preferred_action_id),
        "avoided_q": _score_lookup(scores.get("top_q", []), avoided_action_id),
    }


def _score_lookup(items: Sequence[dict[str, Any]], action_id: int) -> float | None:
    for item in items:
        if int(item.get("action_id", -1)) == int(action_id):
            return float(item["score"])
    return None


def _step_for_policy(divergence: dict[str, Any], policy_label: str, side_key: str) -> dict[str, Any]:
    return divergence.get(side_key) or divergence.get(policy_label) or {}


def _has_observation_arrays(step: dict[str, Any]) -> bool:
    arrays = (step.get("observation") or {}).get("arrays") or {}
    return bool(arrays.get("action_mask")) and bool(arrays.get("scalars"))


def _named_scalars(step: dict[str, Any]) -> dict[str, float]:
    return {
        str(name): float(value)
        for name, value in ((step.get("observation") or {}).get("scalars") or {}).items()
    }


def _action_legal(step: dict[str, Any], action_id: int) -> bool:
    mask = _action_mask(step)
    return mask is not None and 0 <= int(action_id) < mask.shape[0] and bool(mask[int(action_id)] > 0)


def _action_mask(step: dict[str, Any]) -> np.ndarray | None:
    action_mask = ((step.get("observation") or {}).get("arrays") or {}).get("action_mask")
    if action_mask is None:
        return None
    return np.asarray(action_mask, dtype=np.int8)


def load_near_state_report(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
