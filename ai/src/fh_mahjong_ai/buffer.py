from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional

import numpy as np

from .types import TrainBatch, Transition


@dataclass(slots=True)
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
        returns = np.asarray([float(item.rewards[item.observation.seat]) for item in items], dtype=np.float32)
        return TrainBatch(
            planes=planes,
            scalars=scalars,
            action_mask=action_mask,
            action_ids=action_ids,
            returns=returns,
        )
