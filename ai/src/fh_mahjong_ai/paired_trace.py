"""Paired online trace diagnostics for two Mahjong policies."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

import numpy as np
from torch import nn

from .action_catalog import action_label
from .config import EnvConfig
from .env import MahjongEnv
from .evaluate import action_family, action_family_rates, reward_summary
from .policies import TorchGreedyPolicy
from .types import Observation


SCALAR_NAMES = {
    25: "overall_shanten",
    29: "standard_shanten",
    30: "seven_pairs_shanten",
    31: "independence_shanten",
    32: "ukeire",
    33: "best_discard_post_shanten",
    34: "best_discard_ukeire",
    35: "best_discard_route_delta",
    36: "wild_count",
    37: "best_discard_is_wild",
    38: "visible_score_potential",
    39: "active_discard_danger",
    40: "best_discard_danger",
    41: "discard_danger_range",
    42: "is_chongci",
    43: "hand_progress",
    44: "hands_remaining",
    45: "rank_score",
    46: "leader_pressure",
    47: "large_loss_margin",
    48: "self_bust_margin",
    49: "opponent_large_loss_pressure",
    50: "score_ratio",
    51: "net_score_progress",
    52: "score_gap_right",
    53: "score_gap_across",
    54: "score_gap_left",
    55: "next_rank_pressure",
    56: "lower_rank_cushion",
    57: "public_threat",
}


@dataclass(frozen=True)
class StepTrace:
    index: int
    decision_index: int
    seat: int
    action_id: int
    action_family: str
    action_label: str
    value: Optional[float]
    observation: dict[str, Any]


@dataclass(frozen=True)
class EpisodeTrace:
    seed: int
    seat: int
    reward: float
    terminated: bool
    truncated: bool
    steps: tuple[StepTrace, ...]
    outcome: Optional[dict[str, Any]]


def run_policy_trace(
    model: nn.Module,
    seed: int,
    learning_seat: int,
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    match_mode: str = "chongci",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: int = 20000,
    include_observation_arrays: bool = False,
) -> EpisodeTrace:
    """Run one deterministic seed/seat episode and record every learned-policy decision."""
    config = EnvConfig(
        bridge_kind="go",
        bridge_library_path=None if bridge_library_path is None else Path(bridge_library_path),
        learning_seats=(int(learning_seat),),
        auto_play_heuristics=True,
        match_mode=match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
        max_steps_per_episode=max_steps_per_episode,
    )
    env = MahjongEnv(config)
    policy = TorchGreedyPolicy(model, device=device)
    steps: list[StepTrace] = []
    rewards = np.zeros(4, dtype=np.float32)
    terminated = False
    truncated = False
    outcome: Optional[dict[str, Any]] = None

    try:
        observation = env.reset(seed=seed)
        reset_result = env.last_reset_result
        if reset_result is not None and (reset_result.terminated or reset_result.truncated):
            rewards = np.asarray(reset_result.rewards, dtype=np.float32)
            terminated = bool(reset_result.terminated)
            truncated = bool(reset_result.truncated)
            outcome = reset_result.info.get("round_outcome")
            return EpisodeTrace(
                seed=int(seed),
                seat=int(learning_seat),
                reward=float(rewards[int(learning_seat)]),
                terminated=terminated,
                truncated=truncated,
                steps=tuple(steps),
                outcome=outcome,
            )

        while observation.legal_actions:
            choice = policy.choose(observation)
            steps.append(
                StepTrace(
                    index=len(steps),
                    decision_index=int(observation.metadata.get("decision_index", len(steps))),
                    seat=int(observation.seat),
                    action_id=int(choice.action_id),
                    action_family=action_family(int(choice.action_id)),
                    action_label=action_label(int(choice.action_id)),
                    value=choice.value,
                    observation=summarize_observation(observation, include_arrays=include_observation_arrays),
                )
            )
            result = env.step(int(choice.action_id))
            rewards = np.asarray(result.rewards, dtype=np.float32)
            terminated = bool(result.terminated)
            truncated = bool(result.truncated)
            outcome = result.info.get("round_outcome")
            observation = result.observation
            if terminated or truncated:
                break
    finally:
        env.close()

    return EpisodeTrace(
        seed=int(seed),
        seat=int(learning_seat),
        reward=float(rewards[int(learning_seat)]),
        terminated=terminated,
        truncated=truncated,
        steps=tuple(steps),
        outcome=outcome,
    )


def compare_policy_traces(
    left_model: nn.Module,
    right_model: nn.Module,
    seeds: Sequence[int],
    seats: Iterable[int] = (0, 1, 2, 3),
    left_label: str = "left",
    right_label: str = "right",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    match_mode: str = "chongci",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: int = 20000,
    large_loss_threshold: Optional[float] = None,
    worst_delta_count: int = 8,
    include_observation_arrays: bool = False,
    progress_callback: Optional[Callable[[int, int, int, int], None]] = None,
    pair_callback: Optional[Callable[[dict[str, Any], int, int, int, int], None]] = None,
    existing_pairs: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    pairs = deduplicate_trace_pairs(existing_pairs)
    completed_keys = {(int(pair["seed"]), int(pair["seat"])) for pair in pairs}
    seat_list = [int(seat) for seat in seats]
    seed_list = list(seeds)
    total_pairs = len(seed_list) * len(seat_list)
    completed_pairs = min(len(completed_keys), total_pairs)
    for seat in seat_list:
        for seed in seed_list:
            key = (int(seed), int(seat))
            if key in completed_keys:
                continue
            left = run_policy_trace(
                left_model,
                seed=seed,
                learning_seat=int(seat),
                bridge_library_path=bridge_library_path,
                device=device,
                match_mode=match_mode,
                chongci_starting_score=chongci_starting_score,
                chongci_bust_threshold=chongci_bust_threshold,
                chongci_max_hands=chongci_max_hands,
                max_steps_per_episode=max_steps_per_episode,
                include_observation_arrays=include_observation_arrays,
            )
            right = run_policy_trace(
                right_model,
                seed=seed,
                learning_seat=int(seat),
                bridge_library_path=bridge_library_path,
                device=device,
                match_mode=match_mode,
                chongci_starting_score=chongci_starting_score,
                chongci_bust_threshold=chongci_bust_threshold,
                chongci_max_hands=chongci_max_hands,
                max_steps_per_episode=max_steps_per_episode,
                include_observation_arrays=include_observation_arrays,
            )
            pair = compare_episode_trace(left, right, left_label=left_label, right_label=right_label)
            pairs.append(pair)
            completed_keys.add(key)
            completed_pairs += 1
            if pair_callback is not None:
                pair_callback(pair, completed_pairs, total_pairs, int(seed), int(seat))
            if progress_callback is not None:
                progress_callback(completed_pairs, total_pairs, int(seed), int(seat))

    return summarize_trace_pairs(
        pairs,
        left_label=left_label,
        right_label=right_label,
        large_loss_threshold=large_loss_threshold,
        worst_delta_count=worst_delta_count,
    )


def deduplicate_trace_pairs(pairs: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return pairs with duplicate seed/seat entries removed in first-seen order."""
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for pair in pairs:
        key = (int(pair["seed"]), int(pair["seat"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(pair)
    return deduped


def compare_episode_trace(
    left: EpisodeTrace,
    right: EpisodeTrace,
    left_label: str = "left",
    right_label: str = "right",
) -> dict[str, Any]:
    first_divergence = first_divergence_index(
        [step.action_id for step in left.steps],
        [step.action_id for step in right.steps],
    )
    reward_delta = right.reward - left.reward
    return {
        "seed": left.seed,
        "seat": left.seat,
        f"{left_label}_reward": left.reward,
        f"{right_label}_reward": right.reward,
        "reward_delta": reward_delta,
        f"{left_label}_steps": len(left.steps),
        f"{right_label}_steps": len(right.steps),
        f"{left_label}_outcome": left.outcome,
        f"{right_label}_outcome": right.outcome,
        "first_divergence_index": first_divergence,
        "first_divergence": divergence_payload(left, right, first_divergence),
    }


def summarize_trace_pairs(
    pairs: Sequence[dict[str, Any]],
    left_label: str = "left",
    right_label: str = "right",
    large_loss_threshold: Optional[float] = None,
    worst_delta_count: int = 8,
) -> dict[str, Any]:
    left_rewards = [float(pair[f"{left_label}_reward"]) for pair in pairs]
    right_rewards = [float(pair[f"{right_label}_reward"]) for pair in pairs]
    reward_deltas = [float(pair["reward_delta"]) for pair in pairs]
    divergence_indices = [
        int(pair["first_divergence_index"])
        for pair in pairs
        if pair["first_divergence_index"] is not None
    ]
    divergence_pairs = Counter()
    divergence_contexts: dict[str, Counter[str]] = {
        "rank_score": Counter(),
        "leader_pressure": Counter(),
        "large_loss_margin": Counter(),
        "self_bust_margin": Counter(),
        "opponent_large_loss_pressure": Counter(),
        "discard_danger_range": Counter(),
        "overall_shanten": Counter(),
    }
    for pair in pairs:
        divergence = pair.get("first_divergence")
        if not divergence:
            continue
        left_step = divergence.get("left") or {}
        right_step = divergence.get("right") or {}
        left_family = left_step.get("action_family", "missing")
        right_family = right_step.get("action_family", "missing")
        divergence_pairs[f"{left_family}->{right_family}"] += 1
        context_step = left_step or right_step
        scalars = context_step.get("observation", {}).get("scalars", {})
        for name in divergence_contexts:
            divergence_contexts[name][bucket_scalar(name, scalars.get(name))] += 1
    high_risk = summarize_high_risk_trace_pairs(
        pairs,
        left_label=left_label,
        right_label=right_label,
        large_loss_threshold=large_loss_threshold,
        worst_delta_count=worst_delta_count,
    )
    counterfactual_supervision = summarize_counterfactual_supervision(
        pairs,
        left_label=left_label,
        right_label=right_label,
        large_loss_threshold=large_loss_threshold,
    )

    return {
        "schema_version": 1,
        "left_label": left_label,
        "right_label": right_label,
        "pairs": list(pairs),
        "summary": {
            "episodes": len(pairs),
            f"{left_label}_reward": reward_summary(left_rewards),
            f"{right_label}_reward": reward_summary(right_rewards),
            "reward_delta": reward_summary(reward_deltas),
            f"{right_label}_better_rate": (
                sum(1 for value in reward_deltas if value > 0) / len(reward_deltas)
                if reward_deltas
                else 0.0
            ),
            "same_reward_rate": (
                sum(1 for value in reward_deltas if value == 0) / len(reward_deltas)
                if reward_deltas
                else 0.0
            ),
            "divergence_rate": len(divergence_indices) / len(pairs) if pairs else 0.0,
            "first_divergence_mean_index": (
                float(np.mean(np.asarray(divergence_indices, dtype=np.float32)))
                if divergence_indices
                else None
            ),
            "divergence_action_family_pairs": dict(sorted(divergence_pairs.items())),
            "divergence_context_buckets": {
                name: dict(sorted(counter.items()))
                for name, counter in divergence_contexts.items()
            },
            "counterfactual_supervision": counterfactual_supervision,
            **high_risk,
        },
    }


def summarize_counterfactual_supervision(
    pairs: Sequence[dict[str, Any]],
    left_label: str = "left",
    right_label: str = "right",
    large_loss_threshold: Optional[float] = None,
) -> dict[str, Any]:
    """Summarize direct first-divergence labels from paired outcome differences."""
    labels = []
    avoided_family = Counter()
    preferred_family = Counter()
    family_pairs = Counter()
    tag_counts = Counter()
    high_risk_family = Counter()
    reward_gaps = []
    high_risk_reward_gaps = []

    for pair in pairs:
        label = counterfactual_label_from_pair(
            pair,
            left_label=left_label,
            right_label=right_label,
            large_loss_threshold=large_loss_threshold,
        )
        if label is None:
            continue
        labels.append(label)
        reward_gap = float(label["reward_gap"])
        reward_gaps.append(reward_gap)
        preferred = label["preferred_action_family"]
        avoided = label["avoided_action_family"]
        preferred_family[preferred] += 1
        avoided_family[avoided] += 1
        family_pairs[f"{preferred}->{avoided}"] += 1
        for tag in label["tags"]:
            tag_counts[str(tag)] += 1
        if label["is_high_risk"]:
            high_risk_family[avoided] += 1
            high_risk_reward_gaps.append(reward_gap)

    return {
        "labeled_pairs": len(labels),
        "high_risk_labeled_pairs": int(sum(1 for label in labels if label["is_high_risk"])),
        "avoided_action_family_counts": dict(sorted(avoided_family.items())),
        "preferred_action_family_counts": dict(sorted(preferred_family.items())),
        "preferred_to_avoided_family_counts": dict(sorted(family_pairs.items())),
        "high_risk_avoided_action_family_counts": dict(sorted(high_risk_family.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "reward_gap": _summary_or_empty(reward_gaps),
        "high_risk_reward_gap": _summary_or_empty(high_risk_reward_gaps),
        "discard_avoided_cases": [
            label for label in labels if label["avoided_action_family"] == "discard"
        ][:20],
        "high_risk_cases": [
            label for label in labels if label["is_high_risk"]
        ][:20],
    }


def counterfactual_label_from_pair(
    pair: dict[str, Any],
    left_label: str = "left",
    right_label: str = "right",
    large_loss_threshold: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    divergence = pair.get("first_divergence") or {}
    left_step = divergence.get("left") or divergence.get(left_label)
    right_step = divergence.get("right") or divergence.get(right_label)
    if not left_step or not right_step:
        return None

    left_reward = float(pair[f"{left_label}_reward"])
    right_reward = float(pair[f"{right_label}_reward"])
    if left_reward == right_reward:
        return None
    if left_reward > right_reward:
        preferred_label = left_label
        avoided_label = right_label
        preferred_step = left_step
        avoided_step = right_step
        preferred_reward = left_reward
        avoided_reward = right_reward
        preferred_outcome = pair.get(f"{left_label}_outcome")
        avoided_outcome = pair.get(f"{right_label}_outcome")
    else:
        preferred_label = right_label
        avoided_label = left_label
        preferred_step = right_step
        avoided_step = left_step
        preferred_reward = right_reward
        avoided_reward = left_reward
        preferred_outcome = pair.get(f"{right_label}_outcome")
        avoided_outcome = pair.get(f"{left_label}_outcome")

    seat = int(pair["seat"])
    tags = ["worse_reward"]
    avoided_deal_in = _is_deal_in(avoided_outcome, seat)
    preferred_deal_in = _is_deal_in(preferred_outcome, seat)
    if avoided_deal_in:
        tags.append("avoided_deal_in")
    if avoided_deal_in and not preferred_deal_in:
        tags.append("new_deal_in")
    if large_loss_threshold is not None and avoided_reward <= float(large_loss_threshold):
        tags.append("avoided_large_loss")
        if preferred_reward > float(large_loss_threshold):
            tags.append("new_large_loss")

    is_high_risk = any(tag in tags for tag in ("new_deal_in", "new_large_loss", "avoided_large_loss"))
    context_step = avoided_step or preferred_step
    return {
        "seed": int(pair["seed"]),
        "seat": seat,
        "first_divergence_index": pair.get("first_divergence_index"),
        "decision_index": context_step.get("decision_index"),
        "preferred_policy": preferred_label,
        "avoided_policy": avoided_label,
        "preferred_reward": preferred_reward,
        "avoided_reward": avoided_reward,
        "reward_gap": preferred_reward - avoided_reward,
        "preferred_action_id": preferred_step.get("action_id"),
        "preferred_action_label": preferred_step.get("action_label"),
        "preferred_action_family": preferred_step.get("action_family", "missing"),
        "avoided_action_id": avoided_step.get("action_id"),
        "avoided_action_label": avoided_step.get("action_label"),
        "avoided_action_family": avoided_step.get("action_family", "missing"),
        "tags": sorted(set(tags)),
        "is_high_risk": is_high_risk,
        "scalars": (context_step.get("observation") or {}).get("scalars", {}),
    }


def summarize_high_risk_trace_pairs(
    pairs: Sequence[dict[str, Any]],
    left_label: str = "left",
    right_label: str = "right",
    large_loss_threshold: Optional[float] = None,
    worst_delta_count: int = 8,
) -> dict[str, Any]:
    right_large_losses = []
    new_right_large_losses = []
    if large_loss_threshold is not None:
        for pair in pairs:
            left_reward = float(pair[f"{left_label}_reward"])
            right_reward = float(pair[f"{right_label}_reward"])
            if right_reward <= large_loss_threshold:
                right_large_losses.append(high_risk_pair_payload(pair, left_label, right_label))
                if left_reward > large_loss_threshold:
                    new_right_large_losses.append(high_risk_pair_payload(pair, left_label, right_label))

    worst_pairs = sorted(pairs, key=lambda pair: float(pair["reward_delta"]))[: max(0, int(worst_delta_count))]
    return {
        f"{right_label}_large_loss_cases": right_large_losses,
        f"new_{right_label}_large_loss_cases": new_right_large_losses,
        "worst_reward_delta_cases": [
            high_risk_pair_payload(pair, left_label, right_label)
            for pair in worst_pairs
            if float(pair["reward_delta"]) < 0
        ],
    }


def high_risk_pair_payload(
    pair: dict[str, Any],
    left_label: str,
    right_label: str,
) -> dict[str, Any]:
    divergence = pair.get("first_divergence") or {}
    left_step = divergence.get("left") or divergence.get(left_label) or {}
    right_step = divergence.get("right") or divergence.get(right_label) or {}
    context_step = right_step or left_step
    return {
        "seed": int(pair["seed"]),
        "seat": int(pair["seat"]),
        f"{left_label}_reward": float(pair[f"{left_label}_reward"]),
        f"{right_label}_reward": float(pair[f"{right_label}_reward"]),
        "reward_delta": float(pair["reward_delta"]),
        "first_divergence_index": pair.get("first_divergence_index"),
        f"{left_label}_action_id": left_step.get("action_id"),
        f"{left_label}_action_label": left_step.get("action_label"),
        f"{right_label}_action_id": right_step.get("action_id"),
        f"{right_label}_action_label": right_step.get("action_label"),
        "decision_index": context_step.get("decision_index"),
        "scalars": (context_step.get("observation") or {}).get("scalars", {}),
    }


def first_divergence_index(left_actions: Sequence[int], right_actions: Sequence[int]) -> Optional[int]:
    limit = min(len(left_actions), len(right_actions))
    for index in range(limit):
        if int(left_actions[index]) != int(right_actions[index]):
            return index
    if len(left_actions) != len(right_actions):
        return limit
    return None


def divergence_payload(left: EpisodeTrace, right: EpisodeTrace, index: Optional[int]) -> Optional[dict[str, Any]]:
    if index is None:
        return None
    payload: dict[str, Any] = {}
    if index < len(left.steps):
        payload["left"] = step_payload(left.steps[index])
    else:
        payload["left"] = None
    if index < len(right.steps):
        payload["right"] = step_payload(right.steps[index])
    else:
        payload["right"] = None
    return payload


def step_payload(step: StepTrace) -> dict[str, Any]:
    return {
        "index": step.index,
        "decision_index": step.decision_index,
        "seat": step.seat,
        "action_id": step.action_id,
        "action_family": step.action_family,
        "action_label": step.action_label,
        "value": step.value,
        "observation": step.observation,
    }


def summarize_observation(observation: Observation, include_arrays: bool = False) -> dict[str, Any]:
    family_counts = Counter(action_family(action_id) for action_id in observation.legal_actions)
    scalars = {
        name: float(observation.scalars[index])
        for index, name in SCALAR_NAMES.items()
        if index < observation.scalars.shape[0]
    }
    payload: dict[str, Any] = {
        "decision_index": int(observation.metadata.get("decision_index", 0)),
        "phase": int(observation.metadata.get("phase", 0)),
        "active_player": int(observation.metadata.get("active_player", observation.seat)),
        "seat": int(observation.seat),
        "legal_action_count": int(np.count_nonzero(observation.action_mask)),
        "legal_action_family_rates": action_family_rates(family_counts),
        "scalars": scalars,
    }
    if include_arrays:
        payload["arrays"] = {
            "planes": observation.planes.astype(np.float32, copy=False).tolist(),
            "scalars": observation.scalars.astype(np.float32, copy=False).tolist(),
            "action_mask": observation.action_mask.astype(np.int8, copy=False).tolist(),
        }
    return payload


def bucket_scalar(name: str, value: Optional[float]) -> str:
    if value is None:
        return "missing"
    if name in {
        "rank_score",
        "leader_pressure",
        "large_loss_margin",
        "self_bust_margin",
        "opponent_large_loss_pressure",
        "discard_danger_range",
        "overall_shanten",
    }:
        if value < 0.25:
            return "0.00-0.25"
        if value < 0.50:
            return "0.25-0.50"
        if value < 0.75:
            return "0.50-0.75"
        return "0.75-1.00"
    return "present"


def _summary_or_empty(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"count": 0, "mean": None, "min": None, "max": None}
    array = np.asarray(values, dtype=np.float32)
    return {
        "count": int(array.size),
        "mean": float(np.mean(array)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
    }


def _is_deal_in(outcome: Any, seat: int) -> bool:
    if not isinstance(outcome, dict):
        return False
    try:
        discarder_seat = int(outcome.get("discarder_seat", -1))
    except (TypeError, ValueError):
        return False
    return discarder_seat == int(seat) and discarder_seat >= 0
