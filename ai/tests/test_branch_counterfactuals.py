from __future__ import annotations

import numpy as np

from fh_mahjong_ai.branch_counterfactuals import (
    best_worst_branch_label,
    branch_pair_rows_to_arrays,
    legal_discard_actions,
)
from fh_mahjong_ai.types import BranchResult, Observation


def test_best_worst_branch_label_uses_seat_reward_gap() -> None:
    observation = Observation(
        seat=2,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros((58,), dtype=np.float32),
        action_mask=mask_with(5, 6, 80),
        metadata={"decision_index": 17},
    )

    label = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=5, rewards=np.asarray([0.0, 0.0, -0.7, 0.0], dtype=np.float32), terminated=True, decisions=11),
            BranchResult(action_id=6, rewards=np.asarray([0.0, 0.0, 0.2, 0.0], dtype=np.float32), terminated=True, decisions=9),
            BranchResult(action_id=80, rewards=np.asarray([0.0, 0.0, 1.0, 0.0], dtype=np.float32), terminated=True, decisions=3),
        ],
        min_reward_gap=0.5,
    )

    assert label is not None
    assert label.preferred_action_id == 6
    assert label.avoided_action_id == 5
    assert np.isclose(label.reward_gap, 0.9)
    assert legal_discard_actions(observation) == [5, 6]


def test_branch_pair_rows_to_arrays_writes_pairwise_schema() -> None:
    observation = Observation(
        seat=1,
        planes=np.ones((39, 42, 1), dtype=np.float32),
        scalars=np.ones((58,), dtype=np.float32),
        action_mask=mask_with(8, 9),
        metadata={"decision_index": 4},
    )
    label = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=8, rewards=np.asarray([0.0, -0.4, 0.0, 0.0], dtype=np.float32), terminated=True, decisions=5),
            BranchResult(action_id=9, rewards=np.asarray([0.0, 0.1, 0.0, 0.0], dtype=np.float32), terminated=True, decisions=6),
        ],
    )
    assert label is not None

    arrays = branch_pair_rows_to_arrays([(observation, label, {"episode_index": 123})])

    assert arrays["planes"].shape == (1, 39, 42, 1)
    assert arrays["pairwise_preferred_action_ids"].tolist() == [9]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [8]
    assert arrays["pairwise_weights"].tolist() == [1.0]
    assert np.isclose(arrays["pairwise_reward_delta_targets"][0], 0.5)
    assert arrays["episode_index"].tolist() == [123]
    assert arrays["decision_indices"].tolist() == [4]
    assert np.isclose(arrays["terminal_rewards"][0, 1], -0.4)
    assert arrays["branch_greedy_action_ids"].tolist() == [-1]
    assert arrays["branch_sampled_action_ids"].tolist() == [-1]
    assert arrays["branch_sampled_ranks"].tolist() == [-1]
    assert arrays["branch_left_action_ids"].tolist() == [-1]
    assert arrays["branch_right_action_ids"].tolist() == [-1]


def test_best_worst_branch_label_can_include_all_action_families() -> None:
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros((58,), dtype=np.float32),
        action_mask=mask_with(0, 5, 80),
        metadata={"decision_index": 9},
    )

    discard_only = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=0, rewards=np.asarray([0.5, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=5, rewards=np.asarray([-0.1, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=80, rewards=np.asarray([0.8, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
        ],
    )
    all_families = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=0, rewards=np.asarray([0.5, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=5, rewards=np.asarray([-0.1, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=80, rewards=np.asarray([0.8, 0.0, 0.0, 0.0], dtype=np.float32), terminated=True),
        ],
        action_families=None,
    )

    assert discard_only is None
    assert all_families is not None
    assert all_families.preferred_action_id == 80
    assert all_families.avoided_action_id == 5


def test_branch_pair_rows_to_arrays_records_greedy_sampled_metadata() -> None:
    observation = Observation(
        seat=1,
        planes=np.ones((39, 42, 1), dtype=np.float32),
        scalars=np.ones((58,), dtype=np.float32),
        action_mask=mask_with(8, 9),
    )
    label = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=8, rewards=np.asarray([0.0, -0.4, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=9, rewards=np.asarray([0.0, 0.1, 0.0, 0.0], dtype=np.float32), terminated=True),
        ],
    )
    assert label is not None

    arrays = branch_pair_rows_to_arrays(
        [(observation, label, {"episode_index": 123, "greedy_action_id": 8, "sampled_action_id": 9, "sampled_rank": 2})]
    )

    assert arrays["branch_greedy_action_ids"].tolist() == [8]
    assert arrays["branch_sampled_action_ids"].tolist() == [9]
    assert arrays["branch_sampled_ranks"].tolist() == [2]


def test_branch_pair_rows_to_arrays_records_targeted_trace_metadata() -> None:
    observation = Observation(
        seat=1,
        planes=np.ones((39, 42, 1), dtype=np.float32),
        scalars=np.ones((58,), dtype=np.float32),
        action_mask=mask_with(8, 9),
    )
    label = best_worst_branch_label(
        observation,
        [
            BranchResult(action_id=8, rewards=np.asarray([0.0, -0.4, 0.0, 0.0], dtype=np.float32), terminated=True),
            BranchResult(action_id=9, rewards=np.asarray([0.0, 0.1, 0.0, 0.0], dtype=np.float32), terminated=True),
        ],
    )
    assert label is not None

    arrays = branch_pair_rows_to_arrays(
        [
            (
                observation,
                label,
                {
                    "episode_index": 123,
                    "left_action_id": 8,
                    "right_action_id": 9,
                    "target_actual_delta": -0.5,
                    "target_predicted_delta": 0.25,
                },
            )
        ]
    )

    assert arrays["branch_left_action_ids"].tolist() == [8]
    assert arrays["branch_right_action_ids"].tolist() == [9]
    np.testing.assert_allclose(arrays["branch_target_actual_deltas"], np.asarray([-0.5], dtype=np.float32))
    np.testing.assert_allclose(arrays["branch_target_predicted_deltas"], np.asarray([0.25], dtype=np.float32))


def mask_with(*action_ids: int) -> np.ndarray:
    mask = np.zeros((204,), dtype=np.int8)
    for action_id in action_ids:
        mask[action_id] = 1
    return mask
