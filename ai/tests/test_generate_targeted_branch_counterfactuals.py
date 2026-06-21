from __future__ import annotations

import numpy as np

from fh_mahjong_ai.scripts.generate_targeted_branch_counterfactuals import (
    TargetCase,
    group_targets_by_seed_seat,
    load_target_cases,
    select_target_branch_actions,
)
from fh_mahjong_ai.types import Observation


def test_load_target_cases_from_action_ev_false_positive_report() -> None:
    report = {
        "worst_false_positive_cases": [
            {
                "seed": 534003,
                "seat": 0,
                "decision_index": 366,
                "actual_delta": -2.221,
                "predicted_delta": 0.008,
                "left_action_label": "discard 4m",
                "right_action_label": "discard 5p",
            }
        ]
    }

    cases = load_target_cases(report, case_source="worst_false_positive_cases")

    assert cases == [
        TargetCase(
            seed=534003,
            seat=0,
            decision_index=366,
            source_index=0,
            actual_delta=-2.221,
            predicted_delta=0.008,
            left_action_label="discard 4m",
            right_action_label="discard 5p",
        )
    ]


def test_load_target_cases_from_paired_trace_worst_reward_delta_summary() -> None:
    report = {
        "summary": {
            "worst_reward_delta_cases": [
                {
                    "seed": 534001,
                    "seat": 2,
                    "reward_delta": -0.75,
                    "decision_index": 44,
                    "anchor_action_id": 7,
                    "candidate_action_id": 8,
                    "anchor_action_label": "discard 7m",
                    "candidate_action_label": "discard 8m",
                }
            ]
        }
    }

    cases = load_target_cases(report, case_source="worst_reward_delta_cases")

    assert len(cases) == 1
    assert cases[0].seed == 534001
    assert cases[0].seat == 2
    assert cases[0].decision_index == 44
    assert cases[0].actual_delta == -0.75
    assert cases[0].left_action_id == 7
    assert cases[0].right_action_id == 8


def test_select_target_branch_actions_keeps_required_actions_when_sampling() -> None:
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros((58,), dtype=np.float32),
        action_mask=mask_with(1, 2, 3, 80),
    )
    target = TargetCase(
        seed=1,
        seat=0,
        decision_index=9,
        source_index=0,
        left_action_id=1,
        right_action_id=3,
    )

    selected = select_target_branch_actions(
        observation,
        target,
        action_families=("discard",),
        max_branch_actions=1,
        rng=np.random.default_rng(0),
    )

    assert 1 in selected
    assert 3 in selected
    assert 80 not in selected


def test_group_targets_by_seed_seat_sorts_decisions() -> None:
    cases = [
        TargetCase(seed=3, seat=1, decision_index=20, source_index=0),
        TargetCase(seed=3, seat=1, decision_index=5, source_index=1),
        TargetCase(seed=2, seat=0, decision_index=8, source_index=2),
    ]

    grouped = group_targets_by_seed_seat(cases)

    assert list(grouped) == [(2, 0), (3, 1)]
    assert [case.decision_index for case in grouped[(3, 1)]] == [5, 20]


def mask_with(*action_ids: int) -> np.ndarray:
    mask = np.zeros((204,), dtype=np.int8)
    for action_id in action_ids:
        mask[action_id] = 1
    return mask
