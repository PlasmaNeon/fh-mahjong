from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol

import numpy as np
import torch
from torch import nn

from .buffer import ReplayBuffer
from .config import TrainConfig
from .env import MahjongEnv
from .policies import ActionChoice
from .types import StepResult, Transition


class PolicyLike(Protocol):
    def choose(self, observation) -> ActionChoice: ...


@dataclass
class TrainMetrics:
    loss: float
    policy_loss: float
    value_loss: float


def collect_episode(env: MahjongEnv, policy: PolicyLike, seed: Optional[int] = None) -> List[Transition]:
    transitions: List[Transition] = []
    observation = env.reset(seed=seed)

    while True:
        choice = policy.choose(observation)
        step_result = env.step(choice.action_id)
        transitions.append(
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
            return transitions


class BehaviorCloningTrainer:
    def __init__(self, model: nn.Module, optimizer: torch.optim.Optimizer, config: TrainConfig) -> None:
        self.model = model
        self.optimizer = optimizer
        self.config = config

    def train_step(self, replay_buffer: ReplayBuffer) -> TrainMetrics:
        batch = replay_buffer.sample(self.config.batch_size)

        planes = torch.from_numpy(batch.planes).to(self.config.device)
        scalars = torch.from_numpy(batch.scalars).to(self.config.device)
        action_mask = torch.from_numpy(batch.action_mask).to(self.config.device)
        action_ids = torch.from_numpy(batch.action_ids).to(self.config.device)
        returns = torch.from_numpy(batch.returns).to(self.config.device)

        logits, values = self.model(planes, scalars, action_mask)
        policy_loss = nn.functional.cross_entropy(logits, action_ids)
        value_loss = nn.functional.mse_loss(values, returns)
        loss = policy_loss + value_loss

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
        self.optimizer.step()

        return TrainMetrics(
            loss=float(loss.item()),
            policy_loss=float(policy_loss.item()),
            value_loss=float(value_loss.item()),
        )


def fill_buffer_from_episodes(replay_buffer: ReplayBuffer, episodes: Iterable[List[Transition]]) -> None:
    for episode in episodes:
        replay_buffer.extend(episode)
