"""Evaluation utilities for comparing a learned policy against baselines."""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import torch
from torch import nn

from .bridge import build_bridge
from .config import EnvConfig
from .env import MahjongEnv
from .policies import TorchGreedyPolicy
from .trainer import collect_episode
from .types import Transition


def compute_action_agreement(
    model: nn.Module,
    transitions: List[Transition],
    device: str = "cpu",
) -> Dict[str, float]:
    """Compute how often the model's argmax action matches the expert's action.

    Returns dict with: agreement_rate, top3_agreement_rate, total_transitions.
    """
    model.eval()
    exact_matches = 0
    top3_matches = 0
    total = len(transitions)

    if total == 0:
        return {"agreement_rate": 0.0, "top3_agreement_rate": 0.0, "total_transitions": 0}

    with torch.inference_mode():
        for t in transitions:
            planes = torch.from_numpy(t.observation.planes).unsqueeze(0).to(device)
            scalars = torch.from_numpy(t.observation.scalars).unsqueeze(0).to(device)
            mask = torch.from_numpy(t.observation.action_mask).unsqueeze(0).to(device)

            logits, _ = model(planes, scalars, mask)
            top_actions = torch.topk(logits, k=min(3, logits.shape[1]), dim=1).indices[0]
            predicted = int(top_actions[0].item())

            if predicted == t.action_id:
                exact_matches += 1
            if t.action_id in top_actions.tolist():
                top3_matches += 1

    return {
        "agreement_rate": exact_matches / total,
        "top3_agreement_rate": top3_matches / total,
        "total_transitions": total,
    }


def evaluate_online(
    model: nn.Module,
    episodes: int,
    seeds: List[int],
    bridge_kind: str = "go",
    bridge_library_path: Optional[str] = None,
    device: str = "cpu",
) -> Dict[str, float]:
    """Run the learned policy as seat 0 against heuristic opponents.

    Returns dict with: avg_reward, win_count, episodes, per_episode_rewards.
    """
    config = EnvConfig(
        bridge_kind=bridge_kind,
        bridge_library_path=bridge_library_path,
        learning_seats=(0,),
        auto_play_heuristics=True,
    )
    bridge = build_bridge(config)
    env = MahjongEnv(config, bridge)
    policy = TorchGreedyPolicy(model, device=device)

    seat0_rewards: List[float] = []
    wins = 0

    try:
        for i in range(episodes):
            seed = seeds[i] if i < len(seeds) else seeds[-1] + i
            episode = collect_episode(env, policy, seed=seed)
            if episode:
                terminal = episode[-1]
                reward = float(terminal.rewards[0])  # seat 0 payout
                seat0_rewards.append(reward)
                if reward > 0:
                    wins += 1
    finally:
        env.close()

    avg = float(np.mean(seat0_rewards)) if seat0_rewards else 0.0
    return {
        "avg_reward": round(avg, 2),
        "win_count": wins,
        "episodes": len(seat0_rewards),
        "per_episode_rewards": seat0_rewards,
    }
