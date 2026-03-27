from __future__ import annotations

from collections import defaultdict
from typing import List

import numpy as np

from .types import Transition


def split_episodes(transitions: List[Transition]) -> List[List[Transition]]:
    """Group a flat list of transitions by episode_index from info metadata."""
    if not transitions:
        return []

    groups: dict[int, List[Transition]] = defaultdict(list)
    for t in transitions:
        episode_idx = t.info.get("episode_index", 0)
        groups[episode_idx].append(t)

    return [groups[k] for k in sorted(groups)]


def backfill_returns(transitions: List[Transition]) -> List[Transition]:
    """Ensure every transition in a flat list has terminal_rewards in its info.

    Groups transitions by episode, finds the terminal rewards for each episode
    (from info["terminal_rewards"] on the last transition, falling back to the
    last transition's rewards), and copies them into every transition's info.
    """
    if not transitions:
        return transitions

    for episode in split_episodes(transitions):
        last = episode[-1]
        terminal = last.info.get(
            "terminal_rewards",
            np.asarray(last.rewards, dtype=np.float32),
        )
        terminal = np.asarray(terminal, dtype=np.float32)
        for t in episode:
            t.info["terminal_rewards"] = terminal.copy()

    return transitions
