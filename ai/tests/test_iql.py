from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import DiscreteIQLConfig, EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.risk_filter import RiskCase
from fh_mahjong_ai.scripts.train_iql import load_iql_replay_buffer, train_iql
from fh_mahjong_ai.storage import load_compatible_checkpoint, write_transitions_jsonl, write_transitions_npz_shards
from fh_mahjong_ai.trainer import (
    DiscreteIQLTrainer,
    discounted_terminal_returns,
    large_loss_adjusted_rewards,
    large_loss_sample_weights,
    pairwise_margin_loss,
)
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
                info={
                    "episode_index": i // 4,
                    "terminal_rewards": np.asarray([1, -1, 0, 0], dtype=np.float32),
                },
            )
        )
    return transitions


def test_discrete_iql_trainer_runs_one_step() -> None:
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

    trainer = DiscreteIQLTrainer(
        model=model,
        target_model=target_model,
        optimizer=torch.optim.AdamW(model.parameters(), lr=1e-3),
        train_config=TrainConfig(batch_size=4),
        iql_config=DiscreteIQLConfig(target_update_interval=1, target_tau=1.0, max_weight=5.0),
    )

    metrics = trainer.train_step(buf)
    trainer.update_target_network()

    assert np.isfinite(metrics.loss)
    assert np.isfinite(metrics.q_loss)
    assert np.isfinite(metrics.value_loss)
    assert np.isfinite(metrics.policy_loss)
    assert np.isfinite(metrics.bc_loss)
    assert np.isfinite(metrics.cql_loss)
    assert np.isfinite(metrics.pairwise_loss)
    assert 0.0 <= metrics.avg_weight <= 5.0
    assert 0.0 <= metrics.max_weight <= 5.0
    assert metrics.avg_sample_weight == 1.0
    assert metrics.max_sample_weight == 1.0
    assert metrics.pairwise_count == 0


def test_pairwise_margin_loss_prefers_anchor_action() -> None:
    logits = torch.tensor([[0.2, 0.7, 0.4], [0.8, 0.1, 0.3]])
    action_mask = torch.ones((2, 3), dtype=torch.int8)
    preferred = torch.tensor([0, -1])
    avoided = torch.tensor([1, -1])
    weights = torch.tensor([2.0, 0.0])

    loss, count = pairwise_margin_loss(logits, action_mask, preferred, avoided, weights, margin=0.25)

    assert count == 1
    torch.testing.assert_close(loss, torch.tensor(0.75))


def test_pairwise_margin_loss_empty_batch_stays_finite_with_masked_logits() -> None:
    logits = torch.tensor([[0.2, float("-inf"), 0.4]])
    action_mask = torch.tensor([[1, 0, 1]], dtype=torch.int8)
    preferred = torch.tensor([-1])
    avoided = torch.tensor([-1])
    weights = torch.tensor([0.0])

    loss, count = pairwise_margin_loss(logits, action_mask, preferred, avoided, weights, margin=0.25)

    assert count == 0
    torch.testing.assert_close(loss, torch.tensor(0.0))


def test_discounted_terminal_returns_use_steps_to_done() -> None:
    returns = torch.tensor([1.0, 1.0, -2.0])
    steps_to_done = torch.tensor([0, 1, 2])

    targets = discounted_terminal_returns(returns, steps_to_done, gamma=0.5)

    torch.testing.assert_close(targets, torch.tensor([1.0, 0.5, -0.5]))


def test_large_loss_adjusted_rewards_penalizes_only_below_threshold() -> None:
    rewards = torch.tensor([1.0, -0.5, -1.0, -1.5, -2.0])

    adjusted = large_loss_adjusted_rewards(rewards, threshold=-1.0, penalty=0.25)

    torch.testing.assert_close(adjusted, torch.tensor([1.0, -0.5, -1.0, -1.625, -2.25]))


def test_large_loss_adjusted_rewards_is_default_noop() -> None:
    rewards = torch.tensor([1.0, -2.0])

    torch.testing.assert_close(large_loss_adjusted_rewards(rewards, threshold=None, penalty=0.25), rewards)
    torch.testing.assert_close(large_loss_adjusted_rewards(rewards, threshold=-1.0, penalty=0.0), rewards)


def test_large_loss_sample_weights_upweights_threshold_and_below() -> None:
    rewards = torch.tensor([1.0, -0.5, -1.0, -1.5])

    weights = large_loss_sample_weights(rewards, threshold=-1.0, weight=3.0)

    torch.testing.assert_close(weights, torch.tensor([1.0, 1.0, 3.0, 3.0]))
    torch.testing.assert_close(large_loss_sample_weights(rewards, threshold=None, weight=3.0), torch.ones_like(rewards))
    torch.testing.assert_close(large_loss_sample_weights(rewards, threshold=-1.0, weight=1.0), torch.ones_like(rewards))


def test_train_iql_runs_and_saves_checkpoint(tmp_path: Path) -> None:
    env_config = EnvConfig()
    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    metrics = train_iql(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=6,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        large_loss_threshold=-1.0,
        large_loss_penalty=0.1,
        large_loss_weight=2.0,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_train_iql_runs_from_npz_shards_with_limit(tmp_path: Path) -> None:
    env_config = EnvConfig()
    shard_dir = tmp_path / "shards"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_npz_shards(shard_dir, _transitions(12, env_config), shard_size=5)

    metrics = train_iql(
        data_path=shard_dir,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=4,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        max_transitions=8,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_load_iql_replay_buffer_can_add_pairwise_auxiliary_rows(tmp_path: Path) -> None:
    env_config = EnvConfig()
    shard_dir = tmp_path / "shards"
    write_transitions_npz_shards(shard_dir, _transitions(8, env_config), shard_size=8)

    _, transition_count, counts = load_iql_replay_buffer(
        [shard_dir],
        risk_cases=[
            RiskCase(
                seed=100,
                seat=0,
                action_id=0,
                baseline_action_id=1,
            )
        ],
        risk_weight=1.0,
        risk_dataset_start_seeds=[100],
        apply_risk_cases=True,
        pairwise_replay_multiplier=5,
    )

    assert transition_count == 13
    assert counts == [5, 8]


def test_train_iql_runs_from_multiple_npz_shards_with_mixed_scalar_shapes(tmp_path: Path) -> None:
    env_50 = EnvConfig()
    env_42 = EnvConfig(scalar_features=42)
    shard_50 = tmp_path / "shards-50"
    shard_42 = tmp_path / "shards-42"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_npz_shards(shard_50, _transitions(6, env_50), shard_size=3)
    write_transitions_npz_shards(shard_42, _transitions(6, env_42), shard_size=3)

    metrics = train_iql(
        data_path=[shard_42, shard_50],
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=8,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_train_iql_can_initialize_q_head_from_policy(tmp_path: Path) -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    checkpoint = tmp_path / "bc.pt"
    torch.save({"model": {key: value for key, value in model.state_dict().items() if not key.startswith("q_head.")}}, checkpoint)

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    metrics = train_iql(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        init_checkpoint=checkpoint,
        init_q_from_policy=True,
        epochs=1,
        batch_size=6,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0


def test_load_compatible_checkpoint_reuses_matching_architecture_parts(tmp_path: Path) -> None:
    env_config = EnvConfig()
    source = PolicyValueNet(env_config, ModelConfig(residual_blocks=2))
    target = PolicyValueNet(env_config, ModelConfig(residual_blocks=3))
    checkpoint = tmp_path / "source.pt"
    torch.save({"model": source.state_dict(), "step": 7}, checkpoint)

    step, report = load_compatible_checkpoint(checkpoint, target)

    assert step == 7
    assert report["loaded_keys"] > 0
    assert any(str(key).startswith("plane_blocks.2.") for key in report["missing_keys"])


def test_train_iql_supports_partial_init_for_deeper_model(tmp_path: Path) -> None:
    env_config = EnvConfig()
    source = PolicyValueNet(env_config, ModelConfig(residual_blocks=2))
    checkpoint = tmp_path / "source.pt"
    torch.save({"model": source.state_dict(), "step": 2}, checkpoint)

    data_path = tmp_path / "data.jsonl"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_jsonl(data_path, _transitions(12, env_config))

    metrics = train_iql(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        init_checkpoint=checkpoint,
        partial_init_checkpoint=True,
        model_config=ModelConfig(residual_blocks=3),
        epochs=1,
        batch_size=6,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()
