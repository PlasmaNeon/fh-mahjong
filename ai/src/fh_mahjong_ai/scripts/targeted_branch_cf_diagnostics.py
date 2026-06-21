"""Summarize targeted branch-CF proposal quality."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.storage import read_transition_arrays


TARGETED_DIAGNOSTIC_KEYS = (
    "pairwise_preferred_action_ids",
    "pairwise_avoided_action_ids",
    "pairwise_reward_delta_targets",
)

TARGETED_DIAGNOSTIC_OPTIONAL_KEYS = (
    "branch_left_action_ids",
    "branch_right_action_ids",
    "branch_target_actual_deltas",
    "branch_target_predicted_deltas",
)


def targeted_branch_cf_diagnostics(data_paths: Sequence[Path]) -> dict[str, Any]:
    reports = [diagnose_one(path) for path in data_paths]
    return {
        "schema_version": 1,
        "method": "targeted_branch_cf_diagnostics",
        "datasets": reports,
        "combined": combine_reports(reports),
    }


def diagnose_one(path: Path) -> dict[str, Any]:
    arrays = read_transition_arrays(
        path,
        keys=TARGETED_DIAGNOSTIC_KEYS,
        optional_keys=TARGETED_DIAGNOSTIC_OPTIONAL_KEYS,
    )
    preferred = arrays["pairwise_preferred_action_ids"].astype(np.int64, copy=False)
    avoided = arrays["pairwise_avoided_action_ids"].astype(np.int64, copy=False)
    gaps = arrays["pairwise_reward_delta_targets"].astype(np.float32, copy=False)
    left = arrays.get("branch_left_action_ids")
    right = arrays.get("branch_right_action_ids")
    actual_delta = arrays.get("branch_target_actual_deltas")
    predicted_delta = arrays.get("branch_target_predicted_deltas")
    report: dict[str, Any] = {
        "path": str(path),
        "rows": int(preferred.shape[0]),
        "reward_gap": summary(gaps),
        "preferred_family_counts": family_counts(preferred),
        "avoided_family_counts": family_counts(avoided),
    }
    if left is not None:
        report["left_policy"] = action_match_report(left.astype(np.int64, copy=False), preferred, avoided, gaps)
    if right is not None:
        report["right_policy"] = action_match_report(right.astype(np.int64, copy=False), preferred, avoided, gaps)
    if actual_delta is not None:
        report["target_actual_delta"] = summary(actual_delta.astype(np.float32, copy=False), finite_only=True)
    if predicted_delta is not None:
        report["target_predicted_delta"] = summary(predicted_delta.astype(np.float32, copy=False), finite_only=True)
    return report


def action_match_report(
    actions: np.ndarray,
    preferred: np.ndarray,
    avoided: np.ndarray,
    gaps: np.ndarray,
) -> dict[str, Any]:
    valid = actions >= 0
    preferred_match = valid & (actions == preferred)
    avoided_match = valid & (actions == avoided)
    neither_match = valid & ~preferred_match & ~avoided_match
    return {
        "valid_rows": int(np.count_nonzero(valid)),
        "preferred_match_count": int(np.count_nonzero(preferred_match)),
        "preferred_match_rate": rate(preferred_match, valid),
        "avoided_match_count": int(np.count_nonzero(avoided_match)),
        "avoided_match_rate": rate(avoided_match, valid),
        "neither_match_count": int(np.count_nonzero(neither_match)),
        "neither_match_rate": rate(neither_match, valid),
        "preferred_match_reward_gap": summary(gaps[preferred_match]) if np.any(preferred_match) else empty_summary(),
        "avoided_match_reward_gap": summary(gaps[avoided_match]) if np.any(avoided_match) else empty_summary(),
        "action_family_counts": family_counts(actions[valid]),
    }


def combine_reports(reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    rows = int(sum(int(report.get("rows", 0)) for report in reports))
    return {
        "datasets": len(reports),
        "rows": rows,
        "left_policy": combine_policy_reports(reports, "left_policy"),
        "right_policy": combine_policy_reports(reports, "right_policy"),
    }


def combine_policy_reports(reports: Sequence[dict[str, Any]], key: str) -> dict[str, float | int]:
    valid = sum(int((report.get(key) or {}).get("valid_rows", 0)) for report in reports)
    preferred = sum(int((report.get(key) or {}).get("preferred_match_count", 0)) for report in reports)
    avoided = sum(int((report.get(key) or {}).get("avoided_match_count", 0)) for report in reports)
    neither = sum(int((report.get(key) or {}).get("neither_match_count", 0)) for report in reports)
    return {
        "valid_rows": valid,
        "preferred_match_count": preferred,
        "preferred_match_rate": preferred / valid if valid else 0.0,
        "avoided_match_count": avoided,
        "avoided_match_rate": avoided / valid if valid else 0.0,
        "neither_match_count": neither,
        "neither_match_rate": neither / valid if valid else 0.0,
    }


def family_counts(action_ids: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action_id in action_ids.tolist():
        family = action_family(int(action_id))
        counts[family] = counts.get(family, 0) + 1
    return dict(sorted(counts.items()))


def summary(values: np.ndarray, finite_only: bool = False) -> dict[str, float | int]:
    data = np.asarray(values, dtype=np.float32)
    if finite_only:
        data = data[np.isfinite(data)]
    if data.size == 0:
        return empty_summary()
    return {
        "count": int(data.size),
        "mean": float(np.mean(data)),
        "min": float(np.min(data)),
        "max": float(np.max(data)),
    }


def empty_summary() -> dict[str, float | int]:
    return {"count": 0, "mean": 0.0, "min": 0.0, "max": 0.0}


def rate(matches: np.ndarray, valid: np.ndarray) -> float:
    denominator = int(np.count_nonzero(valid))
    return float(np.count_nonzero(matches) / denominator) if denominator else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize targeted branch-CF proposal quality")
    parser.add_argument("--data", type=Path, action="append", required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()

    report = targeted_branch_cf_diagnostics(args.data)
    args.report_output.parent.mkdir(parents=True, exist_ok=True)
    args.report_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    combined = report["combined"]
    print(f"Datasets: {combined['datasets']}")
    print(f"Rows:     {combined['rows']}")
    print(f"Left preferred rate:  {combined['left_policy']['preferred_match_rate']:.2%}")
    print(f"Right preferred rate: {combined['right_policy']['preferred_match_rate']:.2%}")
    print(f"Report saved to {args.report_output}")


if __name__ == "__main__":
    main()
