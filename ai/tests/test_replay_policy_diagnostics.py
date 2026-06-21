from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.replay_policy_diagnostics import (
    build_anchor_preservation_divergence_arrays,
    build_replay_policy_diagnostics,
    write_divergence_shard,
)
from fh_mahjong_ai.storage import read_transition_arrays, save_checkpoint, write_transitions_npz_shards
from fh_mahjong_ai.types import Observation, Transition


def _biased_checkpoint(path: Path, action_id: int) -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    with torch.no_grad():
        model.policy_head.weight.zero_()
        model.policy_head.bias.fill_(-10.0)
        model.policy_head.bias[action_id] = 10.0
    save_checkpoint(path, model, step=7)


def _observation(seed: int, seat: int) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[[5, 6, 47, 183]] = 1
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=rng.standard_normal(58).astype(np.float32),
        action_mask=mask,
    )


def test_build_replay_policy_diagnostics_compares_anchor_candidate_and_replay(tmp_path: Path) -> None:
    anchor = tmp_path / "anchor.pt"
    candidate = tmp_path / "candidate.pt"
    _biased_checkpoint(anchor, action_id=5)
    _biased_checkpoint(candidate, action_id=6)

    terminal_rewards = [
        np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32),
        np.asarray([-1.2, 0.0, 0.0, 0.0], dtype=np.float32),
        np.asarray([0.0, 0.8, 0.0, 0.0], dtype=np.float32),
        np.asarray([0.0, -0.3, 0.0, 0.0], dtype=np.float32),
    ]
    transitions = []
    for index, action_id in enumerate([5, 6, 47, 183]):
        seat = index // 2
        transitions.append(
            Transition(
                observation=_observation(index, seat=seat),
                action_id=action_id,
                rewards=np.zeros(4, dtype=np.float32),
                next_observation=_observation(index + 100, seat=seat),
                terminated=index == 3,
                truncated=False,
                info={
                    "episode_index": index // 2,
                    "policy_source_id": seat,
                    "terminal_rewards": terminal_rewards[index],
                },
            )
        )
    data = tmp_path / "replay"
    write_transitions_npz_shards(data, transitions, shard_size=4)

    report = build_replay_policy_diagnostics(
        data_path=data,
        anchor_checkpoint=anchor,
        candidate_checkpoint=candidate,
        batch_size=2,
        device="cpu",
        large_loss_threshold=-1.0,
    )

    assert report["total_transitions"] == 4
    assert report["anchor_checkpoint_step"] == 7
    assert report["candidate_checkpoint_step"] == 7
    assert report["anchor_vs_replay"]["agreement_count"] == 1
    assert report["candidate_vs_replay"]["agreement_count"] == 1
    assert report["candidate_vs_anchor"]["divergence_count"] == 4
    assert report["candidate_vs_anchor"]["divergence_family_pair_counts"] == {"discard->discard": 4}
    assert report["candidate_vs_anchor"]["divergence_by_policy_source_id"]["0"]["divergence_count"] == 2
    assert report["returns"]["large_loss_divergence_count"] == 1

    arrays, metadata = build_anchor_preservation_divergence_arrays(
        data_path=data,
        anchor_checkpoint=anchor,
        candidate_checkpoint=candidate,
        batch_size=2,
        device="cpu",
        family_pair="discard->discard",
        large_loss_threshold=-1.0,
        pairwise_reward_gap=0.05,
    )
    manifest = write_divergence_shard(tmp_path / "divergence", arrays, metadata)
    loaded = read_transition_arrays(
        tmp_path / "divergence",
        keys=("pairwise_preferred_action_ids", "pairwise_avoided_action_ids", "pairwise_reward_delta_targets"),
    )

    assert manifest["counterfactual"]["label_type"] == "anchor_preservation_divergence"
    assert manifest["counterfactual"]["rows"] == 4
    assert loaded["pairwise_preferred_action_ids"].tolist() == [5, 5, 5, 5]
    assert loaded["pairwise_avoided_action_ids"].tolist() == [6, 6, 6, 6]
    np.testing.assert_allclose(loaded["pairwise_reward_delta_targets"], [0.05, 0.05, 0.05, 0.05])
