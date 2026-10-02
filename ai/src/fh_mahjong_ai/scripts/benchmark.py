"""Absolute-strength benchmark: a checkpoint vs 3 heuristic bots, Tenhou-style stats.

A YARDSTICK, not a gate (the heuristic bots are far weaker than the champion,
so gate use would saturate). The paired protocol (fh-mj-compare /
fh-mj-evaluate --duplicate-seats) remains the promotion gate.

`--opponent-checkpoint` seats a frozen checkpoint's greedy policy in the other
three seats instead (a strong table), `--symmetry-average suits` plays the
suit-averaged policy, and `--workers N` splits each seat's seeds into chunks
run in N spawn processes. Greedy play on a seeded env is deterministic, so the
chunked report equals the sequential one. `--route-study` records route shanten
at every decision of every seat the loop plays (`route_study.py`) and prints
Independence-vs-standard charts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional, Sequence

from fh_mahjong_ai.evaluate import evaluate_policy_online, reward_summary
from fh_mahjong_ai.hand_stats import (
    bootstrap_hand_stats_ci,
    merge_win_pattern_tallies,
    new_win_pattern_tally,
    summarize_hand_stats,
)
from fh_mahjong_ai.policies import SuitAveragedGreedyPolicy, TorchGreedyPolicy
from fh_mahjong_ai.route_study import format_route_study, merge_route_study
from fh_mahjong_ai.scripts.evaluate import load_opponent_policy, resolve_max_steps_per_episode
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
    tallies: list[dict[str, Any]] = []
    for seat, report in sorted(seat_reports.items()):
        pooled.extend(report["per_match_hand_records"])
        unknown += int(report["hand_stats"]["unknown_hands"])
        seat_placement_counts = placement_rate_counts(
            report.get("per_episode_placements", [])
        )
        for label, count in seat_placement_counts.items():
            overall_placement_counts[label] += count
        tallies.append(report.get("win_pattern_stats", new_win_pattern_tally()))
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
    merged = {
        "overall": {
            "hand_stats": overall_stats,
            "ci95": ci95,
            "placement_counts": overall_placement_counts,
            "placement_rates": _rates_from_counts(overall_placement_counts),
            "win_patterns": merge_win_pattern_tallies(tallies),
        },
        "per_seat": per_seat,
    }
    route_studies = [r["route_study"] for _, r in sorted(seat_reports.items()) if "route_study" in r]
    if route_studies:
        merged["overall"]["route_study"] = merge_route_study(route_studies)
    return merged


def combine_chunk_reports(chunks: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One seat's report from its seed chunks (given in seed order), carrying the
    fields `merge_seat_reports` reads."""
    records = [m for c in chunks for m in c["per_match_hand_records"]]
    unknown = sum(int(c["hand_stats"]["unknown_hands"]) for c in chunks)
    placements = [p for c in chunks for p in c.get("per_episode_placements", [])]
    episodes = sum(int(c["episodes"]) for c in chunks)
    truncations = sum(int(c.get("truncation_count", 0)) for c in chunks)
    outcomes: Counter[str] = Counter()
    for c in chunks:
        outcomes.update(c.get("round_outcome_counts", {}))
    combined = {
        "episodes": episodes,
        "hand_stats": summarize_hand_stats(records, unknown),
        "per_match_hand_records": records,
        "per_episode_placements": placements,
        "mean_placement": reward_summary(placements)["mean"],
        "truncation_count": truncations,
        "truncation_rate": truncations / episodes if episodes else 0.0,
        "round_outcome_counts": dict(sorted(outcomes.items())),
        "win_pattern_stats": merge_win_pattern_tallies(
            [c.get("win_pattern_stats", new_win_pattern_tally()) for c in chunks]),
    }
    route_studies = [c["route_study"] for c in chunks if "route_study" in c]
    if route_studies:
        combined["route_study"] = merge_route_study(route_studies)
    return combined


def plan_chunks(seed_base: int, episodes_per_seat: int, workers: int) -> list[tuple[int, list[int]]]:
    """(seat, seeds) jobs: each seat's disjoint seed range cut into chunks, about
    four per worker so uneven match lengths still balance."""
    chunk = max(1, math.ceil(episodes_per_seat * len(_SEATS) / (4 * workers)))
    jobs = []
    for seat in _SEATS:
        start = seed_base + seat * episodes_per_seat
        seeds = list(range(start, start + episodes_per_seat))
        jobs.extend((seat, seeds[i:i + chunk]) for i in range(0, len(seeds), chunk))
    return jobs


def route_study_shard_path(route_study_dir: Optional[Path], seat: int,
                           seeds: Sequence[int]) -> Optional[Path]:
    """One gzip JSONL shard per (seat, seed range); None when the study is off."""
    if route_study_dir is None:
        return None
    return route_study_dir / f"seat{seat}-seeds{seeds[0]}-{seeds[-1]}.jsonl.gz"


# Per-process policies for the spawn workers, built once by _init_worker.
_WORKER: dict[str, Any] = {}


def _build_policies(checkpoint: Path, device: str, symmetry: str,
                    opponent_checkpoint: Optional[Path]) -> tuple[Any, Optional[Any], Optional[dict], int]:
    model = CheckpointPolicy.from_checkpoint(checkpoint, device=device).model
    event_window = int(model.model_config.event_window)
    policy = (SuitAveragedGreedyPolicy(model, device=device) if symmetry == "suits"
              else TorchGreedyPolicy(model, device=device))
    opponent_policy = opponents = None
    if opponent_checkpoint is not None:
        opponent_policy, opponents = load_opponent_policy(opponent_checkpoint, device, event_window)
    return policy, opponent_policy, opponents, event_window


def _init_worker(checkpoint: Path, device: str, symmetry: str,
                 opponent_checkpoint: Optional[Path], eval_kwargs: dict[str, Any]) -> None:
    import torch
    torch.set_num_threads(1)
    policy, opponent_policy, _, event_window = _build_policies(
        checkpoint, device, symmetry, opponent_checkpoint)
    _WORKER.update(policy=policy, opponent_policy=opponent_policy,
                   event_window=event_window, eval_kwargs=eval_kwargs)


def _run_chunk(seat: int, seeds: list[int], route_study_dir: Optional[Path] = None) -> dict[str, Any]:
    return evaluate_policy_online(
        policy=_WORKER["policy"],
        episodes=len(seeds),
        seeds=seeds,
        learning_seat=seat,
        event_history_window=_WORKER["event_window"],
        opponent_policy=_WORKER["opponent_policy"],
        route_study_shard=route_study_shard_path(route_study_dir, seat, seeds),
        **_WORKER["eval_kwargs"],
    )


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


def format_win_pattern_table(win_patterns: dict[str, Any]) -> str:
    """Scoring patterns of the learning seat's wins vs the other seats' wins: the share of
    wins carrying each pattern and its average points, sorted by the learner's share."""
    sides = [win_patterns[name] for name in ("learner", "opponents")]

    def side_header(label: str, side: dict[str, Any]) -> str:
        wins = side["wins"]
        if not wins:
            return f"{label} (no wins)"
        return (f"{label}: {wins} wins, tsumo {side['tsumo_wins'] / wins * 100:.0f}%, "
                f"avg total {side['total_score_sum'] / wins:.1f}")

    def cell(side: dict[str, Any], pattern_id: str) -> str:
        stats = side["patterns"].get(pattern_id)
        if not stats or not side["wins"]:
            return f"{'-':>8}{'':>9}"
        return f"{stats['count'] / side['wins'] * 100:>7.1f}%{stats['points_sum'] / stats['count']:>9.1f}"

    names: dict[str, str] = {}
    for side in sides:
        for pattern_id, stats in side["patterns"].items():
            names.setdefault(pattern_id, stats["name"])
    order = sorted(names, key=lambda pid: tuple(
        -(side["patterns"].get(pid, {}).get("count", 0)) for side in sides))
    header = f"{'pattern':<40}{'learner':>17}{'opponents':>19}"
    lines = [side_header("learner", sides[0]), side_header("opponents", sides[1]),
             header, f"{'':<40}{'% wins':>8}{'avg pts':>9}{'% wins':>10}{'avg pts':>9}",
             "-" * len(header)]
    for pattern_id in order:
        lines.append(f"{names[pattern_id][:39]:<40}{cell(sides[0], pattern_id)}  {cell(sides[1], pattern_id)}")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a checkpoint vs 3 heuristic bots or a frozen checkpoint "
                    "(absolute-strength yardstick; NOT a promotion gate)")
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
    parser.add_argument("--opponent-checkpoint", type=Path, default=None,
                        help="play the three other seats with this checkpoint's greedy policy "
                             "instead of the heuristic bots (a strong table)")
    parser.add_argument("--symmetry-average", choices=("none", "suits"), default="none",
                        help="play the policy averaged over the 6 suit permutations")
    parser.add_argument("--workers", type=int, default=1,
                        help="spawn processes; each seat's seeds are split into chunks "
                             "(same report as --workers 1)")
    parser.add_argument("--route-study", action="store_true",
                        help="record route shanten at every decision (Independence vs standard) "
                             "and print route charts; raw records go to <out stem>.route-study/")
    args = parser.parse_args(argv)

    if args.episodes_per_seat < 1:
        parser.error("--episodes-per-seat must be >= 1")
    if args.bootstrap_iters < 1:
        parser.error("--bootstrap-iters must be >= 1")
    if args.workers < 1:
        parser.error("--workers must be >= 1")
    if args.opponent_checkpoint is not None and not args.opponent_checkpoint.is_file():
        parser.error(f"--opponent-checkpoint {args.opponent_checkpoint} is not a file")

    out_path = args.out if args.out is not None else Path(str(args.checkpoint) + ".benchmark.json")
    route_study_dir = out_path.parent / (out_path.stem + ".route-study") if args.route_study else None
    if route_study_dir is not None:
        if route_study_dir.exists() and any(route_study_dir.iterdir()):
            parser.error(f"{route_study_dir} is not empty; remove it or choose another --out")
        route_study_dir.mkdir(parents=True, exist_ok=True)

    # Metadata-driven load: architecture (incl. event window) is recovered from
    # the checkpoint itself — no model flags to get wrong. Missing/odd payloads
    # fail loudly inside the loader (checkpoint-metadata invariants).
    max_steps = resolve_max_steps_per_episode(args.match_mode, args.max_steps_per_episode)

    policy, opponent_policy, opponents, event_window = _build_policies(
        args.checkpoint, args.device, args.symmetry_average, args.opponent_checkpoint)
    opponent_label = opponents["checkpoint"] if opponents is not None else "3 heuristic bots"
    eval_kwargs = dict(
        bridge_library_path=args.bridge_library_path,
        match_mode=args.match_mode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        max_steps_per_episode=max_steps,
    )

    seat_reports: dict[int, dict[str, Any]] = {}
    if args.workers == 1:
        for seat in _SEATS:
            start = args.seed_base + seat * args.episodes_per_seat
            seeds = list(range(start, start + args.episodes_per_seat))
            print(f"[benchmark] seat {seat}: {args.episodes_per_seat} {args.match_mode} "
                  f"matches vs {opponent_label}, seeds {seeds[0]}..{seeds[-1]}", flush=True)
            seat_reports[seat] = evaluate_policy_online(
                policy=policy,
                episodes=args.episodes_per_seat,
                seeds=seeds,
                learning_seat=seat,
                event_history_window=event_window,
                opponent_policy=opponent_policy,
                route_study_shard=route_study_shard_path(route_study_dir, seat, seeds),
                **eval_kwargs,
            )
    else:
        jobs = plan_chunks(args.seed_base, args.episodes_per_seat, args.workers)
        print(f"[benchmark] {len(jobs)} chunks over {args.workers} workers, "
              f"{args.episodes_per_seat} {args.match_mode} matches/seat vs {opponent_label}", flush=True)
        chunk_reports: dict[int, dict[str, Any]] = {}
        started = time.perf_counter()
        with ProcessPoolExecutor(
            max_workers=args.workers, mp_context=multiprocessing.get_context("spawn"),
            initializer=_init_worker,
            initargs=(args.checkpoint, args.device, args.symmetry_average,
                      args.opponent_checkpoint, eval_kwargs),
        ) as pool:
            futures = {pool.submit(_run_chunk, seat, seeds, route_study_dir): i
                       for i, (seat, seeds) in enumerate(jobs)}
            for future in as_completed(futures):
                i = futures[future]
                chunk_reports[i] = future.result()
                seat, seeds = jobs[i]
                print(f"[benchmark] chunk {len(chunk_reports)}/{len(jobs)} done: seat {seat} "
                      f"seeds {seeds[0]}..{seeds[-1]} ({time.perf_counter() - started:.0f}s)", flush=True)
        for seat in _SEATS:
            seat_reports[seat] = combine_chunk_reports(
                [chunk_reports[i] for i, (s, _) in enumerate(jobs) if s == seat])

    merged = merge_seat_reports(seat_reports, args.bootstrap_iters, args.bootstrap_seed)

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
        "checkpoint_sha256": hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),
        "policy_transform": {"symmetry": args.symmetry_average},
        "opponents": opponents if opponents is not None else {"kind": "heuristic"},
        "bootstrap": {"iters": args.bootstrap_iters, "seed": args.bootstrap_seed},
        "overall": merged["overall"],
        "per_seat": {str(seat): entry for seat, entry in merged["per_seat"].items()},
    }
    if route_study_dir is not None:
        payload["route_study_records"] = str(route_study_dir)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print()
    print(format_stat_table(merged))
    print()
    print(format_win_pattern_table(merged["overall"]["win_patterns"]))
    if "route_study" in merged["overall"]:
        print()
        print(format_route_study(merged["overall"]["route_study"],
                                 {"learner": str(args.checkpoint), "opponents": opponent_label}))
        print(f"route-study records in {route_study_dir}")
    unknown = merged["overall"]["hand_stats"]["unknown_hands"]
    if unknown:
        print(f"WARNING: {unknown} match(es) completed without any observed hand outcome; "
              "rates use observed hands only")
    print(f"\nreport written to {out_path}")


if __name__ == "__main__":
    main()
