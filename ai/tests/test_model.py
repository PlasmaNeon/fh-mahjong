from __future__ import annotations

import torch
from torch import nn

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import ChannelAttention2d, DuelingQHead, PolicyValueNet
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


def test_policy_value_net_forward_pads_legacy_scalar_observations() -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    planes = torch.randn((2, *env_config.plane_shape))
    scalars = torch.randn((2, 42))
    action_mask = torch.zeros((2, env_config.action_space_size), dtype=torch.int8)
    action_mask[:, 5:10] = 1

    logits, values = model(planes, scalars, action_mask)

    assert logits.shape == (2, env_config.action_space_size)
    assert values.shape == (2,)


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
    assert any(isinstance(module, DuelingQHead) for module in model.modules())


def test_policy_value_net_large_loss_head_outputs_probability_logit_and_severity() -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    planes = torch.randn((2, *env_config.plane_shape))
    scalars = torch.randn((2, env_config.scalar_features))

    logits, severity = model.large_loss_predictions(planes, scalars)
    detached_logits, detached_severity = model.large_loss_predictions(planes, scalars, detach_features=True)

    assert logits.shape == (2,)
    assert severity.shape == (2,)
    assert detached_logits.shape == (2,)
    assert detached_severity.shape == (2,)
    assert torch.isfinite(logits).all()
    assert torch.isfinite(detached_logits).all()
    assert (severity >= 0).all()
    assert (detached_severity >= 0).all()


def test_policy_value_net_supports_channel_attention_ablation() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig(channel_attention=True))

    assert any(isinstance(module, ChannelAttention2d) for module in model.modules())


def test_policy_value_net_can_load_old_checkpoint_without_optional_heads(tmp_path) -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    old_state = {
        key: value
        for key, value in model.state_dict().items()
        if not key.startswith(("q_head.", "large_loss_head."))
    }
    checkpoint = tmp_path / "old.pt"
    torch.save({"model": old_state, "step": 3}, checkpoint)

    loaded_model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(checkpoint, loaded_model)

    assert step == 3


def test_policy_value_net_pads_legacy_scalar_encoder_checkpoint(tmp_path) -> None:
    legacy_env_config = EnvConfig(scalar_features=42)
    legacy_model = PolicyValueNet(legacy_env_config, ModelConfig())
    checkpoint = tmp_path / "legacy_scalars.pt"
    torch.save({"model": legacy_model.state_dict(), "step": 5}, checkpoint)

    loaded_model = PolicyValueNet(EnvConfig(), ModelConfig())
    step = load_checkpoint(checkpoint, loaded_model)

    assert step == 5
    first_layer = loaded_model.scalar_encoder[0]
    assert isinstance(first_layer, nn.Linear)
    assert first_layer.weight.shape[1] == 50
    assert torch.count_nonzero(first_layer.weight[:, 42:]) == 0


def test_policy_value_net_can_load_checkpoint_with_legacy_linear_q_head(tmp_path) -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig(dueling_q=False))
    checkpoint = tmp_path / "legacy_q.pt"
    torch.save({"model": model.state_dict(), "step": 4}, checkpoint)

    loaded_model = PolicyValueNet(env_config, ModelConfig())
    step = load_checkpoint(checkpoint, loaded_model)

    assert step == 4


def test_policy_value_net_supports_pooled_ablation() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig(pool_planes=True))

    assert any(isinstance(module, nn.AdaptiveAvgPool2d) for module in model.modules())
