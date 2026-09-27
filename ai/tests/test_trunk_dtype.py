"""PPOConfig.trunk_dtype: the opt-in bfloat16 encoder."""
import copy
from dataclasses import asdict, replace

import numpy as np
import pytest
import torch

from fh_mahjong_ai import train_state as train_state_mod
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import model_config_metadata
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.train_b2b import trunk_autocast_dtype

ENV = EnvConfig(bridge_kind="mock")


def _echo(config: PPOConfig) -> dict:
    return {"ppo_config": asdict(config),
            "model_config": model_config_metadata(ModelConfig()),
            "env_config": asdict(ENV)}


def test_default_is_float32_and_needs_no_autocast():
    assert PPOConfig().trunk_dtype == "float32"
    assert trunk_autocast_dtype(PPOConfig()) is None


def test_bfloat16_requires_the_batched_collector_on_cuda():
    ok = PPOConfig(trunk_dtype="bfloat16", collector="batched", device="cuda")
    assert trunk_autocast_dtype(ok) is torch.bfloat16
    with pytest.raises(ValueError, match="collector='batched'"):
        trunk_autocast_dtype(replace(ok, collector="process"))
    with pytest.raises(ValueError, match="CUDA"):
        trunk_autocast_dtype(replace(ok, device="cpu"))
    with pytest.raises(ValueError, match="unknown"):
        trunk_autocast_dtype(replace(ok, trunk_dtype="float16"))


def test_legacy_state_reads_as_float32_and_rejects_a_bfloat16_resume():
    saved = _echo(PPOConfig())
    del saved["ppo_config"]["trunk_dtype"]
    train_state_mod._validate_resume_config_echo(_echo(PPOConfig()), copy.deepcopy(saved))
    with pytest.raises(ValueError, match="trunk_dtype"):
        train_state_mod._validate_resume_config_echo(
            _echo(PPOConfig(trunk_dtype="bfloat16")), copy.deepcopy(saved))


def test_changing_trunk_dtype_on_resume_is_rejected():
    with pytest.raises(ValueError, match="trunk_dtype"):
        train_state_mod._validate_resume_config_echo(
            _echo(PPOConfig(trunk_dtype="bfloat16")), _echo(PPOConfig()))


def _model() -> PolicyValueNet:
    torch.manual_seed(0)
    return PolicyValueNet(ENV, ModelConfig(
        channels=16, residual_blocks=2, plane_feature_dim=32, scalar_hidden_dim=16,
        trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16,
        event_window=8, privileged_critic=True, aux_heads=True))


def _inputs(device):
    rng = np.random.default_rng(0)
    n = 6
    planes = torch.from_numpy((rng.random((n, 51, 42, 1)) < 0.2).astype(np.float32)).to(device)
    scalars = torch.from_numpy(rng.random((n, 58), dtype=np.float32)).to(device)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(n, 8)).astype(np.int64)).to(device)
    lengths = torch.from_numpy(rng.integers(1, 9, size=n).astype(np.int64)).to(device)
    return planes, scalars, events, lengths


def test_autocast_setting_leaves_cpu_encode_untouched():
    model = _model().eval()
    inputs = _inputs("cpu")
    with torch.no_grad():
        reference = model.encode(*inputs)
        model.trunk_autocast = torch.bfloat16
        features = model.encode(*inputs)
    assert torch.equal(features, reference)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="needs CUDA")
def test_bfloat16_encode_returns_float32_features_near_float32():
    model = _model().cuda().eval()
    inputs = _inputs("cuda")
    with torch.no_grad():
        reference = model.encode(*inputs)
        model.trunk_autocast = torch.bfloat16
        features = model.encode(*inputs)
    assert features.dtype == torch.float32
    assert not torch.equal(features, reference)
    torch.testing.assert_close(features, reference, rtol=5e-2, atol=5e-2)
