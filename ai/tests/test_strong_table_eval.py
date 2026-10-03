"""Strong-table evaluation: the three other seats played by a checkpoint policy
instead of the Go heuristic bots (``opponent_policy`` / ``--opponent-checkpoint``)."""

import os

import pytest
import torch

from conftest import small_model_config
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.evaluate import evaluate_duplicate_seats_policy, evaluate_policy_online
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.scripts.compare_reports import paired_comparison

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)

OPPONENTS = {"kind": "checkpoint", "checkpoint": "opp.pt", "checkpoint_sha256": "b" * 64,
             "event_window": 0, "decision": "greedy"}


def _model(seed: int) -> PolicyValueNet:
    torch.manual_seed(seed)
    return PolicyValueNet(EnvConfig(), small_model_config()).eval()


class _SeatRecorder:
    """Greedy policy that records which seats it was asked to act for."""

    def __init__(self, model):
        self.inner = TorchGreedyPolicy(model)
        self.seats: list[int] = []

    def choose(self, observation):
        self.seats.append(int(observation.seat))
        return self.inner.choose(observation)


@requires_go_lib
def test_learner_acts_only_for_its_seat_and_opponents_for_the_rest():
    learner = _SeatRecorder(_model(1))
    opponent = _SeatRecorder(_model(2))
    report = evaluate_policy_online(
        policy=learner, episodes=2, seeds=[11, 12], learning_seat=2,
        match_mode="classic", opponent_policy=opponent,
    )
    assert report["episodes"] == 2
    assert learner.seats and set(learner.seats) == {2}
    assert opponent.seats and 2 not in set(opponent.seats)
    assert set(opponent.seats) <= {0, 1, 3}
    # Decision counts and action families cover the learning seat only.
    decisions = sum(e["decision_count"] for e in report["episode_summaries"])
    assert decisions == len(learner.seats)
    assert sum(report["action_family_counts"].values()) == len(learner.seats)


@requires_go_lib
def test_self_table_placements_sum_to_zero_per_seed():
    # One deterministic policy in all four seats plays the SAME game in every
    # seat rotation of a seed, so the four seats' placement values are that
    # game's full ranking and sum to 1 + 1/3 - 1/3 - 1 = 0. This fails if the
    # strong table drops the rewards of steps taken by opponent seats.
    model = _model(3)
    seeds = [21, 22, 23]
    report = evaluate_duplicate_seats_policy(
        policy_factory=lambda seat: TorchGreedyPolicy(model),
        seeds=seeds, match_mode="chongci", chongci_max_hands=8, max_steps_per_episode=4000,
        opponent_policy=TorchGreedyPolicy(model), opponents=OPPONENTS,
    )
    assert report["opponents"] == OPPONENTS
    assert report["truncation_rate"] == 0.0
    per_seat = [r["per_episode_placements"] for r in report["seat_reports"]]
    for i in range(len(seeds)):
        assert sum(seat[i] for seat in per_seat) == pytest.approx(0.0, abs=1e-6)
    # Not vacuous: at least one game produced a strict ranking, not an all-tie.
    assert any(abs(p) == pytest.approx(1.0) for seat in per_seat for p in seat)


def test_opponent_policy_requires_identity_record():
    with pytest.raises(ValueError, match="together"):
        evaluate_duplicate_seats_policy(
            policy_factory=lambda seat: None, seeds=[1],
            opponent_policy=object(), opponents=None,
        )


def test_heuristic_report_has_no_opponents_field(monkeypatch):
    calls = []

    def fake_online(**kwargs):
        calls.append(kwargs.get("opponent_policy"))
        raise RuntimeError("stop after dispatch")

    monkeypatch.setattr("fh_mahjong_ai.evaluate.evaluate_policy_online", fake_online)
    with pytest.raises(RuntimeError, match="stop after dispatch"):
        evaluate_duplicate_seats_policy(policy_factory=lambda seat: None, seeds=[1])
    assert calls == [None]


def _report(opponents=None):
    report = {
        "seeds": [1, 2],
        "per_seed_mean_placements": [0.1, -0.1],
        "mean_placement": 0.0,
        "large_loss_rate": 0.0,
        "seat_reports": [{"per_episode_placements": [0.1, -0.1]} for _ in range(4)],
        "match_mode": "chongci",
        "chongci_config": {"starting_score": 2000, "bust_threshold": 0, "max_hands": 50},
        "seats": [0, 1, 2, 3],
        "max_steps_per_episode": 4000,
        "oracle_observation": False,
        "event_history_window": 0,
        "large_loss_threshold": -800.0,
        "bridge_lib_sha256": "a" * 64,
    }
    if opponents is not None:
        report["opponents"] = opponents
    return report


def test_compare_refuses_strong_table_vs_heuristic_table():
    with pytest.raises(ValueError, match="opponents differ"):
        paired_comparison(_report(OPPONENTS), _report())
    with pytest.raises(ValueError, match="opponents differ"):
        paired_comparison(_report(), _report(OPPONENTS), allow_missing_config=True)


def test_compare_refuses_different_opponent_checkpoints():
    other = dict(OPPONENTS, checkpoint_sha256="c" * 64)
    with pytest.raises(ValueError, match="opponents differ"):
        paired_comparison(_report(OPPONENTS), _report(other))


def test_compare_accepts_same_opponents():
    result = paired_comparison(_report(OPPONENTS), _report(OPPONENTS))
    assert result["config_check"] == "strict"


import gzip
import json
from collections import Counter


@requires_go_lib
def test_route_study_records_every_seat_at_a_strong_table(tmp_path):
    shard = tmp_path / "rs.jsonl.gz"
    report = evaluate_policy_online(
        policy=TorchGreedyPolicy(_model(1)), episodes=2, seeds=[11, 12], learning_seat=1,
        match_mode="chongci", chongci_max_hands=4, max_steps_per_episode=4000,
        opponent_policy=TorchGreedyPolicy(_model(2)), route_study_shard=shard,
    )
    study = report["route_study"]
    hands = report["hand_stats"]["hands_played"]
    assert hands > 0
    assert study["learner"]["hands_recorded"] == hands
    assert study["opponents"]["hands_recorded"] == 3 * hands
    with gzip.open(shard, "rt") as fh:
        records = [json.loads(line) for line in fh]
    kinds = Counter(r["kind"] for r in records)
    assert kinds["hand"] == 4 * hands
    assert {r["seat"] for r in records if r["kind"] == "hand"} == {0, 1, 2, 3}
    dealt = sum(cell["hands"] for row in study["learner"]["deal"].values() for cell in row.values())
    assert dealt == hands - study["learner"]["hands_without_deal"]


@requires_go_lib
def test_route_study_off_leaves_report_without_the_key():
    report = evaluate_policy_online(
        policy=TorchGreedyPolicy(_model(1)), episodes=1, seeds=[11], learning_seat=0,
        match_mode="classic",
    )
    assert "route_study" not in report
