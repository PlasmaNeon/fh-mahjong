"""Spec B2c Task 4: metadata-authoritative checkpoint loading (`infer_model_config`)
and event-aware `CheckpointPolicy` serving."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

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
    with pytest.raises(RuntimeError, match="no usable metadata"):
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


# --- (d.1) round 26: inert/non-unique metadata fields must not be rejected ---
# A model's OWN saved metadata must always round-trip through infer_model_config,
# even when a metadata field is inert (has no effect on the constructed
# architecture) or non-unique (multiple values produce the same architecture).

def test_infer_model_config_accepts_own_metadata_with_inert_attention_ratio(tmp_path):
    # channel_attention=False: channel_attention_ratio is never read by
    # ChannelAttention2d (it isn't even constructed), so any ratio value is fine.
    model_config = _b2b_config(channel_attention=False, channel_attention_ratio=8)
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": model_config_metadata(model_config)}
    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed == model_config


def test_infer_model_config_accepts_own_metadata_with_inert_q_hidden_dim(tmp_path):
    # dueling_q=False: q_hidden_dim is never read (plain nn.Linear q_head), so
    # any value is fine.
    model_config = _b2b_config(dueling_q=False, q_hidden_dim=512)
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": model_config_metadata(model_config)}
    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed == model_config


def test_infer_model_config_accepts_own_metadata_with_ratio_that_floors_ambiguously(tmp_path):
    # channels=96, ratio=17 -> hidden = max(1, 96 // 17) = 5. Multiple ratios
    # floor to hidden=5 (e.g. 16..19), so the raw ratio is not recoverable from
    # shapes alone -- only the effective hidden width is, and it must match.
    model_config = _b2b_config(channels=96, channel_attention=True, channel_attention_ratio=17)
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": model_config_metadata(model_config)}
    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed == model_config


def test_infer_model_config_still_rejects_wrong_channels_claim():
    # Negative control: a genuinely wrong (non-inert, non-ambiguous) field must
    # still be rejected pre-construction.
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["residual_blocks"] = doctored["residual_blocks"] + 1
    metadata = {"model_config": doctored}
    with pytest.raises(RuntimeError, match="shape cross-check"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_rejects_attention_ratio_with_different_effective_width():
    # Negative control: channel_attention=True with a ratio that yields a
    # DIFFERENT effective hidden width than the checkpoint's actual weight
    # shape must still be rejected pre-construction.
    model_config = _b2b_config(channels=96, channel_attention=True, channel_attention_ratio=16)
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["channel_attention_ratio"] = 4  # hidden = 96 // 4 = 24, vs actual 96 // 16 = 6
    metadata = {"model_config": doctored}
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


# --- (f) round 16, Finding 2: unbounded/malformed metadata event_window ---
# GRU weights are window-independent, so the shape cross-check can't catch a
# doctored event_window; /act and /evaluate allocate arrays sized by it, so an
# out-of-range value is a remote memory-exhaustion vector. ModelConfig itself
# must reject it (bound = EnvConfig.MAX_EVENT_HISTORY_WINDOW), which makes
# infer_model_config (and thus a checkpoint reload) fail cleanly rather than
# constructing a model with a malformed window.

def test_infer_model_config_rejects_oversized_event_window_in_complete_metadata(tmp_path):
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["event_window"] = 100_000
    metadata = {"model_config": doctored}
    with pytest.raises(ValueError, match="event_window"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_rejects_negative_event_window_in_complete_metadata(tmp_path):
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["event_window"] = -1
    metadata = {"model_config": doctored}
    with pytest.raises(ValueError, match="event_window"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_rejects_non_int_event_window_in_complete_metadata(tmp_path):
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["event_window"] = "128"
    metadata = {"model_config": doctored}
    with pytest.raises(ValueError, match="event_window"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_rejects_oversized_event_window_in_b2b_four_flag_metadata():
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"b2b": {
        "event_window": 100_000,
        "privileged_critic": True,
        "aux_heads": True,
        "residual_blocks": 1,
    }}
    with pytest.raises(ValueError, match="event_window"):
        infer_model_config(model.state_dict(), metadata)


def test_model_config_accepts_boundary_event_window_512():
    ModelConfig(**_SMALL, event_window=512)  # must not raise


def test_model_config_rejects_event_window_513():
    with pytest.raises(ValueError, match="event_window"):
        ModelConfig(**_SMALL, event_window=513)


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


# --- Task 3 (deep16-rezero): growth-aware metadata loading, derivable count,
# fail-closed rules. `_grown_config` deliberately stays plain (no B2b flags)
# so these tests isolate the growth-only surface from the B2b surface above;
# `test_deep16_rezero.py` separately covers growth stacked on a B2b anchor
# via `grow_b2b_model`. ---

def _grown_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, growth_blocks=3)
    fields.update(overrides)
    return ModelConfig(**fields)


def _save_grown_checkpoint(tmp_path: Path, model_config: ModelConfig, *,
                           metadata_override: dict | None = None) -> Path:
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": metadata_override or model_config_metadata(model_config)}
    path = tmp_path / "grown.pt"
    save_checkpoint(path, model, metadata=metadata)
    return path


def test_infer_model_config_round_trips_grown_checkpoint(tmp_path):
    model_config = _grown_config()
    path = _save_grown_checkpoint(tmp_path, model_config)
    saved = torch.load(path, map_location="cpu")
    reconstructed = infer_model_config(saved["model"], saved["metadata"])
    assert reconstructed.growth_blocks == 3
    assert reconstructed == model_config


def test_from_checkpoint_loads_grown_checkpoint_and_choose_works(tmp_path):
    model_config = _grown_config()
    path = _save_grown_checkpoint(tmp_path, model_config)
    policy = CheckpointPolicy.from_checkpoint(path, device="cpu")
    assert policy.model.model_config.growth_blocks == 3

    observation = _obs(window=0, history=np.zeros(0, dtype=np.uint32))
    served = policy.choose(observation)
    assert served.action_id in observation.legal_actions


def test_infer_model_config_growth_blocks_overclaim_raises_before_construction(tmp_path):
    # Doctored metadata claims 5 growth blocks; the checkpoint actually has 3.
    # Must raise BEFORE any PolicyValueNet is constructed (tripwire below).
    model_config = _grown_config(growth_blocks=3)
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["growth_blocks"] = 5
    metadata = {"model_config": doctored}

    with patch.object(PolicyValueNet, "__init__",
                      side_effect=AssertionError("must not construct PolicyValueNet")) as mocked_init:
        with pytest.raises(RuntimeError, match="growth_blocks"):
            infer_model_config(model.state_dict(), metadata)
        mocked_init.assert_not_called()


def test_infer_model_config_rejects_combined_over_limit_claim_before_construction():
    # Adversarial round 17: residual_blocks and growth_blocks are each
    # individually bounded to 64, but nothing stopped them composing --
    # doctored metadata can claim residual_blocks=64 (individually legal)
    # stacked on top of the checkpoint's real growth_blocks=3, for a total
    # of 67 blocks, exceeding the combined depth budget. Must raise BEFORE
    # any PolicyValueNet is constructed (tripwire below), same as the
    # existing growth_blocks-overclaim guard above.
    model_config = _grown_config(growth_blocks=3)
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["residual_blocks"] = 64
    metadata = {"model_config": doctored}

    with patch.object(PolicyValueNet, "__init__",
                      side_effect=AssertionError("must not construct PolicyValueNet")) as mocked_init:
        with pytest.raises(ValueError, match="residual_blocks.*growth_blocks|growth_blocks.*residual_blocks"):
            infer_model_config(model.state_dict(), metadata)
        mocked_init.assert_not_called()


def test_infer_model_config_growth_keys_without_metadata_raises_explicit_message():
    model_config = _grown_config()
    model = PolicyValueNet(_ENV39, model_config)
    with pytest.raises(RuntimeError, match="no usable metadata"):
        infer_model_config(model.state_dict())
    # And the message must actually name growth blocks, not just B2b modules
    # (this checkpoint has neither event encoder, privileged critic, nor aux
    # heads -- only `growth.*` -- so a message that only mentions B2b modules
    # would be misleading).
    with pytest.raises(RuntimeError, match="growth"):
        infer_model_config(model.state_dict())


def test_infer_model_config_growth_claim_positive_but_no_growth_keys_raises():
    # Metadata claims growth_blocks > 0 but the state dict has no growth.* keys.
    legacy_config = ModelConfig(**_SMALL)  # growth_blocks == 0
    legacy_model = PolicyValueNet(_ENV39, legacy_config)
    doctored = model_config_metadata(legacy_config)
    doctored["growth_blocks"] = 4
    metadata = {"model_config": doctored}
    with pytest.raises(RuntimeError, match="growth_blocks"):
        infer_model_config(legacy_model.state_dict(), metadata)


def test_infer_model_config_rejects_oversized_growth_blocks_claim_with_no_allocation():
    model_config = _grown_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["growth_blocks"] = 10 ** 6
    metadata = {"model_config": doctored}

    with patch.object(PolicyValueNet, "__init__",
                      side_effect=AssertionError("must not construct PolicyValueNet")) as mocked_init:
        with pytest.raises(ValueError, match="growth_blocks"):
            infer_model_config(model.state_dict(), metadata)
        mocked_init.assert_not_called()


def test_infer_model_config_legacy_b2b_metadata_without_growth_field_defaults_zero():
    # legacy/b2b metadata (the four-flag form) never carries growth_blocks ->
    # growth_blocks defaults to 0 (unchanged pre-deep16-rezero behavior).
    model_config = _b2b_config()
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"b2b": {
        "event_window": 8, "privileged_critic": True, "aux_heads": True, "residual_blocks": 1,
    }}
    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed.growth_blocks == 0


def test_infer_model_config_growth_keys_with_only_b2b_four_flag_metadata_fails_closed():
    # A checkpoint that carries BOTH B2b modules and deep16-rezero growth.*
    # keys, but whose metadata is only the legacy four-flag "b2b" block (no
    # "model_config", and the four-flag block never carries growth_blocks --
    # see `infer_model_config`'s docstring, case 2). The b2b branch shape-
    # infers growth_blocks as the ModelConfig default (0) since
    # `_shape_inferred_fields` deliberately excludes it, while the state dict
    # actually carries `growth.*` tensors. `_verify_metadata_matches_shapes`
    # must catch that mismatch (claimed 0 vs. derived 3) and raise, rather
    # than silently building a truncated (non-grown) model. Verified manually
    # via `_verify_metadata_matches_shapes` during review; this test locks it in.
    model_config = _b2b_config(growth_blocks=3)
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"b2b": {
        "event_window": 8, "privileged_critic": True, "aux_heads": True, "residual_blocks": 1,
    }}
    with patch.object(PolicyValueNet, "__init__",
                      side_effect=AssertionError("must not construct PolicyValueNet")) as mocked_init:
        with pytest.raises(RuntimeError, match="growth_blocks"):
            infer_model_config(model.state_dict(), metadata)
        mocked_init.assert_not_called()


def test_infer_model_config_rejects_non_contiguous_growth_indices():
    model_config = _grown_config(growth_blocks=3)
    model = PolicyValueNet(_ENV39, model_config)
    state_dict = model.state_dict()
    # Strip the middle block's tensors entirely, leaving indices {0, 2}.
    for key in [k for k in state_dict if k.startswith("growth.1.")]:
        del state_dict[key]
    metadata = {"model_config": model_config_metadata(model_config)}
    with pytest.raises(RuntimeError, match="contiguous"):
        infer_model_config(state_dict, metadata)


def test_growth_blocks_zero_round_trips_with_no_growth_keys(tmp_path):
    # Sanity: growth_blocks=0 needs no growth-specific metadata handling at
    # all (no growth.* keys ever appear), matching pre-deep16-rezero behavior.
    model_config = ModelConfig(**_SMALL)
    path = _save_grown_checkpoint(tmp_path, model_config)
    saved = torch.load(path, map_location="cpu")
    reconstructed = infer_model_config(saved["model"], saved["metadata"])
    assert reconstructed.growth_blocks == 0


# --- Adversarial round 2, Finding 2: residual_blocks=0 + growth_blocks>0 +
# channel_attention=True checkpoints. `_shape_inferred_fields` only ever
# looked for the attention submodule under `plane_blocks.0.`; when there are
# no plane_blocks at all, attention (which really lives under `growth.0.`)
# derives as False and `_verify_metadata_matches_shapes` then rejects the
# checkpoint's own honest metadata. The fix must derive attention presence
# from the first EFFECTIVE block (`plane_blocks.0` when residual_blocks>0,
# else `growth.0`).

def _residual_free_grown_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, residual_blocks=0, growth_blocks=2, channel_attention=True)
    fields.update(overrides)
    return ModelConfig(**fields)


def test_infer_model_config_round_trips_residual_free_grown_attention_checkpoint(tmp_path):
    model_config = _residual_free_grown_config()
    path = _save_grown_checkpoint(tmp_path, model_config)
    saved = torch.load(path, map_location="cpu")

    reconstructed = infer_model_config(saved["model"], saved["metadata"])

    assert reconstructed == model_config
    assert reconstructed.channel_attention is True
    assert reconstructed.residual_blocks == 0
    assert reconstructed.growth_blocks == 2


def test_from_checkpoint_loads_residual_free_grown_attention_checkpoint(tmp_path):
    model_config = _residual_free_grown_config()
    path = _save_grown_checkpoint(tmp_path, model_config)

    policy = CheckpointPolicy.from_checkpoint(path, device="cpu")

    assert policy.model.model_config.channel_attention is True
    assert policy.model.model_config.residual_blocks == 0
    observation = _obs(window=0, history=np.zeros(0, dtype=np.uint32))
    served = policy.choose(observation)
    assert served.action_id in observation.legal_actions


def test_infer_model_config_still_rejects_doctored_attention_claim_without_residual_blocks():
    # Negative control: same residual-free/grown architecture, but metadata
    # dishonestly claims channel_attention=True while the checkpoint was
    # actually saved WITHOUT attention -- must still be rejected.
    model_config = _residual_free_grown_config(channel_attention=False)
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["channel_attention"] = True
    metadata = {"model_config": doctored}

    with pytest.raises(RuntimeError, match="attention"):
        infer_model_config(model.state_dict(), metadata)


# --- gru-width lap (Task 3): metadata-authoritative event_output_dim loading.
# `_widened_config` builds a genuinely non-dormant projection (event_output_dim
# != event_hidden_dim and != 0) so `event_encoder.output_proj.*` keys are
# actually present in the state dict. ---

def _widened_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, event_window=8, event_hidden_dim=16, event_output_dim=8)
    fields.update(overrides)
    return ModelConfig(**fields)


def _save_widened_checkpoint(tmp_path: Path, model_config: ModelConfig, *,
                             metadata_override: dict | None = None) -> Path:
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": metadata_override or model_config_metadata(model_config)}
    path = tmp_path / "widened.pt"
    save_checkpoint(path, model, metadata=metadata)
    return path


def test_infer_model_config_round_trips_widened_checkpoint(tmp_path):
    model_config = _widened_config()
    path = _save_widened_checkpoint(tmp_path, model_config)
    saved = torch.load(path, map_location="cpu")

    reconstructed = infer_model_config(saved["model"], saved["metadata"])

    assert reconstructed == model_config
    assert reconstructed.event_output_dim == 8
    assert reconstructed.event_hidden_dim == 16


def test_from_checkpoint_loads_widened_checkpoint_and_choose_works(tmp_path):
    model_config = _widened_config()
    path = _save_widened_checkpoint(tmp_path, model_config)

    policy = CheckpointPolicy.from_checkpoint(path, device="cpu")

    assert policy.model.model_config.event_output_dim == 8
    assert policy.model.model_config.event_hidden_dim == 16
    observation = _obs(window=8, history=np.asarray([0x140, 0x4A51, 0x8B7], dtype=np.uint32))
    served = policy.choose(observation)
    assert served.action_id in observation.legal_actions


def test_infer_model_config_doctored_event_output_dim_claim_raises_before_construction(tmp_path):
    # Real checkpoint: event_hidden_dim=16, event_output_dim=8 (a real, present
    # output_proj key of shape [8, 16]). Metadata lies and claims
    # event_output_dim=12 (still != hidden_dim, so a projection is still
    # claimed, just the wrong width) -- must be caught BEFORE PolicyValueNet
    # is ever constructed, not slide through to the generic post-construction
    # shape cross-check.
    model_config = _widened_config()
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["event_output_dim"] = 12
    metadata = {"model_config": doctored}

    with pytest.raises(RuntimeError, match="event_output_dim"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_projection_keys_without_metadata_raises_explicit_message(tmp_path):
    # A widened (projected) checkpoint saved with NO metadata at all must
    # still fail closed with the existing "no usable metadata" message (the
    # projection keys live under the event_encoder. prefix, already covered
    # by the B2b-modules guard), not silently shape-infer a wrong config.
    model_config = _widened_config()
    model = PolicyValueNet(_ENV39, model_config)

    with pytest.raises(RuntimeError, match="no usable metadata"):
        infer_model_config(model.state_dict())


def test_infer_model_config_event_output_dim_claim_positive_but_no_projection_keys_raises():
    # Metadata claims event_output_dim > 0 (and != event_hidden_dim, i.e. a
    # real projection) but the checkpoint's state dict carries no
    # event_encoder.output_proj.* keys at all (dormant/default architecture).
    model_config = _b2b_config()  # event_output_dim defaults to 0, dormant
    model = PolicyValueNet(_ENV39, model_config)
    doctored = model_config_metadata(model_config)
    doctored["event_output_dim"] = model_config.event_hidden_dim + 4
    metadata = {"model_config": doctored}

    with pytest.raises(RuntimeError, match="event_output_dim"):
        infer_model_config(model.state_dict(), metadata)


def test_infer_model_config_event_output_dim_equal_to_hidden_dim_claim_matches_no_projection():
    # An honest claim of event_output_dim == event_hidden_dim (the
    # "collapsed to dormant" case -- EventEncoder builds no output_proj
    # module either way) must round-trip cleanly against a checkpoint with no
    # projection keys, not be flagged as a mismatch.
    model_config = _b2b_config(event_output_dim=_b2b_config().event_hidden_dim)
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {"model_config": model_config_metadata(model_config)}

    reconstructed = infer_model_config(model.state_dict(), metadata)
    assert reconstructed.event_output_dim == model_config.event_hidden_dim


def test_infer_model_config_legacy_event_output_dim_defaults_zero():
    legacy = PolicyValueNet(_ENV39, ModelConfig(**_SMALL))
    config = infer_model_config(legacy.state_dict())
    assert config.event_output_dim == 0


def test_evaluate_report_config_includes_event_output_dim_and_event_hidden_dim(tmp_path):
    from fh_mahjong_ai.scripts.model_config_args import model_config_params

    model_config = _widened_config()
    params = model_config_params(model_config)
    assert params["model_event_output_dim"] == 8
    assert params["model_event_hidden_dim"] == 16
