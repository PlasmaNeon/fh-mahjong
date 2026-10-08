"""Route study: when a policy pursues Independence vs the standard hand.

For every recorded seat's decision the recorder reads the seat's route shanten
from the Go bridge (`CtypesGoBridge.route_probe`), classifies discard forks and
chii/pon offers, and at each hand's end emits one hand record. Aggregates merge
by summing, so chunked benchmark runs combine exactly.
Findings: docs/ai-findings.md (Policy behavior).
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from .action_catalog import ACTION_RON, action_family
from .hand_stats import WIN_PATTERN_SIDES, hand_record

ROUTES = ("standard", "seven_pairs", "independence")
UNAVAILABLE = 99
SHANTEN_BUCKETS = ("0", "1", "2", "3", "4", "5", "6", "-")
GAP_BUCKETS = ("-3", "-2", "-1", "0", "1", "2", "3")
TURN_BUCKETS = ("1-3", "4-6", "7-9", "10+")
WILD_BUCKETS = ("0", "1", "2+")

_INDEPENDENCE_PATTERNS = frozenset({"independence"})
_SEVEN_PAIRS_PATTERNS = frozenset({"straight_seven_pairs", "wild_seven_pairs"})
_SPECIAL_PATTERNS = frozenset({
    "uncompleted_all_honors", "completed_all_honors",
    "uncompleted_eight_flowers", "completed_eight_flowers",
})
_CALL_FAMILIES = frozenset({"chii", "pon", "kan"})


def shanten_bucket(value: int) -> str:
    if value >= UNAVAILABLE:
        return "-"
    return str(max(0, min(6, int(value))))


def gap_bucket(independence: int, standard: int) -> str:
    return str(max(-3, min(3, int(independence) - int(standard))))


def turn_bucket(turn: int) -> str:
    if turn <= 3:
        return "1-3"
    if turn <= 6:
        return "4-6"
    if turn <= 9:
        return "7-9"
    return "10+"


def wild_bucket(wilds: int) -> str:
    return "2+" if wilds >= 2 else str(int(wilds))


def win_route(outcome: dict[str, Any], seat: int) -> str:
    """The route a hand was won on, from `seat`'s view: `none` unless it won."""
    if outcome.get("is_draw") or int(outcome.get("winner_seat", -1)) != int(seat):
        return "none"
    ids = {entry.get("pattern_id") for entry in outcome.get("breakdown") or []}
    if ids & _INDEPENDENCE_PATTERNS:
        return "independence"
    if ids & _SEVEN_PAIRS_PATTERNS:
        return "seven_pairs"
    if ids & _SPECIAL_PATTERNS:
        return "special"
    return "standard"


def end_route(routes: dict[str, int], open_meld_count: int) -> str:
    """The route closest to completion: the unique lowest shanten, else `tie`."""
    if open_meld_count > 0:
        return "standard"
    lowest = min(routes[r] for r in ROUTES)
    leaders = [r for r in ROUTES if routes[r] == lowest]
    return leaders[0] if len(leaders) == 1 else "tie"


def classify_fork(probe: dict[str, Any], action_id: int) -> Optional[dict[str, Any]]:
    """The fork facts for a chosen discard, or None when the decision is no fork.

    A fork: no open melds, and no discard minimizes both the after-Independence
    and the after-standard shanten.
    """
    discards = probe["discards"]
    if probe["open_meld_count"] > 0 or not discards:
        return None
    chosen = next((d for d in discards if d["action_id"] == int(action_id)), None)
    if chosen is None:
        return None
    best = {r: min(d["after"][r] for d in discards) for r in ROUTES}
    keeps = {r: {d["action_id"] for d in discards if d["after"][r] == best[r]} for r in ROUTES}
    if keeps["independence"] & keeps["standard"]:
        return None
    if chosen["action_id"] in keeps["independence"]:
        choice = "independence"
    elif chosen["action_id"] in keeps["standard"]:
        choice = "standard"
    else:
        choice = "neither"
    return {"choice": choice, "keeps_seven_pairs": chosen["action_id"] in keeps["seven_pairs"],
            "best_after": best}


def is_call_offer(legal_actions: Sequence[int]) -> bool:
    families = {action_family(a) for a in legal_actions}
    return bool(families & {"chii", "pon"}) and ACTION_RON not in legal_actions


def new_route_study_summary() -> dict[str, Any]:
    return {side: {"deal": {}, "deal_by_wilds": {}, "fork": {}, "call": {},
                   "hands_recorded": 0, "hands_without_deal": 0, "truncated_hands": 0}
            for side in WIN_PATTERN_SIDES}


def _add_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            _add_into(target.setdefault(key, {}), value)
        else:
            target[key] = target.get(key, 0) + value


def merge_route_study(summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    merged = new_route_study_summary()
    for summary in summaries:
        _add_into(merged, summary)
    return merged


def _cell(table: dict[str, Any], *keys: str) -> dict[str, int]:
    for key in keys:
        table = table.setdefault(key, {})
    return table


def _bump(cell: dict[str, int], key: str, amount: int = 1) -> None:
    cell[key] = cell.get(key, 0) + amount


class _SeatHand:
    __slots__ = ("deal", "last_routes", "last_open_melds", "discards")

    def __init__(self) -> None:
        self.deal: Optional[dict[str, int]] = None
        self.last_routes: Optional[dict[str, int]] = None
        self.last_open_melds = 0
        self.discards = 0


class RouteStudyRecorder:
    """Route-study accounting for one evaluation run (one learning seat).

    Call `start_match(seed)` after each reset, `on_decision` for every decision
    BEFORE stepping the env, `on_hand_end` with each delivered round outcome, and
    `on_match_end` when the match stops. Seats outside `recorded_seats` are ignored.
    """

    def __init__(self, learning_seat: int, probe: Callable[[int], dict[str, Any]],
                 recorded_seats: Sequence[int], shard_path: Optional[Path] = None) -> None:
        self.learning_seat = int(learning_seat)
        self._probe = probe
        self._recorded = tuple(int(s) for s in recorded_seats)
        self._shard = gzip.open(shard_path, "wt", encoding="utf-8") if shard_path is not None else None
        self._summary = new_route_study_summary()
        self._seed = -1
        self._hand_index = 0
        self._hands: dict[int, _SeatHand] = {}

    def _side(self, seat: int) -> str:
        return "learner" if seat == self.learning_seat else "opponents"

    def _write(self, record: dict[str, Any]) -> None:
        if self._shard is not None:
            self._shard.write(json.dumps(record, sort_keys=True) + "\n")

    def start_match(self, seed: int) -> None:
        self._seed = int(seed)
        self._hand_index = 0
        self._hands = {}

    def on_decision(self, observation: Any, action_id: int) -> None:
        seat = int(observation.seat)
        if seat not in self._recorded:
            return
        probe = self._probe(seat)
        routes = {r: int(probe["routes"][r]) for r in ROUTES}
        hand = self._hands.setdefault(seat, _SeatHand())
        hand.last_routes = routes
        hand.last_open_melds = int(probe["open_meld_count"])
        side = self._side(seat)
        base = {"seed": self._seed, "seat": seat, "side": side, "hand": self._hand_index,
                "routes": routes, "action_id": int(action_id)}
        if probe["discards"]:
            if hand.deal is None:
                hand.deal = {**routes, "wild_count": int(probe["wild_count"]),
                             "open_meld_count": hand.last_open_melds}
            if action_family(action_id) != "discard":
                return
            hand.discards += 1
            fork = classify_fork(probe, action_id)
            if fork is None:
                return
            cell = _cell(self._summary[side]["fork"],
                         gap_bucket(routes["independence"], routes["standard"]),
                         turn_bucket(hand.discards))
            _bump(cell, "forks")
            _bump(cell, fork["choice"])
            self._write({**base, "kind": "fork", "turn": hand.discards,
                         "wild_count": int(probe["wild_count"]), **fork})
        elif hand.last_open_melds == 0 and is_call_offer(observation.legal_actions):
            called = action_family(action_id) in _CALL_FAMILIES
            cell = _cell(self._summary[side]["call"], shanten_bucket(routes["independence"]))
            _bump(cell, "offers")
            _bump(cell, "called", int(called))
            self._write({**base, "kind": "call", "turn": hand.discards + 1, "called": called})

    def on_hand_end(self, outcome: dict[str, Any]) -> None:
        for seat in self._recorded:
            hand = self._hands.get(seat, _SeatHand())
            side = self._side(seat)
            stats = self._summary[side]
            result = hand_record(outcome, seat)
            route = win_route(outcome, seat)
            ended = (end_route(hand.last_routes, hand.last_open_melds)
                     if hand.last_routes is not None else None)
            stats["hands_recorded"] += 1
            self._write({"kind": "hand", "seed": self._seed, "seat": seat, "side": side,
                         "hand": self._hand_index, "deal": hand.deal, "end_route": ended,
                         "win_route": route, "payout": result["payout"],
                         "win": result["win"], "deal_in": result["deal_in"]})
            if hand.deal is None:
                stats["hands_without_deal"] += 1
                continue
            std = shanten_bucket(hand.deal["standard"])
            ind = shanten_bucket(hand.deal["independence"])
            for cell in (_cell(stats["deal"], std, ind),
                         _cell(stats["deal_by_wilds"], wild_bucket(hand.deal["wild_count"]), std, ind)):
                _bump(cell, "hands")
                _bump(cell, f"end_{ended}")
                if route != "none":
                    _bump(cell, f"win_{route}")
                _bump(cell, "deal_ins", int(result["deal_in"]))
                _bump(cell, "payout_sum", int(result["payout"]))
        self._hand_index += 1
        self._hands = {}

    def on_match_end(self, truncated: bool) -> None:
        if truncated and self._hands:
            for seat in self._recorded:
                self._summary[self._side(seat)]["truncated_hands"] += 1
        self._hands = {}

    def summary(self) -> dict[str, Any]:
        return self._summary

    def close(self) -> None:
        if self._shard is not None:
            self._shard.close()
            self._shard = None


_SHANTEN_LABELS = {"6": "6+"}
_GAP_LABELS = {"-3": "<=-3", "3": ">=+3"}
_CELL_WIDTH = 14


def _rate_cell(numerator: int, denominator: int) -> str:
    return f"{100.0 * numerator / denominator:.1f}% ({denominator})" if denominator else "."


def _grid(title: str, corner: str, rows: Sequence[str], cols: Sequence[str],
          cell: Callable[[str, str], str], row_labels: dict[str, str],
          col_labels: dict[str, str]) -> list[str]:
    lines = [title, f"{corner:>8}" + "".join(f"{col_labels.get(c, c):>{_CELL_WIDTH}}" for c in cols)]
    for row in rows:
        lines.append(f"{row_labels.get(row, row):>8}"
                     + "".join(f"{cell(row, col):>{_CELL_WIDTH}}" for col in cols))
    return lines


def format_route_study(summary: dict[str, Any], labels: dict[str, str]) -> str:
    """Per-side charts: deal pivots, fork pivot, call row."""
    lines: list[str] = []
    for side in WIN_PATTERN_SIDES:
        stats = summary[side]
        if not stats["hands_recorded"]:
            continue
        deal = stats["deal"]

        def deal_counts(row: str, col: str) -> dict[str, int]:
            return deal.get(row, {}).get(col, {})

        def deal_rate(key: str) -> Callable[[str, str], str]:
            return lambda r, c: _rate_cell(deal_counts(r, c).get(key, 0), deal_counts(r, c).get("hands", 0))

        def mean_payout(r: str, c: str) -> str:
            counts = deal_counts(r, c)
            return f"{counts['payout_sum'] / counts['hands']:+.1f}" if counts.get("hands") else "."

        def fork_rate(r: str, c: str) -> str:
            counts = stats["fork"].get(r, {}).get(c, {})
            return _rate_cell(counts.get("independence", 0), counts.get("forks", 0))

        def call_rate(_: str, c: str) -> str:
            counts = stats["call"].get(c, {})
            return _rate_cell(counts.get("called", 0), counts.get("offers", 0))

        rows, cols = SHANTEN_BUCKETS[:-1], SHANTEN_BUCKETS
        lines += [f"Route study — {side} ({labels.get(side, side)}): {stats['hands_recorded']} hands, "
                  f"{stats['hands_without_deal']} without a deal, {stats['truncated_hands']} truncated",
                  "Deal charts: rows = standard shanten at the deal, columns = Independence shanten "
                  "('-' = called before the first discard)", ""]
        lines += _grid("Won by Independence, % of hands (hands)", "std\\ind", rows, cols,
                       deal_rate("win_independence"), _SHANTEN_LABELS, _SHANTEN_LABELS) + [""]
        lines += _grid("Ended on the Independence route, % of hands (hands)", "std\\ind", rows, cols,
                       deal_rate("end_independence"), _SHANTEN_LABELS, _SHANTEN_LABELS) + [""]
        lines += _grid("Mean hand payout", "std\\ind", rows, cols, mean_payout,
                       _SHANTEN_LABELS, _SHANTEN_LABELS) + [""]
        lines += _grid("Forks: % choosing the Independence side (forks); rows = Independence minus "
                       "standard shanten, columns = discard number", "gap", GAP_BUCKETS, TURN_BUCKETS,
                       fork_rate, _GAP_LABELS, {}) + [""]
        lines += _grid("Closed-hand chii/pon offers: % called (offers); columns = Independence shanten",
                       "", ("called",), SHANTEN_BUCKETS[:-1], call_rate, {}, _SHANTEN_LABELS) + [""]
    return "\n".join(lines).rstrip() + "\n"
