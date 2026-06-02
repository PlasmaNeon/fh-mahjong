from __future__ import annotations

from pathlib import Path

import numpy as np

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.risk_filter import RiskCase
from fh_mahjong_ai.scripts.train_action_risk import (
    RiskTrainingConfig,
    balanced_batch_indices,
    chongci_score_pressure,
    risk_targets,
    train_action_risk,
)
from fh_mahjong_ai.storage import save_checkpoint, write_transitions_npz_shards
from fh_mahjong_ai.types import Observation, Transition


def _obs(seed: int, env_config: EnvConfig) -> Observation:
    rng = np.random.default_rng(seed)
    mask = np.ones(env_config.action_space_size, dtype=np.int8)
    return Observation(
        seat=seed % 4,
        planes=rng.standard_normal(env_config.plane_shape).astype(np.float32),
        scalars=rng.standard_normal(env_config.scalar_features).astype(np.float32),
        action_mask=mask,
        metadata={"decision_index": seed},
    )


def _transition(index: int, env_config: EnvConfig, terminal_reward: float) -> Transition:
    rewards = np.zeros(4, dtype=np.float32)
    terminal_rewards = np.zeros(4, dtype=np.float32)
    seat = index % 4
    terminal_rewards[seat] = terminal_reward
    return Transition(
        observation=_obs(index, env_config),
        action_id=index % env_config.action_space_size,
        rewards=rewards,
        next_observation=_obs(index + 100, env_config),
        terminated=index % 3 == 0,
        truncated=False,
        info={
            "episode_index": index // 2,
            "terminal_rewards": terminal_rewards,
        },
    )


def test_risk_targets_use_acting_seat_terminal_reward() -> None:
    arrays = {
        "seats": np.asarray([0, 1, 2], dtype=np.int16),
        "terminal_rewards": np.asarray(
            [
                [-1.5, 0.0, 0.0, 0.0],
                [0.0, -0.5, 0.0, 0.0],
                [0.0, 0.0, -2.25, 0.0],
            ],
            dtype=np.float32,
        ),
    }

    labels, severities = risk_targets(arrays, threshold=-1.0)

    assert labels.tolist() == [1.0, 0.0, 1.0]
    assert np.allclose(severities, [0.5, 0.0, 1.25])


def test_score_pressure_risk_targets_use_visible_chongci_context() -> None:
    scalars = np.zeros((3, 58), dtype=np.float32)
    scalars[:, 42] = 1.0
    scalars[0, 43] = 0.8
    scalars[0, 46] = 0.7
    scalars[0, 47] = 0.1
    scalars[0, 48] = 0.2
    scalars[0, 49] = 0.6
    scalars[0, 57] = 0.5
    scalars[1, 47] = 1.0
    scalars[1, 48] = 1.0
    scalars[2, 42] = 0.0
    arrays = {
        "seats": np.asarray([0, 0, 0], dtype=np.int16),
        "scalars": scalars,
        "action_ids": np.asarray([1, 1, 1], dtype=np.int64),
        "terminal_rewards": np.asarray(
            [
                [-0.25, 0.0, 0.0, 0.0],
                [-0.25, 0.0, 0.0, 0.0],
                [-1.25, 0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        ),
    }

    pressure = chongci_score_pressure(arrays)
    labels, severities = risk_targets(
        arrays,
        threshold=-1.0,
        target_mode="score_pressure",
        score_pressure_threshold=0.6,
        score_pressure_weight=0.5,
    )

    assert pressure[0] > 0.6
    assert pressure[1] < 0.6
    assert labels.tolist() == [1.0, 0.0, 1.0]
    assert severities[0] > 0.0
    assert severities[1] == 0.0
    assert severities[2] == 0.25


def test_balanced_batch_indices_samples_both_classes() -> None:
    rng = np.random.default_rng(1)
    positives = np.asarray([1, 3], dtype=np.int64)
    negatives = np.asarray([0, 2, 4, 5], dtype=np.int64)

    batch = balanced_batch_indices(positives, negatives, batch_size=6, positive_fraction=0.5, rng=rng)

    assert batch.shape == (6,)
    assert sum(int(index in positives) for index in batch) == 3
    assert sum(int(index in negatives) for index in batch) == 3


def test_train_action_risk_writes_checkpoint_and_report(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4)
    model_config = ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
        q_hidden_dim=8,
    )
    transitions = [
        _transition(index, env_config, terminal_reward=-1.5 if index % 2 == 0 else 0.25)
        for index in range(12)
    ]
    data_dir = tmp_path / "risk-data"
    write_transitions_npz_shards(data_dir, transitions, shard_size=12)

    init_model = PolicyValueNet(env_config, model_config)
    init_checkpoint = tmp_path / "init.pt"
    save_checkpoint(init_checkpoint, init_model)
    checkpoint_dir = tmp_path / "checkpoints"
    report_output = tmp_path / "risk_report.json"

    metrics = train_action_risk(
        data_paths=[data_dir],
        checkpoint_dir=checkpoint_dir,
        init_checkpoint=init_checkpoint,
        config=RiskTrainingConfig(
            threshold=-1.0,
            batch_size=6,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=2,
            paired_margin_weight=0.5,
            paired_severity_weight=0.25,
            paired_batch_fraction=0.5,
            device="cpu",
        ),
        env_config=env_config,
        model_config=model_config,
        risk_cases=[
            RiskCase(
                seed=101,
                seat=2,
                decision_index=2,
                action_id=2,
                baseline_action_id=1,
                reward=-1.5,
                baseline_reward=0.25,
            )
        ],
        risk_dataset_start_seeds=[100],
        report_output=report_output,
    )

    assert len(metrics) == 2
    assert max(metric.paired_count for metric in metrics) > 0
    assert (checkpoint_dir / "epoch_001.pt").exists()
    assert report_output.exists()
