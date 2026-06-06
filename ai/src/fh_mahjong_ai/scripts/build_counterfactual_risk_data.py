"""Build direct action-risk training shards from tensor-bearing paired traces."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from fh_mahjong_ai.paired_trace import counterfactual_label_from_pair
from fh_mahjong_ai.storage import SHARDED_TRANSITIONS_SCHEMA_VERSION


def build_counterfactual_risk_arrays(
    report_path: Path,
    left_label: str = "anchor",
    right_label: str = "candidate",
    large_loss_threshold: float = -1.0,
    min_reward_gap: float = 0.0,
    high_risk_only: bool = False,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_left_label = str(report.get("left_label") or left_label)
    report_right_label = str(report.get("right_label") or right_label)
    rows: list[dict[str, Any]] = []
    skipped_missing_arrays = 0
    skipped_reward_gap = 0
    skipped_not_high_risk = 0

    for pair in report.get("pairs", []):
        label = counterfactual_label_from_pair(
            pair,
            left_label=report_left_label,
            right_label=report_right_label,
            large_loss_threshold=large_loss_threshold,
        )
        if label is None:
            continue
        if float(label["reward_gap"]) < float(min_reward_gap):
            skipped_reward_gap += 1
            continue
        if high_risk_only and not bool(label["is_high_risk"]):
            skipped_not_high_risk += 1
            continue
        divergence = pair.get("first_divergence") or {}
        avoided_policy = str(label["avoided_policy"])
        step = divergence.get("right" if avoided_policy == report_right_label else "left") or divergence.get(avoided_policy) or {}
        arrays = (step.get("observation") or {}).get("arrays")
        if not arrays:
            skipped_missing_arrays += 1
            continue
        rows.append({"label": label, "arrays": arrays})

    if not rows:
        raise ValueError(
            "no counterfactual rows with observation arrays were found; "
            "rerun paired_trace with --include-observation-arrays"
        )

    planes = np.stack([np.asarray(row["arrays"]["planes"], dtype=np.float32) for row in rows]).astype(np.float32)
    scalars = np.stack([np.asarray(row["arrays"]["scalars"], dtype=np.float32) for row in rows]).astype(np.float32)
    action_mask = np.stack([np.asarray(row["arrays"]["action_mask"], dtype=np.int8) for row in rows]).astype(np.int8)
    seats = np.asarray([int(row["label"]["seat"]) for row in rows], dtype=np.int16)
    action_ids = np.asarray([int(row["label"]["avoided_action_id"]) for row in rows], dtype=np.int64)
    preferred_action_ids = np.asarray([int(row["label"]["preferred_action_id"]) for row in rows], dtype=np.int64)
    reward_gaps = np.asarray([float(row["label"]["reward_gap"]) for row in rows], dtype=np.float32)
    avoided_rewards = np.asarray([float(row["label"]["avoided_reward"]) for row in rows], dtype=np.float32)
    terminal_rewards = np.zeros((len(rows), 4), dtype=np.float32)
    terminal_rewards[np.arange(len(rows)), seats.astype(np.int64)] = avoided_rewards
    decision_indices = np.asarray(
        [int(row["label"]["decision_index"] if row["label"]["decision_index"] is not None else index) for index, row in enumerate(rows)],
        dtype=np.int64,
    )

    payload = {
        "seats": seats,
        "planes": planes,
        "scalars": scalars,
        "action_mask": action_mask,
        "action_ids": action_ids,
        "decision_indices": decision_indices,
        "episode_index": np.asarray([int(row["label"]["seed"]) for row in rows], dtype=np.int64),
        "terminal_rewards": terminal_rewards,
        "sample_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_preferred_action_ids": preferred_action_ids,
        "pairwise_avoided_action_ids": action_ids,
        "pairwise_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_reward_delta_targets": reward_gaps,
    }
    metadata = {
        "source_report": str(report_path),
        "rows": len(rows),
        "left_label": report_left_label,
        "right_label": report_right_label,
        "large_loss_threshold": float(large_loss_threshold),
        "min_reward_gap": float(min_reward_gap),
        "high_risk_only": bool(high_risk_only),
        "skipped_missing_arrays": skipped_missing_arrays,
        "skipped_reward_gap": skipped_reward_gap,
        "skipped_not_high_risk": skipped_not_high_risk,
        "positive_terminal_rows": int(np.count_nonzero(avoided_rewards <= float(large_loss_threshold))),
        "mean_reward_gap": float(np.mean(reward_gaps)),
        "max_reward_gap": float(np.max(reward_gaps)),
    }
    return payload, metadata


def write_counterfactual_shard(output_dir: Path, arrays: dict[str, np.ndarray], metadata: dict[str, Any]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("transitions-*.npz"):
        path.unlink()
    shard_name = "transitions-00000.npz"
    np.savez(output_dir / shard_name, **arrays)
    manifest = {
        "schema_version": SHARDED_TRANSITIONS_SCHEMA_VERSION,
        "format": "npz_shards",
        "compressed": False,
        "shard_size": int(arrays["action_ids"].shape[0]),
        "transitions": int(arrays["action_ids"].shape[0]),
        "shards": [{"path": shard_name, "transitions": int(arrays["action_ids"].shape[0])}],
        "counterfactual": metadata,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build direct counterfactual action-risk shards")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--left-label", type=str, default="anchor")
    parser.add_argument("--right-label", type=str, default="candidate")
    parser.add_argument("--large-loss-threshold", type=float, default=-1.0)
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--high-risk-only", action="store_true")
    args = parser.parse_args()

    arrays, metadata = build_counterfactual_risk_arrays(
        args.report,
        left_label=args.left_label,
        right_label=args.right_label,
        large_loss_threshold=args.large_loss_threshold,
        min_reward_gap=args.min_reward_gap,
        high_risk_only=args.high_risk_only,
    )
    manifest = write_counterfactual_shard(args.output_dir, arrays, metadata)
    print(json.dumps(manifest["counterfactual"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
