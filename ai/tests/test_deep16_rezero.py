import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, ReZeroResidualBlock


def test_growth_blocks_zero_leaves_state_dict_keys_unchanged() -> None:
    reference_model = PolicyValueNet(EnvConfig(), ModelConfig())
    reference_keys = set(reference_model.state_dict().keys())

    model = PolicyValueNet(EnvConfig(), ModelConfig(growth_blocks=0))
    keys = set(model.state_dict().keys())

    assert keys == reference_keys
    assert not any(key.startswith("growth.") for key in keys)


def test_growth_blocks_twelve_adds_expected_keys() -> None:
    model = PolicyValueNet(EnvConfig(), ModelConfig(growth_blocks=12))
    keys = set(model.state_dict().keys())

    for i in range(12):
        assert f"growth.{i}.alpha" in keys


def test_rezero_alpha_initialized_to_zero() -> None:
    block = ReZeroResidualBlock(channels=8)
    assert block.alpha.item() == 0.0


def test_rezero_forward_is_identity_at_init() -> None:
    torch.manual_seed(0)
    block = ReZeroResidualBlock(channels=8)
    inputs = torch.randn(2, 8, 5, 5)
    outputs = block(inputs)
    assert torch.equal(outputs, inputs)


@pytest.mark.parametrize("value", [-1, 65, True])
def test_growth_blocks_out_of_bounds_or_non_int_raises(value) -> None:
    with pytest.raises(ValueError):
        ModelConfig(growth_blocks=value)


def test_full_net_forward_identical_with_zero_alpha_growth_blocks() -> None:
    torch.manual_seed(42)
    env_config = EnvConfig()

    torch.manual_seed(1)
    baseline_model = PolicyValueNet(env_config, ModelConfig(growth_blocks=0))

    torch.manual_seed(1)
    grown_model = PolicyValueNet(env_config, ModelConfig(growth_blocks=12))

    batch = 3
    channels, height, width = env_config.plane_shape
    planes = torch.randn(batch, channels, height, width)
    scalars = torch.randn(batch, env_config.scalar_features)
    action_mask = torch.ones(batch, env_config.action_space_size)

    baseline_logits, baseline_value = baseline_model(planes, scalars, action_mask)
    grown_logits, grown_value = grown_model(planes, scalars, action_mask)

    assert torch.equal(baseline_logits, grown_logits)
    assert torch.equal(baseline_value, grown_value)
