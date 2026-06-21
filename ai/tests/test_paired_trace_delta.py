from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from fh_mahjong_ai.paired_trace_delta import (
    PairwiseDeltaNet,
    PairwiseSequenceDeltaNet,
    build_pairwise_delta_arrays,
    guard_preflight,
    predict_pairwise_delta,
)
from fh_mahjong_ai.scripts.train_pairwise_delta import sample_batch_indices


def _step(action_id: int) -> dict:
    return {
        "action_id": action_id,
        "action_label": f"discard {action_id}",
        "action_family": "discard",
        "decision_index": 17,
        "observation": {
            "arrays": {
                "planes": np.zeros((39, 42, 1), dtype=np.float32).tolist(),
                "scalars": np.full(58, 0.25, dtype=np.float32).tolist(),
                "action_mask": np.ones(204, dtype=np.int8).tolist(),
            }
        },
    }


def _sequence_step(action_id: int, family: str) -> dict:
    return {
        "action_id": action_id,
        "action_family": family,
        "features": {
            "trace_sequence_age_16": 1.0,
            f"trace_sequence_{family}": 1.0,
            "trace_sequence_overall_shanten": 0.5,
        },
    }


def test_build_pairwise_delta_arrays_uses_candidate_minus_anchor(tmp_path: Path) -> None:
    report = {
        "left_label": "anchor",
        "right_label": "candidate",
        "pairs": [
            {
                "seed": 7,
                "seat": 1,
                "anchor_reward": -0.4,
                "candidate_reward": 0.2,
                "first_divergence": {"left": _step(8), "right": _step(9)},
                "pre_divergence_context": {"trace_context_available": 1.0},
                "pre_divergence_sequence": [_sequence_step(7, "discard")],
            },
            {
                "seed": 8,
                "seat": 2,
                "anchor_reward": 0.1,
                "candidate_reward": 0.1,
                "first_divergence": {"left": _step(10), "right": _step(11)},
                "pre_divergence_context": {"trace_context_available": 1.0},
            },
        ],
    }
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    arrays, metadata = build_pairwise_delta_arrays([path], min_abs_delta=0.01)

    assert metadata["stats"]["rows"] == 1
    assert arrays["episode_index"].tolist() == [7]
    assert arrays["seats"].tolist() == [1]
    assert arrays["source_ids"].tolist() == [0]
    assert arrays["left_action_ids"].tolist() == [8]
    assert arrays["right_action_ids"].tolist() == [9]
    np.testing.assert_allclose(arrays["targets"], np.asarray([0.6], dtype=np.float32))
    assert arrays["scalars"].shape == (1, 81)
    assert arrays["scalars"][0, 58] == 1.0
    assert arrays["sequence_features"].shape[1] == 16
    assert arrays["sequence_features"][0, -1, 0] == 1.0


def test_pairwise_delta_model_predicts_expected_shape() -> None:
    model = PairwiseDeltaNet(scalar_features=81)
    arrays = {
        "scalars": np.zeros((3, 81), dtype=np.float32),
        "left_action_ids": np.asarray([1, 2, 3], dtype=np.int64),
        "right_action_ids": np.asarray([4, 5, 6], dtype=np.int64),
    }

    predictions = predict_pairwise_delta(model, arrays)

    assert predictions.shape == (3,)
    assert np.all(np.isfinite(predictions))


def test_pairwise_sequence_delta_model_predicts_expected_shape() -> None:
    model = PairwiseSequenceDeltaNet(scalar_features=81)
    arrays = {
        "scalars": np.zeros((3, 81), dtype=np.float32),
        "sequence_features": np.zeros((3, 16, 17), dtype=np.float32),
        "left_action_ids": np.asarray([1, 2, 3], dtype=np.int64),
        "right_action_ids": np.asarray([4, 5, 6], dtype=np.int64),
    }

    predictions = predict_pairwise_delta(model, arrays)

    assert predictions.shape == (3,)
    assert np.all(np.isfinite(predictions))


def test_guard_preflight_uses_predicted_delta_to_allow_candidate() -> None:
    predictions = np.asarray([0.5, -0.1, 0.2], dtype=np.float32)
    targets = np.asarray([0.4, -0.3, -0.2], dtype=np.float32)

    result = guard_preflight(predictions, targets, margins=[0.0])

    assert result["0.0000"]["allowed_count"] == 2
    assert result["0.0000"]["harmful_allowed_count"] == 1
    assert result["0.0000"]["actual_allowed_delta_sum"] == pytest.approx(0.2)


def test_sample_batch_indices_can_balance_sources() -> None:
    rng = np.random.default_rng(123)
    train_indices = np.arange(12, dtype=np.int64)
    source_ids = np.asarray([0] * 10 + [1] * 2, dtype=np.int16)

    batch = sample_batch_indices(
        rng,
        train_indices,
        source_ids,
        batch_size=6,
        source_balanced=True,
    )

    sampled_sources = source_ids[batch].tolist()
    assert sampled_sources.count(0) == 3
    assert sampled_sources.count(1) == 3
