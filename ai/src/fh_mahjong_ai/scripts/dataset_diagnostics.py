"""Coverage diagnostics for operation-level Mahjong replay datasets."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.storage import read_transition_arrays

DIAGNOSTIC_KEYS = (
    "seats",
    "scalars",
    "action_ids",
    "episode_index",
    "policy_source_ids",
    "terminal_rewards",
    "terminal_is_draw",
    "terminal_winner_seat",
    "terminal_win_type",
    "terminal_discarder_seat",
    "terminal_total_score",
    "policy_greedy_action_ids",
    "policy_sampling_applied",
    "policy_sampled_from_greedy",
)


def _count_dict(values: np.ndarray) -> dict[str, int]:
    if values.size == 0:
        return {}
    unique, counts = np.unique(values, return_counts=True)
    return {str(int(key)): int(count) for key, count in zip(unique, counts)}


def _rate_dict(counts: dict[str, int], total: int) -> dict[str, float]:
    if total <= 0:
        return {key: 0.0 for key in counts}
    return {key: float(value / total) for key, value in counts.items()}


def _summary(values: np.ndarray) -> dict[str, float]:
    if values.size == 0:
        return {"mean": 0.0, "sum": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(np.mean(values)),
        "sum": float(np.sum(values)),
        "std": float(np.std(values)),
        "min": float(np.min(values)),
        "max": float(np.max(values)),
    }


def _family_counts(action_ids: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action_id in action_ids.astype(np.int64, copy=False).tolist():
        family = action_family(int(action_id))
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def _family_pair_counts(left_actions: np.ndarray, right_actions: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for left, right in zip(left_actions.astype(np.int64, copy=False).tolist(), right_actions.astype(np.int64, copy=False).tolist()):
        pair = f"{action_family(int(left))}->{action_family(int(right))}"
        counts[pair] = counts.get(pair, 0) + 1
    return dict(sorted(counts.items()))


def _bucket_counts(values: np.ndarray, bins: tuple[float, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for low, high in zip(bins[:-1], bins[1:]):
        label = f"[{low:.2f},{high:.2f})"
        counts[label] = int(np.logical_and(values >= low, values < high).sum())
    if values.size:
        counts[f">={bins[-1]:.2f}"] = int((values >= bins[-1]).sum())
        counts[f"<{bins[0]:.2f}"] = int((values < bins[0]).sum())
    return counts


def _score_pressure_buckets(scalars: np.ndarray) -> dict[str, Any]:
    if scalars.ndim != 2 or scalars.shape[1] <= 49:
        return {
            "available": False,
            "reason": "expected scalar width > 49 for Chongci score-pressure features",
            "scalar_width": int(scalars.shape[1]) if scalars.ndim == 2 else 0,
        }
    bins = (0.0, 0.25, 0.50, 0.75, 1.0)
    large_loss_margin = scalars[:, 47].astype(np.float32, copy=False)
    opponent_large_loss_pressure = scalars[:, 49].astype(np.float32, copy=False)
    return {
        "available": True,
        "large_loss_margin_scalar_index": 47,
        "opponent_large_loss_pressure_scalar_index": 49,
        "large_loss_margin": {
            "summary": _summary(large_loss_margin),
            "buckets": _bucket_counts(large_loss_margin, bins),
        },
        "opponent_large_loss_pressure": {
            "summary": _summary(opponent_large_loss_pressure),
            "buckets": _bucket_counts(opponent_large_loss_pressure, bins),
        },
    }


def build_dataset_diagnostics(data_path: Path, large_loss_threshold: float = -1.0) -> dict[str, Any]:
    arrays = read_transition_arrays(data_path, keys=DIAGNOSTIC_KEYS[:11], optional_keys=DIAGNOSTIC_KEYS[11:])
    seats = np.asarray(arrays["seats"], dtype=np.int64)
    action_ids = np.asarray(arrays["action_ids"], dtype=np.int64)
    terminal_rewards = np.asarray(arrays["terminal_rewards"], dtype=np.float32)
    if terminal_rewards.ndim != 2 or terminal_rewards.shape[1] < 4:
        raise ValueError("terminal_rewards must have shape [N, 4]")
    row_indices = np.arange(seats.shape[0], dtype=np.int64)
    acting_returns = terminal_rewards[row_indices, seats]
    total = int(seats.shape[0])
    family_counts = _family_counts(action_ids)
    large_loss_mask = acting_returns <= float(large_loss_threshold)
    positive_mask = acting_returns > 0.0
    winner = np.asarray(arrays["terminal_winner_seat"], dtype=np.int64)
    discarder = np.asarray(arrays["terminal_discarder_seat"], dtype=np.int64)
    is_draw = np.asarray(arrays["terminal_is_draw"], dtype=np.bool_)
    win_mask = np.logical_and(~is_draw, winner == seats)
    deal_in_mask = np.logical_and(~is_draw, discarder == seats)
    policy_counts = _count_dict(np.asarray(arrays["policy_source_ids"], dtype=np.int64))
    seat_counts = _count_dict(seats)

    large_loss_by_family: dict[str, int] = {}
    for action_id, is_large_loss in zip(action_ids.tolist(), large_loss_mask.tolist()):
        if not is_large_loss:
            continue
        family = action_family(int(action_id))
        large_loss_by_family[family] = large_loss_by_family.get(family, 0) + 1

    report: dict[str, Any] = {
        "data_path": str(data_path),
        "transitions": total,
        "episodes": int(np.unique(arrays["episode_index"]).size) if total else 0,
        "large_loss_threshold": float(large_loss_threshold),
        "seats": {
            "counts": seat_counts,
            "rates": _rate_dict(seat_counts, total),
        },
        "policy_source_ids": {
            "counts": policy_counts,
            "rates": _rate_dict(policy_counts, total),
        },
        "action_families": {
            "counts": family_counts,
            "rates": _rate_dict(family_counts, total),
            "large_loss_counts": dict(sorted(large_loss_by_family.items())),
            "large_loss_rates": {
                family: float(large_loss_by_family.get(family, 0) / max(1, count))
                for family, count in family_counts.items()
            },
        },
        "acting_return": {
            **_summary(acting_returns),
            "positive_count": int(positive_mask.sum()),
            "positive_rate": float(positive_mask.mean()) if total else 0.0,
            "large_loss_count": int(large_loss_mask.sum()),
            "large_loss_rate": float(large_loss_mask.mean()) if total else 0.0,
        },
        "terminal_outcomes": {
            "draw_count": int(is_draw.sum()),
            "draw_rate": float(is_draw.mean()) if total else 0.0,
            "win_count": int(win_mask.sum()),
            "win_rate": float(win_mask.mean()) if total else 0.0,
            "deal_in_count": int(deal_in_mask.sum()),
            "deal_in_rate": float(deal_in_mask.mean()) if total else 0.0,
            "winner_seat_counts": _count_dict(winner),
            "discarder_seat_counts": _count_dict(discarder),
            "win_type_counts": _count_dict(np.asarray(arrays["terminal_win_type"], dtype=np.int64)),
            "total_score": _summary(np.asarray(arrays["terminal_total_score"], dtype=np.float32)),
        },
        "score_pressure": _score_pressure_buckets(np.asarray(arrays["scalars"], dtype=np.float32)),
    }
    if "policy_sampling_applied" in arrays and "policy_sampled_from_greedy" in arrays:
        sampling_applied = np.asarray(arrays["policy_sampling_applied"], dtype=np.bool_)
        sampled_from_greedy = np.asarray(arrays["policy_sampled_from_greedy"], dtype=np.bool_)
        greedy_action_ids = np.asarray(
            arrays.get("policy_greedy_action_ids", np.full(total, -1, dtype=np.int64)),
            dtype=np.int64,
        )
        applied_count = int(sampling_applied.sum())
        sampled_count = int(sampled_from_greedy.sum())
        sampled_returns = acting_returns[sampled_from_greedy]
        sampled_large_loss = large_loss_mask[sampled_from_greedy]
        by_source: dict[str, dict[str, float | int]] = {}
        source_ids = np.asarray(arrays["policy_source_ids"], dtype=np.int64)
        for source_id in sorted(np.unique(source_ids).astype(np.int64).tolist()):
            source_mask = source_ids == source_id
            source_applied = np.logical_and(source_mask, sampling_applied)
            source_sampled = np.logical_and(source_mask, sampled_from_greedy)
            by_source[str(source_id)] = {
                "rows": int(source_mask.sum()),
                "sampling_applied_count": int(source_applied.sum()),
                "sampling_applied_rate": float(source_applied.sum() / max(1, int(source_mask.sum()))),
                "sampled_from_greedy_count": int(source_sampled.sum()),
                "sampled_from_greedy_rate": float(source_sampled.sum() / max(1, int(source_applied.sum()))),
            }
        report["policy_sampling"] = {
            "available": True,
            "sampling_applied_count": applied_count,
            "sampling_applied_rate": _rate_dict({"sampling": applied_count}, total).get("sampling", 0.0),
            "sampled_from_greedy_count": sampled_count,
            "sampled_from_greedy_rate": float(sampled_count / max(1, applied_count)),
            "sampled_from_all_rows_rate": float(sampled_count / max(1, total)),
            "sampled_return": {
                **_summary(sampled_returns),
                "large_loss_count": int(sampled_large_loss.sum()),
                "large_loss_rate": float(sampled_large_loss.mean()) if sampled_large_loss.size else 0.0,
                "positive_count": int((sampled_returns > 0.0).sum()),
                "positive_rate": float((sampled_returns > 0.0).mean()) if sampled_returns.size else 0.0,
            },
            "sampled_family_pair_counts": _family_pair_counts(greedy_action_ids[sampled_from_greedy], action_ids[sampled_from_greedy]),
            "by_policy_source_id": by_source,
        }
    else:
        report["policy_sampling"] = {
            "available": False,
            "reason": "dataset does not contain policy sampling instrumentation arrays",
        }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Report operation-level replay dataset coverage")
    parser.add_argument("--data", type=Path, required=True, help="JSONL or sharded NumPy transition dataset")
    parser.add_argument("--large-loss-threshold", type=float, default=-1.0)
    parser.add_argument("--report-output", type=Path, default=None, help="Optional JSON report path")
    args = parser.parse_args()

    report = build_dataset_diagnostics(args.data, large_loss_threshold=args.large_loss_threshold)
    payload = json.dumps(report, indent=2, sort_keys=True)
    if args.report_output is not None:
        args.report_output.parent.mkdir(parents=True, exist_ok=True)
        args.report_output.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
