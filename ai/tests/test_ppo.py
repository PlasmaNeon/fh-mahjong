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
