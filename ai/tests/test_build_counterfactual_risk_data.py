from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.build_counterfactual_risk_data import (
    build_counterfactual_risk_arrays,
    write_counterfactual_shard,
)
from fh_mahjong_ai.storage import read_transition_arrays


def test_build_counterfactual_risk_arrays_from_tensor_trace(tmp_path: Path) -> None:
    report_path = tmp_path / "paired.json"
    planes = np.zeros((2, 3, 1), dtype=np.float32).tolist()
    scalars = np.linspace(0, 1, 4, dtype=np.float32).tolist()
    action_mask = np.ones(8, dtype=np.int8).tolist()
    report_path.write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_reward": -1.25,
                        "reward_delta": -1.5,
                        "anchor_outcome": {"discarder_seat": -1},
                        "candidate_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 0,
                                "action_label": "pass",
                                "action_family": "pass",
                                "observation": {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}},
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                                "action_family": "discard",
                                "observation": {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}},
                            },
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arrays, metadata = build_counterfactual_risk_arrays(report_path, large_loss_threshold=-1.0)

    assert metadata["rows"] == 1
    assert metadata["positive_terminal_rows"] == 1
    assert arrays["planes"].shape == (1, 2, 3, 1)
    assert arrays["scalars"].shape == (1, 4)
    assert arrays["action_ids"].tolist() == [5]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [0]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [5]
    assert arrays["pairwise_reward_delta_targets"].tolist() == [1.5]
    assert arrays["terminal_rewards"].tolist() == [[0.0, 0.0, -1.25, 0.0]]

    output_dir = tmp_path / "out"
    write_counterfactual_shard(output_dir, arrays, metadata)
    loaded = read_transition_arrays(
        output_dir,
        keys=(
            "seats",
            "planes",
            "scalars",
            "action_mask",
            "action_ids",
            "terminal_rewards",
            "episode_index",
            "next_planes",
            "next_scalars",
            "next_action_mask",
            "rewards",
            "terminated",
            "truncated",
        ),
        optional_keys=("pairwise_preferred_action_ids", "pairwise_avoided_action_ids", "pairwise_weights"),
    )

    assert loaded["action_ids"].tolist() == [5]
    assert loaded["pairwise_weights"].tolist() == [1.0]
    assert loaded["next_planes"].shape == (1, 2, 3, 1)
    assert loaded["rewards"].tolist() == [[0.0, 0.0, 0.0, 0.0]]
    assert loaded["terminated"].tolist() == [False]


def test_build_counterfactual_risk_arrays_uses_report_labels(tmp_path: Path) -> None:
    report_path = tmp_path / "paired.json"
    planes = np.zeros((2, 3, 1), dtype=np.float32).tolist()
    scalars = np.linspace(0, 1, 4, dtype=np.float32).tolist()
    action_mask = np.ones(8, dtype=np.int8).tolist()
    report_path.write_text(
        json.dumps(
            {
                "left_label": "anchor",
                "right_label": "candidate_t054_w075",
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_t054_w075_reward": -1.25,
                        "reward_delta": -1.5,
                        "anchor_outcome": {"discarder_seat": -1},
                        "candidate_t054_w075_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 0,
                                "action_label": "pass",
                                "action_family": "pass",
                                "observation": {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}},
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                                "action_family": "discard",
                                "observation": {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}},
                            },
                        },
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arrays, metadata = build_counterfactual_risk_arrays(report_path, large_loss_threshold=-1.0)

    assert metadata["left_label"] == "anchor"
    assert metadata["right_label"] == "candidate_t054_w075"
    assert arrays["action_ids"].tolist() == [5]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [0]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [5]


def test_build_counterfactual_risk_arrays_uses_later_divergences(tmp_path: Path) -> None:
    report_path = tmp_path / "paired.json"
    planes = np.zeros((2, 3, 1), dtype=np.float32).tolist()
    scalars = np.linspace(0, 1, 4, dtype=np.float32).tolist()
    action_mask = np.ones(8, dtype=np.int8).tolist()
    observation = {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}}
    report_path.write_text(
        json.dumps(
            {
                "left_label": "anchor",
                "right_label": "candidate",
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "anchor_reward": 0.25,
                        "candidate_reward": -1.25,
                        "reward_delta": -1.5,
                        "anchor_outcome": {"discarder_seat": -1},
                        "candidate_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 0,
                                "action_label": "pass",
                                "action_family": "pass",
                                "observation": observation,
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                                "action_family": "discard",
                                "observation": observation,
                            },
                        },
                        "divergences": [
                            {
                                "divergence_index": 3,
                                "left": {
                                    "decision_index": 77,
                                    "action_id": 0,
                                    "action_label": "pass",
                                    "action_family": "pass",
                                    "observation": observation,
                                },
                                "right": {
                                    "decision_index": 77,
                                    "action_id": 5,
                                    "action_label": "discard 1m",
                                    "action_family": "discard",
                                    "observation": observation,
                                },
                            },
                            {
                                "divergence_index": 9,
                                "left": {
                                    "decision_index": 91,
                                    "action_id": 2,
                                    "action_label": "discard 2m",
                                    "action_family": "discard",
                                    "observation": observation,
                                },
                                "right": {
                                    "decision_index": 91,
                                    "action_id": 7,
                                    "action_label": "discard 7m",
                                    "action_family": "discard",
                                    "observation": observation,
                                },
                            },
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arrays, metadata = build_counterfactual_risk_arrays(
        report_path,
        large_loss_threshold=-1.0,
        avoided_action_family="discard",
        divergence_source="later",
    )

    assert metadata["divergence_source"] == "later"
    assert metadata["rows"] == 1
    assert arrays["action_ids"].tolist() == [7]
    assert arrays["decision_indices"].tolist() == [91]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [2]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [7]


def test_build_counterfactual_risk_arrays_filters_preferred_policy(tmp_path: Path) -> None:
    report_path = tmp_path / "paired.json"
    planes = np.zeros((2, 3, 1), dtype=np.float32).tolist()
    scalars = np.linspace(0, 1, 4, dtype=np.float32).tolist()
    action_mask = np.ones(8, dtype=np.int8).tolist()
    observation = {"arrays": {"planes": planes, "scalars": scalars, "action_mask": action_mask}}
    report_path.write_text(
        json.dumps(
            {
                "left_label": "promoted_anchor",
                "right_label": "candidate",
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 2,
                        "promoted_anchor_reward": 0.25,
                        "candidate_reward": -1.25,
                        "promoted_anchor_outcome": {"discarder_seat": -1},
                        "candidate_outcome": {"discarder_seat": 2},
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 77,
                                "action_id": 0,
                                "action_label": "pass",
                                "action_family": "pass",
                                "observation": observation,
                            },
                            "right": {
                                "decision_index": 77,
                                "action_id": 5,
                                "action_label": "discard 1m",
                                "action_family": "discard",
                                "observation": observation,
                            },
                        },
                    },
                    {
                        "seed": 101,
                        "seat": 2,
                        "promoted_anchor_reward": -1.25,
                        "candidate_reward": 0.25,
                        "promoted_anchor_outcome": {"discarder_seat": 2},
                        "candidate_outcome": {"discarder_seat": -1},
                        "first_divergence_index": 4,
                        "first_divergence": {
                            "left": {
                                "decision_index": 78,
                                "action_id": 6,
                                "action_label": "discard 2m",
                                "action_family": "discard",
                                "observation": observation,
                            },
                            "right": {
                                "decision_index": 78,
                                "action_id": 1,
                                "action_label": "pass",
                                "action_family": "pass",
                                "observation": observation,
                            },
                        },
                    },
                    {
                        "seed": 102,
                        "seat": 2,
                        "promoted_anchor_reward": 0.15,
                        "candidate_reward": -1.20,
                        "first_divergence_index": 3,
                        "first_divergence": {
                            "left": {
                                "decision_index": 79,
                                "action_id": 2,
                                "action_label": "discard 1m",
                                "action_family": "discard",
                                "observation": observation,
                            },
                            "right": {
                                "decision_index": 79,
                                "action_id": 7,
                                "action_label": "discard 2m",
                                "action_family": "discard",
                                "observation": observation,
                            },
                        },
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arrays, metadata = build_counterfactual_risk_arrays(
        report_path,
        large_loss_threshold=-1.0,
        preferred_policy="promoted_anchor",
    )

    assert metadata["preferred_policy_filter"] == "promoted_anchor"
    assert metadata["skipped_preferred_policy"] == 1
    assert metadata["rows"] == 2
    assert arrays["action_ids"].tolist() == [5, 7]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [0, 2]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [5, 7]

    arrays, metadata = build_counterfactual_risk_arrays(
        report_path,
        large_loss_threshold=-1.0,
        preferred_policy="promoted_anchor",
        preferred_action_family="discard",
        avoided_action_family="discard",
    )

    assert metadata["preferred_action_family_filter"] == "discard"
    assert metadata["avoided_action_family_filter"] == "discard"
    assert metadata["skipped_preferred_action_family"] == 1
    assert metadata["skipped_avoided_action_family"] == 0
    assert metadata["rows"] == 1
    assert arrays["action_ids"].tolist() == [7]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [2]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [7]

    arrays, metadata = build_counterfactual_risk_arrays(
        report_path,
        large_loss_threshold=-1.0,
        preferred_policy="promoted_anchor",
        preferred_action_family="discard",
        avoided_action_family="discard",
        training_target_policy="preferred",
    )

    assert metadata["training_target_policy"] == "preferred"
    assert arrays["action_ids"].tolist() == [2]
    assert arrays["pairwise_preferred_action_ids"].tolist() == [2]
    assert arrays["pairwise_avoided_action_ids"].tolist() == [7]
    assert arrays["terminal_rewards"].tolist() == [[0.0, 0.0, 0.15000000596046448, 0.0]]
