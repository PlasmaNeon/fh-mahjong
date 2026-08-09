"""Absolute-strength benchmark: a checkpoint vs 3 heuristic bots, Tenhou-style stats.

A YARDSTICK, not a gate (the heuristic bots are far weaker than the champion,
so gate use would saturate). The paired protocol (fh-mj-compare /
fh-mj-evaluate --duplicate-seats) remains the promotion gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Sequence

from fh_mahjong_ai.evaluate import evaluate_policy_online
from fh_mahjong_ai.hand_stats import bootstrap_hand_stats_ci, summarize_hand_stats
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.scripts.evaluate import resolve_max_steps_per_episode
from fh_mahjong_ai.serving import CheckpointPolicy

_SEATS = (0, 1, 2, 3)

# Canonical GRP placement values (evaluate._EVAL_PLACEMENT_VALUES): 1st..4th.
# Ties receive AVERAGED values (data.placement_shaped_returns), which match no
# rank — they are counted in a separate "tied" bucket rather than mislabeled.
_PLACEMENT_RANKS = (("1st", 1.0), ("2nd", 1.0 / 3.0), ("3rd", -1.0 / 3.0), ("4th", -1.0))


def placement_rate_counts(per_episode_placements: Sequence[float]) -> dict[str, int]:
    """Count matches by final rank from their GRP placement values."""
    counts = {label: 0 for label, _ in _PLACEMENT_RANKS}
    counts["tied"] = 0
    for value in per_episode_placements:
        for label, canonical in _PLACEMENT_RANKS:
            if abs(float(value) - canonical) < 1e-6:
                counts[label] += 1
                break
        else:
            counts["tied"] += 1
    return counts


def _rates_from_counts(counts: dict[str, int]) -> dict[str, float]:
    total = sum(counts.values())
    return {label: count / total if total else 0.0 for label, count in counts.items()}


def merge_seat_reports(
    seat_reports: dict[int, dict[str, Any]],
    bootstrap_iters: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Pool all seats' matches into overall stats + CIs; keep per-seat sheets."""
    pooled: list[list[dict[str, Any]]] = []
    unknown = 0
    per_seat: dict[int, dict[str, Any]] = {}
    overall_placement_counts = {label: 0 for label, _ in _PLACEMENT_RANKS}
    overall_placement_counts["tied"] = 0
    for seat, report in sorted(seat_reports.items()):
        pooled.extend(report["per_match_hand_records"])
        unknown += int(report["hand_stats"]["unknown_hands"])
        seat_placement_counts = placement_rate_counts(
            report.get("per_episode_placements", [])
        )
        for label, count in seat_placement_counts.items():
            overall_placement_counts[label] += count
        per_seat[seat] = {
            "hand_stats": report["hand_stats"],
            "mean_placement": report.get("mean_placement"),
            "truncation_rate": report.get("truncation_rate"),
            "round_outcome_counts": report.get("round_outcome_counts", {}),
            "placement_counts": seat_placement_counts,
            "placement_rates": _rates_from_counts(seat_placement_counts),
        }
    overall_stats = summarize_hand_stats(pooled, unknown)
    ci95 = bootstrap_hand_stats_ci(pooled, iters=bootstrap_iters, seed=bootstrap_seed)
    return {
        "overall": {
            "hand_stats": overall_stats,
            "ci95": ci95,
            "placement_counts": overall_placement_counts,
            "placement_rates": _rates_from_counts(overall_placement_counts),
        },
        "per_seat": per_seat,
    }


def _fmt_rate(value: Optional[float], ci: Optional[list[float]] = None) -> str:
    if value is None:
        return "n/a"
    text = f"{value * 100:.1f}%"
    if ci is not None:
        text += f" [{ci[0] * 100:.1f}, {ci[1] * 100:.1f}]"
    return text


def _fmt_value(value: Optional[float], ci: Optional[list[float]] = None) -> str:
    if value is None:
        return "n/a"
    text = f"{value:.1f}"
    if ci is not None:
        text += f" [{ci[0]:.1f}, {ci[1]:.1f}]"
    return text


def format_stat_table(merged: dict[str, Any]) -> str:
    """Human-readable stat sheet: one row per seat plus pooled overall."""
    header = (
        f"{'':<10}{'win rate 和了率':<28}{'deal-in rate 放铳率':<28}"
        f"{'avg win value':<22}{'avg deal-in loss':<22}{'hands':>7}"
    )
    lines = [header, "-" * len(header)]
    for seat, entry in sorted(merged["per_seat"].items()):
        stats = entry["hand_stats"]
        lines.append(
            f"{f'seat {seat}':<10}"
            f"{_fmt_rate(stats['win_rate']):<28}"
            f"{_fmt_rate(stats['deal_in_rate']):<28}"
            f"{_fmt_value(stats['avg_win_value']):<22}"
            f"{_fmt_value(stats['avg_deal_in_loss']):<22}"
            f"{stats['hands_played']:>7}"
        )
    overall = merged["overall"]["hand_stats"]
    ci = merged["overall"]["ci95"]
    lines.append("-" * len(header))
    lines.append(
        f"{'overall':<10}"
        f"{_fmt_rate(overall['win_rate'], ci['win_rate']):<28}"
        f"{_fmt_rate(overall['deal_in_rate'], ci['deal_in_rate']):<28}"
        f"{_fmt_value(overall['avg_win_value'], ci['avg_win_value']):<22}"
        f"{_fmt_value(overall['avg_deal_in_loss'], ci['avg_deal_in_loss']):<22}"
        f"{overall['hands_played']:>7}"
    )
    lines.append(
        f"matches={overall['matches']}  hands/match={overall['hands_per_match']:.1f}  "
        f"draw rate={_fmt_rate(overall['draw_rate'], ci['draw_rate'])}  "
        f"unknown hands={overall['unknown_hands']}"
    )
    rates = merged["overall"]["placement_rates"]
    placement_line = "placement: " + "  ".join(
        f"{label} {rates[label] * 100:.1f}%" for label, _ in _PLACEMENT_RANKS
    )
    if rates["tied"]:
        placement_line += f"  tied {rates['tied'] * 100:.1f}%"
    lines.append(placement_line)
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a checkpoint vs 3 heuristic bots (absolute-strength "
                    "yardstick; NOT a promotion gate)")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--episodes-per-seat", type=int, default=100,
                        help="matches per seat; the policy plays every seat 0-3")
    parser.add_argument("--seed-base", type=int, default=1000,
                        help="first seed; seats use disjoint consecutive ranges")
    parser.add_argument("--match-mode", type=str, default="chongci",
                        choices=("chongci", "classic"))
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--max-steps-per-episode", type=int, default=None,
                        help="bridge decision cap per match; unset resolves like "
                             "fh-mj-evaluate (chongci gets a budget that reaches "
                             "MATCH_END instead of truncating at EnvConfig's default)")
    parser.add_argument("--bridge-library-path", type=Path, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--bootstrap-iters", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None,
                        help="JSON report path (default: <checkpoint>.benchmark.json)")
    args = parser.parse_args(argv)

    if args.episodes_per_seat < 1:
        parser.error("--episodes-per-seat must be >= 1")
    if args.bootstrap_iters < 1:
        parser.error("--bootstrap-iters must be >= 1")

    # Metadata-driven load: architecture (incl. event window) is recovered from
    # the checkpoint itself — no model flags to get wrong. Missing/odd payloads
    # fail loudly inside the loader (checkpoint-metadata invariants).
    max_steps = resolve_max_steps_per_episode(args.match_mode, args.max_steps_per_episode)

    checkpoint_policy = CheckpointPolicy.from_checkpoint(args.checkpoint, device=args.device)
    model = checkpoint_policy.model
    event_window = int(model.model_config.event_window)
    policy = TorchGreedyPolicy(model, device=args.device)

    seat_reports: dict[int, dict[str, Any]] = {}
    for seat in _SEATS:
        start = args.seed_base + seat * args.episodes_per_seat
        seeds = list(range(start, start + args.episodes_per_seat))
        print(f"[benchmark] seat {seat}: {args.episodes_per_seat} {args.match_mode} "
              f"matches, seeds {seeds[0]}..{seeds[-1]}", flush=True)
        seat_reports[seat] = evaluate_policy_online(
            policy=policy,
            episodes=args.episodes_per_seat,
            seeds=seeds,
            bridge_library_path=args.bridge_library_path,
            learning_seat=seat,
            match_mode=args.match_mode,
            chongci_starting_score=args.chongci_starting_score,
            chongci_bust_threshold=args.chongci_bust_threshold,
            chongci_max_hands=args.chongci_max_hands,
            max_steps_per_episode=max_steps,
            event_history_window=event_window,
        )

    merged = merge_seat_reports(seat_reports, args.bootstrap_iters, args.bootstrap_seed)

    out_path = args.out if args.out is not None else Path(str(args.checkpoint) + ".benchmark.json")
    payload = {
        "checkpoint": str(args.checkpoint),
        "match_mode": args.match_mode,
        "chongci_config": {
            "starting_score": args.chongci_starting_score,
            "bust_threshold": args.chongci_bust_threshold,
            "max_hands": args.chongci_max_hands,
        },
        "episodes_per_seat": args.episodes_per_seat,
        "seed_base": args.seed_base,
        "max_steps_per_episode": max_steps,
        "event_history_window": event_window,
        "bootstrap": {"iters": args.bootstrap_iters, "seed": args.bootstrap_seed},
        "overall": merged["overall"],
        "per_seat": {str(seat): entry for seat, entry in merged["per_seat"].items()},
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print()
    print(format_stat_table(merged))
    unknown = merged["overall"]["hand_stats"]["unknown_hands"]
    if unknown:
        print(f"WARNING: {unknown} match(es) completed without any observed hand outcome; "
              "rates use observed hands only")
    print(f"\nreport written to {out_path}")


if __name__ == "__main__":
    main()
