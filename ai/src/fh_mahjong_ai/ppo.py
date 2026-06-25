from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import torch


@dataclass
class PPOConfig:
    iterations: int = 50
    matches_per_iter: int = 16
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    entropy_coef: float = 0.01
    value_coef: float = 0.5
    ppo_epochs: int = 4
    minibatch_size: int = 256
    lr: float = 2e-5
    max_grad_norm: float = 1.0
    sample_temperature: float = 1.0
    eval_interval: int = 5
    eval_seeds: int = 80
    eval_start_seed: int = 870000
    match_mode: str = "chongci"
    max_steps_per_episode: Optional[int] = 4000
    device: str = "cpu"


@dataclass
class RolloutBatch:
    planes: np.ndarray
    scalars: np.ndarray
    action_mask: np.ndarray
    actions: np.ndarray
    old_logprobs: np.ndarray
    values: np.ndarray
    rewards: np.ndarray
    dones: np.ndarray  # 1.0 at each match's final learning-seat step

    def __len__(self) -> int:
        return int(self.actions.shape[0])


def masked_policy_distribution(masked_logits: torch.Tensor) -> torch.distributions.Categorical:
    """Categorical over actions; logits are already -inf-masked (finfo.min) for
    illegal actions by PolicyValueNet.forward, so illegal probability is ~0 and
    entropy stays finite."""
    return torch.distributions.Categorical(logits=masked_logits)


def compute_gae(
    rewards: np.ndarray,
    values: np.ndarray,
    dones: np.ndarray,
    gamma: float,
    gae_lambda: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generalized Advantage Estimation over a flat, time-ordered batch where
    `dones[t]==1` marks the final step of a match. Boundaries reset both the value
    bootstrap and the advantage accumulation via the (1-done) factor."""
    rewards = np.asarray(rewards, dtype=np.float32)
    values = np.asarray(values, dtype=np.float32)
    dones = np.asarray(dones, dtype=np.float32)
    n = rewards.shape[0]
    advantages = np.zeros(n, dtype=np.float32)
    last_adv = 0.0
    for t in range(n - 1, -1, -1):
        next_nonterminal = 1.0 - dones[t]
        next_value = values[t + 1] if (t + 1 < n) else 0.0
        delta = rewards[t] + gamma * next_value * next_nonterminal - values[t]
        last_adv = delta + gamma * gae_lambda * next_nonterminal * last_adv
        advantages[t] = last_adv
    returns = advantages + values
    return advantages, returns
