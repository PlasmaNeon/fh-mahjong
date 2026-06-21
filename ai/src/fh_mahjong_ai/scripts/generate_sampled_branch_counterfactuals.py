"""Generate exact branch labels for greedy-vs-sampled checkpoint decisions."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch

from fh_mahjong_ai.action_catalog import action_family
from fh_mahjong_ai.branch_counterfactuals import (
    best_worst_branch_label,
    branch_pair_rows_to_arrays,
)
from fh_mahjong_ai.bridge import build_bridge
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.env import MahjongEnv
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.build_counterfactual_risk_data import write_counterfactual_shard
from fh_mahjong_ai.scripts.generate_data import current_git_commit
from fh_mahjong_ai.storage import load_checkpoint
from fh_mahjong_ai.types import BranchResult, Observation


@dataclass(frozen=True)
class SampledCheckpointDecision:
    greedy_action_id: int
    sampled_action_id: int
    sampled_rank: int
    candidate_action_ids: tuple[int, ...]
    candidate_probabilities: tuple[float, ...]


def choose_greedy_and_sampled_action(
    legal_actions: Sequence[int],
    legal_logits: Sequence[float] | np.ndarray,
    rng: np.random.Generator,
    temperature: float,
    top_k: int,
) -> SampledCheckpointDecision:
    """Choose greedy action and a seeded sampled action from legal logits."""
    actions = np.asarray([int(action_id) for action_id in legal_actions], dtype=np.int64)
    logits = np.asarray(legal_logits, dtype=np.float64)
    if actions.size == 0:
        raise ValueError("cannot choose from an observation with no legal actions")
    if actions.shape[0] != logits.shape[0]:
        raise ValueError("legal_actions and legal_logits must have the same length")

    order = np.argsort(-logits, kind="stable")
    greedy_action_id = int(actions[order[0]])
    effective_top_k = actions.size if int(top_k) <= 0 else min(int(top_k), actions.size)
    candidate_indices = order[:effective_top_k]
    candidate_actions = actions[candidate_indices]
    candidate_logits = logits[candidate_indices]

    if float(temperature) <= 0.0 or effective_top_k == 1:
        probabilities = np.zeros((effective_top_k,), dtype=np.float64)
        probabilities[0] = 1.0
        sampled_index = 0
    else:
        scaled = candidate_logits / float(temperature)
        scaled -= float(np.max(scaled))
        probabilities = np.exp(scaled)
        probabilities /= float(np.sum(probabilities))
        sampled_index = int(rng.choice(np.arange(effective_top_k), p=probabilities))

    return SampledCheckpointDecision(
        greedy_action_id=greedy_action_id,
        sampled_action_id=int(candidate_actions[sampled_index]),
        sampled_rank=int(sampled_index + 1),
        candidate_action_ids=tuple(int(action_id) for action_id in candidate_actions.tolist()),
        candidate_probabilities=tuple(float(probability) for probability in probabilities.tolist()),
    )


@torch.inference_mode()
def checkpoint_decision(
    model: PolicyValueNet,
    observation: Observation,
    rng: np.random.Generator,
    device: str,
    temperature: float,
    top_k: int,
) -> SampledCheckpointDecision:
    legal_actions = observation.legal_actions
    if not legal_actions:
        raise ValueError("observation has no legal actions")

    planes = torch.from_numpy(observation.planes).unsqueeze(0).to(device)
    scalars = torch.from_numpy(observation.scalars).unsqueeze(0).to(device)
    expected_scalars = model.scalar_encoder[0].in_features
    if scalars.shape[1] < expected_scalars:
        scalars = torch.nn.functional.pad(scalars, (0, expected_scalars - scalars.shape[1]))
    elif scalars.shape[1] > expected_scalars:
        raise ValueError(f"expected at most {expected_scalars} scalars, got {scalars.shape[1]}")
    action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0).to(device)
    logits, _ = model(planes, scalars, action_mask)
    legal_logits = logits[0, legal_actions].detach().cpu().numpy()
    return choose_greedy_and_sampled_action(
        legal_actions,
        legal_logits,
        rng=rng,
        temperature=temperature,
        top_k=top_k,
    )


def generate_sampled_branch_counterfactual_dataset(
    episodes: int,
    start_seed: int,
    output_dir: Path,
    checkpoint: Path,
    bridge_kind: str = "go",
    bridge_library_path: Path | None = None,
    match_mode: str = "chongci",
    max_steps_per_episode: int = 0,
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    device: str = "cpu",
    checkpoint_temperature: float = 1.0,
    checkpoint_top_k: int = 3,
    learning_seats: Sequence[int] = (0, 1, 2, 3),
    min_reward_gap: float = 0.0,
    large_loss_threshold: float | None = None,
    high_risk_only: bool = False,
    action_families: Sequence[str] | None = None,
    max_rows: int = 0,
    branch_stop_at_round_end: bool = True,
    branch_max_decisions: int = 0,
    progress_every: int = 0,
    max_elapsed_seconds: float = 0.0,
    seed: int = 1,
) -> dict[str, Any]:
    controlled_seats = tuple(int(seat) for seat in learning_seats)
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
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    checkpoint_step = load_checkpoint(checkpoint, model)
    model.to(device)
    model.eval()
    rng = np.random.default_rng(seed)

    started_at = time.time()
    rows: list[tuple[Observation, Any, dict[str, Any]]] = []
    branch_calls = 0
    branch_results = 0
    skipped_same_action = 0
    skipped_action_family = 0
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
                decision = checkpoint_decision(
                    model,
                    observation,
                    rng=rng,
                    device=device,
                    temperature=checkpoint_temperature,
                    top_k=checkpoint_top_k,
                )
                chosen_action_id = decision.sampled_action_id
                if decision.sampled_action_id == decision.greedy_action_id:
                    skipped_same_action += 1
                elif not decision_matches_families(decision, action_families):
                    skipped_action_family += 1
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
                            greedy_action_id=decision.greedy_action_id,
                            sampled_action_id=decision.sampled_action_id,
                            sampled_rank=decision.sampled_rank,
                            elapsed_seconds=branch_started_at - started_at,
                        )
                    results = bridge.evaluate_branches(
                        [decision.greedy_action_id, decision.sampled_action_id],
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
                        action_families=action_families,
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
                                    "greedy_action_id": decision.greedy_action_id,
                                    "sampled_action_id": decision.sampled_action_id,
                                    "sampled_rank": decision.sampled_rank,
                                    "candidate_action_ids": list(decision.candidate_action_ids),
                                    "candidate_probabilities": list(decision.candidate_probabilities),
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

                step_result = env.step(int(chosen_action_id))
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
        "source": "go_sampled_vs_greedy_branch_evaluation",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": current_git_commit(),
        "checkpoint": str(checkpoint),
        "checkpoint_step": int(checkpoint_step),
        "checkpoint_temperature": float(checkpoint_temperature),
        "checkpoint_top_k": int(checkpoint_top_k),
        "episodes": int(episodes),
        "start_seed": int(start_seed),
        "rows": len(rows),
        "steps": int(steps),
        "branch_calls": int(branch_calls),
        "branch_results": int(branch_results),
        "skipped_same_action": int(skipped_same_action),
        "skipped_action_family": int(skipped_action_family),
        "skipped_no_label": int(skipped_no_label),
        "min_reward_gap": float(min_reward_gap),
        "large_loss_threshold": None if large_loss_threshold is None else float(large_loss_threshold),
        "high_risk_only": bool(high_risk_only),
        "action_families": None if action_families is None else list(action_families),
        "branch_stop_at_round_end": bool(branch_stop_at_round_end),
        "branch_max_decisions": int(branch_max_decisions),
        "match_mode": match_mode,
        "controlled_seats": list(controlled_seats),
        "elapsed_seconds": time.time() - started_at,
        "mean_reward_gap": float(np.mean(arrays["pairwise_reward_delta_targets"])),
        "max_reward_gap": float(np.max(arrays["pairwise_reward_delta_targets"])),
        "preferred_family_counts": family_counts(arrays["pairwise_preferred_action_ids"]),
        "avoided_family_counts": family_counts(arrays["pairwise_avoided_action_ids"]),
        "sampled_preferred_count": int(
            np.count_nonzero(arrays["pairwise_preferred_action_ids"] == arrays["branch_sampled_action_ids"])
        ),
        "greedy_preferred_count": int(
            np.count_nonzero(arrays["pairwise_preferred_action_ids"] == arrays["branch_greedy_action_ids"])
        ),
    }
    manifest = write_counterfactual_shard(output_dir, arrays, metadata)
    return manifest


def decision_matches_families(
    decision: SampledCheckpointDecision,
    action_families: Sequence[str] | None,
) -> bool:
    if action_families is None:
        return True
    allowed = {str(family) for family in action_families}
    return (
        action_family(decision.greedy_action_id) in allowed
        and action_family(decision.sampled_action_id) in allowed
    )


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


def family_counts(action_ids: np.ndarray) -> dict[str, int]:
    counts: dict[str, int] = {}
    for action_id in action_ids.tolist():
        family = action_family(int(action_id))
        counts[family] = counts.get(family, 0) + 1
    return counts


def parse_learning_seats(values: Sequence[int]) -> tuple[int, ...]:
    if not values:
        return (0, 1, 2, 3)
    seats = tuple(int(seat) for seat in values)
    if any(seat < 0 or seat > 3 for seat in seats):
        raise ValueError("--learning-seat values must be 0..3")
    if len(set(seats)) != len(seats):
        raise ValueError("--learning-seat values must be unique")
    return seats


def parse_action_families(values: Sequence[str]) -> tuple[str, ...] | None:
    if not values or any(value == "all" for value in values):
        return None
    return tuple(str(value) for value in values)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate exact branch labels for greedy-vs-sampled checkpoint actions")
    parser.add_argument("--episodes", type=int, required=True)
    parser.add_argument("--start-seed", type=int, default=1)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--bridge-kind", choices=["go", "mock"], default="go")
    parser.add_argument("--bridge-library-path", type=Path, default=None)
    parser.add_argument("--match-mode", choices=["classic", "chongci"], default="chongci")
    parser.add_argument(
        "--max-steps-per-episode",
        type=int,
        default=0,
        help="Episode decision cap. Zero lets the Go bridge use its match-mode default.",
    )
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--checkpoint-temperature", type=float, default=1.0)
    parser.add_argument("--checkpoint-top-k", type=int, default=3)
    parser.add_argument("--learning-seat", type=int, action="append", default=[])
    parser.add_argument("--min-reward-gap", type=float, default=0.0)
    parser.add_argument("--large-loss-threshold", type=float, default=None)
    parser.add_argument("--high-risk-only", action="store_true")
    parser.add_argument(
        "--action-family",
        action="append",
        default=[],
        choices=["all", "discard", "chii", "pon", "kan", "win", "pass", "haitei"],
        help="Restrict rows to decisions where both greedy and sampled actions are in this family. Repeatable. Default all.",
    )
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument(
        "--branch-through-match-end",
        action="store_true",
        help="Roll each branch to match end instead of stopping at the next hand result.",
    )
    parser.add_argument(
        "--branch-max-decisions",
        type=int,
        default=0,
        help="Per-branch decision cap. Zero uses the Go environment cap.",
    )
    parser.add_argument("--progress-every", type=int, default=0)
    parser.add_argument("--max-elapsed-seconds", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    manifest = generate_sampled_branch_counterfactual_dataset(
        episodes=args.episodes,
        start_seed=args.start_seed,
        output_dir=args.output_dir,
        checkpoint=args.checkpoint,
        bridge_kind=args.bridge_kind,
        bridge_library_path=args.bridge_library_path,
        match_mode=args.match_mode,
        max_steps_per_episode=args.max_steps_per_episode,
        chongci_starting_score=args.chongci_starting_score,
        chongci_bust_threshold=args.chongci_bust_threshold,
        chongci_max_hands=args.chongci_max_hands,
        device=args.device,
        checkpoint_temperature=args.checkpoint_temperature,
        checkpoint_top_k=args.checkpoint_top_k,
        learning_seats=parse_learning_seats(args.learning_seat),
        min_reward_gap=args.min_reward_gap,
        large_loss_threshold=args.large_loss_threshold,
        high_risk_only=args.high_risk_only,
        action_families=parse_action_families(args.action_family),
        max_rows=args.max_rows,
        branch_stop_at_round_end=not args.branch_through_match_end,
        branch_max_decisions=args.branch_max_decisions,
        progress_every=args.progress_every,
        max_elapsed_seconds=args.max_elapsed_seconds,
        seed=args.seed,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
