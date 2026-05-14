from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import EnvConfig, ModelConfig, OfflineQConfig, TrainConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.train_offline_q import train_offline_q
from fh_mahjong_ai.storage import write_transitions_jsonl
from fh_mahjong_ai.trainer import OfflineQTrainer
from fh_mahjong_ai.types import Observation, Transition


def _obs(seed: int, env_config: EnvConfig) -> Observation:
    rng = np.random.default_rng(seed)
    return Observation(
        seat=0,
        planes=rng.standard_normal(env_config.plane_shape).astype(np.float32),
        scalars=rng.standard_normal(env_config.scalar_features).astype(np.float32),
        action_mask=np.ones(env_config.action_space_size, dtype=np.int8),
    )


def _transitions(n: int, env_config: EnvConfig) -> list[Transition]:
    transitions = []
    for i in range(n):
        transitions.append(
            Transition(
                observation=_obs(i, env_config),
                action_id=i % env_config.action_space_size,
                rewards=np.asarray([float(i == n - 1), 0, 0, 0], dtype=np.float32),
                next_observation=_obs(i + 100, env_config),
                terminated=i == n - 1,
                info={"terminal_rewards": np.asarray([1, -1, 0, 0], dtype=np.float32)},
            )
        )
    return transitions


def test_offline_q_trainer_runs_one_step() -> None:
    env_config = EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4)
    model_config = ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
    )
    model = PolicyValueNet(env_config, model_config)
    target_model = PolicyValueNet(env_config, model_config)
    target_model.load_state_dict(model.state_dict())

    buf = ReplayBuffer(capacity=8)
    buf.extend(_transitions(8, env_config))

    trainer = OfflineQTrainer(
        model=model,
        target_model=target_model,
        optimizer=torch.optim.AdamW(model.parameters(), lr=1e-3),
        train_config=TrainConfig(batch_size=4),
        q_config=OfflineQConfig(target_update_interval=1),
    )

    metrics = trainer.train_step(buf)
    trainer.update_target_network()

    assert np.isfinite(metrics.loss)
    assert np.isfinite(metrics.td_loss)
    assert np.isfinite(metrics.conservative_loss)


def test_train_offline_q_runs_and_saves_checkpoint(tmp_path: Path) -> None:
    env_config = EnvConfig()
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    metrics = train_offline_q(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=6,
        learning_rate=1e-3,
        target_update_interval=1,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()
