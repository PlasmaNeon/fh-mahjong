from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig, collect_rollouts
from fh_mahjong_ai.parallel_rollouts import ParallelRolloutCollector, _split_counts


def test_split_counts_even_and_remainder():
    assert _split_counts(8, 4) == [2, 2, 2, 2]
    assert _split_counts(5, 2) == [3, 2]
    assert _split_counts(2, 4) == [1, 1, 0, 0]


def _small_model_cfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def _cpu_state_dict(model):
    return {k: v.detach().cpu() for k, v in model.state_dict().items()}


def test_parallel_matches_sequential_rewards():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seq = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=900)

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), [_cpu_state_dict(frozen)], base_seed=900, matches_per_iter=4)
    finally:
        collector.close()

    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum() == 4.0
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)


def test_collector_propagates_worker_exception():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    frozen = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=1)
    collector.start()
    try:
        # A state_dict from an incompatible model shape makes load_state_dict raise in the worker.
        bad = PolicyValueNet(EnvConfig(action_space_size=8, plane_shape=(2, 3, 1), scalar_features=4),
                             _small_model_cfg())
        with pytest.raises(RuntimeError):
            collector.collect(_cpu_state_dict(bad), [_cpu_state_dict(frozen)], base_seed=1, matches_per_iter=2)
    finally:
        collector.close()


def test_collector_close_joins_workers():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    procs = list(collector._procs)
    collector.close()
    assert procs
    assert all(not p.is_alive() for p in procs)


def test_parallel_grp_matches_sequential():
    from fh_mahjong_ai.global_ev import GlobalEVNet

    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    frozen = PolicyValueNet(env_cfg, mcfg)
    grp_net = GlobalEVNet(env_cfg, mcfg)
    grp_state = {k: v.detach().cpu() for k, v in grp_net.state_dict().items()}
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    grp_net.eval()
    seq = collect_rollouts(env_cfg, learner, frozen, cfg, base_seed=222, grp_model=grp_net)

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2, grp_state_dict=grp_state)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), [_cpu_state_dict(frozen)], base_seed=222, matches_per_iter=4)
    finally:
        collector.close()
    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum()
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)


def test_parallel_with_pool_matches_sequential():
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64)
    mcfg = _small_model_cfg()
    learner = PolicyValueNet(env_cfg, mcfg)
    pool_nets = [PolicyValueNet(env_cfg, mcfg), PolicyValueNet(env_cfg, mcfg)]
    pool_states = [_cpu_state_dict(n) for n in pool_nets]
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seq = collect_rollouts(env_cfg, learner, pool_nets[0], cfg, base_seed=1234, opponents=pool_nets)

    collector = ParallelRolloutCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        par = collector.collect(_cpu_state_dict(learner), pool_states, base_seed=1234, matches_per_iter=4)
    finally:
        collector.close()

    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum() == 4.0
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)
