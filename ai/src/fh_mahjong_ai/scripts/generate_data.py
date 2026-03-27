"""Generate heuristic trajectory data for behavior cloning."""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import List, Optional

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
) -> dict:
    """Generate heuristic trajectories and write to JSONL.

    Returns a stats dict with keys: episodes, transitions, elapsed_seconds.
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

    return {
        "episodes": episodes,
        "transitions": len(transitions),
        "elapsed_seconds": round(elapsed, 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate heuristic trajectory data")
    parser.add_argument("--episodes", type=int, default=100, help="Number of episodes")
    parser.add_argument("--start-seed", type=int, default=1, help="Starting RNG seed")
    parser.add_argument("--output", type=Path, default=Path("data/heuristic.jsonl"), help="Output JSONL path")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    args = parser.parse_args()

    print(f"Generating {args.episodes} episodes starting at seed {args.start_seed}...")
    stats = generate_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_path=args.output,
        bridge_kind="go",
        bridge_library_path=args.bridge_lib,
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
