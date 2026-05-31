from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class RiskCase:
    seed: int
    seat: int
    decision_index: Optional[int] = None
    action_id: Optional[int] = None
    action_label: Optional[str] = None
    baseline_action_id: Optional[int] = None
    baseline_action_label: Optional[str] = None
    reward: Optional[float] = None
    baseline_reward: Optional[float] = None
    reward_delta: Optional[float] = None
    source: str = "manual"
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskWeightReport:
    cases: int
    matched_cases: int
    weighted_transitions: int
    weight: float
    dataset_start_seed: Optional[int]
    matched_by: dict[str, int]
    pairwise_cases: int = 0
    pairwise_transitions: int = 0


def load_risk_cases_from_paired_trace_reports(
    paths: Sequence[Path],
    right_label: str = "candidate",
    left_label: str = "anchor",
    large_loss_threshold: Optional[float] = None,
    include_large_losses: bool = True,
    include_new_large_losses: bool = True,
    worst_delta_count: int = 0,
) -> list[RiskCase]:
    """Load high-risk first-divergence cases from paired trace reports.

    The returned cases are keyed by seed, seat, candidate/right action, and the
    first divergent decision index when present. Training can use these cases to
    weight matching transitions in datasets generated from the same seed range.
    """
    cases: dict[tuple[int, int, Optional[int], Optional[int], str], RiskCase] = {}
    for path in paths:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        pairs = list(report.get("pairs", []))
        for pair in pairs:
            right_reward = _float_or_none(pair.get(f"{right_label}_reward"))
            left_reward = _float_or_none(pair.get(f"{left_label}_reward"))
            reward_delta = _float_or_none(pair.get("reward_delta"))
            tags: list[str] = []
            if (
                include_large_losses
                and large_loss_threshold is not None
                and right_reward is not None
                and right_reward <= large_loss_threshold
            ):
                tags.append("right_large_loss")
            if (
                include_new_large_losses
                and large_loss_threshold is not None
                and right_reward is not None
                and left_reward is not None
                and right_reward <= large_loss_threshold
                and left_reward > large_loss_threshold
            ):
                tags.append("new_right_large_loss")
            if tags:
                case = risk_case_from_pair(pair, right_label=right_label, left_label=left_label, tags=tags)
                cases[_case_key(case)] = case

        if worst_delta_count > 0:
            worst_pairs = sorted(pairs, key=lambda pair: float(pair.get("reward_delta", 0.0)))[:worst_delta_count]
            for pair in worst_pairs:
                case = risk_case_from_pair(
                    pair,
                    right_label=right_label,
                    left_label=left_label,
                    tags=("worst_delta",),
                )
                cases[_case_key(case)] = case
    return list(cases.values())


def risk_case_from_pair(
    pair: dict[str, Any],
    right_label: str = "candidate",
    left_label: str = "anchor",
    tags: Iterable[str] = (),
) -> RiskCase:
    divergence = pair.get("first_divergence") or {}
    left_step = divergence.get("left") or divergence.get(left_label) or {}
    right_step = divergence.get("right") or divergence.get(right_label) or {}
    return RiskCase(
        seed=int(pair["seed"]),
        seat=int(pair["seat"]),
        decision_index=_int_or_none(right_step.get("decision_index", pair.get("first_divergence_index"))),
        action_id=_int_or_none(right_step.get("action_id")),
        action_label=str(right_step["action_label"]) if right_step.get("action_label") is not None else None,
        baseline_action_id=_int_or_none(left_step.get("action_id")),
        baseline_action_label=str(left_step["action_label"]) if left_step.get("action_label") is not None else None,
        reward=_float_or_none(pair.get(f"{right_label}_reward")),
        baseline_reward=_float_or_none(pair.get(f"{left_label}_reward")),
        reward_delta=_float_or_none(pair.get("reward_delta")),
        source="paired_trace",
        tags=tuple(sorted(set(tags))),
    )


def apply_risk_case_weights(
    arrays: dict[str, np.ndarray],
    cases: Sequence[RiskCase],
    weight: float,
    dataset_start_seed: Optional[int] = None,
    require_action_match: bool = True,
) -> RiskWeightReport:
    """Attach per-transition sample weights for exact high-risk cases.

    Matching is exact on seat and episode. When `decision_indices` are available
    it also matches the first divergent decision index. Otherwise older datasets
    fall back to seed/seat/action matching. Seed-to-episode mapping requires the
    dataset start seed because current shard manifests store episode indices,
    not original seeds.
    """
    if not cases:
        arrays["sample_weights"] = np.ones(arrays["action_ids"].shape[0], dtype=np.float32)
        return RiskWeightReport(0, 0, 0, float(weight), dataset_start_seed, {})

    sample_weights = np.asarray(
        arrays.get("sample_weights", np.ones(arrays["action_ids"].shape[0], dtype=np.float32)),
        dtype=np.float32,
    ).copy()
    pairwise_preferred_action_ids = np.asarray(
        arrays.get("pairwise_preferred_action_ids", np.full(arrays["action_ids"].shape[0], -1, dtype=np.int64)),
        dtype=np.int64,
    ).copy()
    pairwise_avoided_action_ids = np.asarray(
        arrays.get("pairwise_avoided_action_ids", np.full(arrays["action_ids"].shape[0], -1, dtype=np.int64)),
        dtype=np.int64,
    ).copy()
    pairwise_weights = np.asarray(
        arrays.get("pairwise_weights", np.zeros(arrays["action_ids"].shape[0], dtype=np.float32)),
        dtype=np.float32,
    ).copy()
    risk_case_matches = np.asarray(
        arrays.get("risk_case_matches", np.zeros(arrays["action_ids"].shape[0], dtype=np.bool_)),
        dtype=np.bool_,
    ).copy()
    episode_indices = np.asarray(arrays["episode_index"], dtype=np.int64)
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    action_ids = np.asarray(arrays["action_ids"], dtype=np.int64)
    decision_indices = arrays.get("decision_indices")
    if decision_indices is not None:
        decision_indices = np.asarray(decision_indices, dtype=np.int64)

    matched_cases = 0
    pairwise_cases = 0
    matched_by: dict[str, int] = {}
    for case in cases:
        episode_index = _episode_index_for_case(case, dataset_start_seed)
        if episode_index is None:
            continue

        mask = (episode_indices == episode_index) & (seats == int(case.seat))
        mode = "seed_seat"
        if decision_indices is not None and case.decision_index is not None:
            mask &= decision_indices == int(case.decision_index)
            mode = "seed_seat_decision"
        elif require_action_match and case.action_id is not None:
            mask &= action_ids == int(case.action_id)
            mode = "seed_seat_action"
        elif require_action_match:
            continue

        count = int(np.count_nonzero(mask))
        if count <= 0:
            continue
        risk_case_matches[mask] = True
        if weight > 1.0:
            sample_weights[mask] = np.maximum(sample_weights[mask], float(weight))
        if (
            case.baseline_action_id is not None
            and case.action_id is not None
            and int(case.baseline_action_id) != int(case.action_id)
        ):
            pairwise_preferred_action_ids[mask] = int(case.baseline_action_id)
            pairwise_avoided_action_ids[mask] = int(case.action_id)
            pairwise_weights[mask] = np.maximum(pairwise_weights[mask], 1.0)
            pairwise_cases += 1
        matched_cases += 1
        matched_by[mode] = matched_by.get(mode, 0) + count

    arrays["sample_weights"] = sample_weights
    arrays["pairwise_preferred_action_ids"] = pairwise_preferred_action_ids
    arrays["pairwise_avoided_action_ids"] = pairwise_avoided_action_ids
    arrays["pairwise_weights"] = pairwise_weights
    arrays["risk_case_matches"] = risk_case_matches
    return RiskWeightReport(
        cases=len(cases),
        matched_cases=matched_cases,
        weighted_transitions=int(np.count_nonzero(sample_weights > 1.0)),
        weight=float(weight),
        dataset_start_seed=dataset_start_seed,
        matched_by=dict(sorted(matched_by.items())),
        pairwise_cases=pairwise_cases,
        pairwise_transitions=int(np.count_nonzero(pairwise_weights > 0.0)),
    )


def _episode_index_for_case(case: RiskCase, dataset_start_seed: Optional[int]) -> Optional[int]:
    if dataset_start_seed is None:
        return None
    episode_index = int(case.seed) - int(dataset_start_seed)
    if episode_index < 0:
        return None
    return episode_index


def _case_key(case: RiskCase) -> tuple[int, int, Optional[int], Optional[int], str]:
    return (case.seed, case.seat, case.decision_index, case.action_id, ",".join(case.tags))


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)
