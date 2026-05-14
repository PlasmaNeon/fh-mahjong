from __future__ import annotations

from collections import defaultdict
from typing import List, Tuple

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


def split_train_validation(
    transitions: List[Transition],
    validation_fraction: float = 0.2,
    seed: int = 0,
) -> Tuple[List[Transition], List[Transition]]:
    """Split transitions by episode so validation does not share a round with train."""
    if validation_fraction < 0.0 or validation_fraction >= 1.0:
        raise ValueError("validation_fraction must be in [0.0, 1.0)")

    episodes = split_episodes(transitions)
    if len(episodes) <= 1 or validation_fraction == 0.0:
        return list(transitions), []

    rng = np.random.default_rng(seed)
    indices = np.arange(len(episodes))
    rng.shuffle(indices)

    validation_count = int(round(len(episodes) * validation_fraction))
    validation_count = min(max(validation_count, 1), len(episodes) - 1)
    validation_indices = set(int(index) for index in indices[:validation_count])

    train: List[Transition] = []
    validation: List[Transition] = []
    for index, episode in enumerate(episodes):
        target = validation if index in validation_indices else train
        target.extend(episode)

    return train, validation
