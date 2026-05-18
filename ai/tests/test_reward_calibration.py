from __future__ import annotations

from pathlib import Path

import numpy as np

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.reward_calibration import add_steps_to_done_if_missing, compute_reward_calibration
from fh_mahjong_ai.scripts.reward_calibration import reward_calibration_report
from fh_mahjong_ai.storage import save_checkpoint, write_transitions_jsonl
from fh_mahjong_ai.types import Observation, Transition


def _obs(seed: int, env_config: EnvConfig) -> Observation:
    rng = np.random.default_rng(seed)
    return Observation(
        seat=seed % 4,
        planes=rng.standard_normal(env_config.plane_shape).astype(np.float32),
        scalars=rng.standard_normal(env_config.scalar_features).astype(np.float32),
        action_mask=np.ones(env_config.action_space_size, dtype=np.int8),
    )


def _transitions(n: int, env_config: EnvConfig) -> list[Transition]:
    transitions = []
    terminal_rewards = np.asarray([1.0, -0.5, -0.25, -0.25], dtype=np.float32)
    for index in range(n):
        transitions.append(
            Transition(
                observation=_obs(index, env_config),
                action_id=5 + (index % 8),
                rewards=terminal_rewards if index == n - 1 else np.zeros(4, dtype=np.float32),
                next_observation=_obs(index + 100, env_config),
                terminated=index == n - 1,
                info={
                    "episode_index": 0,
                    "terminal_rewards": terminal_rewards,
                },
            )
        )
    return transitions


def test_add_steps_to_done_if_missing() -> None:
    arrays = {
        "episode_index": np.asarray([0, 0, 0], dtype=np.int64),
        "terminated": np.asarray([False, False, True], dtype=np.bool_),
        "truncated": np.asarray([False, False, False], dtype=np.bool_),
    }

    add_steps_to_done_if_missing(arrays)

    assert arrays["steps_to_done"].tolist() == [2, 1, 0]


def test_compute_reward_calibration_reports_errors(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    model_config = ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
    )
    model = PolicyValueNet(env_config, model_config)
    transitions = _transitions(6, env_config)
    from fh_mahjong_ai.storage import read_transition_arrays

    tmp = tmp_path / "reward-calibration-test.jsonl"
    write_transitions_jsonl(tmp, transitions)
    arrays = read_transition_arrays(tmp)

    report = compute_reward_calibration(model, arrays, gamma=0.99, batch_size=3)

    assert report["total_transitions"] == 6
    assert "discard" in report["by_action_family"]
    assert np.isfinite(report["q_error"]["mae"])


def test_reward_calibration_script_writes_report(tmp_path: Path) -> None:
    env_config = EnvConfig()
    data_path = tmp_path / "data.jsonl"
    checkpoint = tmp_path / "checkpoint.pt"
    report_path = tmp_path / "report.json"
    model = PolicyValueNet(env_config, ModelConfig())
    write_transitions_jsonl(data_path, _transitions(5, env_config))
    save_checkpoint(checkpoint, model, step=2)

    report = reward_calibration_report(
        checkpoint=checkpoint,
        data_path=data_path,
        max_transitions=5,
        batch_size=2,
        report_output=report_path,
    )

    assert report["checkpoint_step"] == 2
    assert report["calibration"]["total_transitions"] == 5
    assert report_path.exists()
