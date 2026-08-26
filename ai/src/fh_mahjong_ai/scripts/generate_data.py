"""Generate heuristic trajectory data for behavior cloning."""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fh_mahjong_ai.bridge import BridgeError, build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.policies import RandomMaskedPolicy
from fh_mahjong_ai.storage import ShardedTransitionWriter, write_transitions_jsonl
from fh_mahjong_ai.offline_trainers import collect_episode
from fh_mahjong_ai.types import Transition

# Episodes per bridge export request when the caller does not specify one.
# Each Go bridge call returns the whole chunk's TrajectoryDataset as a single
# protobuf payload across the ctypes boundary, whose length is carried in a
# 32-bit field. A large chunk (~hundreds of chongci episodes) can exceed 2 GiB
# and get silently truncated to empty, so we cap the default chunk so big
# --episodes requests auto-chunk into bounded, safe payloads.
DEFAULT_CHUNK_SIZE = 20

# Supported --learning-seat-rule values. "all" preserves today's behaviour
# (every seat's transitions are kept); "seed-mod-4" keeps exactly one seat
# per episode, selected by (episode seed - base) % 4 (Amendment 2 §2).
SEAT_RULES = ("all", "seed-mod-4")


def generate_dataset(
    episodes: int,
    start_seed: int,
    output_path: Path,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    chunk_size: Optional[int] = DEFAULT_CHUNK_SIZE,
    output_format: str = "jsonl",
    shard_size: int = 50_000,
    compressed_shards: bool = False,
    match_mode: str = "classic",
    max_steps_per_episode: int = 0,
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    learning_seat_rule: str = "all",
    seat_rule_base_seed: Optional[int] = None,
) -> dict:
    """Generate heuristic trajectories and write to JSONL or NumPy shards.

    Returns a stats dict with keys: episodes, transitions, elapsed_seconds,
    output_path, and manifest_path.

    ``learning_seat_rule`` controls which seats' transitions are kept in each
    chunk, applied before serialization (Amendment 2 §2):
      - "all" (default): keep every seat's transitions (today's behaviour).
      - "seed-mod-4": keep exactly one seat per episode, the seat equal to
        ``(episode_seed - base) % 4`` where ``base`` is ``seat_rule_base_seed``
        (defaulting to ``start_seed``) and ``episode_seed`` is
        ``chunk_seed + (episode_index - episode_offset)``.
    """
    if learning_seat_rule not in SEAT_RULES:
        raise ValueError(
            f"unsupported learning_seat_rule: {learning_seat_rule!r} "
            f"(expected one of {SEAT_RULES})"
        )
    normalized_output_format = normalize_output_format(output_format)
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
        max_steps_per_episode=max_steps_per_episode,
        match_mode=match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
    )
    bridge = build_bridge(config)
    shard_writer: ShardedTransitionWriter | None = None
    chunk_stats: list[dict[str, Any]] = []
    total_transitions = 0
    per_seat: collections.Counter[int] = collections.Counter()
    resolved_seat_rule_base_seed = (
        start_seed if seat_rule_base_seed is None else seat_rule_base_seed
    ) if learning_seat_rule != "all" else None
    try:
        t0 = time.monotonic()
        effective_chunk_size = normalize_chunk_size(episodes, chunk_size)
        if normalized_output_format == "jsonl":
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("", encoding="utf-8")
        else:
            shard_writer = ShardedTransitionWriter(
                output_path,
                shard_size=shard_size,
                compressed=compressed_shards,
            )

        for chunk_index, episode_offset in enumerate(range(0, episodes, effective_chunk_size)):
            chunk_episodes = min(effective_chunk_size, episodes - episode_offset)
            chunk_seed = start_seed + episode_offset
            chunk_t0 = time.monotonic()
            if bridge_kind == "mock":
                transitions = collect_mock_episodes(
                    config=config,
                    bridge=bridge,
                    episodes=chunk_episodes,
                    start_seed=chunk_seed,
                    episode_index_offset=episode_offset,
                )
            else:
                transitions = bridge.generate_heuristic_trajectories(
                    episodes=chunk_episodes,
                    start_seed=chunk_seed,
                )
                offset_episode_indices(transitions, episode_offset)

            if chunk_episodes > 0 and len(transitions) == 0:
                raise BridgeError(
                    f"chunk {chunk_index} generated 0 transitions for "
                    f"{chunk_episodes} episodes (seeds {chunk_seed}.."
                    f"{chunk_seed + chunk_episodes - 1}). This usually means the "
                    f"bridge return payload exceeded its 32-bit size limit and was "
                    f"silently truncated; lower --chunk-size (currently "
                    f"{effective_chunk_size})."
                )

            transitions_before_seat_filter = len(transitions)
            if learning_seat_rule == "seed-mod-4":
                base = resolved_seat_rule_base_seed
                transitions = [
                    t
                    for t in transitions
                    if int(t.observation.seat)
                    == ((chunk_seed + int(t.info["episode_index"]) - episode_offset) - base) % 4
                ]
                if chunk_episodes > 0 and len(transitions) == 0:
                    raise BridgeError(
                        f"chunk {chunk_index} generated 0 transitions for "
                        f"{chunk_episodes} episodes (seeds {chunk_seed}.."
                        f"{chunk_seed + chunk_episodes - 1}) after applying "
                        f"learning_seat_rule={learning_seat_rule!r} (base seed "
                        f"{base}); {transitions_before_seat_filter} transitions "
                        f"existed before the seat filter."
                    )

            for t in transitions:
                per_seat[int(t.observation.seat)] += 1

            backfill_returns(transitions)
            if normalized_output_format == "jsonl":
                write_transitions_jsonl(output_path, transitions, append=True)
            else:
                assert shard_writer is not None
                shard_writer.write_many(transitions)
            total_transitions += len(transitions)
            chunk_elapsed = time.monotonic() - chunk_t0
            chunk_stats.append(
                {
                    "index": chunk_index,
                    "episodes": chunk_episodes,
                    "transitions": len(transitions),
                    "start_seed": chunk_seed,
                    "end_seed": chunk_seed + chunk_episodes - 1 if chunk_episodes > 0 else chunk_seed,
                    "episode_index_offset": episode_offset,
                    "elapsed_seconds": round(chunk_elapsed, 2),
                    "transitions_before_seat_filter": transitions_before_seat_filter,
                }
            )
            print(
                f"chunk {chunk_index + 1}/{(episodes + effective_chunk_size - 1) // effective_chunk_size}: "
                f"episodes={chunk_episodes} transitions={len(transitions)} "
                f"elapsed={chunk_elapsed:.2f}s total_transitions={total_transitions}",
                flush=True,
            )
        shard_manifest = shard_writer.close() if shard_writer is not None else None
        elapsed = time.monotonic() - t0
    finally:
        if shard_writer is not None:
            shard_writer.close()
        bridge.close()

    stats = {
        "episodes": episodes,
        "transitions": total_transitions,
        "elapsed_seconds": round(elapsed, 2),
        "start_seed": start_seed,
        "end_seed": start_seed + episodes - 1 if episodes > 0 else start_seed,
        "output_path": str(output_path),
        "output_format": normalized_output_format,
        "chunk_size": effective_chunk_size,
        "chunks": chunk_stats,
        "shard_size": max(1, int(shard_size)),
        "compressed_shards": compressed_shards,
        "learning_seat_rule": learning_seat_rule,
        "seat_rule_base_seed": resolved_seat_rule_base_seed,
        "per_seat_transitions": {str(seat): count for seat, count in sorted(per_seat.items())},
    }
    if shard_manifest is not None:
        stats["shards"] = shard_manifest["shards"]
        stats["shard_manifest_path"] = str(output_path / "manifest.json")
    manifest = dataset_manifest(
        config=config,
        stats=stats,
        output_path=output_path,
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
    )
    manifest_output = manifest_path or default_manifest_path(output_path)
    write_dataset_manifest(manifest_output, manifest)
    stats["manifest_path"] = str(manifest_output)
    return stats


def normalize_output_format(output_format: str) -> str:
    normalized = output_format.replace("-", "_")
    if normalized not in {"jsonl", "npz_shards"}:
        raise ValueError(f"unsupported output format: {output_format}")
    return normalized


def normalize_chunk_size(episodes: int, chunk_size: Optional[int]) -> int:
    if episodes <= 0:
        return 1
    if chunk_size is None or chunk_size <= 0:
        return episodes
    return min(chunk_size, episodes)


def collect_mock_episodes(
    config: EnvConfig,
    bridge,
    episodes: int,
    start_seed: int,
    episode_index_offset: int,
) -> List[Transition]:
    # MockMahjongBridge does not support generate_heuristic_trajectories; collect
    # episodes manually using reset()/step() with a random policy.
    env = MahjongEnv(config, bridge=bridge)
    policy = RandomMaskedPolicy(seed=start_seed)
    transitions: List[Transition] = []
    for i in range(episodes):
        seed = start_seed + i
        episode = collect_episode(env, policy, seed=seed)
        for t in episode:
            t.info["episode_index"] = episode_index_offset + i
        transitions.extend(episode)
    return transitions


def offset_episode_indices(transitions: List[Transition], episode_index_offset: int) -> None:
    if episode_index_offset == 0:
        return
    for transition in transitions:
        transition.info["episode_index"] = int(transition.info.get("episode_index", 0)) + episode_index_offset


def default_manifest_path(output_path: Path) -> Path:
    if output_path.suffix:
        return output_path.with_suffix(".manifest.json")
    return output_path.with_name(f"{output_path.name}.manifest.json")


def write_dataset_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def dataset_manifest(
    config: EnvConfig,
    stats: dict[str, Any],
    output_path: Path,
    bridge_kind: str,
    bridge_library_path: Optional[Path],
) -> dict[str, Any]:
    policy_source = "mock_random_masked" if bridge_kind == "mock" else "go_heuristic"
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(output_path),
            "format": str(stats["output_format"]),
            "episodes": int(stats["episodes"]),
            "transitions": int(stats["transitions"]),
            "start_seed": int(stats["start_seed"]),
            "end_seed": int(stats["end_seed"]),
            "chunk_size": int(stats["chunk_size"]),
            "elapsed_seconds": float(stats["elapsed_seconds"]),
            "chunks": stats["chunks"],
            "shard_size": int(stats["shard_size"]),
            "compressed_shards": bool(stats["compressed_shards"]),
            "shards": stats.get("shards", []),
            "shard_manifest_path": stats.get("shard_manifest_path"),
            "learning_seat_rule": stats["learning_seat_rule"],
            "seat_rule_base_seed": stats["seat_rule_base_seed"],
            "per_seat_transitions": stats["per_seat_transitions"],
        },
        "source": {
            "policy": policy_source,
            "bridge_kind": bridge_kind,
            "bridge_library_path": str(bridge_library_path) if bridge_library_path else None,
            "git_commit": current_git_commit(),
        },
        "environment": {
            "learning_seats": list(config.learning_seats),
            "auto_play_heuristics": config.auto_play_heuristics,
            "max_steps_per_episode": config.max_steps_per_episode,
            "action_space_size": config.action_space_size,
            "plane_shape": list(config.plane_shape),
            "scalar_features": config.scalar_features,
            "match_mode": config.match_mode,
            "chongci_config": {
                "starting_score": config.chongci_starting_score,
                "bust_threshold": config.chongci_bust_threshold,
                "max_hands": config.chongci_max_hands,
            }
            if config.match_mode == "chongci"
            else None,
        },
        "recommended_seed_splits": {
            "train": [1, 99999],
            "validation": [100001, 100999],
            "evaluation": [200001, 200999],
        },
    }


def current_git_commit() -> str:
    repo_root = None
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            repo_root = parent
            break
    if repo_root is None:
        return "unknown"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate heuristic trajectory data")
    parser.add_argument("--episodes", type=int, default=100, help="Number of episodes")
    parser.add_argument("--start-seed", type=int, default=1, help="Starting RNG seed")
    parser.add_argument("--output", type=Path, default=Path("data/heuristic.jsonl"), help="Output JSONL path or shard directory")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Output manifest JSON path")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument(
        "--format",
        choices=("jsonl", "npz-shards"),
        default="jsonl",
        help="Dataset storage format",
    )
    parser.add_argument("--shard-size", type=int, default=50_000, help="Transitions per NumPy shard")
    parser.add_argument("--compressed-shards", action="store_true", help="Write compressed NumPy shards")
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="classic", help="Simulator match mode")
    parser.add_argument("--max-steps-per-episode", type=int, default=0, help="Bridge decision cap per episode; 0 uses the Go default")
    parser.add_argument("--chongci-starting-score", type=int, default=2000, help="Chongci starting score")
    parser.add_argument("--chongci-bust-threshold", type=int, default=0, help="Chongci bust threshold")
    parser.add_argument("--chongci-max-hands", type=int, default=50, help="Chongci hand cap")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=DEFAULT_CHUNK_SIZE,
        help=(
            "Episodes per bridge export request. Small chunks keep the per-call "
            "payload under the bridge's 32-bit size limit; 0 disables chunking "
            "(unsafe for large --episodes)."
        ),
    )
    parser.add_argument(
        "--learning-seat-rule",
        choices=SEAT_RULES,
        default="all",
        help=(
            "Which seats' transitions to keep before serialization. 'all' keeps "
            "every seat (today's behaviour). 'seed-mod-4' keeps exactly one seat "
            "per episode: (episode_seed - base) %% 4 (Amendment 2 §2)."
        ),
    )
    parser.add_argument(
        "--seat-rule-base-seed",
        type=int,
        default=None,
        help="Base seed for --learning-seat-rule seed-mod-4 (default: --start-seed).",
    )
    args = parser.parse_args()

    print(f"Generating {args.episodes} episodes starting at seed {args.start_seed}...")
    stats = generate_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_path=args.output,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
        manifest_path=args.manifest_output,
        chunk_size=args.chunk_size,
        output_format=args.format,
        shard_size=args.shard_size,
        compressed_shards=args.compressed_shards,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        learning_seat_rule=args.learning_seat_rule,
        seat_rule_base_seed=args.seat_rule_base_seed,
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")
    if "shard_manifest_path" in stats:
        print(f"Shard manifest saved to {stats['shard_manifest_path']}")
    print(f"Manifest saved to {stats['manifest_path']}")


if __name__ == "__main__":
    main()
