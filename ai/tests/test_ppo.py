from __future__ import annotations

import numpy as np
import pytest
import torch

from fh_mahjong_ai.ppo import PPOConfig, masked_policy_distribution


def test_ppo_config_defaults():
    cfg = PPOConfig()
    assert cfg.gamma == 0.99
    assert 0.0 < cfg.clip_eps < 1.0
    assert cfg.ppo_epochs >= 1


def test_masked_distribution_zeros_illegal_actions():
    # logits already masked the way PolicyValueNet.forward produces them
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[0.5, neg, 0.7, neg]])
    dist = masked_policy_distribution(masked_logits)
    probs = dist.probs[0]
    assert probs[1].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[3].item() == pytest.approx(0.0, abs=1e-6)
    assert probs[0].item() + probs[2].item() == pytest.approx(1.0, abs=1e-6)
    assert torch.isfinite(dist.entropy()).all()


def test_masked_distribution_single_legal_action_has_zero_entropy():
    neg = torch.finfo(torch.float32).min
    masked_logits = torch.tensor([[neg, 1.0, neg]])
    dist = masked_policy_distribution(masked_logits)
    assert dist.entropy().item() == pytest.approx(0.0, abs=1e-5)
    assert dist.probs[0, 1].item() == pytest.approx(1.0, abs=1e-6)


from fh_mahjong_ai.ppo import compute_gae


def test_gae_lambda1_gamma1_single_match_is_monte_carlo():
    rewards = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    values = np.array([0.0, 0.0, 0.0], dtype=np.float32)
    dones = np.array([0.0, 0.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [6.0, 5.0, 3.0], rtol=1e-6)
    np.testing.assert_allclose(adv, [6.0, 5.0, 3.0], rtol=1e-6)


def test_gae_resets_at_match_boundary():
    rewards = np.array([1.0, 5.0], dtype=np.float32)
    values = np.array([0.0, 0.0], dtype=np.float32)
    dones = np.array([1.0, 1.0], dtype=np.float32)
    adv, ret = compute_gae(rewards, values, dones, gamma=1.0, gae_lambda=1.0)
    np.testing.assert_allclose(ret, [1.0, 5.0], rtol=1e-6)
