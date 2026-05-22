"""Generate mixed checkpoint self-play trajectories."""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np

from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.data import backfill_returns
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.policies import RandomMaskedPolicy
from fh_mahjong_ai.scripts.generate_data import (
    current_git_commit,
    default_manifest_path,
    normalize_chunk_size,
    normalize_output_format,
    write_dataset_manifest,
)
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import ShardedTransitionWriter, write_transitions_jsonl
from fh_mahjong_ai.types import Observation, Transition


@dataclass(frozen=True)
class SeatPolicySpec:
    seat: int
    kind: str
    checkpoint_path: Optional[Path] = None
    source_id: int = -1

    @property
    def controlled(self) -> bool:
        return self.kind in {"checkpoint", "random"}

    @property
    def source_label(self) -> str:
        if self.kind == "checkpoint" and self.checkpoint_path is not None:
            return f"checkpoint:{self.checkpoint_path}"
        return self.kind


@dataclass
class RuntimeSeatPolicy:
    spec: SeatPolicySpec
    policy: object

    def choose(self, observation: Observation):
        return self.policy.choose(observation)


def parse_seat_policy(value: str) -> SeatPolicySpec:
    """Parse `seat=heuristic`, `seat=random`, or `seat=checkpoint:/path.pt`."""
    if "=" not in value:
        raise ValueError(f"seat policy must use seat=kind syntax, got {value!r}")
    seat_text, policy_text = value.split("=", 1)
    try:
        seat = int(seat_text)
    except ValueError as exc:
        raise ValueError(f"invalid seat in policy spec {value!r}") from exc
    if seat < 0 or seat > 3:
        raise ValueError(f"seat must be 0..3 in policy spec {value!r}")

    if policy_text == "heuristic":
        return SeatPolicySpec(seat=seat, kind="heuristic")
    if policy_text == "random":
        return SeatPolicySpec(seat=seat, kind="random")
    if policy_text.startswith("checkpoint:"):
        checkpoint_text = policy_text.split(":", 1)[1]
        if not checkpoint_text:
            raise ValueError(f"checkpoint policy requires a path in {value!r}")
        return SeatPolicySpec(seat=seat, kind="checkpoint", checkpoint_path=Path(checkpoint_text))
    raise ValueError(f"unknown policy kind in {value!r}; expected heuristic, random, or checkpoint:<path>")


def resolve_seat_policies(
    seat_policy_values: list[str],
    checkpoint: Optional[Path] = None,
    checkpoint_seat: int = 0,
    bridge_kind: str = "go",
) -> list[SeatPolicySpec]:
    parsed: dict[int, SeatPolicySpec] = {}
    for raw in seat_policy_values:
        spec = parse_seat_policy(raw)
        if spec.seat in parsed:
            raise ValueError(f"duplicate policy for seat {spec.seat}")
        parsed[spec.seat] = spec

    if not parsed and checkpoint is not None:
        if checkpoint_seat < 0 or checkpoint_seat > 3:
            raise ValueError("--checkpoint-seat must be 0..3")
        parsed[checkpoint_seat] = SeatPolicySpec(
            seat=checkpoint_seat,
            kind="checkpoint",
            checkpoint_path=checkpoint,
        )

    if not parsed and bridge_kind == "mock":
        parsed = {seat: SeatPolicySpec(seat=seat, kind="random") for seat in range(4)}

    specs = [parsed.get(seat, SeatPolicySpec(seat=seat, kind="heuristic")) for seat in range(4)]
    controlled = [spec for spec in specs if spec.controlled]
    if not controlled:
        raise ValueError("at least one seat must be controlled by random or checkpoint policy")
    if bridge_kind == "mock" and any(spec.kind == "heuristic" for spec in specs):
        raise ValueError("mock bridge self-play requires all seats to be random or checkpoint policies")

    return [
        SeatPolicySpec(
            seat=spec.seat,
            kind=spec.kind,
            checkpoint_path=spec.checkpoint_path,
            source_id=index,
        )
        for index, spec in enumerate(specs)
    ]


def build_runtime_policies(
    specs: list[SeatPolicySpec],
    device: str = "cpu",
    seed: int = 1,
) -> dict[int, RuntimeSeatPolicy]:
    runtime: dict[int, RuntimeSeatPolicy] = {}
    for spec in specs:
        if spec.kind == "heuristic":
            continue
        if spec.kind == "random":
            policy = RandomMaskedPolicy(seed=seed + spec.seat)
        elif spec.kind == "checkpoint":
            if spec.checkpoint_path is None:
                raise ValueError(f"checkpoint policy for seat {spec.seat} is missing path")
            policy = CheckpointPolicy.from_checkpoint(spec.checkpoint_path, device=device)
        else:
            raise ValueError(f"unsupported policy kind {spec.kind!r}")
        runtime[spec.seat] = RuntimeSeatPolicy(spec=spec, policy=policy)
    return runtime


def collect_mixed_selfplay_episodes(
    config: EnvConfig,
    bridge,
    runtime_policies: dict[int, RuntimeSeatPolicy],
    episodes: int,
    start_seed: int,
    episode_index_offset: int = 0,
) -> list[Transition]:
    env = MahjongEnv(config, bridge=bridge)
    transitions: list[Transition] = []
    for episode_offset in range(episodes):
        episode_index = episode_index_offset + episode_offset
        seed = start_seed + episode_offset
        episode_transitions: list[Transition] = []
        observation = env.reset(seed=seed)
        reset_result = env.last_reset_result
        if reset_result is not None and (reset_result.terminated or reset_result.truncated):
            continue
        if not observation.legal_actions:
            continue

        final_rewards = np.zeros(4, dtype=np.float32)
        final_info: dict[str, Any] = {}
        while True:
            runtime_policy = runtime_policies.get(int(observation.seat))
            if runtime_policy is None:
                raise RuntimeError(
                    f"bridge returned uncontrolled seat {observation.seat}; "
                    "heuristic seats should be auto-played by the Go bridge"
                )

            choice = runtime_policy.choose(observation)
            step_result = env.step(int(choice.action_id))
            info = {
                **step_result.info,
                "episode_index": episode_index,
                "acting_seat": int(observation.seat),
                "policy_source_id": int(runtime_policy.spec.source_id),
                "policy_kind": runtime_policy.spec.kind,
                "policy_source": runtime_policy.spec.source_label,
            }
            if getattr(choice, "value", None) is not None:
                info["policy_value"] = float(choice.value)

            transition = Transition(
                observation=observation,
                action_id=int(choice.action_id),
                rewards=step_result.rewards,
                next_observation=step_result.observation,
                terminated=step_result.terminated,
                truncated=step_result.truncated,
                info=info,
            )
            episode_transitions.append(transition)

            observation = step_result.observation
            final_rewards = np.asarray(step_result.rewards, dtype=np.float32)
            final_info = step_result.info
            if step_result.terminated or step_result.truncated:
                break
            if not observation.legal_actions:
                break

        for transition in episode_transitions:
            transition.info["terminal_rewards"] = final_rewards.copy()
            if "terminal_outcome" not in transition.info and "round_outcome" in final_info:
                transition.info["terminal_outcome"] = final_info["round_outcome"]
        transitions.extend(episode_transitions)

    backfill_returns(transitions)
    return transitions


def generate_mixed_selfplay_dataset(
    episodes: int,
    start_seed: int,
    output_path: Path,
    seat_policies: list[SeatPolicySpec],
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    manifest_path: Optional[Path] = None,
    chunk_size: Optional[int] = None,
    output_format: str = "npz_shards",
    shard_size: int = 50_000,
    compressed_shards: bool = False,
    match_mode: str = "classic",
    max_steps_per_episode: int = 0,
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    device: str = "cpu",
) -> dict[str, Any]:
    normalized_output_format = normalize_output_format(output_format)
    controlled_seats = tuple(spec.seat for spec in seat_policies if spec.controlled)
    if not controlled_seats:
        raise ValueError("mixed self-play needs at least one controlled seat")

    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=controlled_seats,
        auto_play_heuristics=True,
        max_steps_per_episode=max_steps_per_episode,
        match_mode=match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
    )
    runtime_policies = build_runtime_policies(seat_policies, device=device, seed=start_seed)
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
            chunk_t0 = time.monotonic()
            transitions = collect_mixed_selfplay_episodes(
                config=config,
                bridge=bridge,
                runtime_policies=runtime_policies,
                episodes=chunk_episodes,
                start_seed=chunk_seed,
                episode_index_offset=episode_offset,
            )
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

    stats: dict[str, Any] = {
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

    manifest = selfplay_manifest(
        config=config,
        stats=stats,
        output_path=output_path,
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        seat_policies=seat_policies,
    )
    manifest_output = manifest_path or default_manifest_path(output_path)
    write_dataset_manifest(manifest_output, manifest)
    stats["manifest_path"] = str(manifest_output)
    return stats


def selfplay_manifest(
    config: EnvConfig,
    stats: dict[str, Any],
    output_path: Path,
    bridge_kind: str,
    bridge_library_path: Optional[Path],
    seat_policies: list[SeatPolicySpec],
) -> dict[str, Any]:
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
        },
        "source": {
            "policy": "mixed_selfplay",
            "bridge_kind": bridge_kind,
            "bridge_library_path": str(bridge_library_path) if bridge_library_path else None,
            "git_commit": current_git_commit(),
        },
        "seat_policies": [
            {
                "seat": spec.seat,
                "kind": spec.kind,
                "source_id": spec.source_id,
                "source": spec.source_label,
                "checkpoint_path": str(spec.checkpoint_path) if spec.checkpoint_path else None,
                "controlled": spec.controlled,
            }
            for spec in seat_policies
        ],
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate mixed checkpoint self-play trajectory data")
    parser.add_argument("--episodes", type=int, default=100, help="Number of episodes")
    parser.add_argument("--start-seed", type=int, default=1, help="Starting RNG seed")
    parser.add_argument("--output", type=Path, default=Path("data/selfplay-npz"), help="Output JSONL path or shard directory")
    parser.add_argument("--manifest-output", type=Path, default=None, help="Output manifest JSON path")
    parser.add_argument("--bridge-lib", type=Path, default=None, help="Path to c-shared library")
    parser.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    parser.add_argument("--checkpoint", type=Path, default=None, help="Convenience checkpoint for --checkpoint-seat")
    parser.add_argument("--checkpoint-seat", type=int, default=0, help="Seat controlled by --checkpoint when --seat-policy is omitted")
    parser.add_argument(
        "--seat-policy",
        action="append",
        default=[],
        help="Repeatable seat policy, e.g. 0=checkpoint:/path/epoch_004.pt, 1=heuristic, 2=random",
    )
    parser.add_argument(
        "--format",
        choices=("jsonl", "npz-shards"),
        default="npz-shards",
        help="Dataset storage format",
    )
    parser.add_argument("--shard-size", type=int, default=50_000, help="Transitions per NumPy shard")
    parser.add_argument("--compressed-shards", action="store_true", help="Write compressed NumPy shards")
    parser.add_argument("--match-mode", choices=("classic", "chongci"), default="classic", help="Simulator match mode")
    parser.add_argument("--max-steps-per-episode", type=int, default=0, help="Bridge decision cap per episode; 0 uses the Go default")
    parser.add_argument("--chongci-starting-score", type=int, default=2000, help="Chongci starting score")
    parser.add_argument("--chongci-bust-threshold", type=int, default=0, help="Chongci bust threshold")
    parser.add_argument("--chongci-max-hands", type=int, default=50, help="Chongci hand cap")
    parser.add_argument("--chunk-size", type=int, default=100, help="Episodes per generation chunk")
    parser.add_argument("--device", type=str, default="cpu", help="Device for checkpoint policies")
    args = parser.parse_args()

    seat_policies = resolve_seat_policies(
        seat_policy_values=args.seat_policy,
        checkpoint=args.checkpoint,
        checkpoint_seat=args.checkpoint_seat,
        bridge_kind=args.bridge_kind,
    )
    print("Seat policies:")
    for spec in seat_policies:
        print(f"  seat {spec.seat}: {spec.source_label}")

    print(f"Generating {args.episodes} mixed self-play episodes starting at seed {args.start_seed}...")
    stats = generate_mixed_selfplay_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_path=args.output,
        seat_policies=seat_policies,
        bridge_kind=args.bridge_kind,
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
        device=args.device,
    )
    print(f"Done: {stats['transitions']} transitions from {stats['episodes']} episodes in {stats['elapsed_seconds']}s")
    print(f"Saved to {args.output}")
    if "shard_manifest_path" in stats:
        print(f"Shard manifest saved to {stats['shard_manifest_path']}")
    print(f"Manifest saved to {stats['manifest_path']}")


if __name__ == "__main__":
    main()
