import math

import numpy as np
import pytest

from fh_mahjong_ai.branch_cf_calibration import (
    branch_cf_diagnostics,
    family_pair_counts,
    lower_is_better_preference_summary,
    preference_summary,
    proposal_rerank_diagnostics,
    reward_gap_buckets,
    guard_choice_diagnostics,
    oracle_preferred_filter_diagnostics,
    weighted_mean,
    weighted_rate,
)


def test_preference_summary_reports_gap_weighted_margins():
    preferred = np.array([1.0, 0.5, 0.2], dtype=np.float32)
    avoided = np.array([0.5, 0.8, 0.2], dtype=np.float32)
    gaps = np.array([0.1, 0.3, 0.0], dtype=np.float32)

    report = preference_summary(preferred, avoided, gaps)

    assert report["count"] == 3
    assert report["preferred_rate"] == pytest.approx(1.0 / 3.0)
    assert report["tie_rate"] == pytest.approx(1.0 / 3.0)
    assert report["mean_margin"] == pytest.approx((0.5 - 0.3 + 0.0) / 3.0)
    assert report["reward_gap_weighted_preferred_rate"] == pytest.approx(0.1 / 0.4)
    assert report["reward_gap_weighted_mean_margin"] == pytest.approx(((0.5 * 0.1) + (-0.3 * 0.3)) / 0.4)
    assert report["by_reward_gap"]["0.05-0.20"]["count"] == 1
    assert report["by_reward_gap"]["0.20-0.50"]["count"] == 1


def test_lower_is_better_summary_inverts_scores():
    preferred_risk = np.array([0.1, 0.9], dtype=np.float32)
    avoided_risk = np.array([0.4, 0.2], dtype=np.float32)

    report = lower_is_better_preference_summary(preferred_risk, avoided_risk)

    assert report["preferred_rate"] == pytest.approx(0.5)
    assert report["mean_margin"] == pytest.approx(((0.4 - 0.1) + (0.2 - 0.9)) / 2.0)


def test_family_pair_counts_uses_action_catalog_labels():
    counts = family_pair_counts(
        np.array([33, 34, 61], dtype=np.int64),
        np.array([34, 33, 62], dtype=np.int64),
    )

    assert counts["discard_over_discard"] == 2
    assert counts["pon_over_pon"] == 1


def test_weighted_helpers_fall_back_to_unweighted_when_weights_are_zero():
    values = np.array([0.0, 1.0], dtype=np.float32)
    weights = np.zeros(2, dtype=np.float32)

    assert weighted_rate(values, weights) == pytest.approx(0.5)
    assert weighted_mean(values, weights) == pytest.approx(0.5)


def test_reward_gap_buckets_are_stable_for_empty_bucket():
    margins = np.array([1.0], dtype=np.float32)
    gaps = np.array([0.75], dtype=np.float32)

    buckets = reward_gap_buckets(margins, gaps)

    assert buckets["0.50+"]["preferred_rate"] == pytest.approx(1.0)
    assert buckets["0.00-0.05"]["count"] == 0
    assert math.isfinite(buckets["0.00-0.05"]["mean_margin"])


def test_branch_cf_diagnostics_reports_high_gap_q_failures():
    preferred = np.array([5, 6, 7], dtype=np.int64)
    avoided = np.array([8, 9, 10], dtype=np.int64)
    reward_gaps = np.array([0.10, 0.75, 0.90], dtype=np.float32)
    policy_margins = np.array([1.0, -0.5, 0.2], dtype=np.float32)
    q_margins = np.array([0.2, -0.1, -0.3], dtype=np.float32)
    scalars = np.zeros((3, 58), dtype=np.float32)
    scalars[:, 47] = np.array([0.8, 0.1, 0.2], dtype=np.float32)

    report = branch_cf_diagnostics(
        preferred,
        avoided,
        reward_gaps,
        policy_margins,
        q_margins,
        scalars,
        high_gap_threshold=0.5,
        max_examples=1,
    )

    assert report["segments"]["high_gap"]["count"] == 2
    assert report["segments"]["q_misrank"]["count"] == 2
    assert report["segments"]["high_gap_q_misrank"]["count"] == 2
    assert report["scalar_segments"]["high_gap_q_misrank"]["large_loss_margin"]["mean"] == pytest.approx(0.15)
    assert report["examples"]["highest_gap_q_misrank"][0]["reward_gap"] == pytest.approx(0.90)
    assert report["examples"]["highest_gap_q_misrank"][0]["preferred_action_label"] == "discard 3m"


def test_guard_choice_diagnostics_counts_rescues_and_harms():
    preferred = np.array([5, 6, 7, 8], dtype=np.int64)
    avoided = np.array([9, 10, 11, 12], dtype=np.int64)
    gaps = np.array([0.5, 0.2, 0.3, 0.1], dtype=np.float32)
    anchor = np.array([9, 6, 7, 50], dtype=np.int64)
    guarded = np.array([5, 10, 13, 50], dtype=np.int64)
    sources = np.array(["risk_guard", "risk_guard", "risk_guard", "anchor"], dtype=object)

    report = guard_choice_diagnostics(preferred, avoided, gaps, anchor, guarded, sources)

    assert report["changed_count"] == 3
    assert report["rescue_count"] == 1
    assert report["harm_count"] == 1
    assert report["changed_to_unlabeled_count"] == 1
    assert report["known_changed_count"] == 2
    assert report["known_reward_delta_sum"] == pytest.approx(0.3)
    assert report["top_rescues"][0]["preferred_action_label"] == "discard 1m"


def test_oracle_preferred_filter_diagnostics_reports_policy_gap_upper_bound():
    preferred = np.array([5, 6, 7], dtype=np.int64)
    avoided = np.array([9, 10, 11], dtype=np.int64)
    gaps = np.array([0.5, 0.2, 0.4], dtype=np.float32)
    anchor = np.array([9, 10, 30], dtype=np.int64)
    logits = np.zeros((3, 204), dtype=np.float32)
    risks = np.full((3, 204), 0.2, dtype=np.float32)

    logits[0, 9] = 5.0
    logits[0, 5] = 4.0
    risks[0, 9] = 0.8
    risks[0, 5] = 0.3

    logits[1, 10] = 8.0
    logits[1, 6] = 2.0
    risks[1, 10] = 0.9
    risks[1, 6] = 0.3

    logits[2, 30] = 3.0
    logits[2, 7] = 2.0
    risks[2, 30] = 0.8
    risks[2, 7] = 0.3

    report = oracle_preferred_filter_diagnostics(
        preferred,
        avoided,
        gaps,
        anchor,
        logits,
        risks,
        anchor_risk_threshold=0.6,
        candidate_risk_threshold=0.45,
        min_risk_reduction=0.2,
        max_policy_logit_gaps=[1.5, None],
    )

    assert report["anchor_avoided_count"] == 2
    assert report["preferred_base_filters_pass_count"] == 2
    assert report["by_max_policy_logit_gap"]["1.5"]["pass_count"] == 1
    assert report["by_max_policy_logit_gap"]["1.5"]["known_rescue_reward_delta_sum"] == pytest.approx(0.5)
    assert report["by_max_policy_logit_gap"]["none"]["pass_count"] == 2
    assert report["by_max_policy_logit_gap"]["none"]["known_rescue_reward_delta_sum"] == pytest.approx(0.7)


def test_proposal_rerank_diagnostics_reports_topk_rescues():
    preferred = np.array([1, 2, 3], dtype=np.int64)
    avoided = np.array([0, 0, 0], dtype=np.int64)
    gaps = np.array([0.5, 0.25, 0.75], dtype=np.float32)
    mask = np.ones((3, 5), dtype=np.int8)
    policy = np.array(
        [
            [5.0, 4.0, 3.0, 2.0, 1.0],
            [5.0, 1.0, 4.0, 3.0, 2.0],
            [5.0, 4.0, 2.0, 3.0, 1.0],
        ],
        dtype=np.float32,
    )
    q_values = np.array(
        [
            [1.0, 5.0, 0.0, 0.0, 0.0],
            [5.0, 0.0, 4.0, 0.0, 0.0],
            [3.0, 0.0, 0.0, 4.0, 0.0],
        ],
        dtype=np.float32,
    )
    risks = np.array(
        [
            [0.9, 0.1, 0.5, 0.5, 0.5],
            [0.1, 0.5, 0.2, 0.5, 0.5],
            [0.9, 0.5, 0.5, 0.2, 0.5],
        ],
        dtype=np.float32,
    )

    report = proposal_rerank_diagnostics(
        preferred,
        avoided,
        gaps,
        policy,
        q_values,
        mask,
        risk_scores=risks,
        top_ks=(2, 3),
    )

    assert report["policy_rank"]["by_top_k"]["2"]["preferred_count"] == 2
    assert report["policy_rank"]["by_top_k"]["3"]["preferred_count"] == 3
    assert report["q_rank"]["preferred_better_than_avoided_rate"] == pytest.approx(2.0 / 3.0)
    top2 = report["rerank_by_policy_top_k"]["2"]
    assert top2["q_rerank"]["rescue_count"] == 1
    assert top2["q_rerank"]["known_reward_delta_sum"] == pytest.approx(0.5)
    top3 = report["rerank_by_policy_top_k"]["3"]
    assert top3["q_rerank"]["rescue_count"] == 2
    assert top3["risk_rerank"]["rescue_count"] == 2
