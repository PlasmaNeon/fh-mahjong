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


# Evaluation settings that must match for a paired comparison to be a
# measurement of the same experiment. Checked only when a key is present in
# BOTH reports, so reports predating a field remain comparable.
_COMPAT_KEYS = (
    "match_mode",
    "chongci_config",
    "seats",
    "max_steps_per_episode",
    "oracle_observation",
    "large_loss_threshold",
    # Window-on vs window-off is a different observation/decision protocol.
    "event_history_window",
    # SHA-256 of the Go simulator library — two reports from different
    # simulator builds measure different games, not different checkpoints.
    # Deliberate cross-simulator comparisons (e.g. the same checkpoint on a
    # pre-fix vs post-fix encoder) use --allow-bridge-mismatch, which labels
    # the result instead of refusing it.
    "bridge_lib_sha256",
)

# Decision-protocol blocks the fh-mj-evaluate wrapper records only when
# active (greedy runs omit them). These must match EXACTLY across the pair —
# a sampled or search-assisted run is a different policy than a greedy one,
# even on identical seeds. A bare (unwrapped) report has no protocol block
# and therefore only compares equal to another protocol-free report.
_WRAPPER_PROTOCOL_KEYS = ("sampling", "search")

# Run RESULTS recorded inside a protocol block (not parameters): two runs of
# the same protocol legitimately differ on these.
_PROTOCOL_RESULT_KEYS = ("fallback_count",)


def _wrapper_protocol(payload: Dict[str, Any]) -> Dict[str, Any]:
    protocol: Dict[str, Any] = {}
    for key in _WRAPPER_PROTOCOL_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            value = {k: v for k, v in value.items() if k not in _PROTOCOL_RESULT_KEYS}
        if value is not None:
            protocol[key] = value
    return protocol


def _unwrap_report(payload: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Accept both a bare duplicate-seat report and the standard
    fh-mj-evaluate --report-output wrapper (which nests it under "online").

    Returns (duplicate-seat report, effective decision protocol). The
    evaluator persists the protocol blocks inside the online report as well,
    so a bare extracted report keeps its protocol; the wrapper fills gaps for
    reports written before the inner copy existed."""
    if "seeds" in payload:
        return payload, _wrapper_protocol(payload)
    online = payload.get("online")
    if isinstance(online, dict) and "seeds" in online:
        return online, {**_wrapper_protocol(payload), **_wrapper_protocol(online)}
    return payload, {}


def _valid_digest(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def _check_comparable(
    report_a: Dict[str, Any],
    report_b: Dict[str, Any],
    protocol_a: Dict[str, Any],
    protocol_b: Dict[str, Any],
    allow_missing_config: bool,
    allow_bridge_mismatch: bool,
    allow_window_mismatch: bool = False,
) -> None:
    if protocol_a != protocol_b:
        label_a = protocol_a if protocol_a else "greedy"
        label_b = protocol_b if protocol_b else "greedy"
        raise ValueError(
            f"reports are not comparable: decision protocol differs ({label_a!r} vs {label_b!r})"
        )
    for key in _COMPAT_KEYS:
        in_a = key in report_a
        in_b = key in report_b
        if not (in_a and in_b):
            if allow_missing_config:
                continue
            where = "both reports" if not in_a and not in_b else ("report A" if not in_a else "report B")
            raise ValueError(
                f"reports are not comparable: {key} missing from {where}. "
                "A gate verdict requires the full evaluation config in both reports; "
                "pass --allow-missing-config to compare a legacy report anyway "
                "(the result is then NOT a valid promotion gate)"
            )
        if key == "bridge_lib_sha256":
            # A null/malformed digest is ABSENT provenance, not a match: two
            # unverifiable reports must not pass as a strict gate.
            invalid = [
                label
                for label, value in (("A", report_a[key]), ("B", report_b[key]))
                if not _valid_digest(value)
            ]
            if invalid:
                if allow_missing_config:
                    continue
                raise ValueError(
                    f"reports are not comparable: report(s) {' and '.join(invalid)} carry no "
                    f"verifiable simulator provenance (bridge_lib_sha256 null or malformed). "
                    "Regenerate with a readable bridge library, or pass --allow-missing-config "
                    "(the result is then NOT a valid promotion gate)"
                )
        if report_a[key] != report_b[key]:
            if key == "bridge_lib_sha256" and allow_bridge_mismatch:
                continue
            if key == "event_history_window" and allow_window_mismatch:
                # The ONE legitimate cross-protocol promotion comparison: a
                # window-on candidate vs the window-off champion, where the
                # window IS the intervention under test. Labeled, not silent.
                continue
            hint = ""
            if key == "bridge_lib_sha256":
                hint = " — pass --allow-bridge-mismatch for a deliberate cross-simulator comparison"
            elif key == "event_history_window":
                hint = " — pass --allow-window-mismatch when the window itself is the intervention under test"
            raise ValueError(
                f"reports are not comparable: {key} differs "
                f"({report_a[key]!r} vs {report_b[key]!r})" + hint
            )


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


def paired_comparison(
    report_a: Dict[str, Any],
    report_b: Dict[str, Any],
    allow_missing_config: bool = False,
    allow_bridge_mismatch: bool = False,
    allow_window_mismatch: bool = False,
) -> Dict[str, Any]:
    report_a, protocol_a = _unwrap_report(report_a)
    report_b, protocol_b = _unwrap_report(report_b)
    _check_comparable(report_a, report_b, protocol_a, protocol_b, allow_missing_config,
                      allow_bridge_mismatch, allow_window_mismatch)
    bridge_mismatched = (
        report_a.get("bridge_lib_sha256") != report_b.get("bridge_lib_sha256")
    )
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
    duplicates = len(seeds_a) - len(set(seeds_a))
    if duplicates:
        raise ValueError(
            f"seed list contains {duplicates} duplicate wall seed(s) — repeated seeds are "
            "identical simulations, not independent clusters, and would shrink the CI"
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
        # A zero-width CI from perfectly consistent per-seed deltas is the
        # point estimate: a constant nonzero delta IS significant. Only the
        # single-seed case (no df) can never be.
        "significant": bool(num_seeds > 1 and abs(mean_delta) > ci95),
        "config_check": "legacy" if allow_missing_config else "strict",
        "bridge_check": "mismatch-allowed" if bridge_mismatched else "match",
        "window_check": (
            "mismatch-allowed"
            if report_a.get("event_history_window") != report_b.get("event_history_window")
            else "match"
        ),
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
    if result.get("config_check") == "legacy":
        lines.append("  WARNING: --allow-missing-config used — NOT a valid promotion gate")
    if result.get("bridge_check") == "mismatch-allowed":
        lines.append("  WARNING: simulator libraries differ — cross-simulator comparison, not a checkpoint gate")
    if result.get("window_check") == "mismatch-allowed":
        lines.append("  NOTE: event_history_window differs — the window is the intervention under test")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_a", help="duplicate-seat report JSON (candidate)")
    parser.add_argument("report_b", help="duplicate-seat report JSON (baseline)")
    parser.add_argument("--json", action="store_true", help="emit the comparison dict as JSON")
    parser.add_argument(
        "--allow-missing-config",
        action="store_true",
        help="compare legacy reports missing persisted evaluation settings; the result is NOT a valid promotion gate",
    )
    parser.add_argument(
        "--allow-window-mismatch",
        action="store_true",
        help="permit differing event_history_window values — for the promotion comparison where "
        "the window itself is the intervention under test; the result is labeled",
    )
    parser.add_argument(
        "--allow-bridge-mismatch",
        action="store_true",
        help="permit differing simulator library digests for a deliberate cross-simulator comparison "
        "(e.g. the same checkpoint on a pre-fix vs post-fix encoder); the result is labeled, not a checkpoint gate",
    )
    args = parser.parse_args(argv)

    with open(args.report_a) as fh:
        report_a = json.load(fh)
    with open(args.report_b) as fh:
        report_b = json.load(fh)

    result = paired_comparison(
        report_a,
        report_b,
        allow_missing_config=args.allow_missing_config,
        allow_bridge_mismatch=args.allow_bridge_mismatch,
        allow_window_mismatch=args.allow_window_mismatch,
    )
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_text(result, args.report_a, args.report_b))


if __name__ == "__main__":
    main()
