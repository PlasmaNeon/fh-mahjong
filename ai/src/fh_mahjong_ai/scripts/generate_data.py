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
from fh_mahjong_ai.storage import write_transitions_jsonl
from fh_mahjong_ai.trainer import collect_episode
from fh_mahjong_ai.types import Transition


def generate_dataset(
    episodes: int,
    start_seed: int,
    output_path: Path,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
) -> dict:
    """Generate heuristic trajectories and write to JSONL.

    Returns a stats dict with keys: episodes, transitions, elapsed_seconds,
    output_path, and manifest_path.
    """
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    try:
        t0 = time.monotonic()
        if bridge_kind == "mock":
            # MockMahjongBridge does not support generate_heuristic_trajectories;
            # collect episodes manually using reset()/step() with a random policy.
            env = MahjongEnv(config, bridge=bridge)
            policy = RandomMaskedPolicy(seed=start_seed)
            transitions: List[Transition] = []
            for i in range(episodes):
                seed = start_seed + i
                episode = collect_episode(env, policy, seed=seed)
                # Tag each transition with its episode index so backfill_returns works.
                for t in episode:
                    t.info.setdefault("episode_index", i)
                transitions.extend(episode)
        else:
            transitions = bridge.generate_heuristic_trajectories(
                episodes=episodes,
                start_seed=start_seed,
            )
        backfill_returns(transitions)
        write_transitions_jsonl(output_path, transitions)
        elapsed = time.monotonic() - t0
    finally:
        bridge.close()

    stats = {
        "episodes": episodes,
        "transitions": len(transitions),
        "elapsed_seconds": round(elapsed, 2),
        "start_seed": start_seed,
        "end_seed": start_seed + episodes - 1 if episodes > 0 else start_seed,
        "output_path": str(output_path),
    }
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
            "format": "jsonl",
            "episodes": int(stats["episodes"]),
            "transitions": int(stats["transitions"]),
            "start_seed": int(stats["start_seed"]),
            "end_seed": int(stats["end_seed"]),
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
    parser.add_argument("--output", type=Path, default=Path("data/heuristic.jsonl"), help="Output JSONL path")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Output manifest JSON path")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    args = parser.parse_args()

    print(f"Generating {args.episodes} episodes starting at seed {args.start_seed}...")
    stats = generate_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_path=args.output,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
        manifest_path=args.manifest_output,
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")
    print(f"Manifest saved to {stats['manifest_path']}")


if __name__ == "__main__":
    main()
