"""Generate heuristic trajectory data for behavior cloning."""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.policies import RandomMaskedPolicy
from fh_mahjong_ai.storage import ShardedTransitionWriter, write_transitions_jsonl
from fh_mahjong_ai.trainer import collect_episode
from fh_mahjong_ai.types import Transition


def generate_dataset(
    episodes: int,
    start_seed: int,
    output_path: Path,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    chunk_size: Optional[int] = None,
    output_format: str = "jsonl",
    shard_size: int = 50_000,
    compressed_shards: bool = False,
) -> dict:
    """Generate heuristic trajectories and write to JSONL or NumPy shards.

    Returns a stats dict with keys: episodes, transitions, elapsed_seconds,
    output_path, and manifest_path.
    """
    normalized_output_format = normalize_output_format(output_format)
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    shard_writer: ShardedTransitionWriter | None = None
    chunk_stats: list[dict[str, Any]] = []
    total_transitions = 0
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

            backfill_returns(transitions)
            if normalized_output_format == "jsonl":
                write_transitions_jsonl(output_path, transitions, append=True)
            else:
                assert shard_writer is not None
                shard_writer.write_many(transitions)
            total_transitions += len(transitions)
            chunk_stats.append(
                {
                    "index": chunk_index,
                    "episodes": chunk_episodes,
                    "transitions": len(transitions),
                    "start_seed": chunk_seed,
                    "end_seed": chunk_seed + chunk_episodes - 1 if chunk_episodes > 0 else chunk_seed,
                    "episode_index_offset": episode_offset,
                }
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
            "chunks": stats["chunks"],
            "shard_size": int(stats["shard_size"]),
            "compressed_shards": bool(stats["compressed_shards"]),
            "shards": stats.get("shards", []),
            "shard_manifest_path": stats.get("shard_manifest_path"),
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
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Episodes per bridge export request (0 disables chunking)",
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
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")
    if "shard_manifest_path" in stats:
        print(f"Shard manifest saved to {stats['shard_manifest_path']}")
    print(f"Manifest saved to {stats['manifest_path']}")


if __name__ == "__main__":
    main()
