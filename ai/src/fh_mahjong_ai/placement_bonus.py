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


def eval_episode_tail(net: np.ndarray, learning_seat: int, starting_score: float,
                      truncated: bool, values: Sequence[float] = PLACEMENT_RESHAPE_VALUES) -> dict:
    """Evaluator-side tail metrics for one episode. Truncation = full 4th-place
    occupancy and the worst utility (the objective's terminal rank does not
    exist; omitting it would censor). `parity_ok` checks that ranking the
    float accumulated net agrees with ranking the exact integer standings."""
    if truncated:
        return {"fourth_share": 1.0, "utility": float(values[3]),
                "occupancy": np.array([0.0, 0.0, 0.0, 1.0]), "parity_ok": True}
    ints = exact_final_scores(net, starting_score)
    occ = rank_occupancy(ints)
    u = placement_utilities(ints, values)
    float_occ = rank_occupancy(np.asarray(net, dtype=np.float64))
    return {"fourth_share": float(occ[learning_seat, 3]), "utility": float(u[learning_seat]),
            "occupancy": occ[learning_seat], "parity_ok": bool(np.allclose(occ, float_occ))}


CALIBRATION_MATCHES = 320
K_REGISTERED = 0.5
GATE_RMS_MAX, GATE_P99_MAX, GATE_CRITIC_MSE_MAX = 1.35, 1.50, 2.00


def calibrate_lambda(telemetry: Sequence[dict], values: Sequence[float] = PLACEMENT_RESHAPE_VALUES,
                     k: float = K_REGISTERED, require_matches: int = CALIBRATION_MATCHES) -> dict:
    """lambda = k * sigma_R / sigma_V over all seat-match records (ddof=0).
    R = dense PPO-credited trajectory return (telemetry["trajectory_returns"]),
    V = registered utility on the full final standings."""
    if len(telemetry) != require_matches:
        raise ValueError(f"calibration requires exactly {require_matches} matches (got {len(telemetry)}); "
                         "spec registers 320")
    if any(t.get("truncated") for t in telemetry):
        raise ValueError("calibration collection contains a truncated match — fail closed")
    R = np.asarray([t["trajectory_returns"] for t in telemetry], dtype=np.float64).ravel()
    Vv = np.asarray([placement_utilities(t["final_scores"], values) for t in telemetry],
                    dtype=np.float64).ravel()
    sR, sV = float(R.std(ddof=0)), float(Vv.std(ddof=0))
    if not (np.isfinite(sR) and np.isfinite(sV)) or sR == 0.0 or sV == 0.0:
        raise ValueError(f"degenerate calibration: sigma_R={sR} sigma_V={sV}")
    return {"lambda": float(k * sR / sV), "sigma_R": sR, "sigma_V": sV,
            "corr_RV": float(np.corrcoef(R, Vv)[0, 1]), "k": float(k),
            "num_matches": len(telemetry), "num_records": int(R.size)}


def apply_terminal_bonus(rewards: np.ndarray, dones: np.ndarray, telemetry: Sequence[dict],
                         values: Sequence[float], lam: float) -> np.ndarray:
    """Return a copy of `rewards` with lam*utility added at every seat's last
    row. Segments (done=1) come 4 per match in seat order 0..3, matches in
    telemetry order — exactly collect_b2b_rollouts' layout."""
    ends = np.flatnonzero(np.asarray(dones) == 1.0)
    if ends.size != 4 * len(telemetry):
        raise ValueError(f"{ends.size} done rows but {len(telemetry)} matches (expected 4 per match)")
    out = np.array(rewards, dtype=np.float32, copy=True)
    for i, t in enumerate(telemetry):
        u = placement_utilities(t["final_scores"], values)
        for k in range(4):
            out[ends[4 * i + k]] += np.float32(lam * u[k])
    return out


def return_scale_gates(raw_returns: np.ndarray, shaped_returns: np.ndarray,
                       values_pred: np.ndarray) -> dict:
    raw = np.asarray(raw_returns, np.float64); shp = np.asarray(shaped_returns, np.float64)
    pred = np.asarray(values_pred, np.float64)
    rms = lambda x: float(np.sqrt(np.mean(x**2)))
    p99 = lambda x: float(np.percentile(np.abs(x), 99))
    mse = lambda x: float(np.mean((pred - x) ** 2))
    finite = bool(np.isfinite(raw).all() and np.isfinite(shp).all())
    g = {
        "rms_ratio": rms(shp) / rms(raw), "p99_ratio": p99(shp) / p99(raw),
        "critic_mse_ratio": mse(shp) / mse(raw), "finite": finite,
        "raw_return_rms": rms(raw), "shaped_return_rms": rms(shp),
        "raw_return_abs_p99": p99(raw), "shaped_return_abs_p99": p99(shp),
        "raw_critic_mse": mse(raw), "shaped_critic_mse": mse(shp),
    }
    g["rms_pass"] = g["rms_ratio"] <= GATE_RMS_MAX
    g["p99_pass"] = g["p99_ratio"] <= GATE_P99_MAX
    g["critic_mse_pass"] = g["critic_mse_ratio"] <= GATE_CRITIC_MSE_MAX
    g["all_pass"] = bool(finite and g["rms_pass"] and g["p99_pass"] and g["critic_mse_pass"])
    return g
