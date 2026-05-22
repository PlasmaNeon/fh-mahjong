from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional, Sequence

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


@dataclass
class CompositeReplayBuffer:
    """Replay buffer that samples across multiple underlying replay sources."""

    buffers: Sequence[ReplayBuffer | ArrayReplayBuffer]

    def __post_init__(self) -> None:
        self.buffers = tuple(buffer for buffer in self.buffers if len(buffer) > 0)
        if not self.buffers:
            raise ValueError("CompositeReplayBuffer requires at least one non-empty buffer")

    def __len__(self) -> int:
        return int(sum(len(buffer) for buffer in self.buffers))

    def sample(self, batch_size: int, seed: Optional[int] = None) -> TrainBatch:
        if batch_size > len(self):
            raise ValueError(f"cannot sample {batch_size} from replay buffer of size {len(self)}")

        rng = np.random.default_rng(seed)
        lengths = np.asarray([len(buffer) for buffer in self.buffers], dtype=np.int64)
        cumulative = np.cumsum(lengths)
        global_indices = rng.choice(int(cumulative[-1]), size=batch_size, replace=False)
        buffer_ids = np.searchsorted(cumulative, global_indices, side="right")
        counts = np.bincount(buffer_ids, minlength=len(self.buffers))

        batches = [
            buffer.sample(int(count), seed=int(rng.integers(0, np.iinfo(np.uint32).max)))
            for buffer, count in zip(self.buffers, counts.tolist())
            if count > 0
        ]
        return concatenate_train_batches(batches)


def concatenate_train_batches(batches: Sequence[TrainBatch]) -> TrainBatch:
    if not batches:
        raise ValueError("cannot concatenate an empty batch list")
    if len(batches) == 1:
        return batches[0]

    return TrainBatch(
        planes=_concat_with_padding([batch.planes for batch in batches]),
        scalars=_concat_with_padding([batch.scalars for batch in batches]),
        action_mask=_concat_with_padding([batch.action_mask for batch in batches]),
        action_ids=np.concatenate([batch.action_ids for batch in batches]).astype(np.int64, copy=False),
        returns=np.concatenate([batch.returns for batch in batches]).astype(np.float32, copy=False),
        steps_to_done=np.concatenate([batch.steps_to_done for batch in batches]).astype(np.int32, copy=False),
        next_planes=_concat_with_padding([batch.next_planes for batch in batches]),
        next_scalars=_concat_with_padding([batch.next_scalars for batch in batches]),
        next_action_mask=_concat_with_padding([batch.next_action_mask for batch in batches]),
        rewards=np.concatenate([batch.rewards for batch in batches]).astype(np.float32, copy=False),
        dones=np.concatenate([batch.dones for batch in batches]).astype(np.float32, copy=False),
    )


def _concat_with_padding(arrays: Sequence[np.ndarray]) -> np.ndarray:
    if not arrays:
        raise ValueError("cannot concatenate an empty array list")

    target_shape = tuple(max(array.shape[axis] for array in arrays) for axis in range(1, arrays[0].ndim))
    padded = [_pad_to_feature_shape(array, target_shape) for array in arrays]
    return np.concatenate(padded, axis=0)


def _pad_to_feature_shape(array: np.ndarray, target_shape: tuple[int, ...]) -> np.ndarray:
    if array.shape[1:] == target_shape:
        return array
    pad_width = [(0, 0)]
    for current, target in zip(array.shape[1:], target_shape):
        if current > target:
            raise ValueError(f"cannot pad array shape {array.shape} down to target feature shape {target_shape}")
        pad_width.append((0, target - current))
    return np.pad(array, pad_width, mode="constant")
