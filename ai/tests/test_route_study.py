import gzip
import json
from types import SimpleNamespace

import pytest

from fh_mahjong_ai.action_catalog import ACTION_PASS, ACTION_RON, CHII_BASE, DISCARD_BASE, PON_BASE
from fh_mahjong_ai.route_study import (
    RouteStudyRecorder,
    classify_fork,
    end_route,
    gap_bucket,
    is_call_offer,
    merge_route_study,
    new_route_study_summary,
    shanten_bucket,
    turn_bucket,
    win_route,
)


def _routes(std, sp, ind):
    return {"overall": min(std, sp, ind), "standard": std, "seven_pairs": sp, "independence": ind}


def _probe(routes, discards=(), wilds=0, open_melds=0, seat=0):
    return {"seat": seat, "routes": routes, "wild_count": wilds, "open_meld_count": open_melds,
            "discards": [{"action_id": a, "is_wild": False, "after": after} for a, after in discards]}


def _obs(seat, legal):
    return SimpleNamespace(seat=seat, legal_actions=tuple(legal))


def _outcome(winner, patterns=(), draw=False, discarder=-1, payouts=None):
    return {"is_draw": draw, "winner_seat": winner, "discarder_seat": discarder,
            "win_type_name": "ACTION_RON" if discarder >= 0 else "ACTION_TSUMO",
            "payouts": payouts or [], "breakdown": [{"pattern_id": p} for p in patterns]}


D1, D2, D3 = DISCARD_BASE, DISCARD_BASE + 1, DISCARD_BASE + 2


def test_buckets_clip_and_mark_unavailable():
    assert [shanten_bucket(v) for v in (-1, 0, 6, 9, 99)] == ["0", "0", "6", "6", "-"]
    assert [gap_bucket(i, s) for i, s in ((0, 5), (2, 2), (8, 1))] == ["-3", "0", "3"]
    assert [turn_bucket(t) for t in (1, 3, 4, 9, 10, 15)] == ["1-3", "1-3", "4-6", "7-9", "10+", "10+"]


def test_win_route_maps_pattern_families():
    assert win_route(_outcome(1, ["independence", "closed_seven_stars"]), 1) == "independence"
    assert win_route(_outcome(1, ["wild_seven_pairs", "open_bomb"]), 1) == "seven_pairs"
    assert win_route(_outcome(1, ["completed_all_honors"]), 1) == "special"
    assert win_route(_outcome(1, ["base_point", "common_win"]), 1) == "standard"
    assert win_route(_outcome(1, ["independence"]), 2) == "none"
    assert win_route(_outcome(0, draw=True), 0) == "none"


def test_end_route_unique_lowest_tie_and_open_meld():
    assert end_route(_routes(3, 4, 1), 0) == "independence"
    assert end_route(_routes(2, 4, 2), 0) == "tie"
    assert end_route(_routes(99, 99, 99) | {"standard": 2}, 1) == "standard"


def test_classify_fork_disjoint_vs_shared_best():
    # D1 best for independence only, D2 best for standard only -> fork.
    probe = _probe(_routes(3, 5, 2), [(D1, _routes(4, 5, 1)), (D2, _routes(2, 5, 3)), (D3, _routes(4, 6, 3))])
    assert classify_fork(probe, D1)["choice"] == "independence"
    assert classify_fork(probe, D2)["choice"] == "standard"
    assert classify_fork(probe, D3)["choice"] == "neither"
    assert classify_fork(probe, D1)["best_after"] == {"standard": 2, "seven_pairs": 5, "independence": 1}
    assert classify_fork(probe, D1)["keeps_seven_pairs"] is True
    # D1 is best for both -> no fork.
    shared = _probe(_routes(3, 5, 2), [(D1, _routes(2, 5, 1)), (D2, _routes(2, 6, 3))])
    assert classify_fork(shared, D2) is None
    # Open meld -> never a fork.
    assert classify_fork(_probe(_routes(3, 99, 99), [(D1, _routes(2, 99, 99))], open_melds=1), D1) is None


def test_is_call_offer_needs_chii_or_pon_and_no_ron():
    assert is_call_offer([ACTION_PASS, PON_BASE])
    assert is_call_offer([ACTION_PASS, CHII_BASE])
    assert not is_call_offer([ACTION_PASS, PON_BASE, ACTION_RON])
    assert not is_call_offer([D1, D2])


class _ScriptedProbe:
    def __init__(self):
        self.next = {}

    def __call__(self, seat):
        return self.next[seat]


def _recorder(tmp_path, recorded=(0, 1, 2, 3), learning_seat=0):
    probe = _ScriptedProbe()
    rec = RouteStudyRecorder(learning_seat, probe=probe, recorded_seats=recorded,
                             shard_path=tmp_path / "rs.jsonl.gz")
    rec.start_match(500)
    return rec, probe


def _records(tmp_path):
    with gzip.open(tmp_path / "rs.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


def test_hand_record_deal_chart_fork_and_turns(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    fork_probe = _probe(_routes(3, 5, 2), [(D1, _routes(4, 5, 1)), (D2, _routes(2, 5, 3))], wilds=1)
    probe.next[0] = fork_probe
    rec.on_decision(_obs(0, [D1, D2]), D1)          # deal + fork at turn 1, independence side
    rec.on_decision(_obs(0, [D1, D2]), D2)          # fork at turn 2, standard side
    probe.next[1] = _probe(_routes(2, 4, 4), [(D1, _routes(1, 4, 4))], seat=1)
    rec.on_decision(_obs(1, [D1]), D1)              # seat 1 deal, no fork (single option is best for both)
    rec.on_hand_end(_outcome(0, ["independence"], payouts=[{"seat": 0, "amount": 150}, {"seat": 1, "amount": -50}]))
    rec.on_match_end(truncated=False)
    rec.close()

    learner = rec.summary()["learner"]
    assert learner["hands_recorded"] == 1
    cell = learner["deal"]["3"]["2"]
    assert cell == {"hands": 1, "end_independence": 1, "win_independence": 1, "deal_ins": 0, "payout_sum": 150}
    assert learner["deal_by_wilds"]["1"]["3"]["2"]["hands"] == 1
    assert learner["fork"]["-1"]["1-3"] == {"forks": 2, "independence": 1, "standard": 1}
    opponents = rec.summary()["opponents"]
    assert opponents["deal"]["2"]["4"]["end_standard"] == 1
    assert opponents["deal"]["2"]["4"]["payout_sum"] == -50

    records = _records(tmp_path)
    forks = [r for r in records if r["kind"] == "fork"]
    assert [(f["turn"], f["choice"]) for f in forks] == [(1, "independence"), (2, "standard")]
    hands = [r for r in records if r["kind"] == "hand"]
    assert {(h["seat"], h["side"], h["win_route"]) for h in hands} == {(0, "learner", "independence"), (1, "opponents", "none")}
    assert all(h["seed"] == 500 and h["hand"] == 0 for h in hands)


def test_seat_without_a_discard_decision_counts_without_deal(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    probe.next[0] = _probe(_routes(3, 5, 2), [(D1, _routes(3, 5, 2))])
    rec.on_decision(_obs(0, [D1]), D1)
    rec.on_hand_end(_outcome(1, ["base_point"], discarder=0))   # seat 1 never decided
    summary = rec.summary()
    assert summary["opponents"]["hands_without_deal"] == 1
    assert summary["opponents"]["deal"] == {}
    assert summary["learner"]["deal"]["3"]["2"]["deal_ins"] == 1


def test_call_offers_with_closed_hand_only(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(2,), learning_seat=2)
    probe.next[2] = _probe(_routes(3, 4, 1), seat=2)
    rec.on_decision(_obs(2, [ACTION_PASS, PON_BASE]), ACTION_PASS)
    rec.on_decision(_obs(2, [ACTION_PASS, CHII_BASE]), CHII_BASE)
    probe.next[2] = _probe(_routes(2, 99, 99), seat=2, open_melds=1)
    rec.on_decision(_obs(2, [ACTION_PASS, PON_BASE]), PON_BASE)    # already open: not an offer
    assert rec.summary()["learner"]["call"] == {"1": {"offers": 2, "called": 1}}


def test_truncated_match_drops_open_hand(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    probe.next[0] = _probe(_routes(3, 5, 2), [(D1, _routes(3, 5, 2))])
    rec.on_decision(_obs(0, [D1]), D1)
    rec.on_match_end(truncated=True)
    rec.close()
    summary = rec.summary()
    assert summary["learner"]["hands_recorded"] == 0
    assert summary["learner"]["truncated_hands"] == 1
    assert summary["opponents"]["truncated_hands"] == 1
    assert [r for r in _records(tmp_path) if r["kind"] == "hand"] == []


def test_unrecorded_seats_are_ignored(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0,))
    rec.on_decision(_obs(3, [D1]), D1)     # probe has no entry for seat 3: must not be called
    rec.on_hand_end(_outcome(3, ["base_point"]))
    assert rec.summary()["learner"]["hands_without_deal"] == 1
    assert rec.summary()["opponents"]["hands_recorded"] == 0


def test_merge_sums_nested_counts():
    a, b = new_route_study_summary(), new_route_study_summary()
    a["learner"]["deal"] = {"3": {"2": {"hands": 1, "payout_sum": 10}}}
    a["learner"]["hands_recorded"] = 1
    b["learner"]["deal"] = {"3": {"2": {"hands": 2, "payout_sum": -4}, "1": {"hands": 1}}}
    b["learner"]["hands_recorded"] = 3
    merged = merge_route_study([a, b])
    assert merged["learner"]["deal"] == {"3": {"2": {"hands": 3, "payout_sum": 6}, "1": {"hands": 1}}}
    assert merged["learner"]["hands_recorded"] == 4
    assert merged["opponents"]["hands_recorded"] == 0
