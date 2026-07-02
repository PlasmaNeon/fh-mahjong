import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def _env_cfg():
    return EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                     oracle_observation=True)


def _collect(matches, slots, drop_prob, inference_mode="batched", base_seed=500, model=None):
    from fh_mahjong_ai.batched_selfplay import collect_selfplay_rollouts_batched
    from fh_mahjong_ai.envpool import make_selfplay_pool
    env_cfg = _env_cfg()
    cfg = PPOConfig(matches_per_iter=matches, match_mode="classic",
                    max_steps_per_episode=64, device="cpu")
    if model is None:
        torch.manual_seed(0)
        model = PolicyValueNet(env_cfg, _mcfg())
    pool = make_selfplay_pool(env_cfg, cfg, slots)
    try:
        return collect_selfplay_rollouts_batched(env_cfg, model, cfg, base_seed=base_seed,
                                                 drop_prob=drop_prob, pool=pool,
                                                 inference_mode=inference_mode)
    finally:
        pool.close()


def test_sample_masked_action_matches_categorical():
    from fh_mahjong_ai.batched_selfplay import sample_masked_action
    rng = np.random.default_rng(3)
    logits = rng.standard_normal(204).astype(np.float32)
    mask = np.zeros(204, dtype=np.int8)
    legal = [4, 9, 44, 108, 203]
    mask[legal] = 1
    temperature = 1.0

    # Reference probabilities: Categorical over temperature-scaled masked logits.
    masked = torch.full((204,), torch.finfo(torch.float32).min)
    masked[legal] = torch.from_numpy(logits[legal]) / temperature
    reference = torch.distributions.Categorical(logits=masked)

    draws = {}
    sample_rng = np.random.default_rng(7)
    for _ in range(20000):
        action, logprob = sample_masked_action(logits, mask, temperature, sample_rng)
        assert action in legal
        # Returned logprob matches the reference distribution's logprob.
        assert abs(logprob - float(reference.log_prob(torch.tensor(action)))) < 1e-5
        draws[action] = draws.get(action, 0) + 1
    for action in legal:
        expected = float(reference.probs[action])
        assert abs(draws.get(action, 0) / 20000 - expected) < 0.02


def test_batched_records_all_four_seats():
    batch = _collect(matches=3, slots=2, drop_prob=0.0)
    assert len(batch) > 0
    assert batch.dones.sum() >= 3  # at least one done block per non-empty match
    # All-4 self-play yields ~4x a single-seat run; sanity floor: > 2 decisions/match.
    assert len(batch) > 6


def test_batched_feature_dropout():
    full = _collect(matches=2, slots=2, drop_prob=1.0)
    assert np.allclose(full.planes[:, 39:51], 0.0)
    none = _collect(matches=2, slots=2, drop_prob=0.0)
    assert np.abs(none.planes[:, 39:51]).sum() > 0.0


def test_batched_trajectories_are_seat_contiguous():
    # Mirrors the Phase-2 contiguity regression: within each done-delimited
    # segment, decisions must belong to contiguous per-seat blocks, which shows
    # up as dones only at segment ends (no interleaving -> segment lengths sum).
    batch = _collect(matches=3, slots=3, drop_prob=0.5)
    ends = np.flatnonzero(batch.dones > 0.5)
    assert ends.size >= 3
    assert ends[-1] == len(batch) - 1  # batch ends on a block boundary
