"""fh-mj-compare: seed-clustered paired comparison of two duplicate-seat reports.

Every promotion or lever-verdict claim must come from this tool run on two
reports produced on the SAME seed window (see the seed-window policy in
docs/rl-papers/chongci-rl-experiment-progress.md).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional, Sequence

import numpy as np

from fh_mahjong_ai.evaluate import _t_critical_975, clustered_placement_stats


def _per_seed_means(report: Dict[str, Any], num_seeds: int) -> list[float]:
    """Per-seed mean placements: the report field when present, otherwise
    reconstructed from seat_reports (reports that predate the field)."""
    means = report.get("per_seed_mean_placements")
    if isinstance(means, list) and len(means) == num_seeds:
        return [float(m) for m in means]
    per_seat = [
        [float(p) for p in seat.get("per_episode_placements", [])]
        for seat in report.get("seat_reports", [])
    ]
    stats = clustered_placement_stats(per_seat)
    if stats["num_seeds"] != num_seeds:
        raise ValueError(
            f"cannot recover per-seed means: report has {stats['num_seeds']} seeds of placements "
            f"but a seed list of {num_seeds}"
        )
    return stats["per_seed_mean_placements"]


def paired_comparison(report_a: Dict[str, Any], report_b: Dict[str, Any]) -> Dict[str, Any]:
    seeds_a = list(report_a.get("seeds", []))
    seeds_b = list(report_b.get("seeds", []))
    if not seeds_a or not seeds_b:
        raise ValueError("both reports must carry a non-empty seed list")
    if seeds_a != seeds_b:
        raise ValueError(
            f"seed lists differ ({len(seeds_a)} vs {len(seeds_b)} seeds; "
            "first mismatch at index "
            f"{next((i for i, (a, b) in enumerate(zip(seeds_a, seeds_b)) if a != b), min(len(seeds_a), len(seeds_b)))}) "
            "— paired comparison requires reports from the SAME seed window"
        )

    num_seeds = len(seeds_a)
    means_a = np.asarray(_per_seed_means(report_a, num_seeds), dtype=np.float64)
    means_b = np.asarray(_per_seed_means(report_b, num_seeds), dtype=np.float64)
    deltas = means_a - means_b

    mean_delta = float(deltas.mean())
    if num_seeds > 1:
        sem = float(np.std(deltas, ddof=1) / np.sqrt(num_seeds))
        ci95 = _t_critical_975(num_seeds - 1) * sem
    else:
        sem = 0.0
        ci95 = 0.0

    return {
        "num_seeds": num_seeds,
        "per_seed_deltas": [float(d) for d in deltas],
        "mean_delta": mean_delta,
        "delta_sem_clustered": sem,
        "delta_ci95_clustered": ci95,
        "mean_placement_a": float(report_a.get("mean_placement", means_a.mean())),
        "mean_placement_b": float(report_b.get("mean_placement", means_b.mean())),
        "large_loss_rate_a": report_a.get("large_loss_rate"),
        "large_loss_rate_b": report_b.get("large_loss_rate"),
        "significant": bool(ci95 > 0.0 and abs(mean_delta) > ci95),
    }


def _format_text(result: Dict[str, Any], label_a: str, label_b: str) -> str:
    lines = [
        f"paired comparison over {result['num_seeds']} wall seeds (A - B)",
        f"  A: {label_a}",
        f"  B: {label_b}",
        f"  mean placement A: {result['mean_placement_a']:+.4f}   large_loss A: {result['large_loss_rate_a']}",
        f"  mean placement B: {result['mean_placement_b']:+.4f}   large_loss B: {result['large_loss_rate_b']}",
        f"  mean delta: {result['mean_delta']:+.4f} ± {result['delta_ci95_clustered']:.4f} (seed-clustered CI95)",
        f"  significant at 95%: {'YES' if result['significant'] else 'no'}",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_a", help="duplicate-seat report JSON (candidate)")
    parser.add_argument("report_b", help="duplicate-seat report JSON (baseline)")
    parser.add_argument("--json", action="store_true", help="emit the comparison dict as JSON")
    args = parser.parse_args(argv)

    with open(args.report_a) as fh:
        report_a = json.load(fh)
    with open(args.report_b) as fh:
        report_b = json.load(fh)

    result = paired_comparison(report_a, report_b)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_text(result, args.report_a, args.report_b))


if __name__ == "__main__":
    main()
