from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Protocol

import numpy as np
import torch
from torch import nn

from .buffer import ReplayBuffer
from .config import AdvantageWeightedBCConfig, DiscreteIQLConfig, OfflineQConfig, TrainConfig
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


@dataclass
class AdvantageWeightedBCMetrics:
    loss: float
    policy_loss: float
    value_loss: float
    avg_weight: float
    max_weight: float
    avg_advantage: float


@dataclass
class DiscreteIQLMetrics:
    loss: float
    q_loss: float
    value_loss: float
    policy_loss: float
    bc_loss: float
    cql_loss: float
    avg_q: float
    avg_v: float
    avg_target_q: float
    avg_advantage: float
    avg_weight: float
    max_weight: float
    avg_sample_weight: float
    max_sample_weight: float


def collect_episode(env: MahjongEnv, policy: PolicyLike, seed: Optional[int] = None) -> List[Transition]:
    transitions: List[Transition] = []
    observation = env.reset(seed=seed)
    reset_result = env.last_reset_result
    if reset_result is not None and (reset_result.terminated or reset_result.truncated):
        return transitions
    if not observation.legal_actions:
        return transitions

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


class AdvantageWeightedBCTrainer:
    """Conservative offline policy improvement via advantage-weighted imitation."""

    def __init__(
        self,
        model: nn.Module,
        optimizer: torch.optim.Optimizer,
        train_config: TrainConfig,
        awbc_config: Optional[AdvantageWeightedBCConfig] = None,
    ) -> None:
        self.model = model
        self.optimizer = optimizer
        self.train_config = train_config
        self.awbc_config = awbc_config or AdvantageWeightedBCConfig()
        self._sample_rng = np.random.default_rng(train_config.seed)

    def train_step(self, replay_buffer: ReplayBuffer) -> AdvantageWeightedBCMetrics:
        sample_seed = int(self._sample_rng.integers(0, np.iinfo(np.uint32).max))
        batch = replay_buffer.sample(self.train_config.batch_size, seed=sample_seed)

        planes = torch.from_numpy(batch.planes).to(self.train_config.device)
        scalars = torch.from_numpy(batch.scalars).to(self.train_config.device)
        action_mask = torch.from_numpy(batch.action_mask).to(self.train_config.device)
        action_ids = torch.from_numpy(batch.action_ids).to(self.train_config.device)
        returns = torch.from_numpy(batch.returns).to(self.train_config.device)

        logits, values = self.model(planes, scalars, action_mask)
        advantages = returns - values.detach()
        weights = torch.exp(advantages / max(self.awbc_config.temperature, 1e-6))
        weights = torch.clamp(weights, max=self.awbc_config.max_weight)

        per_sample_policy_loss = nn.functional.cross_entropy(logits, action_ids, reduction="none")
        policy_loss = (weights * per_sample_policy_loss).mean()
        value_loss = nn.functional.mse_loss(values, returns)
        loss = policy_loss + self.awbc_config.value_weight * value_loss

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.train_config.max_grad_norm)
        self.optimizer.step()

        return AdvantageWeightedBCMetrics(
            loss=float(loss.item()),
            policy_loss=float(policy_loss.item()),
            value_loss=float(value_loss.item()),
            avg_weight=float(weights.mean().item()),
            max_weight=float(weights.max().item()),
            avg_advantage=float(advantages.mean().item()),
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


class DiscreteIQLTrainer:
    """Implicit Q-learning style offline RL with separate policy and critic heads."""

    def __init__(
        self,
        model: nn.Module,
        target_model: nn.Module,
        optimizer: torch.optim.Optimizer,
        train_config: TrainConfig,
        iql_config: Optional[DiscreteIQLConfig] = None,
    ) -> None:
        self.model = model
        self.target_model = target_model
        self.optimizer = optimizer
        self.train_config = train_config
        self.iql_config = iql_config or DiscreteIQLConfig()
        self._sample_rng = np.random.default_rng(train_config.seed)

    def train_step(self, replay_buffer: ReplayBuffer) -> DiscreteIQLMetrics:
        sample_seed = int(self._sample_rng.integers(0, np.iinfo(np.uint32).max))
        batch = replay_buffer.sample(self.train_config.batch_size, seed=sample_seed)

        planes = torch.from_numpy(batch.planes).to(self.train_config.device)
        scalars = torch.from_numpy(batch.scalars).to(self.train_config.device)
        action_mask = torch.from_numpy(batch.action_mask).to(self.train_config.device)
        action_ids = torch.from_numpy(batch.action_ids).to(self.train_config.device)
        next_planes = torch.from_numpy(batch.next_planes).to(self.train_config.device)
        next_scalars = torch.from_numpy(batch.next_scalars).to(self.train_config.device)
        next_action_mask = torch.from_numpy(batch.next_action_mask).to(self.train_config.device)
        rewards = torch.from_numpy(batch.rewards).to(self.train_config.device)
        dones = torch.from_numpy(batch.dones).to(self.train_config.device)
        returns = torch.from_numpy(batch.returns).to(self.train_config.device)
        steps_to_done = torch.from_numpy(batch.steps_to_done).to(self.train_config.device)
        external_sample_weights = torch.from_numpy(batch.sample_weights).to(self.train_config.device)
        utility_returns = large_loss_adjusted_rewards(
            returns,
            self.iql_config.large_loss_threshold,
            self.iql_config.large_loss_penalty,
        )
        utility_rewards = large_loss_adjusted_rewards(
            rewards,
            self.iql_config.large_loss_threshold,
            self.iql_config.large_loss_penalty,
        )
        sample_weights = external_sample_weights * large_loss_sample_weights(
            returns,
            self.iql_config.large_loss_threshold,
            self.iql_config.large_loss_weight,
        )

        policy_logits, values = self.model(planes, scalars, action_mask)
        q_values, _ = self.model.q_values(planes, scalars, action_mask)
        dataset_q = q_values.gather(1, action_ids.unsqueeze(1)).squeeze(1)

        target_mode = self.iql_config.target_mode.lower()
        if target_mode == "mc":
            target_q = discounted_terminal_returns(utility_returns, steps_to_done, self.iql_config.gamma)
        elif target_mode == "td":
            with torch.no_grad():
                _, next_values = self.target_model(next_planes, next_scalars, next_action_mask)
                target_q = utility_rewards + self.iql_config.gamma * (1.0 - dones) * next_values
        else:
            raise ValueError(f"unsupported discrete IQL target_mode={self.iql_config.target_mode!r}")

        q_loss = weighted_mean(
            nn.functional.smooth_l1_loss(dataset_q, target_q, reduction="none"),
            sample_weights,
        )
        value_loss = expectile_loss(
            dataset_q.detach() - values,
            self.iql_config.expectile,
            sample_weights=sample_weights,
        )
        cql_loss = weighted_mean(torch.logsumexp(q_values, dim=1) - dataset_q, sample_weights)

        advantages = dataset_q.detach() - values.detach()
        advantage_weights = torch.exp(advantages / max(self.iql_config.temperature, 1e-6))
        advantage_weights = torch.clamp(advantage_weights, max=self.iql_config.max_weight)
        per_sample_policy_loss = nn.functional.cross_entropy(policy_logits, action_ids, reduction="none")
        policy_loss = weighted_mean(advantage_weights * per_sample_policy_loss, sample_weights)
        bc_loss = weighted_mean(per_sample_policy_loss, sample_weights)

        loss = (
            self.iql_config.q_weight * q_loss
            + self.iql_config.value_weight * value_loss
            + self.iql_config.policy_weight * policy_loss
            + self.iql_config.bc_weight * bc_loss
            + self.iql_config.cql_weight * cql_loss
        )

        self.optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.train_config.max_grad_norm)
        self.optimizer.step()

        return DiscreteIQLMetrics(
            loss=float(loss.item()),
            q_loss=float(q_loss.item()),
            value_loss=float(value_loss.item()),
            policy_loss=float(policy_loss.item()),
            bc_loss=float(bc_loss.item()),
            cql_loss=float(cql_loss.item()),
            avg_q=float(dataset_q.mean().item()),
            avg_v=float(values.mean().item()),
            avg_target_q=float(target_q.mean().item()),
            avg_advantage=float(advantages.mean().item()),
            avg_weight=float(advantage_weights.mean().item()),
            max_weight=float(advantage_weights.max().item()),
            avg_sample_weight=float(sample_weights.mean().item()),
            max_sample_weight=float(sample_weights.max().item()),
        )

    def update_target_network(self) -> None:
        tau = self.iql_config.target_tau
        with torch.no_grad():
            for target_param, source_param in zip(self.target_model.parameters(), self.model.parameters()):
                target_param.data.mul_(1.0 - tau)
                target_param.data.add_(source_param.data, alpha=tau)


def expectile_loss(
    diff: torch.Tensor,
    expectile: float,
    sample_weights: Optional[torch.Tensor] = None,
) -> torch.Tensor:
    tau = min(0.999, max(0.001, expectile))
    weights = torch.where(diff > 0, tau, 1.0 - tau)
    losses = weights * diff.pow(2)
    if sample_weights is not None:
        return weighted_mean(losses, sample_weights)
    return losses.mean()


def weighted_mean(values: torch.Tensor, sample_weights: torch.Tensor) -> torch.Tensor:
    weights = sample_weights.to(dtype=values.dtype, device=values.device)
    return (values * weights).sum() / torch.clamp(weights.sum(), min=1e-6)


def discounted_terminal_returns(returns: torch.Tensor, steps_to_done: torch.Tensor, gamma: float) -> torch.Tensor:
    discount = torch.pow(
        torch.as_tensor(gamma, dtype=returns.dtype, device=returns.device),
        steps_to_done.to(dtype=returns.dtype, device=returns.device),
    )
    return returns * discount


def large_loss_adjusted_rewards(
    rewards: torch.Tensor,
    threshold: Optional[float],
    penalty: float,
) -> torch.Tensor:
    if threshold is None or penalty <= 0.0:
        return rewards
    downside = torch.clamp(
        torch.as_tensor(threshold, dtype=rewards.dtype, device=rewards.device) - rewards,
        min=0.0,
    )
    return rewards - float(penalty) * downside


def large_loss_sample_weights(
    rewards: torch.Tensor,
    threshold: Optional[float],
    weight: float,
) -> torch.Tensor:
    if threshold is None or weight <= 1.0:
        return torch.ones_like(rewards)
    threshold_tensor = torch.as_tensor(threshold, dtype=rewards.dtype, device=rewards.device)
    return torch.where(rewards <= threshold_tensor, torch.full_like(rewards, float(weight)), torch.ones_like(rewards))


def fill_buffer_from_episodes(replay_buffer: ReplayBuffer, episodes: Iterable[List[Transition]]) -> None:
    for episode in episodes:
        replay_buffer.extend(episode)
