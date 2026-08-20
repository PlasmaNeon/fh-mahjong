from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest
import torch
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.scripts.serve_policy import PolicyHolder, observation_from_json
from fh_mahjong_ai.serving import CheckpointPolicy, run_bridge_serving_smoke
from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
from fh_mahjong_ai.types import Observation


def _checkpoint(tmp_path: Path) -> Path:
    path = tmp_path / "model.pt"
    save_checkpoint(path, PolicyValueNet(EnvConfig(), ModelConfig()), step=7)
    return path


def test_checkpoint_policy_selects_legal_masked_action(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[5:8] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    action = policy.choose(observation)

    assert action.action_id in observation.legal_actions
    assert action.checkpoint_step == 7


def test_checkpoint_policy_temperature_sampling_is_seeded(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    first = CheckpointPolicy.from_checkpoint(checkpoint, sample_temperature=1.0, seed=11)
    second = CheckpointPolicy.from_checkpoint(checkpoint, sample_temperature=1.0, seed=11)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:12] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    first_actions = [first.choose(observation).action_id for _ in range(8)]
    second_actions = [second.choose(observation).action_id for _ in range(8)]

    assert first_actions == second_actions
    assert set(first_actions).issubset(set(observation.legal_actions))


def test_checkpoint_policy_temperature_sampling_respects_top_k(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    policy = CheckpointPolicy.from_checkpoint(checkpoint, sample_temperature=1.0, sample_top_k=2, seed=13)
    mask = np.zeros(204, dtype=np.int8)
    mask[5:12] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    with torch.inference_mode():
        planes = torch.from_numpy(observation.planes).unsqueeze(0)
        scalars = torch.from_numpy(observation.scalars).unsqueeze(0)
        action_mask = torch.from_numpy(observation.action_mask).unsqueeze(0)
        logits, _ = policy.model(planes, scalars, action_mask)
    legal_actions = np.asarray(observation.legal_actions, dtype=np.int64)
    legal_logits = logits[0, observation.legal_actions].numpy()
    top_two = set(legal_actions[np.argsort(-legal_logits)[:2]].tolist())

    sampled_actions = {policy.choose(observation).action_id for _ in range(20)}

    assert sampled_actions.issubset(top_two)
    sampled_choice = policy.choose(observation)
    assert sampled_choice.greedy_action_id in observation.legal_actions
    assert sampled_choice.sampling_applied is True


def test_checkpoint_policy_family_limited_sampling_keeps_mixed_decisions_greedy(tmp_path: Path) -> None:
    checkpoint = _checkpoint(tmp_path)
    sampled = CheckpointPolicy.from_checkpoint(
        checkpoint,
        sample_temperature=1.0,
        sample_top_k=2,
        sample_action_family="discard",
        seed=17,
    )
    greedy = CheckpointPolicy.from_checkpoint(checkpoint)
    mask = np.zeros(204, dtype=np.int8)
    mask[0] = 1
    mask[5:8] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    sampled_actions = [sampled.choose(observation).action_id for _ in range(8)]
    greedy_choice = greedy.choose(observation)

    assert sampled_actions == [greedy_choice.action_id] * 8
    choice = sampled.choose(observation)
    assert choice.greedy_action_id == greedy_choice.action_id
    assert choice.sampling_applied is False
    assert choice.sampled_from_greedy is False


def test_checkpoint_policy_rejects_empty_mask(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=np.zeros(204, dtype=np.int8),
    )

    try:
        policy.choose(observation)
    except ValueError as exc:
        assert "no legal actions" in str(exc)
    else:
        raise AssertionError("expected empty mask to be rejected")


# FINDING 3 (adversarial round 2): the masked-logits list `choose(...,
# return_logits=True)` attaches (and serve_policy.py's /act serializes for
# `return_logits: true` requests) must round-trip through JSON without
# error. Illegal-action entries carry `torch.finfo(dtype).min` — a large but
# FINITE negative float, not -inf — so no NaN/Infinity ever reaches
# `json.dumps` (which raises ValueError on those by default).
def test_choose_return_logits_illegal_entries_are_finite_and_json_serializable(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[5:8] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    action = policy.choose(observation, return_logits=True)

    assert action.logits is not None
    assert action.logits.shape == (204,)
    illegal_value = float(action.logits[0])  # index 0 is masked out (outside 5:8)
    assert math.isfinite(illegal_value)
    assert illegal_value < -1e30  # torch.finfo(float32).min-scale sentinel, not a real logit

    encoded = json.dumps([float(v) for v in action.logits.tolist()])
    decoded = json.loads(encoded)
    assert math.isfinite(decoded[0])
    assert decoded[5:8] == [float(v) for v in action.logits[5:8].tolist()]


def test_choose_without_return_logits_leaves_logits_none(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[5:8] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(42, dtype=np.float32),
        action_mask=mask,
    )

    action = policy.choose(observation)

    assert action.logits is None


def test_serving_smoke_uses_bridge_validation(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_checkpoint(tmp_path))

    report = run_bridge_serving_smoke(policy, episodes=2, start_seed=3, bridge_kind="mock", max_decisions=4)

    assert report["episodes"] == 2
    assert report["decisions"] > 0


def test_choose_empty_event_history_default_still_raises(tmp_path: Path) -> None:
    """Adversarial round 10, Finding 2: the default (`allow_empty_event_history=False`)
    must keep the original defense-in-depth raise for any DIRECT caller of
    choose() (smoke tests, the parity harness, any other direct use) that
    hands it an Observation with an empty event_history — only serve_policy's
    /act handler (after observation_from_json's own validation) is allowed to
    pass allow_empty_event_history=True."""
    policy = CheckpointPolicy.from_checkpoint(_event_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[0:3] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(58, dtype=np.float32),
        action_mask=mask,
        event_history=np.zeros(0, dtype=np.uint32),
    )

    with pytest.raises(ValueError, match="EMPTY event_history"):
        policy.choose(observation)


def test_choose_empty_event_history_with_explicit_flag_succeeds(tmp_path: Path) -> None:
    """The escape hatch itself: with allow_empty_event_history=True, an empty
    history produces a legal action instead of raising (mirrors the
    zero-length row evaluate_batch already handles for a validated
    zero-count observation)."""
    policy = CheckpointPolicy.from_checkpoint(_event_checkpoint(tmp_path))
    mask = np.zeros(204, dtype=np.int8)
    mask[0:3] = 1
    observation = Observation(
        seat=0,
        planes=np.zeros((39, 42, 1), dtype=np.float32),
        scalars=np.zeros(58, dtype=np.float32),
        action_mask=mask,
        event_history=np.zeros(0, dtype=np.uint32),
    )

    action = policy.choose(observation, allow_empty_event_history=True)

    assert action.action_id in (0, 1, 2)


def _event_checkpoint(tmp_path: Path, event_window: int = 8) -> Path:
    # Mirrors ai/tests/test_checkpoint_loading.py's small event-model helpers: a tiny
    # PolicyValueNet with event_window > 0 (a B2b-style event checkpoint),
    # saved with complete model_config metadata so CheckpointPolicy.from_checkpoint
    # reconstructs model_config.event_window == event_window.
    small = dict(
        channels=16,
        residual_blocks=1,
        plane_feature_dim=32,
        scalar_hidden_dim=16,
        trunk_hidden_dim=32,
        value_hidden_dim=16,
        q_hidden_dim=16,
        event_window=event_window,
        privileged_critic=True,
        aux_heads=True,
    )
    model_config = ModelConfig(**small)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"), model_config)
    metadata = {"model_config": model_config_metadata(model_config)}
    path = tmp_path / "event_checkpoint.pt"
    save_checkpoint(path, model, metadata=metadata)
    return path


# FINDING 2 (adversarial round 2): run_bridge_serving_smoke built its EnvConfig
# without event_history_window, so the mock bridge returned empty event
# histories on every step. For an event model (event_window > 0),
# CheckpointPolicy.choose raises "EMPTY event_history" on the very first
# decision, so the serving smoke could never actually exercise an event
# checkpoint end-to-end. Threading policy.model.model_config.event_window into
# EnvConfig(event_history_window=...) fixes this.
def test_serving_smoke_runs_event_model_via_mock_bridge(tmp_path: Path) -> None:
    policy = CheckpointPolicy.from_checkpoint(_event_checkpoint(tmp_path), device="cpu")
    assert policy.model.model_config.event_window == 8

    report = run_bridge_serving_smoke(policy, episodes=2, start_seed=5, bridge_kind="mock", max_decisions=4)

    assert report["episodes"] == 2
    assert report["decisions"] > 0


def test_policy_holder_hot_swaps_checkpoint(tmp_path: Path) -> None:
    first = tmp_path / "a.pt"
    second = tmp_path / "b.pt"
    save_checkpoint(first, PolicyValueNet(EnvConfig(), ModelConfig()), step=1)
    save_checkpoint(second, PolicyValueNet(EnvConfig(), ModelConfig()), step=2)

    holder = PolicyHolder(
        CheckpointPolicy.from_checkpoint(first),
        manifest_path=tmp_path / "manifest.json",
    )
    assert holder.policy.checkpoint_step == 1

    holder.reload(checkpoint=str(second))
    assert holder.policy.checkpoint_step == 2
    assert holder.policy.checkpoint_path == second


def test_policy_holder_failed_reload_keeps_previous(tmp_path: Path) -> None:
    good = tmp_path / "good.pt"
    save_checkpoint(good, PolicyValueNet(EnvConfig(), ModelConfig()), step=5)
    holder = PolicyHolder(CheckpointPolicy.from_checkpoint(good), manifest_path=tmp_path / "m.json")

    try:
        holder.reload(checkpoint=str(tmp_path / "does_not_exist.pt"))
    except Exception:
        pass
    else:
        raise AssertionError("expected reload of a missing checkpoint to fail")

    # The previous model is still serving.
    assert holder.policy.checkpoint_step == 5
    assert holder.policy.checkpoint_path == good


def test_observation_from_json_validates_shapes() -> None:
    payload = {
        "seat": 1,
        "planes": np.zeros((39, 42, 1), dtype=np.float32).tolist(),
        "scalars": np.zeros(42, dtype=np.float32).tolist(),
        "action_mask": np.ones(204, dtype=np.int8).tolist(),
    }

    observation = observation_from_json(payload, model_event_window=0)

    assert observation.seat == 1
    assert observation.planes.shape == (39, 42, 1)
    assert observation.action_mask.shape == (204,)


# --- adversarial round 20, Finding 1: metadata-claimed architecture dims are bounded ------


def test_model_config_rejects_oversized_architecture_dimensions() -> None:
    """Round 20, Finding 1a: every architecture dimension in ModelConfig must
    be bounded (round 16 only bounded event_window) -- otherwise malformed or
    hostile checkpoint metadata can request an unboundedly large network."""
    with pytest.raises(ValueError, match="channels"):
        ModelConfig(channels=10**6)
    with pytest.raises(ValueError, match="residual_blocks"):
        ModelConfig(residual_blocks=10**6)
    with pytest.raises(ValueError, match="q_hidden_dim"):
        ModelConfig(q_hidden_dim=10**6)
    with pytest.raises(ValueError, match="trunk_hidden_dim"):
        ModelConfig(trunk_hidden_dim=10**6)
    with pytest.raises(ValueError, match="channels"):
        ModelConfig(channels=0)
    with pytest.raises(ValueError, match="channels"):
        ModelConfig(channels=True)  # bool is not an acceptable int


def test_infer_model_config_rejects_oversized_metadata_channels_without_constructing_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Round 20, Finding 1: infer_model_config must reject a metadata-claimed
    channels=10**6 before ANY PolicyValueNet is constructed for the shape
    cross-check -- pinned with a tripwire that counts PolicyValueNet.__init__
    calls."""
    from dataclasses import asdict

    from fh_mahjong_ai.model import infer_model_config

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    state_dict = model.state_dict()
    bad_metadata = {"model_config": {**asdict(ModelConfig()), "channels": 10**6}}

    calls = {"n": 0}
    real_init = PolicyValueNet.__init__

    def _counting_init(self, *args, **kwargs):
        calls["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(PolicyValueNet, "__init__", _counting_init)

    with pytest.raises(ValueError, match="channels"):
        infer_model_config(state_dict, bad_metadata)

    assert calls["n"] == 0


def test_infer_model_config_rejects_oversized_metadata_residual_blocks_without_constructing_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import asdict

    from fh_mahjong_ai.model import infer_model_config

    model = PolicyValueNet(EnvConfig(), ModelConfig())
    state_dict = model.state_dict()
    bad_metadata = {"model_config": {**asdict(ModelConfig()), "residual_blocks": 10**6}}

    calls = {"n": 0}
    real_init = PolicyValueNet.__init__

    def _counting_init(self, *args, **kwargs):
        calls["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(PolicyValueNet, "__init__", _counting_init)

    with pytest.raises(ValueError, match="residual_blocks"):
        infer_model_config(state_dict, bad_metadata)

    assert calls["n"] == 0


def test_infer_model_config_rejects_metadata_mismatched_with_shapes_without_constructing_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A metadata-claimed `channels` that is well within bounds but does not
    match the checkpoint's actual conv-weight shape must still be rejected
    BEFORE any PolicyValueNet is constructed -- cheap, allocation-free
    shape-derived comparison catches this without ever building the
    (bounded-but-still-wrong) net."""
    from dataclasses import asdict

    from fh_mahjong_ai.model import infer_model_config

    model = PolicyValueNet(EnvConfig(), ModelConfig())  # channels=96
    state_dict = model.state_dict()
    bad_metadata = {"model_config": {**asdict(ModelConfig()), "channels": 128}}

    calls = {"n": 0}
    real_init = PolicyValueNet.__init__

    def _counting_init(self, *args, **kwargs):
        calls["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(PolicyValueNet, "__init__", _counting_init)

    with pytest.raises(RuntimeError, match="shape"):
        infer_model_config(state_dict, bad_metadata)

    assert calls["n"] == 0


def test_infer_model_config_rejects_b2b_metadata_residual_blocks_mismatch_without_constructing_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The b2b-flag overlay path also lets metadata claim `residual_blocks`
    directly (not shape-derived) -- a bounded-but-wrong value must be caught
    the same way as the model_config path."""
    from fh_mahjong_ai.model import infer_model_config

    model = PolicyValueNet(EnvConfig(), ModelConfig(residual_blocks=2))
    state_dict = model.state_dict()
    bad_metadata = {
        "b2b": {
            "event_window": 0,
            "privileged_critic": False,
            "aux_heads": False,
            "residual_blocks": 60,
        }
    }

    calls = {"n": 0}
    real_init = PolicyValueNet.__init__

    def _counting_init(self, *args, **kwargs):
        calls["n"] += 1
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(PolicyValueNet, "__init__", _counting_init)

    with pytest.raises(RuntimeError, match="shape"):
        infer_model_config(state_dict, bad_metadata)

    assert calls["n"] == 0


def test_infer_model_config_recovers_architecture_variants() -> None:
    from fh_mahjong_ai.model import infer_model_config

    for config in (
        ModelConfig(),
        ModelConfig(residual_blocks=4),
        ModelConfig(channels=64, residual_blocks=3, plane_feature_dim=128, scalar_hidden_dim=96,
                    trunk_hidden_dim=192, value_hidden_dim=64, q_hidden_dim=128),
        ModelConfig(dueling_q=False),
        ModelConfig(pool_planes=True),
        ModelConfig(channel_attention=True, channel_attention_ratio=8),
    ):
        model = PolicyValueNet(EnvConfig(), config)
        inferred = infer_model_config(model.state_dict())
        for field in ("channels", "residual_blocks", "plane_feature_dim", "scalar_hidden_dim",
                      "trunk_hidden_dim", "value_hidden_dim", "q_hidden_dim", "pool_planes",
                      "channel_attention", "channel_attention_ratio", "dueling_q"):
            assert getattr(inferred, field) == getattr(config, field), (
                f"{field}: inferred {getattr(inferred, field)} != {getattr(config, field)} for {config}"
            )


def test_checkpoint_policy_loads_non_default_architecture(tmp_path: Path) -> None:
    config = ModelConfig(residual_blocks=4)
    env_config = EnvConfig()
    model = PolicyValueNet(env_config, config)
    checkpoint_path = tmp_path / "deep4.pt"
    save_checkpoint(checkpoint_path, model)

    policy = CheckpointPolicy.from_checkpoint(checkpoint_path)

    channels, height, width = env_config.plane_shape
    planes = torch.zeros((1, channels, height, width))
    scalars = torch.zeros((1, env_config.scalar_features))
    mask = torch.ones((1, env_config.action_space_size))
    model.eval()
    with torch.no_grad():
        expected_logits, _ = model(planes, scalars, mask)
        actual_logits, _ = policy.model(planes, scalars, mask)
    assert torch.allclose(expected_logits, actual_logits, atol=1e-6)


def test_policy_holder_reload_preserves_sampling(tmp_path: Path) -> None:
    """Hot-swapping the checkpoint must keep whatever sampling config was
    explicitly set at launch — a reload must never silently change serving
    behavior. (Production serves greedy — no sampling flags; this guards
    experimental sampled configurations.)"""
    first = tmp_path / "a.pt"
    second = tmp_path / "b.pt"
    save_checkpoint(first, PolicyValueNet(EnvConfig(), ModelConfig()), step=1)
    save_checkpoint(second, PolicyValueNet(EnvConfig(), ModelConfig()), step=2)

    holder = PolicyHolder(
        CheckpointPolicy.from_checkpoint(first, sample_temperature=0.7, sample_top_k=3,
                                         sample_action_family="discard", seed=7),
        manifest_path=tmp_path / "manifest.json",
    )
    holder.reload(checkpoint=str(second))

    policy = holder.policy
    assert policy.checkpoint_step == 2
    assert policy.sample_temperature == 0.7
    assert policy.sample_top_k == 3
    assert policy.sample_action_family == "discard"


# FINDING 2 (adversarial round 5): the OLD reload() flow loaded the model
# from `checkpoint` and only afterward re-opened the SAME path to compute its
# sha256 — an atomic file replacement landing between those two independent
# opens would make /healthz attest the NEW bytes while the OLD weights kept
# serving. The fix reads the checkpoint's bytes exactly once and derives both
# the loaded policy and its hash from that same buffer
# (`load_checkpoint_policy_with_hash`). This test simulates the race directly:
# it patches `Path.read_bytes` so that, immediately after ANY read of the
# checkpoint path completes, the file on disk is swapped for different
# content — mirroring "an atomic replace lands between load and hash" in the
# old two-open flow. With the fix, the holder's reported hash matches the
# bytes actually used to build the policy (the original ones), never the
# swapped-in bytes, and the deserialized policy matches too.
def test_policy_holder_reload_hash_matches_bytes_actually_loaded_despite_concurrent_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint_path = tmp_path / "model.pt"
    save_checkpoint(checkpoint_path, PolicyValueNet(EnvConfig(), ModelConfig()), step=1)
    original_bytes = checkpoint_path.read_bytes()
    original_sha256 = hashlib.sha256(original_bytes).hexdigest()

    swapped_path = tmp_path / "swapped.pt"
    save_checkpoint(swapped_path, PolicyValueNet(EnvConfig(), ModelConfig()), step=99)
    swapped_bytes = swapped_path.read_bytes()
    swapped_sha256 = hashlib.sha256(swapped_bytes).hexdigest()
    assert swapped_sha256 != original_sha256

    holder = PolicyHolder(
        CheckpointPolicy.from_checkpoint(checkpoint_path),
        manifest_path=tmp_path / "manifest.json",
    )

    real_read_bytes = Path.read_bytes
    swap_done = False

    def _read_then_swap(self: Path, *args: object, **kwargs: object) -> bytes:
        data = real_read_bytes(self, *args, **kwargs)
        nonlocal swap_done
        if self == checkpoint_path and not swap_done:
            # Simulate an atomic file replacement landing immediately after
            # this read of the checkpoint returns — the old flow's SECOND
            # open (for hashing) would observe these new bytes instead of the
            # ones just loaded into the model.
            swap_done = True
            checkpoint_path.write_bytes(swapped_bytes)
        return data

    monkeypatch.setattr(Path, "read_bytes", _read_then_swap)

    holder.reload(checkpoint=str(checkpoint_path))

    assert holder.checkpoint_sha256 == original_sha256
    assert holder.checkpoint_sha256 != swapped_sha256
    # The deserialized policy must also come from the original bytes (step=1),
    # not the swapped-in checkpoint (step=99) — hash and weights stay coupled.
    assert holder.policy.checkpoint_step == 1


def test_policy_holder_manifest_reload_preserves_sampling_and_seed(tmp_path: Path) -> None:
    """The manifest reload path must also carry the sampling config (incl. the
    base seed) — and note: the sampler RNG deliberately RESTARTS from that base
    seed on reload (config preserved, generator state not)."""
    import json

    first = tmp_path / "a.pt"
    second = tmp_path / "b.pt"
    save_checkpoint(first, PolicyValueNet(EnvConfig(), ModelConfig()), step=1)
    save_checkpoint(second, PolicyValueNet(EnvConfig(), ModelConfig()), step=2)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "current_reward_trained_best": {"id": "current", "method": "test",
                                        "checkpoint_path": str(second)},
    }))

    holder = PolicyHolder(
        CheckpointPolicy.from_checkpoint(first, sample_temperature=0.7, sample_top_k=3,
                                         sample_action_family="discard", seed=7),
        manifest_path=manifest,
    )
    holder.reload(checkpoint_id="current")

    policy = holder.policy
    assert policy.checkpoint_step == 2
    assert policy.sample_temperature == 0.7
    assert policy.sample_top_k == 3
    assert policy.sample_action_family == "discard"
    assert policy.sample_seed == 7
