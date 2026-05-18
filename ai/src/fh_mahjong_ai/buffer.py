from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional

import numpy as np

from .types import TrainBatch, Transition


@dataclass
class ReplayBuffer:
    capacity: int

    def __post_init__(self) -> None:
        self._items: Deque[Transition] = deque(maxlen=self.capacity)

    def append(self, transition: Transition) -> None:
        self._items.append(transition)

    def extend(self, transitions: Iterable[Transition]) -> None:
        for transition in transitions:
            self.append(transition)

    def __len__(self) -> int:
        return len(self._items)

    def sample(self, batch_size: int, seed: Optional[int] = None) -> TrainBatch:
        if batch_size > len(self._items):
            raise ValueError(f"cannot sample {batch_size} from replay buffer of size {len(self._items)}")

        rng = np.random.default_rng(seed)
        indices = rng.choice(len(self._items), size=batch_size, replace=False)
        items = [self._items[int(index)] for index in indices]

        planes = np.stack([item.observation.planes for item in items]).astype(np.float32)
        scalars = np.stack([item.observation.scalars for item in items]).astype(np.float32)
        action_mask = np.stack([item.observation.action_mask for item in items]).astype(np.int8)
        action_ids = np.asarray([item.action_id for item in items], dtype=np.int64)

        def _return_for(item: Transition) -> float:
            seat = item.observation.seat
            tr = item.info.get("terminal_rewards")
            if tr is not None:
                return float(tr[seat])
            return float(item.rewards[seat])

        def _reward_for(item: Transition) -> float:
            return float(item.rewards[item.observation.seat])

        returns = np.asarray([_return_for(item) for item in items], dtype=np.float32)
        steps_to_done = np.asarray(
            [int(item.info.get("steps_to_done", 0)) for item in items],
            dtype=np.int32,
        )
        next_planes = np.stack([item.next_observation.planes for item in items]).astype(np.float32)
        next_scalars = np.stack([item.next_observation.scalars for item in items]).astype(np.float32)
        next_action_mask = np.stack([item.next_observation.action_mask for item in items]).astype(np.int8)
        rewards = np.asarray([_reward_for(item) for item in items], dtype=np.float32)
        dones = np.asarray(
            [float(item.terminated or item.truncated) for item in items],
            dtype=np.float32,
        )
        return TrainBatch(
            planes=planes,
            scalars=scalars,
            action_mask=action_mask,
            action_ids=action_ids,
            returns=returns,
            steps_to_done=steps_to_done,
            next_planes=next_planes,
            next_scalars=next_scalars,
            next_action_mask=next_action_mask,
            rewards=rewards,
            dones=dones,
        )


@dataclass
class ArrayReplayBuffer:
    """Replay buffer backed by contiguous NumPy arrays instead of Transition objects."""

    arrays: dict[str, np.ndarray]
    indices: np.ndarray

    def __post_init__(self) -> None:
        self.indices = np.asarray(self.indices, dtype=np.int64)

    def __len__(self) -> int:
        return int(self.indices.size)

    def sample(self, batch_size: int, seed: Optional[int] = None) -> TrainBatch:
        if batch_size > len(self):
            raise ValueError(f"cannot sample {batch_size} from replay buffer of size {len(self)}")

        rng = np.random.default_rng(seed)
        positions = rng.choice(len(self), size=batch_size, replace=False)
        indices = self.indices[positions]
        seats = self.arrays["seats"][indices].astype(np.int64, copy=False)

        returns = self.arrays["terminal_rewards"][indices, seats].astype(np.float32, copy=False)
        steps_to_done = (
            self.arrays["steps_to_done"][indices].astype(np.int32, copy=False)
            if "steps_to_done" in self.arrays
            else np.zeros(batch_size, dtype=np.int32)
        )
        rewards = (
            self.arrays["rewards"][indices, seats].astype(np.float32, copy=False)
            if "rewards" in self.arrays
            else np.zeros(batch_size, dtype=np.float32)
        )
        dones = (
            np.logical_or(
                self.arrays["terminated"][indices],
                self.arrays["truncated"][indices],
            ).astype(np.float32)
            if "terminated" in self.arrays and "truncated" in self.arrays
            else np.zeros(batch_size, dtype=np.float32)
        )

        return TrainBatch(
            planes=self.arrays["planes"][indices].astype(np.float32, copy=False),
            scalars=self.arrays["scalars"][indices].astype(np.float32, copy=False),
            action_mask=self.arrays["action_mask"][indices].astype(np.int8, copy=False),
            action_ids=self.arrays["action_ids"][indices].astype(np.int64, copy=False),
            returns=returns,
            steps_to_done=steps_to_done,
            next_planes=self.arrays["next_planes"][indices].astype(np.float32, copy=False)
            if "next_planes" in self.arrays
            else np.empty((batch_size, 0), dtype=np.float32),
            next_scalars=self.arrays["next_scalars"][indices].astype(np.float32, copy=False)
            if "next_scalars" in self.arrays
            else np.empty((batch_size, 0), dtype=np.float32),
            next_action_mask=self.arrays["next_action_mask"][indices].astype(np.int8, copy=False)
            if "next_action_mask" in self.arrays
            else np.empty((batch_size, 0), dtype=np.int8),
            rewards=rewards,
            dones=dones,
        )
