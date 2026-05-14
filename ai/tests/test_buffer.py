from __future__ import annotations

import numpy as np

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0) -> Observation:
    return Observation(
        seat=seat,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(29, dtype=np.float32),
        action_mask=np.ones(204, dtype=np.int8),
    )


def test_sample_uses_terminal_rewards_when_available() -> None:
    buf = ReplayBuffer(capacity=10)
    t = Transition(
        observation=_obs(seat=0),
        action_id=5,
        rewards=np.asarray([0, 0, 0, 0], dtype=np.float32),
        next_observation=_obs(seat=0),
        terminated=False,
        info={"terminal_rewards": np.asarray([10, -5, -3, -2], dtype=np.float32)},
    )
    buf.append(t)
    batch = buf.sample(1, seed=42)
    assert batch.returns[0] == 10.0  # seat 0's terminal reward


def test_sample_falls_back_to_step_rewards() -> None:
    buf = ReplayBuffer(capacity=10)
    t = Transition(
        observation=_obs(seat=1),
        action_id=5,
        rewards=np.asarray([0, 7, 0, 0], dtype=np.float32),
        next_observation=_obs(seat=1),
        terminated=True,
        info={},
    )
    buf.append(t)
    batch = buf.sample(1, seed=42)
    assert batch.returns[0] == 7.0  # seat 1's step reward


def test_sample_includes_next_observation_and_td_fields() -> None:
    buf = ReplayBuffer(capacity=10)
    next_obs = _obs(seat=2)
    next_obs.scalars[0] = 1.0
    t = Transition(
        observation=_obs(seat=2),
        action_id=5,
        rewards=np.asarray([0, 0, 3, 0], dtype=np.float32),
        next_observation=next_obs,
        terminated=True,
        info={},
    )
    buf.append(t)

    batch = buf.sample(1, seed=42)

    assert batch.next_planes.shape == (1, 39, 42, 1)
    assert batch.next_scalars[0, 0] == 1.0
    assert batch.next_action_mask.shape == (1, 204)
    assert batch.rewards[0] == 3.0
    assert batch.dones[0] == 1.0
