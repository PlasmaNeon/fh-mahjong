"""Smoke-test a checkpoint-backed policy through the bridge legality path."""
from __future__ import annotations

import argparse
from pathlib import Path

from fh_mahjong_ai.checkpoint_manifest import DEFAULT_MANIFEST_PATH
from fh_mahjong_ai.serving import load_policy_from_manifest, run_bridge_serving_smoke


def main() -> None:
    parser = argparse.ArgumentParser(description="Run served checkpoint actions through bridge validation")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_PATH)
    parser.add_argument("--checkpoint-id", type=str, default="current")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Override manifest checkpoint path")
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--bridge-kind", choices=("mock", "go"), default="mock")
    parser.add_argument("--bridge-lib", type=Path, default=None)
    parser.add_argument("--episodes", type=int, default=4)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--max-decisions", type=int, default=512)
    args = parser.parse_args()

    policy = load_policy_from_manifest(
        manifest_path=args.manifest,
        checkpoint_id=args.checkpoint_id,
        checkpoint_override=args.checkpoint,
        device=args.device,
    )
    report = run_bridge_serving_smoke(
        policy=policy,
        episodes=args.episodes,
        start_seed=args.start_seed,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_lib,
        max_decisions=args.max_decisions,
    )
    print(f"Loaded checkpoint: {policy.checkpoint_path}")
    print(f"Checkpoint step:   {policy.checkpoint_step}")
    print(f"Episodes:          {report['episodes']}")
    print(f"Decisions:         {report['decisions']}")


if __name__ == "__main__":
    main()
