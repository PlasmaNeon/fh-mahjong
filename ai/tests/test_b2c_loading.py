"""Spec B2c Task 4: metadata-authoritative checkpoint loading (`infer_model_config`)
and event-aware `CheckpointPolicy` serving."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.serving import CheckpointPolicy
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
from fh_mahjong_ai.types import Observation

_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)

_ENV39 = EnvConfig(bridge_kind="mock")


def _b2b_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, event_window=8, privileged_critic=True, aux_heads=True)
    fields.update(overrides)
    return ModelConfig(**fields)


def _save_b2b_checkpoint(tmp_path: Path, model_config: ModelConfig, complete_metadata: bool) -> Path:
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {
        "b2b": {
            "event_window": int(model_config.event_window),
            "privileged_critic": bool(model_config.privileged_critic),
            "aux_heads": bool(model_config.aux_heads),
            "residual_blocks": int(model_config.residual_blocks),
        }
    }
    if complete_metadata:
        metadata["model_config"] = model_config_metadata(model_config)
    path = tmp_path / "checkpoint.pt"
    save_checkpoint(path, model, metadata=metadata)
    return path


def _obs(window: int, history: np.ndarray | None) -> Observation:
    mask = np.zeros(204, dtype=np.int8)
    mask[:4] = 1
    rng = np.random.default_rng(0)
    return Observation(
        seat=0,
        planes=rng.random((39, 42, 1), dtype=np.float32),
        scalars=rng.random(58, dtype=np.float32),
        action_mask=mask,
        event_history=np.zeros(0, dtype=np.uint32) if history is None else history,
    )


# --- (a) iter_075-style checkpoint: B2b modules + four-flag "b2b" metadata only ---

def test_infer_model_config_reconstructs_from_b2b_four_flag_metadata(tmp_path):
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"b2b": {
        "event_window": 8,
        "privileged_critic": True,
        "aux_heads": True,
        "residual_blocks": 1,
    }}
    reconstructed = infer_model_config(model.state_dict(), metadata)

    assert reconstructed.event_window == 8
    assert reconstructed.privileged_critic is True
    assert reconstructed.aux_heads is True
    assert reconstructed.residual_blocks == 1
    # Shape-inferable fields must also match, field-for-field, where determinable.
    assert reconstructed.channels == model_config.channels
    assert reconstructed.plane_feature_dim == model_config.plane_feature_dim
    assert reconstructed.scalar_hidden_dim == model_config.scalar_hidden_dim
    assert reconstructed.trunk_hidden_dim == model_config.trunk_hidden_dim
    assert reconstructed.value_hidden_dim == model_config.value_hidden_dim
    assert reconstructed.q_hidden_dim == model_config.q_hidden_dim
    assert reconstructed.event_embed_dim == model_config.event_embed_dim
    assert reconstructed.event_hidden_dim == model_config.event_hidden_dim


# --- (b) complete-metadata checkpoint: every ModelConfig field round-trips ---

def test_infer_model_config_round_trips_complete_metadata(tmp_path):
    model_config = _b2b_config(channels=24)  # non-default channels
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": model_config_metadata(model_config)}
    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed == model_config


# --- (c) B2b modules without metadata: still raises (unchanged guard) ---

def test_infer_model_config_raises_without_metadata_for_b2b_modules():
    model = PolicyValueNet(_ENV39, _b2b_config())
    with pytest.raises(RuntimeError, match="Spec B2c"):
        infer_model_config(model.state_dict())


def test_infer_model_config_legacy_checkpoints_still_infer_fine():
    legacy = PolicyValueNet(_ENV39, ModelConfig(**_SMALL))
    config = infer_model_config(legacy.state_dict())
    assert config.residual_blocks == 1
    assert config.event_window == 0


def test_infer_model_config_tolerates_whole_prefix_absent_optional_head():
    # Pins the "_cross_check_shapes" exemption for _COMPATIBLE_OPTIONAL_PREFIXES:
    # a prefix is exempt only when ALL keys under it are absent on one side (the
    # legitimate "older checkpoint predates this optional head" case). Every
    # current PolicyValueNet always instantiates `large_loss_head`, so no
    # existing checkpoint in these tests exercises that branch; strip it
    # entirely here to simulate an older checkpoint saved before that head
    # existed, and confirm the exemption lets reconstruction through cleanly.
    legacy = PolicyValueNet(_ENV39, ModelConfig(**_SMALL))
    state_dict = {
        key: value for key, value in legacy.state_dict().items()
        if not key.startswith("large_loss_head.")
    }
    config = infer_model_config(state_dict)
    assert config.residual_blocks == 1
    assert config.event_window == 0


# --- (d) doctored metadata contradicting tensor shapes: raises "shape cross-check" ---

def test_infer_model_config_doctored_metadata_raises_shape_cross_check():
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["channels"] = doctored["channels"] + 1  # contradicts plane_stem.0.weight shape
    metadata = {"model_config": doctored}
    with pytest.raises(RuntimeError, match="shape cross-check"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_doctored_dueling_q_flag_raises_shape_cross_check():
    # Flipping `dueling_q` reconstructs a disjoint q_head architecture
    # (DuelingQHead vs plain nn.Linear) whose parameter names both live under
    # the "q_head." prefix that _cross_check_shapes otherwise exempts for
    # legitimate "optional head absent in older checkpoint" cases. The
    # exemption must not swallow this: the key sets differ on both sides, so
    # this must still raise.
    model_config = _b2b_config(dueling_q=True)
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["dueling_q"] = False
    metadata = {"model_config": doctored}
    with pytest.raises(RuntimeError, match="shape cross-check"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_doctored_b2b_flags_raise_shape_cross_check():
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    # aux_heads=False contradicts the belief_head/dealin_head/rank_head keys present.
    metadata = {"b2b": {
        "event_window": 8, "privileged_critic": True, "aux_heads": False, "residual_blocks": 1,
    }}
    with pytest.raises(RuntimeError, match="shape cross-check"):
        infer_model_config(model.state_dict(), metadata)


# --- (e) CheckpointPolicy.choose: event history parity + empty-history guard ---

def test_from_checkpoint_loads_b2b_checkpoint_via_four_flag_metadata(tmp_path):
    model_config = _b2b_config()
    path = _save_b2b_checkpoint(tmp_path, model_config, complete_metadata=False)
    policy = CheckpointPolicy.from_checkpoint(path, device="cpu")
    assert policy.model.model_config.event_window == 8
    assert policy.model.wants_events is True


def test_from_checkpoint_loads_b2b_checkpoint_via_complete_metadata(tmp_path):
    model_config = _b2b_config(channels=24)
    path = _save_b2b_checkpoint(tmp_path, model_config, complete_metadata=True)
    policy = CheckpointPolicy.from_checkpoint(path, device="cpu")
    assert policy.model.model_config.channels == 24
    assert policy.model.model_config.event_window == 8


def test_choose_matches_torch_greedy_policy_with_populated_history(tmp_path):
    model_config = _b2b_config()
    path = _save_b2b_checkpoint(tmp_path, model_config, complete_metadata=True)
    checkpoint_policy = CheckpointPolicy.from_checkpoint(path, device="cpu")
    checkpoint_policy.model.eval()

    greedy_policy = TorchGreedyPolicy(checkpoint_policy.model, device="cpu")

    observation = _obs(window=8, history=np.asarray([0x140, 0x4A51, 0x8B7], dtype=np.uint32))

    served = checkpoint_policy.choose(observation)
    choice = greedy_policy.choose(observation)
    assert served.action_id == choice.action_id
    assert served.value == pytest.approx(choice.value, abs=1e-5)


def test_choose_raises_on_empty_history_for_event_model(tmp_path):
    model_config = _b2b_config()
    path = _save_b2b_checkpoint(tmp_path, model_config, complete_metadata=True)
    checkpoint_policy = CheckpointPolicy.from_checkpoint(path, device="cpu")

    observation = _obs(window=8, history=np.zeros(0, dtype=np.uint32))
    with pytest.raises(ValueError, match="EMPTY event_history"):
        checkpoint_policy.choose(observation)


def test_choose_window_zero_model_unaffected_by_empty_history(tmp_path):
    model_config = ModelConfig(**_SMALL)  # event_window == 0
    model = PolicyValueNet(_ENV39, model_config)
    path = tmp_path / "legacy.pt"
    save_checkpoint(path, model)
    checkpoint_policy = CheckpointPolicy.from_checkpoint(path, device="cpu")

    observation = _obs(window=0, history=np.zeros(0, dtype=np.uint32))
    served = checkpoint_policy.choose(observation)
    assert served.action_id in observation.legal_actions


def test_evaluate_batch_threads_events_for_event_model(tmp_path):
    model_config = _b2b_config()
    path = _save_b2b_checkpoint(tmp_path, model_config, complete_metadata=True)
    checkpoint_policy = CheckpointPolicy.from_checkpoint(path, device="cpu")
    checkpoint_policy.model.eval()

    n = 3
    env = EnvConfig()
    rng = np.random.default_rng(2)
    planes = rng.random((n, *env.plane_shape), dtype=np.float32)
    scalars = rng.random((n, env.scalar_features), dtype=np.float32)
    masks = np.zeros((n, env.action_space_size), dtype=np.int8)
    masks[:, :4] = 1
    events = rng.integers(0, 0x10000, size=(n, 8), dtype=np.int64)
    lengths = np.array([8, 3, 0], dtype=np.int64)

    probs, values = checkpoint_policy.evaluate_batch(planes, scalars, masks,
                                                       events=events, event_lengths=lengths)
    assert probs.shape == (n, env.action_space_size)
    assert values.shape == (n,)

    # Cross-check row 0 against direct model.forward with the same events tensor.
    with torch.inference_mode():
        p = torch.from_numpy(planes[:1])
        s = torch.from_numpy(scalars[:1])
        m = torch.from_numpy(masks[:1])
        ev = torch.from_numpy(events[:1])
        ev_len = torch.from_numpy(lengths[:1])
        logits, value = checkpoint_policy.model(p, s, m, events=ev, event_lengths=ev_len)
        expected_probs = torch.softmax(logits.masked_fill(m <= 0, float("-inf")), dim=1)
    np.testing.assert_allclose(probs[0], expected_probs[0].numpy(), atol=1e-5)
    assert values[0] == pytest.approx(float(value.item()), abs=1e-5)
