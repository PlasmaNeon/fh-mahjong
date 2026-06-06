from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch

from fh_mahjong_ai.buffer import ReplayBuffer
from fh_mahjong_ai.config import DiscreteIQLConfig, EnvConfig, ModelConfig, TrainConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.risk_filter import RiskCase
from fh_mahjong_ai.scripts.train_iql import load_iql_replay_buffer, risk_context_indices, train_iql
from fh_mahjong_ai.storage import load_compatible_checkpoint, save_checkpoint, write_transitions_jsonl, write_transitions_npz_shards
from fh_mahjong_ai.trainer import (
    DiscreteIQLTrainer,
    discounted_terminal_returns,
    external_risk_policy_regularizer,
    large_loss_behavior_cloning_loss,
    large_loss_auxiliary_losses,
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
    assert np.isfinite(metrics.pairwise_q_loss)
    assert np.isfinite(metrics.large_loss_aux_loss)
    assert np.isfinite(metrics.large_loss_severity_loss)
    assert np.isfinite(metrics.large_loss_bc_loss)
    assert metrics.large_loss_bc_loss == 0.0
    assert metrics.large_loss_bc_count == 0
    assert np.isfinite(metrics.external_risk_policy_loss)
    assert metrics.external_risk_policy_loss == 0.0
    assert metrics.large_loss_target_rate == 0.0
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


def test_pairwise_margin_loss_can_scale_by_reward_delta_targets() -> None:
    logits = torch.tensor([[0.5, 0.2], [0.5, 0.2]])
    action_mask = torch.ones((2, 2), dtype=torch.int8)
    preferred = torch.tensor([0, 0])
    avoided = torch.tensor([1, 1])
    weights = torch.ones(2)
    reward_deltas = torch.tensor([0.0, 1.0])

    base_loss, count = pairwise_margin_loss(
        logits,
        action_mask,
        preferred,
        avoided,
        weights,
        margin=0.25,
    )
    scaled_loss, scaled_count = pairwise_margin_loss(
        logits,
        action_mask,
        preferred,
        avoided,
        weights,
        reward_delta_targets=reward_deltas,
        margin=0.25,
        reward_delta_margin_scale=0.5,
    )

    assert count == 2
    assert scaled_count == 2
    torch.testing.assert_close(base_loss, torch.tensor(0.0))
    torch.testing.assert_close(scaled_loss, torch.tensor(0.225))


def test_discrete_iql_trainer_runs_q_pairwise_loss() -> None:
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

    transitions = _transitions(8, env_config)
    for transition in transitions:
        transition.info["pairwise_preferred_action_id"] = 1
        transition.info["pairwise_avoided_action_id"] = 2
        transition.info["pairwise_weight"] = 1.0
    buf = ReplayBuffer(capacity=8)
    buf.extend(transitions)

    trainer = DiscreteIQLTrainer(
        model=model,
        target_model=target_model,
        optimizer=torch.optim.AdamW(model.parameters(), lr=1e-3),
        train_config=TrainConfig(batch_size=4),
        iql_config=DiscreteIQLConfig(
            target_update_interval=1,
            target_tau=1.0,
            max_weight=5.0,
            pairwise_q_weight=0.5,
            pairwise_q_margin=0.25,
        ),
    )

    metrics = trainer.train_step(buf)

    assert np.isfinite(metrics.loss)
    assert np.isfinite(metrics.pairwise_q_loss)
    assert metrics.pairwise_count > 0


def test_pairwise_margin_loss_empty_batch_stays_finite_with_masked_logits() -> None:
    logits = torch.tensor([[0.2, float("-inf"), 0.4]])
    action_mask = torch.tensor([[1, 0, 1]], dtype=torch.int8)
    preferred = torch.tensor([-1])
    avoided = torch.tensor([-1])
    weights = torch.tensor([0.0])

    loss, count = pairwise_margin_loss(logits, action_mask, preferred, avoided, weights, margin=0.25)

    assert count == 0
    torch.testing.assert_close(loss, torch.tensor(0.0))


def test_large_loss_auxiliary_losses_train_probability_and_severity_targets() -> None:
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
    planes = torch.randn((4, *env_config.plane_shape))
    scalars = torch.randn((4, env_config.scalar_features))
    returns = torch.tensor([0.5, -1.0, -1.5, -2.0])
    sample_weights = torch.ones(4)

    aux_loss, severity_loss, diagnostics = large_loss_auxiliary_losses(
        model,
        planes,
        scalars,
        torch.ones((4, env_config.action_space_size), dtype=torch.int8),
        torch.tensor([0, 1, 2, 3]),
        returns,
        sample_weights,
        threshold=-1.0,
        aux_weight=0.25,
        severity_weight=0.1,
        detach_features=True,
    )

    assert torch.isfinite(aux_loss)
    assert torch.isfinite(severity_loss)
    assert diagnostics["target_rate"] == 0.75
    assert 0.0 <= diagnostics["avg_probability"] <= 1.0
    assert diagnostics["avg_severity"] >= 0.0


def test_large_loss_auxiliary_losses_gather_dataset_action_risk() -> None:
    env_config = EnvConfig(action_space_size=4, plane_shape=(2, 3, 1), scalar_features=4)
    model_config = ModelConfig(
        channels=4,
        residual_blocks=1,
        plane_feature_dim=8,
        scalar_hidden_dim=8,
        trunk_hidden_dim=8,
        value_hidden_dim=8,
    )
    model = PolicyValueNet(env_config, model_config)
    planes = torch.randn((3, *env_config.plane_shape))
    scalars = torch.randn((3, env_config.scalar_features))
    action_mask = torch.ones((3, env_config.action_space_size), dtype=torch.int8)
    action_ids = torch.tensor([0, 2, 3])
    returns = torch.tensor([0.5, -1.5, -2.0])
    sample_weights = torch.ones(3)

    aux_loss, severity_loss, diagnostics = large_loss_auxiliary_losses(
        model,
        planes,
        scalars,
        action_mask,
        action_ids,
        returns,
        sample_weights,
        threshold=-1.0,
        aux_weight=0.25,
        severity_weight=0.1,
    )

    assert torch.isfinite(aux_loss)
    assert torch.isfinite(severity_loss)
    assert np.isclose(diagnostics["target_rate"], 2 / 3)


def test_external_risk_policy_regularizer_penalizes_risky_policy_mass() -> None:
    class FixedRiskModel(torch.nn.Module):
        def action_risk_predictions(self, planes, scalars, action_mask):
            logits = torch.tensor([[2.0, -2.0, 2.0, -2.0]], dtype=torch.float32).repeat(planes.shape[0], 1)
            severities = torch.zeros_like(logits)
            return logits, severities

    policy_logits = torch.tensor([[4.0, 0.0, 0.0, 0.0], [0.0, 4.0, 0.0, 0.0]], dtype=torch.float32)
    action_mask = torch.ones((2, 4), dtype=torch.int8)
    planes = torch.zeros((2, 2, 3, 1), dtype=torch.float32)
    scalars = torch.zeros((2, 4), dtype=torch.float32)
    sample_weights = torch.ones(2)

    loss, diagnostics = external_risk_policy_regularizer(
        risk_model=FixedRiskModel(),
        policy_logits=policy_logits,
        planes=planes,
        scalars=scalars,
        action_mask=action_mask,
        sample_weights=sample_weights,
        weight=1.0,
        threshold=0.6,
        family="all",
    )

    assert torch.isfinite(loss)
    assert loss.item() > 0.0
    assert 0.0 < diagnostics["avg_probability"] < 1.0
    assert np.isclose(diagnostics["policy_mass"], 1.0)


def test_large_loss_behavior_cloning_loss_applies_only_to_tail_rows() -> None:
    per_sample_policy_loss = torch.tensor([0.1, 0.2, 1.0, 2.0])
    returns = torch.tensor([0.5, -0.5, -1.0, -2.0])
    sample_weights = torch.tensor([1.0, 1.0, 2.0, 1.0])

    loss, count = large_loss_behavior_cloning_loss(
        per_sample_policy_loss,
        returns,
        sample_weights,
        threshold=-1.0,
        weight=1.0,
    )

    assert count == 2
    torch.testing.assert_close(loss, torch.tensor((1.0 * 2.0 + 2.0 * 1.0) / 3.0))

    disabled, disabled_count = large_loss_behavior_cloning_loss(
        per_sample_policy_loss,
        returns,
        sample_weights,
        threshold=-1.0,
        weight=0.0,
    )
    assert disabled_count == 0
    torch.testing.assert_close(disabled, torch.tensor(0.0))


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
    risk_ckpt = tmp_path / "risk.pt"
    write_transitions_jsonl(data_path, _transitions(12, env_config))
    save_checkpoint(risk_ckpt, PolicyValueNet(env_config, ModelConfig()), step=1)

    metrics = train_iql(
        data_path=data_path,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=6,
        learning_rate=1e-3,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        large_loss_threshold=1.0,
        large_loss_penalty=0.1,
        large_loss_weight=2.0,
        large_loss_aux_weight=0.25,
        large_loss_severity_weight=0.1,
        large_loss_aux_detach=True,
        large_loss_bc_weight=0.5,
        external_risk_checkpoint=risk_ckpt,
        external_risk_policy_weight=0.05,
        external_risk_policy_family="discard",
        device="cpu",
        log_interval=1,
    )

    assert len(metrics) > 0
    assert (ckpt_dir / "epoch_001.pt").exists()
    assert any(metric.large_loss_bc_count > 0 for metric in metrics)
    assert any(metric.external_risk_policy_loss >= 0.0 for metric in metrics)


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


def test_train_iql_can_use_counterfactual_risk_trace_pairwise_labels(tmp_path: Path) -> None:
    env_config = EnvConfig()
    transitions = _transitions(8, env_config)
    transitions[1].observation.metadata["decision_index"] = 11

    shard_dir = tmp_path / "shards"
    ckpt_dir = tmp_path / "checkpoints"
    write_transitions_npz_shards(shard_dir, transitions, shard_size=8)

    report_path = tmp_path / "paired_trace.json"
    report_path.write_text(
        json.dumps(
            {
                "pairs": [
                    {
                        "seed": 100,
                        "seat": 0,
                        "anchor_reward": 0.2,
                        "candidate_reward": -1.4,
                        "reward_delta": -1.6,
                        "first_divergence_index": 11,
                        "first_divergence": {
                            "left": {
                                "decision_index": 11,
                                "action_id": 2,
                                "action_label": "discard 2m",
                            },
                            "right": {
                                "decision_index": 11,
                                "action_id": 1,
                                "action_label": "discard 1m",
                            },
                        },
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    metrics = train_iql(
        data_path=shard_dir,
        checkpoint_dir=ckpt_dir,
        epochs=1,
        batch_size=8,
        learning_rate=1e-3,
        large_loss_threshold=-1.0,
        pairwise_q_weight=0.5,
        pairwise_q_margin=0.25,
        risk_trace_reports=[report_path],
        risk_trace_dataset_start_seeds=[100],
        risk_trace_counterfactual_labels=True,
        risk_trace_min_counterfactual_reward_gap=0.1,
        pairwise_replay_multiplier=2,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
    )

    assert any(metric.pairwise_count > 0 for metric in metrics)
    assert (ckpt_dir / "epoch_001.pt").exists()


def test_train_iql_can_mix_direct_pairwise_auxiliary_data(tmp_path: Path) -> None:
    env_config = EnvConfig()
    base_dir = tmp_path / "base-shards"
    pairwise_dir = tmp_path / "pairwise-shards"
    ckpt_dir = tmp_path / "checkpoints"
    transitions = _transitions(8, env_config)
    write_transitions_npz_shards(base_dir, transitions, shard_size=8)

    planes = np.stack([transitions[1].observation.planes, transitions[2].observation.planes]).astype(np.float32)
    scalars = np.stack([transitions[1].observation.scalars, transitions[2].observation.scalars]).astype(np.float32)
    action_mask = np.stack([transitions[1].observation.action_mask, transitions[2].observation.action_mask]).astype(np.int8)
    pairwise_dir.mkdir()
    np.savez(
        pairwise_dir / "transitions-00000.npz",
        seats=np.asarray([0, 0], dtype=np.int16),
        planes=planes,
        scalars=scalars,
        action_mask=action_mask,
        action_ids=np.asarray([1, 2], dtype=np.int64),
        episode_index=np.asarray([900, 901], dtype=np.int64),
        terminal_rewards=np.asarray([[-1.2, 0.0, 0.0, 0.0], [-1.1, 0.0, 0.0, 0.0]], dtype=np.float32),
        sample_weights=np.ones(2, dtype=np.float32),
        pairwise_preferred_action_ids=np.asarray([3, 4], dtype=np.int64),
        pairwise_avoided_action_ids=np.asarray([1, 2], dtype=np.int64),
        pairwise_weights=np.ones(2, dtype=np.float32),
        pairwise_reward_delta_targets=np.asarray([0.25, 1.25], dtype=np.float32),
    )
    (pairwise_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "format": "npz_shards",
                "compressed": False,
                "shard_size": 2,
                "transitions": 2,
                "shards": [{"path": "transitions-00000.npz", "transitions": 2}],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    buf, transition_count, counts = load_iql_replay_buffer(
        [base_dir],
        pairwise_data_paths=[pairwise_dir],
    )
    batch = buf.sample(10, seed=0)

    assert transition_count == 10
    assert counts == [8, 2]
    assert np.count_nonzero(batch.sample_weights == 0.0) == 2
    assert np.count_nonzero(batch.pairwise_weights > 0.0) == 2
    assert sorted(batch.pairwise_reward_delta_targets[batch.pairwise_weights > 0.0].tolist()) == [0.25, 1.25]

    metrics = train_iql(
        data_path=base_dir,
        checkpoint_dir=ckpt_dir,
        pairwise_data_paths=[pairwise_dir],
        epochs=1,
        batch_size=10,
        learning_rate=1e-3,
        pairwise_q_weight=0.5,
        pairwise_q_margin=0.25,
        pairwise_reward_delta_margin_scale=0.1,
        target_update_interval=1,
        target_tau=1.0,
        max_weight=5.0,
        device="cpu",
        log_interval=1,
    )

    assert any(metric.pairwise_count > 0 for metric in metrics)


def test_risk_context_indices_keeps_exact_matches_and_same_seat_context() -> None:
    arrays = {
        "action_ids": np.arange(6, dtype=np.int64),
        "episode_index": np.asarray([0, 0, 0, 0, 1, 0], dtype=np.int64),
        "seats": np.asarray([0, 0, 0, 1, 0, 0], dtype=np.int64),
        "decision_indices": np.asarray([9, 10, 11, 10, 10, 14], dtype=np.int64),
        "risk_case_matches": np.asarray([False, True, False, False, False, False], dtype=np.bool_),
    }

    indices = risk_context_indices(arrays, radius=1)

    assert indices.tolist() == [0, 1, 2]


def test_load_iql_replay_buffer_can_filter_secondary_risk_datasets(tmp_path: Path) -> None:
    env_config = EnvConfig()
    base_dir = tmp_path / "base-shards"
    risk_dir = tmp_path / "risk-shards"
    base_transitions = _transitions(8, env_config)
    risk_transitions = _transitions(8, env_config)
    for index, transition in enumerate(risk_transitions):
        transition.observation.metadata["decision_index"] = index

    write_transitions_npz_shards(base_dir, base_transitions, shard_size=8)
    write_transitions_npz_shards(risk_dir, risk_transitions, shard_size=8)

    _, transition_count, counts = load_iql_replay_buffer(
        [base_dir, risk_dir],
        risk_cases=[
            RiskCase(
                seed=201,
                seat=0,
                decision_index=5,
                action_id=5,
                baseline_action_id=4,
            )
        ],
        risk_weight=3.0,
        risk_dataset_start_seeds=[1000, 200],
        apply_risk_cases=True,
        risk_filter_datasets=True,
        risk_context_radius=1,
    )

    assert transition_count == 11
    assert counts == [8, 3]


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
