from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .action_catalog import action_family
from .types import BranchResult, Observation


@dataclass(frozen=True)
class BranchPairLabel:
    seat: int
    preferred_action_id: int
    avoided_action_id: int
    preferred_reward: float
    avoided_reward: float
    reward_gap: float
    preferred_decisions: int
    avoided_decisions: int


def legal_discard_actions(observation: Observation) -> list[int]:
    return [action_id for action_id in observation.legal_actions if action_family(action_id) == "discard"]


def best_worst_branch_label(
    observation: Observation,
    results: Sequence[BranchResult],
    min_reward_gap: float = 0.0,
    large_loss_threshold: float | None = None,
    high_risk_only: bool = False,
    action_families: Sequence[str] | None = ("discard",),
) -> BranchPairLabel | None:
    seat = int(observation.seat)
    allowed_families = None if action_families is None else {str(family) for family in action_families}
    scored: list[tuple[float, BranchResult]] = []
    for result in results:
        if result.error or result.truncated or len(result.rewards) <= seat:
            continue
        if allowed_families is not None and action_family(int(result.action_id)) not in allowed_families:
            continue
        scored.append((float(result.rewards[seat]), result))

    if len(scored) < 2:
        return None

    scored.sort(key=lambda item: item[0])
    avoided_reward, avoided = scored[0]
    preferred_reward, preferred = scored[-1]
    reward_gap = preferred_reward - avoided_reward
    if reward_gap < float(min_reward_gap):
        return None
    if high_risk_only:
        if large_loss_threshold is None:
            raise ValueError("large_loss_threshold is required when high_risk_only=True")
        if avoided_reward > float(large_loss_threshold):
            return None

    return BranchPairLabel(
        seat=seat,
        preferred_action_id=int(preferred.action_id),
        avoided_action_id=int(avoided.action_id),
        preferred_reward=preferred_reward,
        avoided_reward=avoided_reward,
        reward_gap=reward_gap,
        preferred_decisions=int(preferred.decisions),
        avoided_decisions=int(avoided.decisions),
    )


def branch_pair_rows_to_arrays(rows: Sequence[tuple[Observation, BranchPairLabel, dict[str, Any]]]) -> dict[str, np.ndarray]:
    if not rows:
        raise ValueError("cannot build branch counterfactual arrays from zero rows")

    observations = [row[0] for row in rows]
    labels = [row[1] for row in rows]
    metadata = [row[2] for row in rows]
    seats = np.asarray([label.seat for label in labels], dtype=np.int16)
    action_ids = np.asarray([label.avoided_action_id for label in labels], dtype=np.int64)
    terminal_rewards = np.zeros((len(rows), 4), dtype=np.float32)
    terminal_rewards[np.arange(len(rows)), seats.astype(np.int64)] = np.asarray(
        [label.avoided_reward for label in labels],
        dtype=np.float32,
    )

    return {
        "seats": seats,
        "planes": np.stack([obs.planes for obs in observations]).astype(np.float32),
        "scalars": np.stack([obs.scalars for obs in observations]).astype(np.float32),
        "action_mask": np.stack([obs.action_mask for obs in observations]).astype(np.int8),
        "action_ids": action_ids,
        "decision_indices": np.asarray(
            [int(obs.metadata.get("decision_index", -1)) for obs in observations],
            dtype=np.int64,
        ),
        "episode_index": np.asarray([int(item.get("episode_index", 0)) for item in metadata], dtype=np.int64),
        "terminal_rewards": terminal_rewards,
        "rewards": np.zeros((len(rows), 4), dtype=np.float32),
        "next_planes": np.stack([obs.planes for obs in observations]).astype(np.float32),
        "next_scalars": np.stack([obs.scalars for obs in observations]).astype(np.float32),
        "next_action_mask": np.stack([obs.action_mask for obs in observations]).astype(np.int8),
        "terminated": np.zeros(len(rows), dtype=np.bool_),
        "truncated": np.zeros(len(rows), dtype=np.bool_),
        "steps_to_done": np.zeros(len(rows), dtype=np.int32),
        "sample_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_preferred_action_ids": np.asarray(
            [label.preferred_action_id for label in labels],
            dtype=np.int64,
        ),
        "pairwise_avoided_action_ids": np.asarray(
            [label.avoided_action_id for label in labels],
            dtype=np.int64,
        ),
        "pairwise_weights": np.ones(len(rows), dtype=np.float32),
        "pairwise_reward_delta_targets": np.asarray([label.reward_gap for label in labels], dtype=np.float32),
        "branch_preferred_rewards": np.asarray([label.preferred_reward for label in labels], dtype=np.float32),
        "branch_avoided_rewards": np.asarray([label.avoided_reward for label in labels], dtype=np.float32),
        "branch_preferred_decisions": np.asarray([label.preferred_decisions for label in labels], dtype=np.int32),
        "branch_avoided_decisions": np.asarray([label.avoided_decisions for label in labels], dtype=np.int32),
        "branch_greedy_action_ids": np.asarray(
            [int(item.get("greedy_action_id", -1)) for item in metadata],
            dtype=np.int64,
        ),
        "branch_sampled_action_ids": np.asarray(
            [int(item.get("sampled_action_id", -1)) for item in metadata],
            dtype=np.int64,
        ),
        "branch_left_action_ids": np.asarray(
            [int(item.get("left_action_id", -1) if item.get("left_action_id") is not None else -1) for item in metadata],
            dtype=np.int64,
        ),
        "branch_right_action_ids": np.asarray(
            [int(item.get("right_action_id", -1) if item.get("right_action_id") is not None else -1) for item in metadata],
            dtype=np.int64,
        ),
        "branch_target_actual_deltas": np.asarray(
            [
                float(item.get("target_actual_delta", np.nan))
                if item.get("target_actual_delta") is not None
                else np.nan
                for item in metadata
            ],
            dtype=np.float32,
        ),
        "branch_target_predicted_deltas": np.asarray(
            [
                float(item.get("target_predicted_delta", np.nan))
                if item.get("target_predicted_delta") is not None
                else np.nan
                for item in metadata
            ],
            dtype=np.float32,
        ),
        "branch_sampled_ranks": np.asarray(
            [int(item.get("sampled_rank", -1)) for item in metadata],
            dtype=np.int16,
        ),
    }
