"""Per-hand Tenhou/Majsoul-style outcome statistics for heuristic benchmarking.

Consumes the ``round_outcome`` dicts decoded by ``CtypesGoBridge._decode_round_outcome``
(keys: ``is_draw``, ``winner_seat``, ``win_type``, ``win_type_name``,
``discarder_seat``, ``total_score``, ``payouts=[{seat, amount}]``,
``breakdown=[{pattern_id, pattern_name, points}]``). Payout amounts are actual
per-seat nets, so Fenghua liability rules are already reflected.

The win-pattern tally counts each win's scoring patterns, split into the learning
seat's wins and the other seats' wins (pooled).

Denominators count OBSERVED hands only: the Go env can drop a hand's outcome when no learning-seat decision occurs before the next boundary, and such hands are invisible here.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

_RON = "ACTION_RON"

_RATE_STATS = ("win_rate", "deal_in_rate", "draw_rate")
_VALUE_STATS = ("avg_win_value", "avg_deal_in_loss")
CI_STATS = _RATE_STATS + _VALUE_STATS


def hand_record(outcome: dict[str, Any], learning_seat: int) -> dict[str, Any]:
    """Classify one hand's outcome from the learning seat's perspective."""
    payout = 0
    for entry in outcome.get("payouts") or []:
        if int(entry.get("seat", -1)) == int(learning_seat):
            payout = int(entry.get("amount", 0))
            break
    is_draw = bool(outcome.get("is_draw", False))
    winner = int(outcome.get("winner_seat", -1))
    discarder = int(outcome.get("discarder_seat", -1))
    win_type_name = str(outcome.get("win_type_name", ""))
    win = (not is_draw) and winner == int(learning_seat)
    deal_in = (
        (not is_draw)
        and win_type_name == _RON
        and discarder == int(learning_seat)
        and winner != int(learning_seat)
    )
    return {
        "is_draw": is_draw,
        "win": win,
        "deal_in": deal_in,
        "win_type_name": win_type_name,
        "payout": payout,
    }


WIN_PATTERN_SIDES = ("learner", "opponents")


def new_win_pattern_tally() -> dict[str, Any]:
    return {side: {"wins": 0, "tsumo_wins": 0, "total_score_sum": 0, "patterns": {}}
            for side in WIN_PATTERN_SIDES}


def tally_win_patterns(tally: dict[str, Any], outcome: dict[str, Any], learning_seat: int) -> None:
    """Add one hand's scoring patterns to ``tally`` (draws add nothing)."""
    if bool(outcome.get("is_draw", False)):
        return
    side = tally["learner" if int(outcome.get("winner_seat", -1)) == int(learning_seat) else "opponents"]
    side["wins"] += 1
    side["tsumo_wins"] += int(str(outcome.get("win_type_name", "")) == "ACTION_TSUMO")
    side["total_score_sum"] += int(outcome.get("total_score", 0))
    for entry in outcome.get("breakdown") or []:
        stats = side["patterns"].setdefault(
            str(entry["pattern_id"]), {"name": str(entry["pattern_name"]), "count": 0, "points_sum": 0})
        stats["count"] += 1
        stats["points_sum"] += int(entry["points"])


def merge_win_pattern_tallies(tallies: list[dict[str, Any]]) -> dict[str, Any]:
    merged = new_win_pattern_tally()
    for tally in tallies:
        for side_name in WIN_PATTERN_SIDES:
            side, into = tally[side_name], merged[side_name]
            for key in ("wins", "tsumo_wins", "total_score_sum"):
                into[key] += side[key]
            for pattern_id, stats in side["patterns"].items():
                target = into["patterns"].setdefault(
                    pattern_id, {"name": stats["name"], "count": 0, "points_sum": 0})
                target["count"] += stats["count"]
                target["points_sum"] += stats["points_sum"]
    return merged


def summarize_hand_stats(
    per_match_records: list[list[dict[str, Any]]],
    unknown_hands: int = 0,
) -> dict[str, Any]:
    """Aggregate per-hand records (grouped by match) into the core stat sheet."""
    records = [rec for match in per_match_records for rec in match]
    hands = len(records)
    wins = sum(1 for r in records if r["win"])
    deal_ins = sum(1 for r in records if r["deal_in"])
    draws = sum(1 for r in records if r["is_draw"])
    win_values = [r["payout"] for r in records if r["win"]]
    deal_in_losses = [abs(r["payout"]) for r in records if r["deal_in"]]
    matches = len(per_match_records)
    return {
        "matches": matches,
        "hands_played": hands,
        "unknown_hands": int(unknown_hands),
        "wins": wins,
        "deal_ins": deal_ins,
        "draws": draws,
        "win_rate": wins / hands if hands else 0.0,
        "deal_in_rate": deal_ins / hands if hands else 0.0,
        "draw_rate": draws / hands if hands else 0.0,
        "avg_win_value": float(np.mean(win_values)) if win_values else None,
        "avg_deal_in_loss": float(np.mean(deal_in_losses)) if deal_in_losses else None,
        "hands_per_match": hands / matches if matches else 0.0,
    }


def bootstrap_hand_stats_ci(
    per_match_records: list[list[dict[str, Any]]],
    iters: int = 1000,
    seed: int = 0,
) -> dict[str, Optional[list[float]]]:
    """95% percentile CIs via match-level bootstrap.

    Matches (not hands) are resampled with replacement because hands within a
    match are correlated; hand-level binomial CIs would be overconfident.
    A stat with no defined value in the ORIGINAL sample (e.g. no deal-ins
    anywhere) gets ``None``; bootstrap iterations where a value stat has no
    samples are skipped for that stat.
    """
    matches = len(per_match_records)
    if matches < 2:
        return {stat: None for stat in CI_STATS}
    point = summarize_hand_stats(per_match_records)
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {stat: [] for stat in CI_STATS}
    for _ in range(int(iters)):
        indices = rng.integers(0, matches, size=matches)
        resampled = [per_match_records[i] for i in indices]
        stats = summarize_hand_stats(resampled)
        for stat in CI_STATS:
            value = stats[stat]
            if value is not None:
                samples[stat].append(float(value))
    cis: dict[str, Optional[list[float]]] = {}
    for stat in CI_STATS:
        if point[stat] is None or not samples[stat]:
            cis[stat] = None
        else:
            lo, hi = np.percentile(samples[stat], [2.5, 97.5])
            cis[stat] = [float(lo), float(hi)]
    return cis
