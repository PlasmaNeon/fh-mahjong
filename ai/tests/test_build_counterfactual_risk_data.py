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
        keys=("seats", "planes", "scalars", "action_mask", "action_ids", "terminal_rewards", "episode_index"),
        optional_keys=("pairwise_preferred_action_ids", "pairwise_avoided_action_ids", "pairwise_weights"),
    )

    assert loaded["action_ids"].tolist() == [5]
    assert loaded["pairwise_weights"].tolist() == [1.0]


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
