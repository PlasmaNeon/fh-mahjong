import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from fh_mahjong_ai.storage import load_checkpoint, model_config_metadata, save_checkpoint
from fh_mahjong_ai.train_b2b import _b2b_model_env_config, build_b2b_model

B2B = dict(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)


def _init_checkpoint(tmp_path):
    env = EnvConfig(bridge_kind="mock")
    config = ModelConfig(**B2B)
    model = PolicyValueNet(env, config)
    path = tmp_path / "init.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(config)})
    return env, config, path


def _inputs(seed=0, batch=4):
    rng = np.random.default_rng(seed)
    public = torch.from_numpy(rng.random((batch, 39, 42, 1), dtype=np.float32))
    lookahead = torch.from_numpy(rng.random((batch, 13, 42, 1), dtype=np.float32))
    oracle = torch.from_numpy(rng.random((batch, 12, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((batch, 58), dtype=np.float32))
    mask = torch.ones((batch, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(batch, 8)).astype(np.int64))
    lengths = torch.full((batch,), 8, dtype=torch.int64)
    return public, lookahead, oracle, scalars, mask, events, lengths


def test_widened_warm_start_matches_init_at_step_zero(tmp_path):
    env0, config0, path = _init_checkpoint(tmp_path)
    init = PolicyValueNet(env0, config0)
    load_checkpoint(path, init)
    init.eval()
    env1 = _b2b_model_env_config(EnvConfig(bridge_kind="mock", oracle_observation=True, lookahead_version=1))
    assert env1.plane_shape == (52, 42, 1)
    model = build_b2b_model(env1, ModelConfig(**B2B, lookahead_version=1), path)
    assert model.policy_channels == 52
    public, lookahead, oracle, scalars, mask, events, lengths = _inputs()
    with torch.no_grad():
        ref_logits, ref_value = init(torch.cat([public, oracle], 1), scalars, mask, events, lengths)
        logits, value = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        ref_aux = init.aux_predictions(init.encode(torch.cat([public, oracle], 1), scalars, events, lengths))
        aux = model.aux_predictions(model.encode(torch.cat([public, lookahead, oracle], 1), scalars, events, lengths))
    assert torch.allclose(logits, ref_logits, atol=1e-5)
    assert torch.allclose(value, ref_value, atol=1e-5)
    for key in ref_aux:
        assert torch.allclose(aux[key], ref_aux[key], atol=1e-5), key
    assert torch.equal(logits.argmax(1), ref_logits.argmax(1))


def test_privileged_slice_follows_policy_channels():
    env1 = EnvConfig(bridge_kind="mock", lookahead_version=1)
    model = PolicyValueNet(env1, ModelConfig(**B2B, lookahead_version=1))
    model.eval()
    public, lookahead, oracle, scalars, mask, events, lengths = _inputs(seed=1)
    with torch.no_grad():
        _, va = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        _, vb = model(torch.cat([public, lookahead, torch.rand_like(oracle)], 1), scalars, mask, events, lengths)
        la, _ = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        lb, _ = model(torch.cat([public, torch.rand_like(lookahead), oracle], 1), scalars, mask, events, lengths)
    assert not torch.allclose(va, vb)  # value reads channels 52-63
    assert not torch.allclose(la, lb)  # the policy reads the look-ahead block


def test_env_and_model_versions_must_agree(tmp_path):
    with pytest.raises(ValueError, match="lookahead_version"):
        PolicyValueNet(EnvConfig(), ModelConfig(**B2B, lookahead_version=1))
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    payload = torch.load(path, map_location="cpu")
    assert infer_model_config(payload["model"], payload["metadata"]).lookahead_version == 1
    stripped = dict(payload["metadata"]["model_config"], lookahead_version=0)
    with pytest.raises(Exception):
        PolicyValueNet(EnvConfig(), infer_model_config(payload["model"], {"model_config": stripped}))\
            .load_state_dict(payload["model"])


def test_serving_loader_builds_version_one_models(tmp_path):
    from fh_mahjong_ai.serving import CheckpointPolicy
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    loaded = CheckpointPolicy.from_checkpoint(path)
    assert loaded.model.policy_channels == 52


def test_version_one_forward_without_privileged_planes():
    # 52 channels = public + look-ahead, no oracle planes: the privileged branch must
    # see zeros, not an empty slice past the look-ahead block.
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    model.eval()
    public, lookahead, _, scalars, mask, events, lengths = _inputs(seed=2)
    with torch.no_grad():
        logits, value = model(torch.cat([public, lookahead], 1), scalars, mask, events, lengths)
    assert logits.shape == (4, 204) and value.shape == (4,)


def test_oracle_feature_dropout_pipeline_rejects_lookahead(tmp_path):
    from fh_mahjong_ai.oracle import build_oracle_model, collect_selfplay_rollouts
    from fh_mahjong_ai.ppo import PPOConfig
    env1 = EnvConfig(bridge_kind="mock", oracle_observation=True, lookahead_version=1)
    with pytest.raises(ValueError, match="lookahead_version 0 only"):
        build_oracle_model(env1, ModelConfig(**SMALL_MODEL, lookahead_version=1), tmp_path / "x.pt")
    with pytest.raises(ValueError, match="lookahead_version 0 only"):
        collect_selfplay_rollouts(env1, None, PPOConfig(device="cpu"), base_seed=1, drop_prob=0.0)
