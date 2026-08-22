"""Placement-reshape experiment (spec 2026-08-21): the registered asymmetric
terminal placement utility and the exact-standings helpers shared by the B2b
collector (training bonus), the calibration script, and the evaluator.

Everything here is pure numpy on final scores — no bridge, no model — so the
tie/bust semantics are testable exhaustively and identical on both sides.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .data import placement_shaped_returns

# (10, 5, 1, -10) mean-subtracted and RMS-matched to the canonical eval vector
# (1, 1/3, -1/3, -1). Registered to full precision; never rescale this — any
# rescaling is cancelled by an inverse rescaling of lambda (spec, Design).
PLACEMENT_RESHAPE_VALUES: tuple[float, float, float, float] = (
    0.8601670494, 0.3541864321, -0.0505980617, -1.1637554197,
)

NUM_SEATS = 4


def exact_final_scores(match_net: Sequence[float], starting_score: float) -> list[int]:
    """Integer final scores from reward-scale (score/1000) per-seat nets — the
    same ×1000-and-round reconstruction train_b2b uses for hindsight labels,
    so utilities and labels can never disagree on a tie or a bust."""
    net = np.asarray(match_net, dtype=np.float64)
    if net.shape != (NUM_SEATS,):
        raise ValueError(f"match_net must have {NUM_SEATS} seats, got shape {net.shape}")
    return [int(round(starting_score + round(float(n) * 1000.0))) for n in net]


def placement_utilities(final_scores: Sequence[float],
                        values: Sequence[float] = PLACEMENT_RESHAPE_VALUES) -> np.ndarray:
    """Per-seat utility from final standings: descending score → values[rank];
    tied seats (busted or not) average the utilities of the slots they share.
    Busted seats are ranked by their exact score like everyone else (the aux
    `rank_labels` class 4 is NOT a 4th-place utility)."""
    scores = np.asarray(final_scores, dtype=np.float64)
    if scores.shape != (NUM_SEATS,):
        raise ValueError(f"final_scores must have {NUM_SEATS} seats, got shape {scores.shape}")
    result = placement_shaped_returns(scores[None, :].astype(np.float32),
                                      tuple(float(v) for v in values))[0].astype(np.float64)
    # Re-center to correct for float32 rounding errors
    return result - result.mean()


def rank_occupancy(final_scores: Sequence[float]) -> np.ndarray:
    """[seat, rank-slot] fractional occupancy: a seat tied with k-1 others over
    slots s..s+k-1 occupies each of them 1/k. Rows and columns sum to 1."""
    scores = np.asarray(final_scores, dtype=np.float64)
    if scores.shape != (NUM_SEATS,):
        raise ValueError(f"final_scores must have {NUM_SEATS} seats, got shape {scores.shape}")
    occ = np.zeros((NUM_SEATS, NUM_SEATS), dtype=np.float64)
    order = np.argsort(-scores, kind="stable")
    slot = 0
    while slot < NUM_SEATS:
        tied = [order[slot]]
        j = slot + 1
        while j < NUM_SEATS and scores[order[j]] == scores[order[slot]]:
            tied.append(order[j]); j += 1
        share = 1.0 / len(tied)
        for seat in tied:
            occ[seat, slot:j] = share
        slot = j
    return occ
