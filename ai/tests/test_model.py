from __future__ import annotations

import pytest
import torch
from torch import nn

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import ChannelAttention2d, DuelingQHead, PolicyValueNet, infer_model_config
from fh_mahjong_ai.storage import load_checkpoint
from conftest import SMALL_MODEL


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


def test_policy_value_net_action_risk_head_outputs_masked_action_scores() -> None:
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, ModelConfig())
    planes = torch.randn((2, *env_config.plane_shape))
    scalars = torch.randn((2, env_config.scalar_features))
    action_mask = torch.zeros((2, env_config.action_space_size), dtype=torch.int8)
    action_mask[:, 5:10] = 1

    logits, severity = model.action_risk_predictions(planes, scalars, action_mask)

    assert logits.shape == (2, env_config.action_space_size)
    assert severity.shape == (2, env_config.action_space_size)
    assert torch.isfinite(logits[:, 5:10]).all()
    assert (logits[:, :5] == torch.finfo(logits.dtype).min).all()
    assert (severity[:, :5] == 0.0).all()
    assert (severity[:, 5:10] >= 0.0).all()


def test_policy_value_net_supports_channel_attention_ablation() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig(channel_attention=True))

    assert any(isinstance(module, ChannelAttention2d) for module in model.modules())


def test_policy_value_net_can_load_old_checkpoint_without_optional_heads(tmp_path) -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    old_state = {
        key: value
        for key, value in model.state_dict().items()
        if not key.startswith(("q_head.", "large_loss_head.", "action_risk_probability_head.", "action_risk_severity_head."))
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
    assert first_layer.weight.shape[1] == EnvConfig().scalar_features
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


def test_state_dict_keys_are_unprefixed_after_trunk_extraction():
    """The shared trunk must stay loose modules on the parent, not a sub-Module.

    build_plane_scalar_encoders returns the modules for the caller to assign
    under their historical names. If anyone ever wraps them in a container
    Module, every key gains a prefix and EVERY committed checkpoint -- including
    the deployed champion -- stops loading. This pins the shape.
    """
    from conftest import DEFAULT_ENV, small_model_config
    from fh_mahjong_ai.model import PolicyValueNet

    keys = set(PolicyValueNet(DEFAULT_ENV, small_model_config()).state_dict())
    # Each trunk module keeps its own top-level key prefix.
    for name in ("plane_stem", "plane_blocks", "plane_head", "scalar_encoder"):
        assert any(k.startswith(f"{name}.") for k in keys), f"{name} lost its top-level key"
    # ...and none of them got nested behind a container. (PolicyValueNet has a
    # genuine `trunk` Sequential of its own, so only the container names the
    # extraction could plausibly introduce are checked here.)
    assert not any(k.startswith(("encoders.", "plane_scalar_encoders.")) for k in keys)


def test_default_kernel_width_keeps_state_dict_shapes() -> None:
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    stem = model.state_dict()["plane_stem.0.weight"]
    assert ModelConfig().kernel_width == 3
    assert tuple(stem.shape[2:]) == (3, 3)
    block = model.state_dict()["plane_blocks.0.layers.0.weight"]
    assert tuple(block.shape[2:]) == (3, 3)


def test_kernel_width_one_builds_1d_convs_and_forwards() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    sd = model.state_dict()
    assert tuple(sd["plane_stem.0.weight"].shape[2:]) == (3, 1)
    assert tuple(sd["plane_blocks.0.layers.0.weight"].shape[2:]) == (3, 1)
    assert tuple(sd["plane_blocks.0.layers.2.weight"].shape[2:]) == (3, 1)
    planes = torch.zeros(2, 39, 42, 1)
    scalars = torch.zeros(2, 58)
    mask = torch.ones(2, 204, dtype=torch.int8)
    logits, value = model(planes, scalars, mask)
    assert logits.shape == (2, 204) and value.shape == (2,)


def test_kernel_width_one_has_one_third_conv_params() -> None:
    env = EnvConfig(bridge_kind="mock")
    wide = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=3))
    narrow = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    assert narrow.plane_blocks[0].layers[0].weight.numel() * 3 == wide.plane_blocks[0].layers[0].weight.numel()


def test_kernel_width_is_shape_inferred() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    inferred = infer_model_config(model.state_dict())
    assert inferred.kernel_width == 1
    assert inferred == ModelConfig(**SMALL_MODEL, kernel_width=1)


def test_kernel_width_growth_blocks_follow_config() -> None:
    env = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1, growth_blocks=1))
    assert tuple(model.state_dict()["growth.0.layers.0.weight"].shape[2:]) == (3, 1)


# `True` is an int in Python and `True in (1, 3)` is True, so a bare
# membership test would build a width-1 conv out of a boolean.
@pytest.mark.parametrize("bad", [0, 2, 5, True])
def test_kernel_width_rejects_values_outside_one_and_three(bad: int) -> None:
    with pytest.raises(ValueError, match="kernel_width"):
        ModelConfig(**SMALL_MODEL, kernel_width=bad)


# --- mortal-scale-scratch Amendment 3: ReZero main trunk ---------------------

def test_default_trunk_rezero_false_keeps_state_dict_identical() -> None:
    from fh_mahjong_ai.model import ResidualBlock
    assert ModelConfig().trunk_rezero is False
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), ModelConfig(**SMALL_MODEL))
    keys = set(model.state_dict())
    assert not any(key.startswith("plane_blocks.") and key.endswith(".alpha") for key in keys)
    assert isinstance(model.plane_blocks[0], ResidualBlock)


def test_trunk_rezero_builds_rezero_blocks_that_start_as_identity() -> None:
    from fh_mahjong_ai.model import ReZeroResidualBlock
    env = EnvConfig(bridge_kind="mock")
    cfg = ModelConfig(**dict(SMALL_MODEL, residual_blocks=3), kernel_width=1, trunk_rezero=True)
    model = PolicyValueNet(env, cfg)
    for block in model.plane_blocks:
        assert isinstance(block, ReZeroResidualBlock)
        assert block.alpha.item() == 0.0
    sd = model.state_dict()
    assert {f"plane_blocks.{i}.alpha" for i in range(3)} <= set(sd)
    assert tuple(sd["plane_blocks.0.layers.0.weight"].shape[2:]) == (3, 1)
    # alpha == 0 => the whole stack is the identity on the stem output.
    x = torch.randn(2, cfg.channels, 42, 1)
    assert torch.equal(model.plane_blocks(x), x)
    planes = torch.zeros(2, 39, 42, 1)
    scalars = torch.zeros(2, 58)
    mask = torch.ones(2, 204, dtype=torch.int8)
    logits, value = model(planes, scalars, mask)
    assert logits.shape == (2, 204) and value.shape == (2,)


def test_trunk_rezero_adds_exactly_one_scalar_per_block() -> None:
    env = EnvConfig(bridge_kind="mock")
    plain = PolicyValueNet(env, ModelConfig(**dict(SMALL_MODEL, residual_blocks=3)))
    rezero = PolicyValueNet(env, ModelConfig(**dict(SMALL_MODEL, residual_blocks=3), trunk_rezero=True))

    def count(m):
        return sum(p.numel() for p in m.parameters())

    assert count(rezero) == count(plain) + 3


def test_trunk_rezero_is_shape_inferred_and_metadata_roundtrips() -> None:
    from fh_mahjong_ai.storage import model_config_metadata
    env = EnvConfig(bridge_kind="mock")
    cfg = ModelConfig(**SMALL_MODEL, kernel_width=1, trunk_rezero=True)
    model = PolicyValueNet(env, cfg)
    assert infer_model_config(model.state_dict()) == cfg
    assert infer_model_config(model.state_dict(), {"model_config": model_config_metadata(cfg)}) == cfg
    plain = PolicyValueNet(env, ModelConfig(**SMALL_MODEL, kernel_width=1))
    assert infer_model_config(plain.state_dict()).trunk_rezero is False


@pytest.mark.parametrize("bad", [0, 1, "true", None])
def test_trunk_rezero_rejects_non_bool(bad) -> None:
    with pytest.raises(ValueError, match="trunk_rezero"):
        ModelConfig(**SMALL_MODEL, trunk_rezero=bad)
