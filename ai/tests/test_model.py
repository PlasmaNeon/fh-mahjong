from __future__ import annotations

import torch
from torch import nn

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import load_checkpoint


def test_policy_value_net_default_preserves_tile_positions() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig())

    assert not any(isinstance(module, nn.AdaptiveAvgPool2d) for module in model.modules())


def test_policy_value_net_forward_masks_illegal_actions() -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    planes = torch.randn((2, *env_config.plane_shape))
    scalars = torch.randn((2, env_config.scalar_features))
    action_mask = torch.zeros((2, env_config.action_space_size), dtype=torch.int8)
    action_mask[:, 5:10] = 1

    logits, values = model(planes, scalars, action_mask)

    assert logits.shape == (2, env_config.action_space_size)
    assert values.shape == (2,)
    assert torch.isfinite(logits[:, 5:10]).all()
    assert (logits[:, :5] == torch.finfo(logits.dtype).min).all()


def test_policy_value_net_q_head_masks_illegal_actions() -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    planes = torch.randn((2, *env_config.plane_shape))
    scalars = torch.randn((2, env_config.scalar_features))
    action_mask = torch.zeros((2, env_config.action_space_size), dtype=torch.int8)
    action_mask[:, 5:10] = 1

    q_values, values = model.q_values(planes, scalars, action_mask)

    assert q_values.shape == (2, env_config.action_space_size)
    assert values.shape == (2,)
    assert torch.isfinite(q_values[:, 5:10]).all()
    assert (q_values[:, :5] == torch.finfo(q_values.dtype).min).all()


def test_policy_value_net_can_load_old_checkpoint_without_q_head(tmp_path) -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    old_state = {key: value for key, value in model.state_dict().items() if not key.startswith("q_head.")}
    checkpoint = tmp_path / "old.pt"
    torch.save({"model": old_state, "step": 3}, checkpoint)

    loaded_model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(checkpoint, loaded_model)

    assert step == 3


def test_policy_value_net_supports_pooled_ablation() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig(pool_planes=True))

    assert any(isinstance(module, nn.AdaptiveAvgPool2d) for module in model.modules())
