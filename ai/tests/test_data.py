from __future__ import annotations

import numpy as np
import pytest

from fh_mahjong_ai.data import backfill_returns, split_episodes
from fh_mahjong_ai.types import Observation, Transition


def _obs(seat: int = 0) -> Observation:
    return Observation(
        seat=seat,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(29, dtype=np.float32),
        action_mask=np.ones(204, dtype=np.int8),
    )


def _transition(
    seat: int = 0,
    episode: int = 0,
    terminated: bool = False,
    rewards: list[float] | None = None,
    terminal_rewards: list[float] | None = None,
) -> Transition:
    info: dict = {"acting_seat": seat, "episode_index": episode}
    if terminal_rewards is not None:
        info["terminal_rewards"] = np.asarray(terminal_rewards, dtype=np.float32)
    return Transition(
        observation=_obs(seat),
        action_id=5,
        rewards=np.asarray(rewards or [0, 0, 0, 0], dtype=np.float32),
        next_observation=_obs(seat),
        terminated=terminated,
        info=info,
    )


class TestSplitEpisodes:
    def test_empty(self) -> None:
        assert split_episodes([]) == []

    def test_single_episode(self) -> None:
        transitions = [_transition(episode=0), _transition(episode=0, terminated=True)]
        episodes = split_episodes(transitions)
        assert len(episodes) == 1
        assert len(episodes[0]) == 2

    def test_multiple_episodes(self) -> None:
        transitions = [
            _transition(episode=0),
            _transition(episode=0, terminated=True),
            _transition(episode=1),
            _transition(episode=1),
            _transition(episode=1, terminated=True),
        ]
        episodes = split_episodes(transitions)
        assert len(episodes) == 2
        assert len(episodes[0]) == 2
        assert len(episodes[1]) == 3

    def test_preserves_order(self) -> None:
        transitions = [
            _transition(episode=0, seat=0),
            _transition(episode=0, seat=1),
        ]
        episodes = split_episodes(transitions)
        assert episodes[0][0].info["acting_seat"] == 0
        assert episodes[0][1].info["acting_seat"] == 1


class TestBackfillReturns:
    def test_backfills_terminal_rewards(self) -> None:
        transitions = [
            _transition(episode=0, rewards=[0, 0, 0, 0]),
            _transition(
                episode=0,
                terminated=True,
                rewards=[10, -5, -3, -2],
                terminal_rewards=[10, -5, -3, -2],
            ),
        ]
        result = backfill_returns(transitions)
        for t in result:
            np.testing.assert_array_equal(
                t.info["terminal_rewards"],
                np.asarray([10, -5, -3, -2], dtype=np.float32),
            )

    def test_uses_last_rewards_if_no_terminal_field(self) -> None:
        transitions = [
            _transition(episode=0, rewards=[0, 0, 0, 0]),
            _transition(episode=0, terminated=True, rewards=[8, -2, -3, -3]),
        ]
        result = backfill_returns(transitions)
        np.testing.assert_array_equal(
            result[0].info["terminal_rewards"],
            np.asarray([8, -2, -3, -3], dtype=np.float32),
        )

    def test_empty_input(self) -> None:
        assert backfill_returns([]) == []
