from __future__ import annotations

import numpy as np

from fh_mahjong_ai.scripts.generate_sampled_branch_counterfactuals import (
    choose_greedy_and_sampled_action,
)


def test_choose_greedy_and_sampled_action_respects_top_k() -> None:
    rng = np.random.default_rng(7)
    legal_actions = [5, 6, 7, 8]
    legal_logits = [0.1, 3.0, 2.0, -4.0]

    sampled = {
        choose_greedy_and_sampled_action(
            legal_actions,
            legal_logits,
            rng=rng,
            temperature=1.0,
            top_k=2,
        ).sampled_action_id
        for _ in range(40)
    }

    assert sampled.issubset({6, 7})


def test_choose_greedy_and_sampled_action_top_one_is_greedy() -> None:
    decision = choose_greedy_and_sampled_action(
        legal_actions=[5, 6, 7],
        legal_logits=[0.1, 3.0, 2.0],
        rng=np.random.default_rng(3),
        temperature=1.0,
        top_k=1,
    )

    assert decision.greedy_action_id == 6
    assert decision.sampled_action_id == 6
    assert decision.sampled_rank == 1
    assert decision.candidate_action_ids == (6,)
    assert decision.candidate_probabilities == (1.0,)
