from __future__ import annotations

import pytest
import numpy as np
from torch import nn

from fh_mahjong_ai.paired_trace import (
    EpisodeTrace,
    StepTrace,
    compare_policy_traces,
    counterfactual_label_from_pair,
    deduplicate_trace_pairs,
    first_divergence_index,
    summarize_observation,
    summarize_trace_pairs,
)
from fh_mahjong_ai.types import Observation


def test_first_divergence_index_detects_action_change() -> None:
    assert first_divergence_index([5, 6, 7], [5, 8, 7]) == 1


def test_first_divergence_index_detects_length_change() -> None:
    assert first_divergence_index([5, 6], [5, 6, 7]) == 2
    assert first_divergence_index([5, 6], [5, 6]) is None


def test_deduplicate_trace_pairs_keeps_first_seed_seat_pair() -> None:
    pairs = [
        {"seed": 1, "seat": 0, "reward_delta": 0.1},
        {"seed": 1, "seat": 0, "reward_delta": 0.2},
        {"seed": 1, "seat": 1, "reward_delta": 0.3},
    ]

    deduped = deduplicate_trace_pairs(pairs)

    assert [pair["reward_delta"] for pair in deduped] == [0.1, 0.3]


def test_compare_policy_traces_skips_existing_pairs(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyModel(nn.Module):
        def __init__(self, action_id: int, reward_offset: float) -> None:
            super().__init__()
            self.action_id = action_id
            self.reward_offset = reward_offset

    calls: list[tuple[int, int, int]] = []

    def fake_run_policy_trace(model: DummyModel, seed: int, learning_seat: int, **kwargs: object) -> EpisodeTrace:
        del kwargs
        calls.append((int(model.action_id), int(seed), int(learning_seat)))
        step = StepTrace(
            index=0,
            decision_index=10,
            seat=int(learning_seat),
            action_id=int(model.action_id),
            action_family="discard",
            action_label=f"action {model.action_id}",
            value=None,
            observation={"scalars": {}},
        )
        return EpisodeTrace(
            seed=int(seed),
            seat=int(learning_seat),
            reward=float(seed) + float(model.reward_offset),
            terminated=True,
            truncated=False,
            steps=(step,),
            outcome=None,
        )

    monkeypatch.setattr("fh_mahjong_ai.paired_trace.run_policy_trace", fake_run_policy_trace)
    existing_pair = {
        "seed": 1,
        "seat": 0,
        "left_reward": 0.0,
        "right_reward": 1.0,
        "reward_delta": 1.0,
        "left_steps": 1,
        "right_steps": 1,
        "left_outcome": None,
        "right_outcome": None,
        "first_divergence_index": None,
        "first_divergence": None,
    }
    completed: list[tuple[int, int, int, int]] = []

    report = compare_policy_traces(
        left_model=DummyModel(action_id=4, reward_offset=0.0),
        right_model=DummyModel(action_id=5, reward_offset=0.5),
        seeds=[1, 2],
        seats=[0],
        existing_pairs=[existing_pair],
        progress_callback=lambda done, total, seed, seat: completed.append((done, total, seed, seat)),
    )

    assert calls == [(4, 2, 0), (5, 2, 0)]
    assert completed == [(2, 2, 2, 0)]
    assert report["summary"]["episodes"] == 2
    assert [pair["seed"] for pair in report["pairs"]] == [1, 2]


def test_summarize_observation_reports_legal_family_rates_and_scalars() -> None:
    mask = np.zeros(204, dtype=np.int8)
    mask[0] = 1
    mask[5] = 1
    mask[47] = 1
    scalars = np.zeros(50, dtype=np.float32)
    scalars[25] = 0.5
    scalars[47] = 0.75
    scalars[48] = 0.25
    observation = Observation(
        seat=2,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=scalars,
        action_mask=mask,
        metadata={"decision_index": 9, "phase": 2, "active_player": 2},
    )

    summary = summarize_observation(observation)

    assert summary["decision_index"] == 9
    assert summary["legal_action_count"] == 3
    assert summary["legal_action_family_rates"] == {
        "discard": 1 / 3,
        "pass": 1 / 3,
        "pon": 1 / 3,
    }
    assert summary["scalars"]["overall_shanten"] == 0.5
    assert summary["scalars"]["large_loss_margin"] == 0.75
    assert summary["scalars"]["self_bust_margin"] == 0.25


def test_summarize_trace_pairs_handles_terminal_length_divergence() -> None:
    report = summarize_trace_pairs(
        [
            {
                "left_reward": 0.0,
                "right_reward": 1.0,
                "reward_delta": 1.0,
                "first_divergence_index": 2,
                "first_divergence": {
                    "left": {
                        "action_family": "discard",
                        "action_label": "discard 1m",
                        "observation": {"scalars": {"overall_shanten": 0.1}},
                    },
                    "right": None,
                },
            }
        ]
    )

    assert report["summary"]["divergence_action_family_pairs"] == {"discard->missing": 1}


def test_summarize_trace_pairs_reports_high_risk_cases() -> None:
    report = summarize_trace_pairs(
        [
            {
                "seed": 534005,
                "seat": 0,
                "anchor_reward": -0.9,
                "candidate_reward": -1.4,
                "reward_delta": -0.5,
                "first_divergence_index": 12,
                "first_divergence": {
                    "left": {"action_id": 0, "action_label": "pass", "action_family": "pass"},
                    "right": {
                        "action_id": 47,
                        "action_label": "pon 1m",
                        "action_family": "pon",
                        "decision_index": 173,
                        "observation": {"scalars": {"rank_score": 0.5}},
                    },
                },
            }
        ],
        left_label="anchor",
        right_label="candidate",
        large_loss_threshold=-1.0,
    )

    summary = report["summary"]
    assert len(summary["candidate_large_loss_cases"]) == 1
    assert len(summary["new_candidate_large_loss_cases"]) == 1
    assert summary["candidate_large_loss_cases"][0]["candidate_action_label"] == "pon 1m"
    assert summary["candidate_large_loss_cases"][0]["decision_index"] == 173
    assert summary["worst_reward_delta_cases"][0]["seed"] == 534005


def test_summarize_trace_pairs_reports_counterfactual_supervision() -> None:
    pair = {
        "seed": 534005,
        "seat": 0,
        "anchor_reward": 0.1,
        "candidate_reward": -1.4,
        "reward_delta": -1.5,
        "anchor_outcome": {"discarder_seat": -1},
        "candidate_outcome": {"discarder_seat": 0},
        "first_divergence_index": 12,
        "first_divergence": {
            "left": {
                "action_id": 0,
                "action_label": "pass",
                "action_family": "pass",
                "decision_index": 173,
                "observation": {"scalars": {"rank_score": 0.5}},
            },
            "right": {
                "action_id": 5,
                "action_label": "discard 1m",
                "action_family": "discard",
                "decision_index": 173,
                "observation": {"scalars": {"rank_score": 0.5}},
            },
        },
    }

    label = counterfactual_label_from_pair(
        pair,
        left_label="anchor",
        right_label="candidate",
        large_loss_threshold=-1.0,
    )
    report = summarize_trace_pairs(
        [pair],
        left_label="anchor",
        right_label="candidate",
        large_loss_threshold=-1.0,
    )

    assert label is not None
    assert label["preferred_action_family"] == "pass"
    assert label["avoided_action_family"] == "discard"
    assert label["reward_gap"] == pytest.approx(1.5)
    assert label["tags"] == ["avoided_deal_in", "avoided_large_loss", "new_deal_in", "new_large_loss", "worse_reward"]
    supervision = report["summary"]["counterfactual_supervision"]
    assert supervision["labeled_pairs"] == 1
    assert supervision["high_risk_labeled_pairs"] == 1
    assert supervision["avoided_action_family_counts"] == {"discard": 1}
    assert supervision["high_risk_avoided_action_family_counts"] == {"discard": 1}
    assert supervision["tag_counts"]["new_deal_in"] == 1
