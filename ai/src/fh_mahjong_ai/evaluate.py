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
    large_loss_threshold: float = -16.0,
) -> Dict[str, Any]:
    """Run the learned policy for one seat against heuristic opponents.

    Returns aggregate reward and action-frequency metrics.
    """
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(learning_seat,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge)
    policy = TorchGreedyPolicy(model, device=device)

    seat_rewards: List[float] = []
    action_counts: Counter[str] = Counter()
    wins = 0
    large_losses = 0

    def record_episode(rewards: np.ndarray, episode: list[Transition]) -> None:
        nonlocal wins, large_losses
        reward = float(rewards[learning_seat])
        seat_rewards.append(reward)
        if reward > 0:
            wins += 1
        if reward <= large_loss_threshold:
            large_losses += 1
        action_counts.update(action_family(t.action_id) for t in episode)

    try:
        for i in range(episodes):
            seed = seeds[i] if i < len(seeds) else seeds[-1] + i
            episode: list[Transition] = []
            observation = env.reset(seed=seed)
            reset_result = env.last_reset_result
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                record_episode(reset_result.rewards, episode)
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
                    record_episode(step_result.rewards, episode)
                    break
                if not observation.legal_actions:
                    break
    finally:
        env.close()

    completed = len(seat_rewards)
    avg = float(np.mean(seat_rewards)) if seat_rewards else 0.0
    return {
        "seat": learning_seat,
        "avg_reward": round(avg, 2),
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "episodes": completed,
        "per_episode_rewards": seat_rewards,
        "action_family_counts": dict(sorted(action_counts.items())),
    }


def evaluate_duplicate_seats(
    model: nn.Module,
    seeds: Sequence[int],
    seats: Iterable[int] = (0, 1, 2, 3),
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
    large_loss_threshold: float = -16.0,
) -> Dict[str, Any]:
    """Evaluate the same seeds with the learning agent rotated through seats."""
    seat_list = list(seats)
    seat_reports = []
    all_rewards: list[float] = []
    action_counts: Counter[str] = Counter()
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
        )
        seat_reports.append(report)
        all_rewards.extend(float(reward) for reward in report["per_episode_rewards"])
        action_counts.update(report["action_family_counts"])
        wins += int(report["win_count"])
        large_losses += int(report["large_loss_count"])
        completed += int(report["episodes"])

    avg = float(np.mean(all_rewards)) if all_rewards else 0.0
    return {
        "seeds": list(seeds),
        "seats": seat_list,
        "avg_reward": round(avg, 2),
        "win_count": wins,
        "win_rate": wins / completed if completed else 0.0,
        "large_loss_count": large_losses,
        "large_loss_rate": large_losses / completed if completed else 0.0,
        "episodes": completed,
        "per_episode_rewards": all_rewards,
        "action_family_counts": dict(sorted(action_counts.items())),
        "seat_reports": seat_reports,
    }
