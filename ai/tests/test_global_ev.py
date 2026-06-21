from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.global_ev import (
    ActionGlobalEVNet,
    GlobalEVNet,
    branch_action_ev_arrays,
    constant_baseline_metrics,
    episode_split_indices,
    global_ev_targets,
    regression_metrics,
)
from fh_mahjong_ai.scripts.train_global_ev import GlobalEVTrainConfig, train_global_ev
from fh_mahjong_ai.storage import write_transitions_jsonl
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.types import Observation, Transition


def _observation(index: int, env_config: EnvConfig) -> Observation:
    rng = np.random.default_rng(index)
    return Observation(
        seat=index % 4,
        planes=rng.standard_normal(env_config.plane_shape).astype(np.float32),
        scalars=rng.standard_normal(env_config.scalar_features).astype(np.float32),
        action_mask=np.ones(env_config.action_space_size, dtype=np.int8),
    )


def _transitions(count: int, env_config: EnvConfig) -> list[Transition]:
    transitions: list[Transition] = []
    for index in range(count):
        episode_index = index // 3
        terminal_rewards = np.asarray(
            [
                1.0 + 0.1 * episode_index,
                -0.5,
                -0.25,
                -0.25 - 0.1 * episode_index,
            ],
            dtype=np.float32,
        )
        observation = _observation(index, env_config)
        transitions.append(
            Transition(
                observation=observation,
                action_id=index % env_config.action_space_size,
                rewards=terminal_rewards if index % 3 == 2 else np.zeros(4, dtype=np.float32),
                next_observation=_observation(index + 100, env_config),
                terminated=index % 3 == 2,
                info={
                    "episode_index": episode_index,
                    "terminal_rewards": terminal_rewards,
                },
            )
        )
    return transitions


def _small_model_config() -> ModelConfig:
    return ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
        q_hidden_dim=8,
        pool_planes=False,
    )


def test_global_ev_targets_use_acting_seat_reward() -> None:
    arrays = {
        "seats": np.asarray([0, 2, 3], dtype=np.int16),
        "terminal_rewards": np.asarray(
            [
                [1.0, 0.0, -0.5, -0.5],
                [-0.2, -0.3, 0.8, -0.3],
                [-0.1, -0.2, -0.3, 0.6],
            ],
            dtype=np.float32,
        ),
    }

    np.testing.assert_allclose(global_ev_targets(arrays), np.asarray([1.0, 0.8, 0.6], dtype=np.float32))


def test_episode_split_indices_hold_out_whole_episode_mod_bucket() -> None:
    train_indices, validation_indices = episode_split_indices(
        np.asarray([0, 0, 1, 1, 2, 2, 3, 3], dtype=np.int64),
        validation_mod=2,
        validation_remainder=0,
    )

    assert train_indices.tolist() == [2, 3, 6, 7]
    assert validation_indices.tolist() == [0, 1, 4, 5]


def test_global_ev_model_outputs_one_value_per_row() -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    model = GlobalEVNet(env_config, _small_model_config())

    values = model(torch.zeros((5, 2, 3, 1)), torch.zeros((5, 4)))

    assert values.shape == (5,)


def test_action_global_ev_model_outputs_one_value_per_row() -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    model = ActionGlobalEVNet(env_config, _small_model_config())

    values = model(torch.zeros((5, 2, 3, 1)), torch.zeros((5, 4)), torch.arange(5))

    assert values.shape == (5,)


def test_branch_action_ev_arrays_expands_preferred_and_avoided_rows() -> None:
    arrays = {
        "seats": np.asarray([2], dtype=np.int16),
        "planes": np.ones((1, 2, 3, 1), dtype=np.float32),
        "scalars": np.ones((1, 4), dtype=np.float32),
        "pairwise_preferred_action_ids": np.asarray([9], dtype=np.int64),
        "pairwise_avoided_action_ids": np.asarray([5], dtype=np.int64),
        "branch_preferred_rewards": np.asarray([0.7], dtype=np.float32),
        "branch_avoided_rewards": np.asarray([-0.2], dtype=np.float32),
        "episode_index": np.asarray([17], dtype=np.int64),
        "decision_indices": np.asarray([33], dtype=np.int64),
    }

    expanded = branch_action_ev_arrays(arrays)

    assert expanded["planes"].shape == (2, 2, 3, 1)
    assert expanded["action_ids"].tolist() == [9, 5]
    assert expanded["branch_role_ids"].tolist() == [1, 0]
    assert expanded["episode_index"].tolist() == [17, 17]
    assert expanded["decision_indices"].tolist() == [33, 33]
    np.testing.assert_allclose(expanded["terminal_rewards"][:, 2], np.asarray([0.7, -0.2], dtype=np.float32))


def test_regression_and_baseline_metrics_are_finite() -> None:
    targets = np.asarray([1.0, 0.0, -1.0], dtype=np.float32)
    predictions = np.asarray([0.8, 0.1, -0.4], dtype=np.float32)

    metrics = regression_metrics(predictions, targets)
    baseline = constant_baseline_metrics(targets[:2], targets[2:])

    assert metrics.count == 3
    assert np.isfinite(metrics.mae)
    assert np.isfinite(metrics.correlation)
    assert baseline.count == 1
    assert np.isfinite(baseline.mae)


def test_train_global_ev_writes_checkpoint_and_report(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    data_path = tmp_path / "transitions.jsonl"
    checkpoint_dir = tmp_path / "checkpoints"
    report_path = tmp_path / "reports" / "global_ev.json"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    report = train_global_ev(
        data_paths=[data_path],
        checkpoint_dir=checkpoint_dir,
        config=GlobalEVTrainConfig(
            batch_size=4,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=2,
            validation_mod=2,
            device="cpu",
        ),
        model_config=_small_model_config(),
        report_output=report_path,
    )

    assert report["method"] == "global_ev"
    assert report["validation_transitions"] > 0
    assert "baseline_validation" in report
    assert (checkpoint_dir / "epoch_001.pt").exists()
    saved_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved_report["validation"]["count"] == report["validation"]["count"]


def test_train_action_global_ev_writes_checkpoint_and_report(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    data_path = tmp_path / "transitions.jsonl"
    checkpoint_dir = tmp_path / "checkpoints"
    report_path = tmp_path / "reports" / "action_global_ev.json"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    report = train_global_ev(
        data_paths=[data_path],
        checkpoint_dir=checkpoint_dir,
        config=GlobalEVTrainConfig(
            batch_size=4,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=2,
            validation_mod=2,
            device="cpu",
            action_conditioned=True,
        ),
        model_config=_small_model_config(),
        report_output=report_path,
    )

    assert report["method"] == "action_global_ev"
    assert "baseline_validation" in report
    assert (checkpoint_dir / "epoch_001.pt").exists()


def test_train_action_global_ev_can_initialize_from_checkpoint(tmp_path: Path) -> None:
    env_config = EnvConfig(action_space_size=16, plane_shape=(2, 3, 1), scalar_features=4)
    data_path = tmp_path / "transitions.jsonl"
    init_checkpoint = tmp_path / "init.pt"
    checkpoint_dir = tmp_path / "checkpoints"
    write_transitions_jsonl(data_path, _transitions(12, env_config))
    init_env_config = EnvConfig(plane_shape=env_config.plane_shape, scalar_features=env_config.scalar_features)
    save_checkpoint(init_checkpoint, ActionGlobalEVNet(init_env_config, _small_model_config()), step=7)

    report = train_global_ev(
        data_paths=[data_path],
        checkpoint_dir=checkpoint_dir,
        config=GlobalEVTrainConfig(
            batch_size=4,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=1,
            validation_mod=2,
            device="cpu",
            action_conditioned=True,
        ),
        model_config=_small_model_config(),
        init_checkpoint=init_checkpoint,
    )

    assert report["init_checkpoint_step"] == 7
    assert (checkpoint_dir / "epoch_001.pt").exists()


def test_train_branch_action_global_ev_writes_checkpoint_and_report(tmp_path: Path) -> None:
    shard_dir = tmp_path / "branch_cf"
    shard_dir.mkdir()
    report_path = tmp_path / "reports" / "branch_action_ev.json"
    checkpoint_dir = tmp_path / "checkpoints"
    arrays = {
        "seats": np.asarray([0, 1, 2, 3], dtype=np.int16),
        "planes": np.random.default_rng(0).standard_normal((4, 2, 3, 1)).astype(np.float32),
        "scalars": np.random.default_rng(1).standard_normal((4, 4)).astype(np.float32),
        "action_ids": np.asarray([5, 6, 7, 8], dtype=np.int64),
        "pairwise_preferred_action_ids": np.asarray([1, 2, 3, 4], dtype=np.int64),
        "pairwise_avoided_action_ids": np.asarray([5, 6, 7, 8], dtype=np.int64),
        "branch_preferred_rewards": np.asarray([0.5, 0.2, 0.1, 0.4], dtype=np.float32),
        "branch_avoided_rewards": np.asarray([-0.5, -0.2, -0.1, -0.4], dtype=np.float32),
        "episode_index": np.asarray([0, 1, 2, 3], dtype=np.int64),
    }
    np.savez(shard_dir / "transitions-00000.npz", **arrays)
    (shard_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "npz_shards",
                "compressed": False,
                "shard_size": 4,
                "transitions": 4,
                "shards": [{"path": "transitions-00000.npz", "transitions": 4}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = train_global_ev(
        data_paths=[shard_dir],
        checkpoint_dir=checkpoint_dir,
        config=GlobalEVTrainConfig(
            batch_size=4,
            learning_rate=1e-3,
            epochs=1,
            steps_per_epoch=2,
            validation_mod=2,
            device="cpu",
            action_conditioned=True,
            branch_cf_action_targets=True,
            branch_cf_pairwise_weight=0.25,
            branch_cf_pairwise_margin=0.1,
            branch_cf_pairwise_reward_gap_weight=0.5,
            branch_cf_pairwise_reward_gap_margin_scale=0.1,
        ),
        model_config=_small_model_config(),
        report_output=report_path,
    )

    assert report["method"] == "branch_action_global_ev"
    assert report["transitions"] == 8
    assert report["branch_pairwise_validation"]["count"] == 2
    assert "branch_pairwise_validation_preferred_rate" in report["history"][0]
    assert report["history"][0]["train_pairwise_count"] > 0
    assert (checkpoint_dir / "epoch_001.pt").exists()
