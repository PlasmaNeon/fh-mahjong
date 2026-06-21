from __future__ import annotations

from typing import Any

import numpy as np

from .action_catalog import action_family, action_label
from .paired_trace import SCALAR_NAMES

BRANCH_CF_ARRAY_KEYS = (
    "planes",
    "scalars",
    "action_mask",
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_reward_delta_targets",
)


def preference_summary(
    preferred_scores: np.ndarray,
    avoided_scores: np.ndarray,
    reward_gaps: np.ndarray | None = None,
) -> dict[str, Any]:
    preferred_scores = np.asarray(preferred_scores, dtype=np.float32)
    avoided_scores = np.asarray(avoided_scores, dtype=np.float32)
    if preferred_scores.shape != avoided_scores.shape:
        raise ValueError("preferred_scores and avoided_scores must have the same shape")
    margins = preferred_scores - avoided_scores
    count = int(margins.size)
    gaps = np.ones(count, dtype=np.float32) if reward_gaps is None else np.asarray(reward_gaps, dtype=np.float32)
    if gaps.shape != margins.shape:
        raise ValueError("reward_gaps must match score shapes")
    weights = np.maximum(gaps, 0.0)
    positive = margins > 0.0
    tied = margins == 0.0
    return {
        "count": count,
        "preferred_rate": float(np.mean(positive)) if count else 0.0,
        "tie_rate": float(np.mean(tied)) if count else 0.0,
        "mean_margin": float(np.mean(margins)) if count else 0.0,
        "median_margin": float(np.median(margins)) if count else 0.0,
        "min_margin": float(np.min(margins)) if count else 0.0,
        "max_margin": float(np.max(margins)) if count else 0.0,
        "reward_gap_weighted_preferred_rate": weighted_rate(positive.astype(np.float32), weights),
        "reward_gap_weighted_mean_margin": weighted_mean(margins, weights),
        "by_reward_gap": reward_gap_buckets(margins, gaps),
    }


def lower_is_better_preference_summary(
    preferred_scores: np.ndarray,
    avoided_scores: np.ndarray,
    reward_gaps: np.ndarray | None = None,
) -> dict[str, Any]:
    return preference_summary(-np.asarray(preferred_scores), -np.asarray(avoided_scores), reward_gaps)


def family_pair_counts(preferred_action_ids: np.ndarray, avoided_action_ids: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for preferred, avoided in zip(preferred_action_ids.tolist(), avoided_action_ids.tolist()):
        key = f"{action_family(int(preferred))}_over_{action_family(int(avoided))}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def proposal_rerank_diagnostics(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    policy_scores: np.ndarray,
    q_scores: np.ndarray,
    action_mask: np.ndarray,
    risk_scores: np.ndarray | None = None,
    top_ks: tuple[int, ...] = (3, 5, 10, 20),
) -> dict[str, Any]:
    """Measure whether exact branch labels are reachable by top-k proposals and rerankers."""

    preferred_action_ids = np.asarray(preferred_action_ids, dtype=np.int64)
    avoided_action_ids = np.asarray(avoided_action_ids, dtype=np.int64)
    reward_gaps = np.asarray(reward_gaps, dtype=np.float32)
    policy_scores = np.asarray(policy_scores, dtype=np.float32)
    q_scores = np.asarray(q_scores, dtype=np.float32)
    action_mask = np.asarray(action_mask)
    if not (preferred_action_ids.shape == avoided_action_ids.shape == reward_gaps.shape):
        raise ValueError("proposal label arrays must share the same row shape")
    if policy_scores.shape != q_scores.shape:
        raise ValueError("policy_scores and q_scores must have the same shape")
    if action_mask.shape != policy_scores.shape:
        raise ValueError("action_mask must match score shape")
    if policy_scores.shape[0] != preferred_action_ids.shape[0]:
        raise ValueError("score row count must match branch rows")
    if risk_scores is not None:
        risk_scores = np.asarray(risk_scores, dtype=np.float32)
        if risk_scores.shape != policy_scores.shape:
            raise ValueError("risk_scores must match policy_scores shape")

    normalized_top_ks = tuple(sorted({max(1, int(k)) for k in top_ks}))
    policy_ranks = action_ranks(policy_scores, action_mask, descending=True)
    q_ranks = action_ranks(q_scores, action_mask, descending=True)
    risk_ranks = action_ranks(risk_scores, action_mask, descending=False) if risk_scores is not None else None
    row_indices = np.arange(preferred_action_ids.shape[0], dtype=np.int64)
    report: dict[str, Any] = {
        "rows": int(preferred_action_ids.shape[0]),
        "top_ks": list(normalized_top_ks),
        "policy_rank": label_rank_summary(policy_ranks, preferred_action_ids, avoided_action_ids, reward_gaps, normalized_top_ks),
        "q_rank": label_rank_summary(q_ranks, preferred_action_ids, avoided_action_ids, reward_gaps, normalized_top_ks),
        "rerank_by_policy_top_k": {},
    }
    if risk_ranks is not None:
        report["risk_lower_rank"] = label_rank_summary(
            risk_ranks,
            preferred_action_ids,
            avoided_action_ids,
            reward_gaps,
            normalized_top_ks,
        )

    policy_top1 = np.argmin(policy_ranks, axis=1).astype(np.int64)
    for top_k in normalized_top_ks:
        candidates = top_k_candidate_mask(policy_ranks, action_mask, top_k)
        q_selected = masked_argmax(q_scores, candidates)
        top_k_report: dict[str, Any] = {
            "preferred_in_policy_top_k_count": int(np.count_nonzero(candidates[row_indices, preferred_action_ids])),
            "preferred_in_policy_top_k_rate": rate(candidates[row_indices, preferred_action_ids]),
            "avoided_in_policy_top_k_count": int(np.count_nonzero(candidates[row_indices, avoided_action_ids])),
            "avoided_in_policy_top_k_rate": rate(candidates[row_indices, avoided_action_ids]),
            "q_rerank": rerank_selection_summary(
                preferred_action_ids,
                avoided_action_ids,
                reward_gaps,
                policy_top1,
                q_selected,
            ),
        }
        if risk_scores is not None:
            risk_selected = masked_argmin(risk_scores, candidates)
            top_k_report["risk_rerank"] = rerank_selection_summary(
                preferred_action_ids,
                avoided_action_ids,
                reward_gaps,
                policy_top1,
                risk_selected,
            )
        report["rerank_by_policy_top_k"][str(top_k)] = top_k_report
    return report


def action_ranks(scores: np.ndarray | None, action_mask: np.ndarray, descending: bool) -> np.ndarray:
    if scores is None:
        raise ValueError("scores are required")
    scores = np.asarray(scores, dtype=np.float32)
    action_mask = np.asarray(action_mask)
    if scores.shape != action_mask.shape:
        raise ValueError("scores and action_mask must have the same shape")
    ranks = np.full(scores.shape, scores.shape[1] + 1, dtype=np.int32)
    for row_index in range(scores.shape[0]):
        legal = np.flatnonzero(action_mask[row_index] > 0)
        if legal.size == 0:
            continue
        legal_scores = scores[row_index, legal]
        order = np.argsort(-legal_scores if descending else legal_scores, kind="stable")
        ranks[row_index, legal[order]] = np.arange(1, legal.size + 1, dtype=np.int32)
    return ranks


def label_rank_summary(
    ranks: np.ndarray,
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    top_ks: tuple[int, ...],
) -> dict[str, Any]:
    rows = np.arange(preferred_action_ids.shape[0], dtype=np.int64)
    preferred_ranks = ranks[rows, preferred_action_ids]
    avoided_ranks = ranks[rows, avoided_action_ids]
    report = {
        "preferred": numeric_summary(preferred_ranks.astype(np.float32)),
        "avoided": numeric_summary(avoided_ranks.astype(np.float32)),
        "preferred_better_than_avoided_rate": rate(preferred_ranks < avoided_ranks),
        "reward_gap_weighted_preferred_better_rate": weighted_rate(
            (preferred_ranks < avoided_ranks).astype(np.float32),
            np.maximum(reward_gaps, 0.0),
        ),
        "by_top_k": {},
    }
    for top_k in top_ks:
        preferred_in = preferred_ranks <= top_k
        avoided_in = avoided_ranks <= top_k
        report["by_top_k"][str(top_k)] = {
            "preferred_rate": rate(preferred_in),
            "avoided_rate": rate(avoided_in),
            "preferred_count": int(np.count_nonzero(preferred_in)),
            "avoided_count": int(np.count_nonzero(avoided_in)),
            "reward_gap_weighted_preferred_rate": weighted_rate(
                preferred_in.astype(np.float32),
                np.maximum(reward_gaps, 0.0),
            ),
        }
    return report


def top_k_candidate_mask(ranks: np.ndarray, action_mask: np.ndarray, top_k: int) -> np.ndarray:
    return (np.asarray(action_mask) > 0) & (np.asarray(ranks) <= int(top_k))


def masked_argmax(scores: np.ndarray, candidate_mask: np.ndarray) -> np.ndarray:
    masked = np.where(candidate_mask, scores, -np.inf)
    return np.argmax(masked, axis=1).astype(np.int64)


def masked_argmin(scores: np.ndarray, candidate_mask: np.ndarray) -> np.ndarray:
    masked = np.where(candidate_mask, scores, np.inf)
    return np.argmin(masked, axis=1).astype(np.int64)


def rerank_selection_summary(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    selected_action_ids: np.ndarray,
) -> dict[str, Any]:
    source = np.where(selected_action_ids == anchor_action_ids, "anchor", "rerank")
    report = guard_choice_diagnostics(
        preferred_action_ids,
        avoided_action_ids,
        reward_gaps,
        anchor_action_ids,
        selected_action_ids,
        source,
    )
    report["selected_preferred_count"] = report["guarded_preferred_count"]
    report["selected_avoided_count"] = report["guarded_avoided_count"]
    report["selected_unlabeled_count"] = report["guarded_unlabeled_count"]
    return report


def branch_cf_diagnostics(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    policy_margins: np.ndarray,
    q_margins: np.ndarray,
    scalars: np.ndarray,
    risk_margins: np.ndarray | None = None,
    high_gap_threshold: float = 0.5,
    max_examples: int = 20,
) -> dict[str, Any]:
    """Summarize where checkpoint scores disagree with exact branch labels."""

    preferred_action_ids = np.asarray(preferred_action_ids, dtype=np.int64)
    avoided_action_ids = np.asarray(avoided_action_ids, dtype=np.int64)
    reward_gaps = np.asarray(reward_gaps, dtype=np.float32)
    policy_margins = np.asarray(policy_margins, dtype=np.float32)
    q_margins = np.asarray(q_margins, dtype=np.float32)
    scalars = np.asarray(scalars, dtype=np.float32)
    if not (
        preferred_action_ids.shape
        == avoided_action_ids.shape
        == reward_gaps.shape
        == policy_margins.shape
        == q_margins.shape
    ):
        raise ValueError("branch diagnostic arrays must share the same row shape")
    if scalars.shape[0] != preferred_action_ids.shape[0]:
        raise ValueError("scalars row count must match pairwise rows")

    total = int(reward_gaps.size)
    masks = {
        "all": np.ones(total, dtype=np.bool_),
        "high_gap": reward_gaps >= float(high_gap_threshold),
        "policy_misrank": policy_margins <= 0.0,
        "q_misrank": q_margins <= 0.0,
        "both_misrank": (policy_margins <= 0.0) & (q_margins <= 0.0),
        "high_gap_policy_misrank": (reward_gaps >= float(high_gap_threshold)) & (policy_margins <= 0.0),
        "high_gap_q_misrank": (reward_gaps >= float(high_gap_threshold)) & (q_margins <= 0.0),
        "high_gap_both_misrank": (
            (reward_gaps >= float(high_gap_threshold)) & (policy_margins <= 0.0) & (q_margins <= 0.0)
        ),
    }
    if risk_margins is not None:
        risk_margins = np.asarray(risk_margins, dtype=np.float32)
        if risk_margins.shape != reward_gaps.shape:
            raise ValueError("risk_margins must match pairwise rows")
        masks["risk_misrank"] = risk_margins <= 0.0
        masks["high_gap_risk_misrank"] = (reward_gaps >= float(high_gap_threshold)) & (risk_margins <= 0.0)

    return {
        "rows": total,
        "high_gap_threshold": float(high_gap_threshold),
        "segments": {
            name: segment_summary(mask, reward_gaps, policy_margins, q_margins, risk_margins)
            for name, mask in masks.items()
        },
        "scalar_segments": {
            name: scalar_segment_summary(scalars, mask)
            for name, mask in masks.items()
            if name in {"all", "high_gap", "policy_misrank", "q_misrank", "high_gap_q_misrank", "both_misrank"}
        },
        "top_q_misrank_pairs": top_action_pair_summary(
            preferred_action_ids,
            avoided_action_ids,
            reward_gaps,
            q_margins,
            masks["q_misrank"],
            limit=20,
        ),
        "top_high_gap_q_misrank_pairs": top_action_pair_summary(
            preferred_action_ids,
            avoided_action_ids,
            reward_gaps,
            q_margins,
            masks["high_gap_q_misrank"],
            limit=20,
        ),
        "examples": {
            "highest_gap_q_misrank": top_examples(
                preferred_action_ids,
                avoided_action_ids,
                reward_gaps,
                policy_margins,
                q_margins,
                scalars,
                masks["q_misrank"],
                max_examples,
                risk_margins=risk_margins,
            ),
            "highest_gap_policy_misrank": top_examples(
                preferred_action_ids,
                avoided_action_ids,
                reward_gaps,
                policy_margins,
                q_margins,
                scalars,
                masks["policy_misrank"],
                max_examples,
                risk_margins=risk_margins,
            ),
        },
    }


def guard_choice_diagnostics(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    guarded_action_ids: np.ndarray,
    guard_sources: np.ndarray,
) -> dict[str, Any]:
    preferred_action_ids = np.asarray(preferred_action_ids, dtype=np.int64)
    avoided_action_ids = np.asarray(avoided_action_ids, dtype=np.int64)
    reward_gaps = np.asarray(reward_gaps, dtype=np.float32)
    anchor_action_ids = np.asarray(anchor_action_ids, dtype=np.int64)
    guarded_action_ids = np.asarray(guarded_action_ids, dtype=np.int64)
    guard_sources = np.asarray(guard_sources)
    if not (
        preferred_action_ids.shape
        == avoided_action_ids.shape
        == reward_gaps.shape
        == anchor_action_ids.shape
        == guarded_action_ids.shape
        == guard_sources.shape
    ):
        raise ValueError("guard diagnostic arrays must share the same row shape")

    total = int(preferred_action_ids.size)
    changed = guarded_action_ids != anchor_action_ids
    source_changed = guard_sources == "risk_guard"
    anchor_preferred = anchor_action_ids == preferred_action_ids
    anchor_avoided = anchor_action_ids == avoided_action_ids
    anchor_labeled = anchor_preferred | anchor_avoided
    guarded_preferred = guarded_action_ids == preferred_action_ids
    guarded_avoided = guarded_action_ids == avoided_action_ids
    guarded_labeled = guarded_preferred | guarded_avoided
    known_delta_mask = anchor_labeled & guarded_labeled & changed
    rescue = anchor_avoided & guarded_preferred
    harm = anchor_preferred & guarded_avoided

    delta_units = guarded_preferred.astype(np.float32) - anchor_preferred.astype(np.float32)
    known_reward_delta = delta_units * reward_gaps

    return {
        "rows": total,
        "changed_count": int(np.count_nonzero(changed)),
        "changed_rate": rate(changed),
        "source_risk_guard_count": int(np.count_nonzero(source_changed)),
        "source_risk_guard_rate": rate(source_changed),
        "anchor_preferred_count": int(np.count_nonzero(anchor_preferred)),
        "anchor_preferred_rate": rate(anchor_preferred),
        "anchor_avoided_count": int(np.count_nonzero(anchor_avoided)),
        "anchor_avoided_rate": rate(anchor_avoided),
        "anchor_unlabeled_count": int(np.count_nonzero(~anchor_labeled)),
        "anchor_unlabeled_rate": rate(~anchor_labeled),
        "guarded_preferred_count": int(np.count_nonzero(guarded_preferred)),
        "guarded_preferred_rate": rate(guarded_preferred),
        "guarded_avoided_count": int(np.count_nonzero(guarded_avoided)),
        "guarded_avoided_rate": rate(guarded_avoided),
        "guarded_unlabeled_count": int(np.count_nonzero(~guarded_labeled)),
        "guarded_unlabeled_rate": rate(~guarded_labeled),
        "rescue_count": int(np.count_nonzero(rescue)),
        "rescue_rate": rate(rescue),
        "harm_count": int(np.count_nonzero(harm)),
        "harm_rate": rate(harm),
        "known_changed_count": int(np.count_nonzero(known_delta_mask)),
        "known_reward_delta_sum": float(np.sum(known_reward_delta[known_delta_mask])) if total else 0.0,
        "known_reward_delta_mean": float(np.mean(known_reward_delta[known_delta_mask]))
        if np.count_nonzero(known_delta_mask)
        else 0.0,
        "changed_to_preferred_count": int(np.count_nonzero(changed & guarded_preferred)),
        "changed_to_avoided_count": int(np.count_nonzero(changed & guarded_avoided)),
        "changed_to_unlabeled_count": int(np.count_nonzero(changed & ~guarded_labeled)),
        "changed_reward_gap": numeric_summary(reward_gaps[changed]),
        "rescue_reward_gap": numeric_summary(reward_gaps[rescue]),
        "harm_reward_gap": numeric_summary(reward_gaps[harm]),
        "top_rescues": guard_examples(preferred_action_ids, avoided_action_ids, reward_gaps, anchor_action_ids, guarded_action_ids, rescue),
        "top_harms": guard_examples(preferred_action_ids, avoided_action_ids, reward_gaps, anchor_action_ids, guarded_action_ids, harm),
    }


def oracle_preferred_filter_diagnostics(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    anchor_logits: np.ndarray,
    risk_probabilities: np.ndarray,
    anchor_risk_threshold: float,
    candidate_risk_threshold: float,
    min_risk_reduction: float,
    max_policy_logit_gaps: list[float | None],
) -> dict[str, Any]:
    """Upper-bound a guard by asking whether exact preferred branches pass filters."""

    preferred_action_ids = np.asarray(preferred_action_ids, dtype=np.int64)
    avoided_action_ids = np.asarray(avoided_action_ids, dtype=np.int64)
    reward_gaps = np.asarray(reward_gaps, dtype=np.float32)
    anchor_action_ids = np.asarray(anchor_action_ids, dtype=np.int64)
    anchor_logits = np.asarray(anchor_logits, dtype=np.float32)
    risk_probabilities = np.asarray(risk_probabilities, dtype=np.float32)
    if not (
        preferred_action_ids.shape
        == avoided_action_ids.shape
        == reward_gaps.shape
        == anchor_action_ids.shape
    ):
        raise ValueError("oracle guard arrays must share the same row shape")
    if anchor_logits.shape != risk_probabilities.shape:
        raise ValueError("anchor_logits and risk_probabilities must have the same shape")
    if anchor_logits.shape[0] != preferred_action_ids.shape[0]:
        raise ValueError("score row count must match branch rows")

    rows = np.arange(preferred_action_ids.shape[0], dtype=np.int64)
    preferred_risk = risk_probabilities[rows, preferred_action_ids]
    anchor_risk = risk_probabilities[rows, anchor_action_ids]
    preferred_logit = anchor_logits[rows, preferred_action_ids]
    anchor_logit = anchor_logits[rows, anchor_action_ids]
    risk_reduction = anchor_risk - preferred_risk
    logit_gap = anchor_logit - preferred_logit
    anchor_avoided = anchor_action_ids == avoided_action_ids
    anchor_trigger = anchor_risk >= float(anchor_risk_threshold)
    candidate_risk_pass = preferred_risk <= float(candidate_risk_threshold)
    risk_reduction_pass = risk_reduction >= float(min_risk_reduction)
    base_pass = anchor_avoided & anchor_trigger & candidate_risk_pass & risk_reduction_pass

    cap_reports: dict[str, Any] = {}
    for max_gap in max_policy_logit_gaps:
        if max_gap is None or not np.isfinite(float(max_gap)):
            cap_key = "none"
            logit_gap_pass = np.ones_like(base_pass, dtype=np.bool_)
        else:
            cap_key = str(float(max_gap))
            logit_gap_pass = logit_gap <= float(max_gap)
        all_pass = base_pass & logit_gap_pass
        cap_reports[cap_key] = {
            "max_policy_logit_gap": None if cap_key == "none" else float(max_gap),
            "pass_count": int(np.count_nonzero(all_pass)),
            "pass_rate": rate(all_pass),
            "known_rescue_reward_delta_sum": float(np.sum(reward_gaps[all_pass])) if reward_gaps.size else 0.0,
            "known_rescue_reward_delta_mean": float(np.mean(reward_gaps[all_pass]))
            if np.count_nonzero(all_pass)
            else 0.0,
            "reward_gap": numeric_summary(reward_gaps[all_pass]),
            "logit_gap": numeric_summary(logit_gap[all_pass]),
            "risk_reduction": numeric_summary(risk_reduction[all_pass]),
            "top_exact_rescues": oracle_preferred_examples(
                preferred_action_ids,
                avoided_action_ids,
                reward_gaps,
                anchor_action_ids,
                preferred_risk,
                anchor_risk,
                logit_gap,
                all_pass,
            ),
        }

    return {
        "anchor_avoided_count": int(np.count_nonzero(anchor_avoided)),
        "anchor_avoided_rate": rate(anchor_avoided),
        "anchor_avoided_reward_gap": numeric_summary(reward_gaps[anchor_avoided]),
        "anchor_avoided_anchor_risk": numeric_summary(anchor_risk[anchor_avoided]),
        "anchor_avoided_preferred_risk": numeric_summary(preferred_risk[anchor_avoided]),
        "anchor_avoided_risk_reduction": numeric_summary(risk_reduction[anchor_avoided]),
        "anchor_avoided_logit_gap": numeric_summary(logit_gap[anchor_avoided]),
        "anchor_avoided_trigger_count": int(np.count_nonzero(anchor_avoided & anchor_trigger)),
        "preferred_candidate_risk_pass_count": int(np.count_nonzero(anchor_avoided & candidate_risk_pass)),
        "preferred_risk_reduction_pass_count": int(np.count_nonzero(anchor_avoided & risk_reduction_pass)),
        "preferred_base_filters_pass_count": int(np.count_nonzero(base_pass)),
        "preferred_base_filters_reward_gap": numeric_summary(reward_gaps[base_pass]),
        "by_max_policy_logit_gap": cap_reports,
    }


def oracle_preferred_examples(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    preferred_risk: np.ndarray,
    anchor_risk: np.ndarray,
    logit_gap: np.ndarray,
    mask: np.ndarray,
    limit: int = 20,
) -> list[dict[str, Any]]:
    selected = np.flatnonzero(np.asarray(mask, dtype=np.bool_))
    if selected.size == 0:
        return []
    selected = selected[np.argsort(reward_gaps[selected])[::-1]]
    examples = []
    for index in selected[: max(0, int(limit))].tolist():
        examples.append(
            {
                "row_index": int(index),
                "reward_gap": float(reward_gaps[index]),
                "preferred_action_id": int(preferred_action_ids[index]),
                "preferred_action_label": action_label(int(preferred_action_ids[index])),
                "avoided_action_id": int(avoided_action_ids[index]),
                "avoided_action_label": action_label(int(avoided_action_ids[index])),
                "anchor_action_id": int(anchor_action_ids[index]),
                "anchor_action_label": action_label(int(anchor_action_ids[index])),
                "anchor_risk": float(anchor_risk[index]),
                "preferred_risk": float(preferred_risk[index]),
                "risk_reduction": float(anchor_risk[index] - preferred_risk[index]),
                "logit_gap": float(logit_gap[index]),
            }
        )
    return examples


def guard_examples(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    anchor_action_ids: np.ndarray,
    guarded_action_ids: np.ndarray,
    mask: np.ndarray,
    limit: int = 20,
) -> list[dict[str, Any]]:
    selected = np.flatnonzero(np.asarray(mask, dtype=np.bool_))
    if selected.size == 0:
        return []
    selected = selected[np.argsort(reward_gaps[selected])[::-1]]
    examples = []
    for index in selected[: max(0, int(limit))].tolist():
        examples.append(
            {
                "row_index": int(index),
                "reward_gap": float(reward_gaps[index]),
                "preferred_action_id": int(preferred_action_ids[index]),
                "preferred_action_label": action_label(int(preferred_action_ids[index])),
                "avoided_action_id": int(avoided_action_ids[index]),
                "avoided_action_label": action_label(int(avoided_action_ids[index])),
                "anchor_action_id": int(anchor_action_ids[index]),
                "anchor_action_label": action_label(int(anchor_action_ids[index])),
                "guarded_action_id": int(guarded_action_ids[index]),
                "guarded_action_label": action_label(int(guarded_action_ids[index])),
            }
        )
    return examples


def segment_summary(
    mask: np.ndarray,
    reward_gaps: np.ndarray,
    policy_margins: np.ndarray,
    q_margins: np.ndarray,
    risk_margins: np.ndarray | None = None,
) -> dict[str, Any]:
    selected = np.asarray(mask, dtype=np.bool_)
    count = int(np.count_nonzero(selected))
    total = int(selected.size)
    report: dict[str, Any] = {
        "count": count,
        "rate": float(count / total) if total else 0.0,
        "reward_gap": numeric_summary(reward_gaps[selected]),
        "policy_margin": numeric_summary(policy_margins[selected]),
        "q_margin": numeric_summary(q_margins[selected]),
    }
    if risk_margins is not None:
        report["risk_margin"] = numeric_summary(risk_margins[selected])
    return report


def scalar_segment_summary(scalars: np.ndarray, mask: np.ndarray) -> dict[str, dict[str, float | int | None]]:
    selected = scalars[np.asarray(mask, dtype=np.bool_)]
    report: dict[str, dict[str, float | int | None]] = {}
    for index, name in SCALAR_NAMES.items():
        if index >= scalars.shape[1]:
            continue
        report[name] = numeric_summary(selected[:, index] if selected.size else np.asarray([], dtype=np.float32))
    return report


def top_action_pair_summary(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    margins: np.ndarray,
    mask: np.ndarray,
    limit: int = 20,
) -> list[dict[str, Any]]:
    aggregates: dict[tuple[int, int], dict[str, Any]] = {}
    for preferred, avoided, gap, margin, keep in zip(
        preferred_action_ids.tolist(),
        avoided_action_ids.tolist(),
        reward_gaps.tolist(),
        margins.tolist(),
        mask.tolist(),
    ):
        if not keep:
            continue
        key = (int(preferred), int(avoided))
        item = aggregates.setdefault(
            key,
            {
                "preferred_action_id": int(preferred),
                "preferred_action_label": action_label(int(preferred)),
                "avoided_action_id": int(avoided),
                "avoided_action_label": action_label(int(avoided)),
                "count": 0,
                "reward_gaps": [],
                "margins": [],
            },
        )
        item["count"] += 1
        item["reward_gaps"].append(float(gap))
        item["margins"].append(float(margin))
    rows: list[dict[str, Any]] = []
    for item in aggregates.values():
        gap_array = np.asarray(item.pop("reward_gaps"), dtype=np.float32)
        margin_array = np.asarray(item.pop("margins"), dtype=np.float32)
        item["mean_reward_gap"] = float(np.mean(gap_array)) if gap_array.size else 0.0
        item["max_reward_gap"] = float(np.max(gap_array)) if gap_array.size else 0.0
        item["mean_margin"] = float(np.mean(margin_array)) if margin_array.size else 0.0
        rows.append(item)
    rows.sort(key=lambda row: (row["count"], row["mean_reward_gap"]), reverse=True)
    return rows[: max(0, int(limit))]


def top_examples(
    preferred_action_ids: np.ndarray,
    avoided_action_ids: np.ndarray,
    reward_gaps: np.ndarray,
    policy_margins: np.ndarray,
    q_margins: np.ndarray,
    scalars: np.ndarray,
    mask: np.ndarray,
    limit: int,
    risk_margins: np.ndarray | None = None,
) -> list[dict[str, Any]]:
    selected_indices = np.flatnonzero(np.asarray(mask, dtype=np.bool_))
    if selected_indices.size == 0:
        return []
    selected_indices = selected_indices[np.argsort(reward_gaps[selected_indices])[::-1]]
    examples = []
    for index in selected_indices[: max(0, int(limit))].tolist():
        item = {
            "row_index": int(index),
            "reward_gap": float(reward_gaps[index]),
            "preferred_action_id": int(preferred_action_ids[index]),
            "preferred_action_label": action_label(int(preferred_action_ids[index])),
            "avoided_action_id": int(avoided_action_ids[index]),
            "avoided_action_label": action_label(int(avoided_action_ids[index])),
            "policy_margin": float(policy_margins[index]),
            "q_margin": float(q_margins[index]),
            "scalars": scalar_values_for_row(scalars[index]),
        }
        if risk_margins is not None:
            item["risk_margin"] = float(risk_margins[index])
        examples.append(item)
    return examples


def scalar_values_for_row(row: np.ndarray) -> dict[str, float]:
    return {
        name: float(row[index])
        for index, name in SCALAR_NAMES.items()
        if index < row.shape[0]
    }


def numeric_summary(values: np.ndarray) -> dict[str, float | int | None]:
    values = np.asarray(values, dtype=np.float32)
    if values.size == 0:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": int(values.size),
        "mean": float(np.mean(values)),
        "median": float(np.median(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def reward_gap_buckets(margins: np.ndarray, reward_gaps: np.ndarray) -> dict[str, dict[str, float | int]]:
    buckets = {
        "0.00-0.05": (0.0, 0.05),
        "0.05-0.20": (0.05, 0.20),
        "0.20-0.50": (0.20, 0.50),
        "0.50+": (0.50, np.inf),
    }
    report: dict[str, dict[str, float | int]] = {}
    for name, (low, high) in buckets.items():
        mask = (reward_gaps >= low) & (reward_gaps < high)
        selected = margins[mask]
        report[name] = {
            "count": int(selected.size),
            "preferred_rate": float(np.mean(selected > 0.0)) if selected.size else 0.0,
            "mean_margin": float(np.mean(selected)) if selected.size else 0.0,
        }
    return report


def weighted_rate(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    total = float(np.sum(weights))
    if total <= 0.0:
        return float(np.mean(values))
    return float(np.sum(values * weights) / total)


def weighted_mean(values: np.ndarray, weights: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    total = float(np.sum(weights))
    if total <= 0.0:
        return float(np.mean(values))
    return float(np.sum(values * weights) / total)


def rate(mask: np.ndarray) -> float:
    mask = np.asarray(mask, dtype=np.bool_)
    if mask.size == 0:
        return 0.0
    return float(np.mean(mask))
