"""Generate exact same-state branch counterfactual shards from the Go bridge."""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.branch_counterfactuals import (
    best_worst_branch_label,
    branch_pair_rows_to_arrays,
    legal_discard_actions,
)
from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.scripts.build_counterfactual_risk_data import write_counterfactual_shard
from fh_mahjong_ai.scripts.generate_data import current_git_commit
from fh_mahjong_ai.scripts.generate_selfplay import (
    build_runtime_policies,
    resolve_seat_policies,
)
from fh_mahjong_ai.types import BranchResult, Observation


def generate_branch_counterfactual_dataset(
    episodes: int,
    start_seed: int,
    output_dir: Path,
    seat_policy_values: list[str],
    checkpoint: Optional[Path] = None,
    checkpoint_seat: int = 0,
    bridge_kind: str = "go",
    bridge_library_path: Optional[Path] = None,
    match_mode: str = "chongci",
    max_steps_per_episode: int = 8192,
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    device: str = "cpu",
    min_reward_gap: float = 0.0,
    large_loss_threshold: Optional[float] = None,
    high_risk_only: bool = False,
    max_rows: int = 0,
    max_branch_actions: int = 0,
    branch_stop_at_round_end: bool = True,
    branch_max_decisions: int = 1024,
    progress_every: int = 0,
    max_elapsed_seconds: float = 0.0,
    seed: int = 1,
) -> dict[str, Any]:
    seat_policies = resolve_seat_policies(
        seat_policy_values,
        checkpoint=checkpoint,
        checkpoint_seat=checkpoint_seat,
        bridge_kind=bridge_kind,
    )
    controlled_seats = tuple(spec.seat for spec in seat_policies if spec.controlled)
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
    rng = np.random.default_rng(seed)
    started_at = time.time()
    rows: list[tuple[Observation, Any, dict[str, Any]]] = []
    branch_calls = 0
    branch_results = 0
    skipped_not_enough_discards = 0
    skipped_no_label = 0
    steps = 0

    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge=bridge)
    try:
        for episode_offset in range(episodes):
            episode_index = start_seed + episode_offset
            observation = env.reset(seed=episode_index)
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                continue

            while observation.legal_actions:
                runtime_policy = runtime_policies.get(int(observation.seat))
                if runtime_policy is None:
                    raise RuntimeError(
                        f"bridge returned uncontrolled seat {observation.seat}; "
                        "heuristic seats should be auto-played by the Go bridge"
                    )
                choice = runtime_policy.choose(observation)

                discard_actions = legal_discard_actions(observation)
                selected_branch_actions = select_branch_actions(
                    discard_actions,
                    policy_action_id=int(choice.action_id),
                    max_branch_actions=max_branch_actions,
                    rng=rng,
                )
                if len(selected_branch_actions) < 2:
                    skipped_not_enough_discards += 1
                else:
                    branch_calls += 1
                    branch_started_at = time.time()
                    if should_log_progress(progress_every, branch_calls):
                        log_progress(
                            "branch_start",
                            episode_index=episode_index,
                            steps=steps,
                            rows=len(rows),
                            branch_calls=branch_calls,
                            actions=len(selected_branch_actions),
                            elapsed_seconds=branch_started_at - started_at,
                        )
                    results = bridge.evaluate_branches(
                        selected_branch_actions,
                        stop_at_round_end=branch_stop_at_round_end,
                        max_decisions=branch_max_decisions,
                    )
                    branch_elapsed = time.time() - branch_started_at
                    branch_results += len(results)
                    label = best_worst_branch_label(
                        observation,
                        results,
                        min_reward_gap=min_reward_gap,
                        large_loss_threshold=large_loss_threshold,
                        high_risk_only=high_risk_only,
                    )
                    if label is None:
                        skipped_no_label += 1
                    else:
                        rows.append(
                            (
                                observation,
                                label,
                                {
                                    "episode_index": episode_index,
                                    "acting_seat": int(observation.seat),
                                    "branch_actions": selected_branch_actions,
                                },
                            )
                        )
                        if max_rows > 0 and len(rows) >= max_rows:
                            break
                    if should_log_progress(progress_every, branch_calls):
                        log_progress(
                            "branch_done",
                            episode_index=episode_index,
                            steps=steps,
                            rows=len(rows),
                            branch_calls=branch_calls,
                            branch_results=branch_results,
                            skipped_no_label=skipped_no_label,
                            **summarize_branch_results(results),
                            branch_elapsed_seconds=branch_elapsed,
                            elapsed_seconds=time.time() - started_at,
                        )
                    if max_elapsed_seconds > 0 and (time.time() - started_at) >= max_elapsed_seconds:
                        log_progress(
                            "elapsed_stop",
                            episode_index=episode_index,
                            steps=steps,
                            rows=len(rows),
                            branch_calls=branch_calls,
                            elapsed_seconds=time.time() - started_at,
                        )
                        break

                step_result = env.step(int(choice.action_id))
                steps += 1
                observation = step_result.observation
                if step_result.terminated or step_result.truncated:
                    break
            if max_rows > 0 and len(rows) >= max_rows:
                break
            if max_elapsed_seconds > 0 and (time.time() - started_at) >= max_elapsed_seconds:
                break
    finally:
        bridge.close()

    arrays = branch_pair_rows_to_arrays(rows)
    metadata: dict[str, Any] = {
        "source": "go_branch_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit(),
        "episodes": int(episodes),
        "start_seed": int(start_seed),
        "rows": len(rows),
        "steps": int(steps),
        "branch_calls": int(branch_calls),
        "branch_results": int(branch_results),
        "skipped_not_enough_discards": int(skipped_not_enough_discards),
        "skipped_no_label": int(skipped_no_label),
        "min_reward_gap": float(min_reward_gap),
        "large_loss_threshold": None if large_loss_threshold is None else float(large_loss_threshold),
        "high_risk_only": bool(high_risk_only),
        "max_branch_actions": int(max_branch_actions),
        "branch_stop_at_round_end": bool(branch_stop_at_round_end),
        "branch_max_decisions": int(branch_max_decisions),
        "match_mode": match_mode,
        "controlled_seats": list(controlled_seats),
        "seat_policies": [spec.source_label for spec in seat_policies],
        "elapsed_seconds": time.time() - started_at,
        "mean_reward_gap": float(np.mean(arrays["pairwise_reward_delta_targets"])),
        "max_reward_gap": float(np.max(arrays["pairwise_reward_delta_targets"])),
        "preferred_family_counts": family_counts(arrays["pairwise_preferred_action_ids"]),
        "avoided_family_counts": family_counts(arrays["pairwise_avoided_action_ids"]),
    }
    manifest = write_counterfactual_shard(output_dir, arrays, metadata)
    return manifest


def should_log_progress(progress_every: int, branch_calls: int) -> bool:
    return progress_every > 0 and branch_calls % progress_every == 0


def log_progress(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, sort_keys=True), file=sys.stderr, flush=True)


def summarize_branch_results(results: Sequence[BranchResult]) -> dict[str, int]:
    return {
        "result_errors": sum(1 for result in results if result.error),
        "result_truncated": sum(1 for result in results if result.truncated),
        "result_terminated": sum(1 for result in results if result.terminated),
    }


def select_branch_actions(
    discard_actions: list[int],
    policy_action_id: Optional[int],
    max_branch_actions: int,
    rng: np.random.Generator,
) -> list[int]:
    if max_branch_actions <= 0 or len(discard_actions) <= max_branch_actions:
        return list(discard_actions)
    selected = set(int(action_id) for action_id in rng.choice(discard_actions, size=max_branch_actions, replace=False))
    if policy_action_id is not None and action_family(policy_action_id) == "discard":
        selected.add(int(policy_action_id))
    return sorted(selected)


def family_counts(action_ids: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action_id in action_ids.tolist():
        family = action_family(int(action_id))
        counts[family] = counts.get(family, 0) + 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate exact Go-branch counterfactual discard shards")
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seat-policy", action="append", default=[])
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--checkpoint-seat", type=int, default=0)
    parser.add_argument("--bridge-kind", choices=["go", "mock"], default="go")
    parser.add_argument("--bridge-library-path", type=Path, default=None)
    parser.add_argument("--match-mode", choices=["classic", "chongci"], default="chongci")
    parser.add_argument("--max-steps-per-episode", type=int, default=8192)
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--high-risk-only", action="store_true")
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--max-branch-actions", type=int, default=0)
    parser.add_argument(
        "--branch-through-match-end",
        action="store_true",
        help="Roll each branch to match end instead of stopping at the next hand result.",
    )
    parser.add_argument(
        "--branch-max-decisions",
        type=int,
        default=1024,
        help="Per-branch decision cap. Zero uses the environment max-decision cap.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help="Write JSON progress lines to stderr every N branch evaluations.",
    )
    parser.add_argument(
        "--max-elapsed-seconds",
        type=float,
        default=0.0,
        help="Stop after this wall-clock budget once the current branch evaluation returns. Zero disables.",
    )
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    manifest = generate_branch_counterfactual_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_dir=args.output_dir,
        seat_policy_values=args.seat_policy,
        checkpoint=args.checkpoint,
        checkpoint_seat=args.checkpoint_seat,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_library_path,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        device=args.device,
        min_reward_gap=args.min_reward_gap,
        large_loss_threshold=args.large_loss_threshold,
        high_risk_only=args.high_risk_only,
        max_rows=args.max_rows,
        max_branch_actions=args.max_branch_actions,
        branch_stop_at_round_end=not args.branch_through_match_end,
        branch_max_decisions=args.branch_max_decisions,
        progress_every=args.progress_every,
        max_elapsed_seconds=args.max_elapsed_seconds,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
