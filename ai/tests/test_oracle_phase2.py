import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import save_checkpoint


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def test_feature_dropout_schedule():
    from fh_mahjong_ai.oracle import feature_dropout_schedule
    T = 50
    vals = [feature_dropout_schedule(i, T) for i in range(1, T + 1)]
    assert vals[0] == 0.0                      # first iter: full perfect info
    assert vals[-1] == 1.0                     # last iter: fully masked
    assert all(0.0 <= v <= 1.0 for v in vals)  # probability
    assert all(b >= a - 1e-9 for a, b in zip(vals, vals[1:]))  # monotone nondecreasing
    # the first 20% hold at 0, the final 20% hold at 1
    assert feature_dropout_schedule(10, T) == 0.0   # iter 10 / 50 = 0.2 boundary still 0
    assert feature_dropout_schedule(45, T) == 1.0   # within the final-20% hold
