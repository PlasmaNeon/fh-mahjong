import json
from dataclasses import replace
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


# --- Task 4: resumable training state ---

def _champion39(tmp_path: Path) -> tuple[EnvConfig, Path]:
    env39 = EnvConfig(bridge_kind="mock")
    model = PolicyValueNet(env39, ModelConfig(**_SMALL))
    path = tmp_path / "champion.pt"
    save_checkpoint(path, model)
    return env39, path


def _b2b_run_configs(tmp_path: Path, *, iterations: int, lr: float = 2e-5):
    _, champion_path = _champion39(tmp_path)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    model_config = ModelConfig(**_SMALL, event_window=8, privileged_critic=True, aux_heads=True)
    config = PPOConfig(device="cpu", iterations=iterations, matches_per_iter=2, lr=lr,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    return env, model_config, champion_path, config


def test_train_state_written_every_n_iterations_and_atomic(tmp_path) -> None:
    env, model_config, champion_path, config = _b2b_run_configs(tmp_path, iterations=4)
    checkpoint_dir = tmp_path / "ckpt"

    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config,
                        base_seed=5, train_state_every=2)

    assert len(history) == 4
    state_path = checkpoint_dir / "train_state.pt"
    assert state_path.exists()
    assert not (checkpoint_dir / "train_state.pt.tmp").exists()
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    # Last write happens at completion (iteration 4, a multiple of 2 anyway);
    # next_iteration must point one past the last completed iteration.
    assert state["next_iteration"] == 5
    assert state["config_echo"]["ppo_config"]["lr"] == config.lr
    assert state["config_echo"]["model_config"]["event_window"] == model_config.event_window
    assert state["base_seed"] == 5
    for key in ("model", "optimizer", "torch_rng", "numpy_rng", "python_rng"):
        assert key in state


def test_resume_from_state_continues_iteration_count_and_history(tmp_path) -> None:
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    state_before = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state_before["next_iteration"] == 3

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2,
                        resume_from_state=state_path)

    assert len(history) == 4
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
    history_on_disk = json.loads((checkpoint_dir / "history.json").read_text())
    assert [row["iteration"] for row in history_on_disk] == [1, 2, 3, 4]
    for i in (3, 4):
        saved = torch.load(checkpoint_dir / f"iter_{i:03d}.pt", map_location="cpu")
        assert saved["metadata"]["model_config"]["event_window"] == model_config.event_window
    # Resuming must not have re-run the champion warm-start: iter_001/002
    # checkpoints from the first run are untouched (same file, not rewritten).
    assert (checkpoint_dir / "iter_001.pt").exists()
    assert (checkpoint_dir / "iter_002.pt").exists()


def test_resume_from_state_raises_on_different_lr(tmp_path) -> None:
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    config_different_lr = replace(config_first, iterations=4, lr=config_first.lr * 2)
    with pytest.raises(ValueError, match="lr"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_different_lr,
                 base_seed=5, resume_from_state=state_path)


def test_train_state_written_at_completion_even_when_not_multiple_of_every(tmp_path) -> None:
    env, model_config, champion_path, config = _b2b_run_configs(tmp_path, iterations=3)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
             base_seed=5, train_state_every=5)

    state = torch.load(checkpoint_dir / "train_state.pt", map_location="cpu", weights_only=False)
    assert state["next_iteration"] == 4


def test_resume_from_stale_state_reconciles_history_no_duplicates(tmp_path) -> None:
    # CRITICAL repro (reviewer-reported): train_state.pt is only saved every
    # `train_state_every` iterations (here 5), but history.json is appended
    # every iteration. If the process advances past a save point without
    # reaching the next one (e.g. dies at iteration 7 with the last state
    # snapshot from iteration 5), resuming from that STALE state must not
    # replay iterations 6-7 on top of the already-appended rows -- pre-fix,
    # that produced [1,2,3,4,5,6,7,6,7,8]. The fix reconciles history.json
    # down to the state's next_iteration boundary before continuing.
    env, model_config, champion_path, config5 = _b2b_run_configs(tmp_path, iterations=5)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config5,
             base_seed=5, train_state_every=5)
    state_path = checkpoint_dir / "train_state.pt"
    stale_state = torch.load(state_path, map_location="cpu", weights_only=False)
    assert stale_state["next_iteration"] == 6
    stale_state_bytes = state_path.read_bytes()  # snapshot the iter-5 state aside

    # Continue to iteration 7 without another state-save boundary (next one
    # is 10): this appends iterations 6 and 7 to history.json, but the
    # completion save at the end of THIS call overwrites train_state.pt with
    # a fresh (non-stale) next_iteration=8 snapshot.
    config7 = replace(config5, iterations=7)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config7,
             base_seed=5, train_state_every=5, resume_from_state=state_path)
    history_after_7 = json.loads((checkpoint_dir / "history.json").read_text())
    assert [row["iteration"] for row in history_after_7] == [1, 2, 3, 4, 5, 6, 7]

    # Simulate the crash: the completion save at iteration 7 never made it to
    # disk (box died first) -- only the iter-5 snapshot survived.
    state_path.write_bytes(stale_state_bytes)

    config8 = replace(config5, iterations=8)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config8,
                        base_seed=5, train_state_every=5, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5, 6, 7, 8]
    history_on_disk = json.loads((checkpoint_dir / "history.json").read_text())
    iterations_seen = [row["iteration"] for row in history_on_disk]
    assert iterations_seen == [1, 2, 3, 4, 5, 6, 7, 8]
    assert len(iterations_seen) == len(set(iterations_seen)), "no duplicate iteration rows"
    # The replayed iterations (6, 7) also overwrote iter_006.pt/iter_007.pt by
    # name during the crash-recovery run above; that's benign because
    # restoring the exact model/optimizer/RNG state before replaying makes
    # each re-run of iteration N a deterministic recomputation of the same
    # rollout+update, not a second distinct result.
    for i in range(1, 9):
        assert (checkpoint_dir / f"iter_{i:03d}.pt").exists()


def test_resume_growth_run_rejects_wrong_growth_blocks_then_succeeds_with_correct_config(tmp_path) -> None:
    # MINOR 1: exercise --resume-from-state together with a growth_blocks>0
    # lap. A caller who forgets that resume needs the GROWN model_config
    # (anchor's architecture + growth_blocks folded in, per train_b2b's
    # docstring) and instead passes growth_blocks=0 must get a clear,
    # naming ValueError from _validate_resume_config_echo -- not a silent
    # shape mismatch deeper in model loading. The correctly-reconstructed
    # grown config must then resume cleanly.
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config_first = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                             max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                             num_workers=1, match_mode="classic")
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, anchor_config, anchor_path, checkpoint_dir, config_first,
             base_seed=5, growth_blocks=2, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    assert state_path.exists()

    grown_config = replace(anchor_config, growth_blocks=2)
    wrong_config = replace(anchor_config, growth_blocks=0)
    config_resumed = replace(config_first, iterations=4)

    with pytest.raises(ValueError, match="growth_blocks"):
        train_b2b(env, wrong_config, anchor_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=2, resume_from_state=state_path)

    history = train_b2b(env, grown_config, anchor_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
