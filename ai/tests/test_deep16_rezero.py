from pathlib import Path

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, ReZeroResidualBlock
from fh_mahjong_ai.oracle import grow_b2b_model, train_b2b
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import load_checkpoint, model_config_metadata, save_checkpoint

# Reused from test_b2c_loading.py: a tiny B2b architecture + a 39ch mock-bridge
# EnvConfig, so anchor checkpoints in this file build and load fast.
_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)
_ENV39 = EnvConfig(bridge_kind="mock")


def _b2b_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, event_window=8, privileged_critic=True, aux_heads=True)
    fields.update(overrides)
    return ModelConfig(**fields)


def _save_anchor(tmp_path: Path, model_config: ModelConfig, *, with_model_config_metadata: bool = True,
                 model_config_metadata_override: dict | None = None) -> Path:
    model = PolicyValueNet(_ENV39, model_config)
    metadata = {}
    if with_model_config_metadata:
        metadata["model_config"] = model_config_metadata_override or model_config_metadata(model_config)
    path = tmp_path / "anchor.pt"
    save_checkpoint(path, model, metadata=metadata)
    return path


def _batch(n: int = 4, event_window: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    planes = torch.from_numpy(rng.random((n, 51, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((n, 58), dtype=np.float32))
    mask = torch.ones((n, 204), dtype=torch.int8)
    mask[:, ::7] = 0  # non-trivial mask so greedy-action equality is meaningful
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(n, event_window),
                                           dtype=np.uint32).astype(np.int64))
    lengths = torch.from_numpy(rng.integers(0, event_window + 1, size=(n,)).astype(np.int64))
    return planes, scalars, mask, events, lengths


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


# --- Task 2: grow_b2b_model warm-start + step-zero parity ---

def test_grow_b2b_model_preserves_every_anchor_tensor(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    anchor_state = torch.load(anchor_path, map_location="cpu")["model"]

    grown = grow_b2b_model(anchor_path, growth_blocks=3)
    grown_state = grown.state_dict()

    for key, value in anchor_state.items():
        assert torch.equal(grown_state[key], value), key
    for i in range(3):
        assert grown_state[f"growth.{i}.alpha"].item() == 0.0


def test_grow_b2b_model_step_zero_parity(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    anchor = PolicyValueNet(_ENV39, anchor_config)
    load_checkpoint(anchor_path, anchor)
    anchor.eval()

    grown = grow_b2b_model(anchor_path, growth_blocks=5)
    grown.eval()

    for seed in range(4):
        planes, scalars, mask, events, lengths = _batch(seed=seed)
        with torch.no_grad():
            anchor_logits, anchor_value = anchor(planes, scalars, mask, events=events, event_lengths=lengths)
            grown_logits, grown_value = grown(planes, scalars, mask, events=events, event_lengths=lengths)

            anchor_features = anchor.encode(planes, scalars, events, lengths)
            grown_features = grown.encode(planes, scalars, events, lengths)
            anchor_q, _ = anchor.q_values(planes, scalars, mask)
            grown_q, _ = grown.q_values(planes, scalars, mask)
            anchor_aux = anchor.aux_predictions(anchor_features)
            grown_aux = grown.aux_predictions(grown_features)

        assert torch.equal(anchor_logits, grown_logits)
        assert torch.equal(anchor_value, grown_value)
        assert torch.equal(anchor_q, grown_q)
        for key in ("belief", "dealin", "rank"):
            assert torch.equal(anchor_aux[key], grown_aux[key])
        assert torch.equal(anchor_logits.argmax(dim=-1), grown_logits.argmax(dim=-1))


def test_grow_b2b_model_raises_without_model_config_metadata(tmp_path) -> None:
    anchor_path = _save_anchor(tmp_path, _b2b_config(), with_model_config_metadata=False)
    with pytest.raises(RuntimeError, match="model_config"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_already_grown_anchor(tmp_path) -> None:
    anchor_path = _save_anchor(tmp_path, _b2b_config(growth_blocks=2))
    with pytest.raises(RuntimeError, match="grow"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_mismatched_trunk_shape(tmp_path) -> None:
    anchor_config = _b2b_config()
    lying_metadata = model_config_metadata(anchor_config)
    lying_metadata["trunk_hidden_dim"] = anchor_config.trunk_hidden_dim * 2
    anchor_path = _save_anchor(tmp_path, anchor_config, model_config_metadata_override=lying_metadata)
    with pytest.raises(RuntimeError):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_ignores_env_config_mismatch_when_not_passed(tmp_path) -> None:
    # Backward-compat: callers that don't pass env_config (e.g. exercising
    # grow_b2b_model in isolation with no "live env" to check against) get
    # the old unchecked behavior.
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    grown = grow_b2b_model(anchor_path, growth_blocks=3)
    assert grown.model_config.growth_blocks == 3


def test_grow_b2b_model_raises_on_scalar_feature_drift_against_live_env(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", scalar_features=_ENV39.scalar_features + 1)
    with pytest.raises(RuntimeError, match="scalar_features"):
        grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)


def test_grow_b2b_model_raises_on_action_space_drift_against_live_env(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", action_space_size=_ENV39.action_space_size + 10)
    with pytest.raises(RuntimeError, match="action_space_size"):
        grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)


def test_grow_b2b_model_matched_env_config_unchanged(tmp_path) -> None:
    # Live env_config matches what the anchor was actually built under (39ch
    # mock, default scalar/action-space sizes, matching event_window) — the
    # cross-check must be a no-op.
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", event_history_window=anchor_config.event_window)
    grown = grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)
    assert grown.model_config.growth_blocks == 3


def test_train_b2b_growth_raises_on_stale_anchor_env_config_drift(tmp_path) -> None:
    # The finding this guards: train_b2b's growth_blocks>0 routing must
    # cross-check the anchor's construction shapes against the LIVE
    # env_config collection will run under, not silently build a model
    # shaped to a stale anchor while collection runs on a different env.
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    live_env = EnvConfig(bridge_kind="mock", event_history_window=anchor_config.event_window,
                         oracle_observation=True, max_steps_per_episode=16,
                         scalar_features=_ENV39.scalar_features + 1)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    with pytest.raises(RuntimeError, match="scalar_features"):
        train_b2b(live_env, anchor_config, anchor_path, tmp_path / "ckpt", config,
                 base_seed=5, growth_blocks=2)


def test_grow_b2b_model_raises_on_missing_non_growth_tensor(tmp_path) -> None:
    # Minor coverage gap: an anchor checkpoint that genuinely LACKS a
    # non-growth tensor (e.g. a stripped belief_head) must raise via the
    # bad_missing path, not silently build a model with a randomly
    # initialized head the anchor never trained.
    anchor_config = _b2b_config()
    model = PolicyValueNet(_ENV39, anchor_config)
    state_dict = model.state_dict()
    missing_keys = [k for k in state_dict if k.startswith("belief_head.")]
    assert missing_keys, "expected aux_heads=True anchor to have belief_head tensors"
    for key in missing_keys:
        del state_dict[key]
    path = tmp_path / "anchor_missing_tensor.pt"
    torch.save({"model": state_dict, "step": 0,
               "metadata": {"model_config": model_config_metadata(anchor_config)}}, path)
    with pytest.raises(RuntimeError, match="belief_head"):
        grow_b2b_model(path, growth_blocks=3)


def test_train_b2b_growth_blocks_smoke_saves_metadata(tmp_path) -> None:
    # growth_blocks>0 warm-starts from a post-B2b anchor (grow_b2b_model's
    # contract), not the raw 39ch champion the surgery path (growth_blocks=0)
    # expects.
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, anchor_config, anchor_path, tmp_path / "ckpt", config,
                        base_seed=5, growth_blocks=2)
    assert len(history) == 1
    saved = torch.load(tmp_path / "ckpt" / "iter_001.pt", map_location="cpu")
    assert saved["metadata"]["model_config"]["growth_blocks"] == 2


def test_train_b2b_cli_help_shows_growth_blocks_flag() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--model-growth-blocks" in result.stdout
