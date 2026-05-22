"""Evaluation utilities for comparing a learned policy against baselines."""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence

import numpy as np
import torch
from torch import nn

from .bridge import build_bridge
from .config import EnvConfig
from .env import MahjongEnv
from .policies import TorchGreedyPolicy
from .types import Transition

ACTION_PASS = 0
ACTION_TSUMO = 1
ACTION_RON = 2
ACTION_ACCEPT_HAITEI = 3
ACTION_REFUSE_HAITEI = 4
DISCARD_BASE = 5
DISCARD_COUNT = 42
PON_BASE = DISCARD_BASE + DISCARD_COUNT
PON_COUNT = 34
KAN_DIRECT_BASE = PON_BASE + PON_COUNT
KAN_MODE_COUNT = 34
KAN_CLOSED_BASE = KAN_DIRECT_BASE + KAN_MODE_COUNT
KAN_UPGRADED_BASE = KAN_CLOSED_BASE + KAN_MODE_COUNT
CHII_BASE = KAN_UPGRADED_BASE + KAN_MODE_COUNT
CHII_COUNT = 21


def action_family(action_id: int) -> str:
    if action_id == ACTION_PASS:
        return "pass"
    if action_id in (ACTION_TSUMO, ACTION_RON):
        return "win"
    if action_id in (ACTION_ACCEPT_HAITEI, ACTION_REFUSE_HAITEI):
        return "haitei"
    if DISCARD_BASE <= action_id < DISCARD_BASE + DISCARD_COUNT:
        return "discard"
    if PON_BASE <= action_id < PON_BASE + PON_COUNT:
        return "pon"
    if KAN_DIRECT_BASE <= action_id < KAN_UPGRADED_BASE + KAN_MODE_COUNT:
        return "kan"
    if CHII_BASE <= action_id < CHII_BASE + CHII_COUNT:
        return "chii"
    return "unknown"


def reward_summary(rewards: Sequence[float]) -> Dict[str, Any]:
    values = [float(reward) for reward in rewards]
    if not values:
        return {
            "count": 0,
            "sum": 0.0,
            "mean": 0.0,
            "std": 0.0,
            "min": 0.0,
            "max": 0.0,
            "positive_count": 0,
            "zero_count": 0,
            "negative_count": 0,
            "positive_rate": 0.0,
            "zero_rate": 0.0,
            "negative_rate": 0.0,
        }

    array = np.asarray(values, dtype=np.float32)
    count = int(array.size)
    positive_count = int(np.sum(array > 0))
    zero_count = int(np.sum(array == 0))
    negative_count = int(np.sum(array < 0))
    return {
        "count": count,
        "sum": float(np.sum(array)),
        "mean": float(np.mean(array)),
        "std": float(np.std(array)),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "positive_count": positive_count,
        "zero_count": zero_count,
        "negative_count": negative_count,
        "positive_rate": positive_count / count,
        "zero_rate": zero_count / count,
        "negative_rate": negative_count / count,
    }


def action_family_rates(action_counts: Counter[str]) -> Dict[str, float]:
    total = sum(action_counts.values())
    if total == 0:
        return {}
    return {
        family: count / total
        for family, count in sorted(action_counts.items())
    }


def outcome_rates(outcome_counts: Counter[str]) -> Dict[str, float]:
    total = sum(outcome_counts.values())
    if total == 0:
        return {}
    return {
        name: count / total
        for name, count in sorted(outcome_counts.items())
    }


def update_outcome_counts(outcome_counts: Counter[str], outcome: Optional[dict[str, Any]], learning_seat: int) -> None:
    if not outcome:
        outcome_counts["unknown"] += 1
        return

    if bool(outcome.get("is_draw", False)):
        outcome_counts["draw"] += 1
        return

    winner = int(outcome.get("winner_seat", -1))
    discarder = int(outcome.get("discarder_seat", -1))
    win_type_name = str(outcome.get("win_type_name", ""))

    if win_type_name == "ACTION_TSUMO":
        if winner == learning_seat:
            outcome_counts["tsumo_win"] += 1
        else:
            outcome_counts["tsumo_loss"] += 1
        return

    if win_type_name == "ACTION_RON":
        if winner == learning_seat:
            outcome_counts["ron_win"] += 1
        elif discarder == learning_seat:
            outcome_counts["deal_in"] += 1
        else:
            outcome_counts["ron_other_loss"] += 1
        return

    outcome_counts["other"] += 1


def _normalize_match_mode(match_mode: str) -> str:
    normalized = match_mode.lower()
    if normalized not in {"classic", "chongci"}:
        raise ValueError(f"unsupported match_mode={match_mode!r}; expected 'classic' or 'chongci'")
    return normalized


def _default_large_loss_threshold(match_mode: str) -> float:
    if match_mode == "chongci":
        return -1.0
    return -16.0


def _chongci_report_config(
    match_mode: str,
    starting_score: int,
    bust_threshold: int,
    max_hands: int,
) -> Optional[dict[str, int]]:
    if match_mode != "chongci":
        return None
    return {
        "starting_score": int(starting_score),
        "bust_threshold": int(bust_threshold),
        "max_hands": int(max_hands),
    }


def compute_action_agreement(
    model: nn.Module,
    transitions: List[Transition],
    device: str = "cpu",
    batch_size: int = 1024,
) -> Dict[str, Any]:
    """Compute how often the model's argmax action matches the expert's action.

    Returns dict with aggregate and action-family agreement metrics.
    """
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = len(transitions)
    families: dict[str, dict[str, int]] = {}

    if total == 0:
        return {
            "agreement_rate": 0.0,
            "top3_agreement_rate": 0.0,
            "total_transitions": 0,
            "action_family_counts": {},
            "family_agreement": {},
        }

    batches = (
        {
            "planes": np.stack([t.observation.planes for t in transitions[start : start + max(1, batch_size)]]).astype(
                np.float32,
                copy=False,
            ),
            "scalars": np.stack([t.observation.scalars for t in transitions[start : start + max(1, batch_size)]]).astype(
                np.float32,
                copy=False,
            ),
            "action_mask": np.stack(
                [t.observation.action_mask for t in transitions[start : start + max(1, batch_size)]]
            ).astype(np.int8, copy=False),
            "action_ids": np.asarray(
                [t.action_id for t in transitions[start : start + max(1, batch_size)]],
                dtype=np.int64,
            ),
        }
        for start in range(0, total, max(1, batch_size))
    )
    return compute_action_agreement_from_batches(model, batches, device=device)


def compute_action_agreement_from_batches(
    model: nn.Module,
    batches: Iterator[dict[str, np.ndarray]],
    device: str = "cpu",
) -> Dict[str, Any]:
    """Compute action agreement from pre-batched observation/action arrays."""
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = 0
    families: dict[str, dict[str, int]] = {}

    with torch.inference_mode():
        for batch in batches:
            action_ids = np.asarray(batch["action_ids"], dtype=np.int64)
            if action_ids.size == 0:
                continue

            planes = torch.from_numpy(np.asarray(batch["planes"], dtype=np.float32)).to(device)
            scalars = torch.from_numpy(np.asarray(batch["scalars"], dtype=np.float32)).to(device)
            mask = torch.from_numpy(np.asarray(batch["action_mask"], dtype=np.int8)).to(device)

            logits, _ = model(planes, scalars, mask)
            top_actions_tensor = torch.topk(logits, k=min(3, logits.shape[1]), dim=1).indices.cpu()
            top_actions = top_actions_tensor.numpy()
            predicted_actions = top_actions[:, 0]

            exact_batch = predicted_actions == action_ids
            top3_batch = (top_actions == action_ids[:, None]).any(axis=1)
            exact_matches += int(exact_batch.sum())
            top3_matches += int(top3_batch.sum())
            total += int(action_ids.size)

            for index, action_id in enumerate(action_ids.tolist()):
                family = action_family(int(action_id))
                family_stats = families.setdefault(family, {"total": 0, "exact": 0, "top3": 0})
                family_stats["total"] += 1
                if bool(exact_batch[index]):
                    family_stats["exact"] += 1
                if bool(top3_batch[index]):
                    family_stats["top3"] += 1

    if total == 0:
        return {
            "agreement_rate": 0.0,
            "top3_agreement_rate": 0.0,
            "total_transitions": 0,
            "action_family_counts": {},
            "family_agreement": {},
        }

    family_agreement = {
        family: {
            "total": counts["total"],
            "agreement_rate": counts["exact"] / counts["total"],
            "top3_agreement_rate": counts["top3"] / counts["total"],
        }
        for family, counts in sorted(families.items())
    }

    return {
        "agreement_rate": exact_matches / total,
        "top3_agreement_rate": top3_matches / total,
        "total_transitions": total,
        "action_family_counts": {
            family: counts["total"]
            for family, counts in sorted(families.items())
        },
        "family_agreement": family_agreement,
    }


def evaluate_online(
    model: nn.Module,
    episodes: int,
    seeds: List[int],
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    learning_seat: int = 0,
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
) -> Dict[str, Any]:
    """Run the learned policy for one seat against heuristic opponents.

    Returns aggregate reward and action-frequency metrics.
    """
    normalized_match_mode = _normalize_match_mode(match_mode)
    resolved_large_loss_threshold = (
        float(large_loss_threshold)
        if large_loss_threshold is not None
        else _default_large_loss_threshold(normalized_match_mode)
    )
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(learning_seat,),
        auto_play_heuristics=True,
        match_mode=normalized_match_mode,
        chongci_starting_score=chongci_starting_score,
        chongci_bust_threshold=chongci_bust_threshold,
        chongci_max_hands=chongci_max_hands,
    )
    if max_steps_per_episode is not None:
        config.max_steps_per_episode = int(max_steps_per_episode)
    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge)
    policy = TorchGreedyPolicy(model, device=device)

    seat_rewards: List[float] = []
    action_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    wins = 0
    large_losses = 0

    def record_episode(
        rewards: np.ndarray,
        episode: list[Transition],
        outcome: Optional[dict[str, Any]],
        truncated: bool = False,
    ) -> None:
        nonlocal wins, large_losses
        reward = float(rewards[learning_seat])
        seat_rewards.append(reward)
        if reward > 0:
            wins += 1
        if reward <= resolved_large_loss_threshold:
            large_losses += 1
        action_counts.update(action_family(t.action_id) for t in episode)
        if outcome is None and normalized_match_mode == "chongci":
            outcome_counts["match_truncated" if truncated else "match_end"] += 1
        else:
            update_outcome_counts(outcome_counts, outcome, learning_seat)

    try:
        for i in range(episodes):
            seed = seeds[i] if i < len(seeds) else seeds[-1] + i
            episode: list[Transition] = []
            observation = env.reset(seed=seed)
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                record_episode(
                    reset_result.rewards,
                    episode,
                    reset_result.info.get("round_outcome"),
                    truncated=reset_result.truncated,
                )
                continue
            if not observation.legal_actions:
                continue

            while True:
                choice = policy.choose(observation)
                step_result = env.step(choice.action_id)
                episode.append(
                    Transition(
                        observation=observation,
                        action_id=choice.action_id,
                        rewards=step_result.rewards,
                        next_observation=step_result.observation,
                        terminated=step_result.terminated,
                        truncated=step_result.truncated,
                        info=step_result.info,
                    )
                )

                observation = step_result.observation
                if step_result.terminated or step_result.truncated:
                    record_episode(
                        step_result.rewards,
                        episode,
                        step_result.info.get("round_outcome"),
                        truncated=step_result.truncated,
                    )
                    break
                if not observation.legal_actions:
                    break
    finally:
        env.close()

    completed = len(seat_rewards)
    rewards = reward_summary(seat_rewards)
    positive_reward_count = int(rewards["positive_count"])
    zero_reward_count = int(rewards["zero_count"])
    negative_reward_count = int(rewards["negative_count"])
    return {
        "match_mode": normalized_match_mode,
        "chongci_config": _chongci_report_config(
            normalized_match_mode,
            chongci_starting_score,
            chongci_bust_threshold,
            chongci_max_hands,
        ),
        "seat": learning_seat,
        "avg_reward": round(float(rewards["mean"]), 2),
        "mean_reward": rewards["mean"],
        "reward_sum": rewards["sum"],
        "reward_summary": rewards,
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "win_metric_note": (
            "Backward-compatible reward-positive count; for chongci this is final match net-positive rate, "
            "not single-hand win rate."
            if normalized_match_mode == "chongci"
            else "Reward-positive single-round result."
        ),
        "positive_reward_count": positive_reward_count,
        "positive_reward_rate": rewards["positive_rate"],
        "zero_reward_count": zero_reward_count,
        "zero_reward_rate": rewards["zero_rate"],
        "negative_reward_count": negative_reward_count,
        "negative_reward_rate": rewards["negative_rate"],
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "large_loss_threshold": resolved_large_loss_threshold,
        "episodes": completed,
        "per_episode_rewards": seat_rewards,
        "action_family_counts": dict(sorted(action_counts.items())),
        "action_family_rates": action_family_rates(action_counts),
        "round_outcome_counts": dict(sorted(outcome_counts.items())),
        "round_outcome_rates": outcome_rates(outcome_counts),
    }


def evaluate_duplicate_seats(
    model: nn.Module,
    seeds: Sequence[int],
    seats: Iterable[int] = (0, 1, 2, 3),
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    large_loss_threshold: Optional[float] = None,
    match_mode: str = "classic",
    chongci_starting_score: int = 2000,
    chongci_bust_threshold: int = 0,
    chongci_max_hands: int = 50,
    max_steps_per_episode: Optional[int] = None,
) -> Dict[str, Any]:
    """Evaluate the same seeds with the learning agent rotated through seats."""
    normalized_match_mode = _normalize_match_mode(match_mode)
    seat_list = list(seats)
    seat_reports = []
    all_rewards: list[float] = []
    action_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    wins = 0
    large_losses = 0
    completed = 0

    for seat in seat_list:
        report = evaluate_online(
            model=model,
            episodes=len(seeds),
            seeds=list(seeds),
            bridge_kind=bridge_kind,
            bridge_library_path=bridge_library_path,
            device=device,
            learning_seat=seat,
            large_loss_threshold=large_loss_threshold,
            match_mode=normalized_match_mode,
            chongci_starting_score=chongci_starting_score,
            chongci_bust_threshold=chongci_bust_threshold,
            chongci_max_hands=chongci_max_hands,
            max_steps_per_episode=max_steps_per_episode,
        )
        seat_reports.append(report)
        all_rewards.extend(float(reward) for reward in report["per_episode_rewards"])
        action_counts.update(report["action_family_counts"])
        outcome_counts.update(report.get("round_outcome_counts", {}))
        wins += int(report["win_count"])
        large_losses += int(report["large_loss_count"])
        completed += int(report["episodes"])

    rewards = reward_summary(all_rewards)
    seat_summary = {
        str(report["seat"]): {
            "episodes": report["episodes"],
            "mean_reward": report["mean_reward"],
            "reward_sum": report["reward_sum"],
            "win_rate": report["win_rate"],
            "positive_reward_rate": report["positive_reward_rate"],
            "negative_reward_rate": report["negative_reward_rate"],
            "large_loss_rate": report["large_loss_rate"],
            "action_family_rates": report["action_family_rates"],
            "round_outcome_rates": report.get("round_outcome_rates", {}),
        }
        for report in seat_reports
    }
    return {
        "match_mode": normalized_match_mode,
        "chongci_config": _chongci_report_config(
            normalized_match_mode,
            chongci_starting_score,
            chongci_bust_threshold,
            chongci_max_hands,
        ),
        "seeds": list(seeds),
        "seats": seat_list,
        "avg_reward": round(float(rewards["mean"]), 2),
        "mean_reward": rewards["mean"],
        "reward_sum": rewards["sum"],
        "reward_summary": rewards,
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "win_metric_note": (
            "Backward-compatible reward-positive count; for chongci this is final match net-positive rate, "
            "not single-hand win rate."
            if normalized_match_mode == "chongci"
            else "Reward-positive single-round result."
        ),
        "positive_reward_count": int(rewards["positive_count"]),
        "positive_reward_rate": rewards["positive_rate"],
        "zero_reward_count": int(rewards["zero_count"]),
        "zero_reward_rate": rewards["zero_rate"],
        "negative_reward_count": int(rewards["negative_count"]),
        "negative_reward_rate": rewards["negative_rate"],
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "large_loss_threshold": seat_reports[0]["large_loss_threshold"] if seat_reports else None,
        "episodes": completed,
        "per_episode_rewards": all_rewards,
        "action_family_counts": dict(sorted(action_counts.items())),
        "action_family_rates": action_family_rates(action_counts),
        "round_outcome_counts": dict(sorted(outcome_counts.items())),
        "round_outcome_rates": outcome_rates(outcome_counts),
        "seat_summary": seat_summary,
        "seat_reports": seat_reports,
    }
