from __future__ import annotations

from pathlib import Path

import numpy as np

from fh_mahjong_ai.scripts.dataset_diagnostics import build_dataset_diagnostics
from fh_mahjong_ai.storage import write_transitions_npz_shards
from fh_mahjong_ai.types import Observation, Transition


def _observation(seed: int, seat: int) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.zeros(204, dtype=np.int8)
    mask[[0, 5, 47, 183]] = 1
    scalars = np.zeros(58, dtype=np.float32)
    scalars[47] = 0.25 * seat
    scalars[49] = 0.1 * (seat + 1)
    return Observation(
        seat=seat,
        planes=rng.standard_normal((39, 42, 1)).astype(np.float32),
        scalars=scalars,
        action_mask=mask,
        metadata={"decision_index": seed},
    )


def test_build_dataset_diagnostics_reports_operation_level_coverage(tmp_path: Path) -> None:
    action_ids = [5, 0, 47, 183]
    terminal_rewards = [
        np.asarray([1.0, -1.2, 0.0, 0.2], dtype=np.float32),
        np.asarray([0.5, -1.1, 0.3, 0.0], dtype=np.float32),
        np.asarray([-0.4, 0.2, 0.8, -1.3], dtype=np.float32),
        np.asarray([0.1, -0.2, 0.4, 1.2], dtype=np.float32),
    ]
    transitions = []
    for index, action_id in enumerate(action_ids):
        seat = index % 4
        transitions.append(
            Transition(
                observation=_observation(index, seat=seat),
                action_id=action_id,
                rewards=np.zeros(4, dtype=np.float32),
                next_observation=_observation(index + 100, seat=(seat + 1) % 4),
                terminated=index == len(action_ids) - 1,
                truncated=False,
                info={
                    "episode_index": index // 2,
                    "policy_source_id": seat,
                    "policy_greedy_action_id": 5 if index < 2 else action_id,
                    "policy_sampling_applied": index < 2,
                    "policy_sampled_from_greedy": index == 1,
                    "terminal_rewards": terminal_rewards[index],
                    "terminal_outcome": {
                        "is_draw": False,
                        "winner_seat": seat if index in (0, 3) else 0,
                        "win_type": 6,
                        "discarder_seat": seat if index == 1 else 1,
                        "total_score": 8 + index,
                        "payouts": [],
                    },
                },
            )
        )
    data_dir = tmp_path / "replay"
    write_transitions_npz_shards(data_dir, transitions, shard_size=2)

    report = build_dataset_diagnostics(data_dir, large_loss_threshold=-1.0)

    assert report["transitions"] == 4
    assert report["episodes"] == 2
    assert report["seats"]["counts"] == {"0": 1, "1": 1, "2": 1, "3": 1}
    assert report["policy_source_ids"]["counts"] == {"0": 1, "1": 1, "2": 1, "3": 1}
    assert report["action_families"]["counts"] == {"chii": 1, "discard": 1, "pass": 1, "pon": 1}
    assert report["acting_return"]["large_loss_count"] == 1
    assert report["acting_return"]["positive_count"] == 3
    assert report["terminal_outcomes"]["win_count"] == 2
    assert report["terminal_outcomes"]["deal_in_count"] == 1
    assert report["score_pressure"]["available"] is True
    assert report["score_pressure"]["large_loss_margin_scalar_index"] == 47
    assert report["policy_sampling"]["available"] is True
    assert report["policy_sampling"]["sampling_applied_count"] == 2
    assert report["policy_sampling"]["sampled_from_greedy_count"] == 1
    assert report["policy_sampling"]["sampled_family_pair_counts"] == {"discard->pass": 1}
    assert report["policy_sampling"]["sampled_return"]["large_loss_count"] == 1
