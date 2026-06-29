import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.oracle import build_oracle_model


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_collect_oracle_rollouts_single_seat_mock():
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.oracle import collect_oracle_rollouts
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)  # 51ch
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=2, match_mode="classic", max_steps_per_episode=64, device="cpu")
    batch = collect_oracle_rollouts(env_cfg, model, cfg, base_seed=3)
    assert len(batch) >= 2
    assert batch.dones.sum() == 2          # one terminal per match
    assert batch.planes.shape[1] == 51     # oracle channels


def test_train_oracle_runs_on_mock_and_writes_checkpoint(tmp_path):
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.storage import save_checkpoint
    from fh_mahjong_ai.oracle import train_oracle
    mcfg = _mcfg()
    # 39ch anchor checkpoint to warm-start from
    anchor = tmp_path / "anchor.pt"
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(iterations=2, matches_per_iter=2, ppo_epochs=1, minibatch_size=8,
                    match_mode="classic", max_steps_per_episode=64, device="cpu")
    history = train_oracle(env_config=env_cfg, model_config=mcfg, anchor_checkpoint=anchor,
                           checkpoint_dir=tmp_path / "oracle", config=cfg, base_seed=1, run_eval=False)
    assert len(history) == 2
    assert (tmp_path / "oracle" / "iter_002.pt").exists()
    assert all(np.isfinite(h["policy_loss"]) for h in history)


def test_oracle_warmstart_matches_anchor_when_oracle_channels_zero(tmp_path):
    mcfg = _mcfg()
    anchor_env = EnvConfig()  # 39ch
    anchor = PolicyValueNet(anchor_env, mcfg).eval()
    ckpt = tmp_path / "anchor.pt"
    save_checkpoint(ckpt, anchor)

    oracle_env = EnvConfig(oracle_observation=True)  # 51ch
    oracle = build_oracle_model(oracle_env, mcfg, ckpt, device="cpu").eval()

    # input conv: first 39 channels copied from anchor, last 12 zeroed
    aw = anchor.plane_stem[0].weight.detach()
    ow = oracle.plane_stem[0].weight.detach()
    assert torch.allclose(ow[:, :39], aw)
    assert torch.count_nonzero(ow[:, 39:]) == 0

    # same observation, oracle channels zeroed -> identical policy logits
    rng = np.random.default_rng(0)
    planes39 = rng.standard_normal((1, 39, 42, 1)).astype(np.float32)
    planes51 = np.concatenate([planes39, np.zeros((1, 12, 42, 1), np.float32)], axis=1)
    scalars = rng.standard_normal((1, 58)).astype(np.float32)
    mask = np.ones((1, 204), np.int8)
    with torch.no_grad():
        la, _ = anchor(torch.from_numpy(planes39), torch.from_numpy(scalars), torch.from_numpy(mask))
        lo, _ = oracle(torch.from_numpy(planes51), torch.from_numpy(scalars), torch.from_numpy(mask))
    assert torch.allclose(la, lo, atol=1e-5)


def test_parallel_oracle_matches_sequential():
    # Parallel single-seat oracle collection over disjoint seed blocks must equal
    # the sequential run on the same seeds (same matches, order-independent rewards).
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.oracle import collect_oracle_rollouts, ParallelOracleCollector
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    mcfg = _mcfg()
    model = PolicyValueNet(env_cfg, mcfg)
    cfg = PPOConfig(matches_per_iter=4, match_mode="classic", max_steps_per_episode=64, device="cpu")

    seq = collect_oracle_rollouts(env_cfg, model, cfg, base_seed=222)

    collector = ParallelOracleCollector(env_cfg, mcfg, cfg, num_workers=2)
    collector.start()
    try:
        state = {k: v.detach().cpu() for k, v in model.state_dict().items()}
        par = collector.collect(state, base_seed=222, matches_per_iter=4)
    finally:
        collector.close()

    assert len(par) == len(seq)
    assert par.dones.sum() == seq.dones.sum()
    np.testing.assert_allclose(np.sort(par.rewards), np.sort(seq.rewards), rtol=1e-5)
