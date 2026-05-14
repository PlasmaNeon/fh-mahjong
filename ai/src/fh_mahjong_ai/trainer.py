from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol

import numpy as np
import torch
from torch import nn

from .buffer import ReplayBuffer
from .config import OfflineQConfig, TrainConfig
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


@dataclass
class OfflineQMetrics:
    loss: float
    td_loss: float
    conservative_loss: float
    bc_loss: float
    value_loss: float
    avg_q: float
    avg_target: float


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
        self._sample_rng = np.random.default_rng(config.seed)

    def train_step(self, replay_buffer: ReplayBuffer) -> TrainMetrics:
        sample_seed = int(self._sample_rng.integers(0, np.iinfo(np.uint32).max))
        batch = replay_buffer.sample(self.config.batch_size, seed=sample_seed)

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


class OfflineQTrainer:
    """Conservative offline Q-learning over the existing masked action head.

    `PolicyValueNet` was originally named around behavior cloning, but its
    action head already emits one scalar per discrete action. This trainer
    treats those scalars as Q-values and trains only on dataset transitions.
    """

    def __init__(
        self,
        model: nn.Module,
        target_model: nn.Module,
        optimizer: torch.optim.Optimizer,
        train_config: TrainConfig,
        q_config: Optional[OfflineQConfig] = None,
    ) -> None:
        self.model = model
        self.target_model = target_model
        self.optimizer = optimizer
        self.train_config = train_config
        self.q_config = q_config or OfflineQConfig()
        self._sample_rng = np.random.default_rng(train_config.seed)

    def train_step(self, replay_buffer: ReplayBuffer) -> OfflineQMetrics:
        sample_seed = int(self._sample_rng.integers(0, np.iinfo(np.uint32).max))
        batch = replay_buffer.sample(self.train_config.batch_size, seed=sample_seed)

        planes = torch.from_numpy(batch.planes).to(self.train_config.device)
        scalars = torch.from_numpy(batch.scalars).to(self.train_config.device)
        action_mask = torch.from_numpy(batch.action_mask).to(self.train_config.device)
        action_ids = torch.from_numpy(batch.action_ids).to(self.train_config.device)
        returns = torch.from_numpy(batch.returns).to(self.train_config.device)
        next_planes = torch.from_numpy(batch.next_planes).to(self.train_config.device)
        next_scalars = torch.from_numpy(batch.next_scalars).to(self.train_config.device)
        next_action_mask = torch.from_numpy(batch.next_action_mask).to(self.train_config.device)
        rewards = torch.from_numpy(batch.rewards).to(self.train_config.device)
        dones = torch.from_numpy(batch.dones).to(self.train_config.device)

        q_values, values = self.model(planes, scalars, action_mask)
        dataset_q = q_values.gather(1, action_ids.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            next_q_values, _ = self.target_model(next_planes, next_scalars, next_action_mask)
            next_q = next_q_values.max(dim=1).values
            target_q = rewards + self.q_config.gamma * (1.0 - dones) * next_q

        td_loss = nn.functional.smooth_l1_loss(dataset_q, target_q)
        conservative_loss = (torch.logsumexp(q_values, dim=1) - dataset_q).mean()
        bc_loss = nn.functional.cross_entropy(q_values, action_ids)
        value_loss = nn.functional.mse_loss(values, returns)
        loss = (
            td_loss
            + self.q_config.conservative_weight * conservative_loss
            + self.q_config.bc_weight * bc_loss
            + self.q_config.value_weight * value_loss
        )

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.train_config.max_grad_norm)
        self.optimizer.step()

        return OfflineQMetrics(
            loss=float(loss.item()),
            td_loss=float(td_loss.item()),
            conservative_loss=float(conservative_loss.item()),
            bc_loss=float(bc_loss.item()),
            value_loss=float(value_loss.item()),
            avg_q=float(dataset_q.mean().item()),
            avg_target=float(target_q.mean().item()),
        )

    def update_target_network(self) -> None:
        tau = self.q_config.target_tau
        with torch.no_grad():
            for target_param, source_param in zip(self.target_model.parameters(), self.model.parameters()):
                target_param.data.mul_(1.0 - tau)
                target_param.data.add_(source_param.data, alpha=tau)


def fill_buffer_from_episodes(replay_buffer: ReplayBuffer, episodes: Iterable[List[Transition]]) -> None:
    for episode in episodes:
        replay_buffer.extend(episode)
