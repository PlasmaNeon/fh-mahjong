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


_TAIL_FIELDS = {
    "fourth_share": "per_seed_mean_fourth_share",
    "large_loss": "per_seed_mean_large_loss",
    "training_utility": "per_seed_mean_training_utility",
}
# Spec 2026-08-21 confirmation gate (tail-primary). Reported only; never
# feeds `significant`, which stays the canonical placement test.
FOURTH_PRIMARY_MAX_DELTA = -0.010
CANONICAL_NONINFERIORITY_CI_LOWER = -0.030
LARGE_LOSS_SAFETY_CI_UPPER = 0.005


def _paired_delta(a: np.ndarray, b: np.ndarray) -> Dict[str, Any]:
    d = a - b; n = d.size
    mean = float(d.mean())
    sem = float(np.std(d, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    ci = _t_critical_975(n - 1) * sem if n > 1 else 0.0
    return {"mean_delta": mean, "delta_sem_clustered": sem, "delta_ci95_clustered": ci,
            "ci95_lower": mean - ci, "ci95_upper": mean + ci,
            "a": float(a.mean()), "b": float(b.mean())}


def _tail_metrics(report_a, report_b, num_seeds):
    have_a = all(isinstance(report_a.get(f), list) for f in _TAIL_FIELDS.values())
    have_b = all(isinstance(report_b.get(f), list) for f in _TAIL_FIELDS.values())
    if have_a != have_b:
        raise ValueError("tail-metric arrays present in only one report — regenerate both reports "
                         "with the tail-aware evaluator before a placement-reshape comparison")
    if not have_a:
        return None
    out = {}
    for name, field in _TAIL_FIELDS.items():
        a = np.asarray(report_a[field], dtype=np.float64); b = np.asarray(report_b[field], dtype=np.float64)
        if a.size != num_seeds or b.size != num_seeds:
            raise ValueError(f"{field} length != seed count — ragged tail arrays (fail closed)")
        out[name] = _paired_delta(a, b)
    return out


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

    tail = _tail_metrics(report_a, report_b, num_seeds)
    tail_gate = None
    if tail is not None:
        f, ll = tail["fourth_share"], tail["large_loss"]
        tail_gate = {
            "fourth_primary_pass": bool(f["mean_delta"] <= FOURTH_PRIMARY_MAX_DELTA and f["ci95_upper"] < 0.0),
            "canonical_noninferiority_pass": bool(mean_delta - ci95 > CANONICAL_NONINFERIORITY_CI_LOWER),
            "large_loss_safety_pass": bool(ll["ci95_upper"] <= LARGE_LOSS_SAFETY_CI_UPPER),
        }
        tail_gate["all_pass"] = all(tail_gate.values())

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
        "tail_metrics": tail,
        "tail_gate": tail_gate,
        "deal_in_rate_a": report_a.get("deal_in_rate"),
        "deal_in_rate_b": report_b.get("deal_in_rate"),
        "rank_parity_mismatches_a": report_a.get("rank_parity_mismatches"),
        "rank_parity_mismatches_b": report_b.get("rank_parity_mismatches"),
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
    tail = result.get("tail_metrics")
    if tail is None:
        lines.append("  NOTE: no tail metrics — reports predate the tail-aware evaluator")
    else:
        f, ll, u = tail["fourth_share"], tail["large_loss"], tail["training_utility"]
        lines.append(
            f"  4th-share delta: {f['mean_delta']:+.4f} [{f['ci95_lower']:+.4f}, {f['ci95_upper']:+.4f}]"
        )
        lines.append(
            f"  large-loss delta: {ll['mean_delta']:+.4f} [{ll['ci95_lower']:+.4f}, {ll['ci95_upper']:+.4f}]"
        )
        lines.append(
            f"  training-utility delta: {u['mean_delta']:+.4f} [{u['ci95_lower']:+.4f}, {u['ci95_upper']:+.4f}]"
        )
        lines.append(
            f"  deal-in rate A: {result.get('deal_in_rate_a')}   deal-in rate B: {result.get('deal_in_rate_b')}"
        )
        g = result["tail_gate"]
        lines.append(
            f"  tail gate: {'PASS' if g['all_pass'] else 'FAIL'} "
            f"(primary {'pass' if g['fourth_primary_pass'] else 'fail'}, "
            f"non-inferiority {'pass' if g['canonical_noninferiority_pass'] else 'fail'}, "
            f"safety {'pass' if g['large_loss_safety_pass'] else 'fail'})"
        )
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
