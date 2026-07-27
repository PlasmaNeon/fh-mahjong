import json
import logging
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, ReZeroResidualBlock
from fh_mahjong_ai.oracle import grow_b2b_model, read_b2b_history_rows, train_b2b
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


def test_growth_alpha_mean_abs_reflects_alpha_values() -> None:
    # Adversarial round 2, Finding 1: the null-interpretation rule ("alphas
    # hugging 0 = protocol null signal") needs the actual alpha magnitudes in
    # telemetry, not just their existence. Unit-test the pure helper directly
    # so this doesn't depend on how much a PPO step happens to move alpha.
    from fh_mahjong_ai.oracle import _growth_alpha_mean_abs

    model_config = _b2b_config(growth_blocks=2)
    model = PolicyValueNet(_ENV39, model_config)
    assert _growth_alpha_mean_abs(model) == pytest.approx(0.0)  # ReZero alphas init to 0

    with torch.no_grad():
        model.growth[0].alpha.fill_(0.5)
    # mean(|0.5|, |0.0|) over the two growth blocks.
    assert _growth_alpha_mean_abs(model) == pytest.approx(0.25)


def test_growth_alpha_mean_abs_none_without_growth_blocks() -> None:
    from fh_mahjong_ai.oracle import _growth_alpha_mean_abs

    model_config = _b2b_config()  # growth_blocks=0 (default)
    model = PolicyValueNet(_ENV39, model_config)
    assert _growth_alpha_mean_abs(model) is None


def test_train_b2b_history_includes_growth_alpha_telemetry(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, anchor_config, anchor_path, tmp_path / "ckpt", config,
                        base_seed=5, growth_blocks=2)

    assert "growth_alpha_mean_abs" in history[0]
    assert isinstance(history[0]["growth_alpha_mean_abs"], float)


def test_train_b2b_history_omits_growth_alpha_telemetry_without_growth_blocks(tmp_path) -> None:
    env, model_config, champion_path, config = _b2b_run_configs(tmp_path, iterations=1)

    history = train_b2b(env, model_config, champion_path, tmp_path / "ckpt", config, base_seed=5)

    assert "growth_alpha_mean_abs" not in history[0]


def test_train_b2b_cli_help_shows_growth_blocks_flag() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--model-growth-blocks" in result.stdout


def test_cli_resume_growth_lap_with_only_cli_flags(tmp_path) -> None:
    # C1 (final review): the library-level resume tests above (e.g.
    # test_resume_growth_run_rejects_wrong_growth_blocks_then_succeeds_with_correct_config)
    # call train_b2b() directly with a hand-built ModelConfig that already
    # carries growth_blocks explicitly -- they can never catch a bug in the
    # CLI's OWN argument wiring. This test instead drives train_b2b.py's real
    # argparse/main() via subprocess, mirroring the runbook's launch-then-
    # resume pattern (identical flags + --resume-from-state, --champion
    # dropped on resume): a regression where model_config_from_args silently
    # drops --model-growth-blocks (so --resume-from-state always sees
    # growth_blocks=0 and _validate_resume_config_echo always raises for a
    # growth lap) is caught here even though it passes at the library level.
    import subprocess
    import sys

    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    checkpoint_dir = tmp_path / "ckpt"

    common_flags = [
        "--model-channels", "16", "--model-residual-blocks", "1",
        "--model-plane-feature-dim", "32", "--model-scalar-hidden-dim", "16",
        "--model-trunk-hidden-dim", "32", "--model-value-hidden-dim", "16",
        "--model-q-hidden-dim", "16", "--model-growth-blocks", "2",
        "--event-window", "8",
        "--checkpoint-dir", str(checkpoint_dir),
        "--matches-per-iter", "2", "--num-workers", "1",
        "--match-mode", "classic", "--max-steps-per-episode", "16",
        "--bridge-kind", "mock", "--device", "cpu",
        "--train-state-every", "1",
    ]

    launch = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b",
         "--champion", str(anchor_path), "--iterations", "1", *common_flags],
        capture_output=True, text=True,
    )
    assert launch.returncode == 0, launch.stderr
    assert (checkpoint_dir / "train_state.pt").exists()

    resume = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b",
         "--iterations", "2", "--resume-from-state", str(checkpoint_dir / "train_state.pt"),
         *common_flags],
        capture_output=True, text=True,
    )
    assert resume.returncode == 0, resume.stderr
    assert (checkpoint_dir / "iter_002.pt").exists()


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
    for key in ("model", "optimizer", "torch_rng", "numpy_rng", "python_rng", "run_id"):
        assert key in state
    assert state["run_id"]  # non-empty uuid4 hex for a fresh run
    raw_history = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history["run_id"] == state["run_id"]


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
    history_on_disk = read_b2b_history_rows(checkpoint_dir / "history.json")
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


def test_resume_from_state_raises_on_different_base_seed(tmp_path) -> None:
    env, model_config, champion_path, config_first = _b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
              base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(
            ValueError, match=r"base_seed.*state file has 5.*requested.*6"):
        train_b2b(
            env, model_config, champion_path, checkpoint_dir, config_resumed,
            base_seed=6, resume_from_state=state_path)


def test_resume_with_corrupt_history_succeeds_and_warns(tmp_path, caplog) -> None:
    env, model_config, champion_path, config_first = _b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
              base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    (checkpoint_dir / "history.json").write_text('[{"iteration": 1')

    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(
            env, model_config, champion_path, checkpoint_dir, config_resumed,
            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]
    assert "history.json" in caplog.text
    assert "reset" in caplog.text
    assert "corrupt" in caplog.text
    assert "per-iteration checkpoints are unaffected" in caplog.text.lower()


def test_history_write_uses_atomic_replace_and_leaves_no_temp_file(
        tmp_path, monkeypatch) -> None:
    import fh_mahjong_ai.oracle as oracle

    env, model_config, champion_path, config = _b2b_run_configs(
        tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"
    replace_calls = []
    real_replace = oracle.os.replace

    def recording_replace(src, dst):
        replace_calls.append((Path(src), Path(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(oracle.os, "replace", recording_replace)
    train_b2b(env, model_config, champion_path, checkpoint_dir, config,
              base_seed=5, train_state_every=1)

    history_path = checkpoint_dir / "history.json"
    assert (checkpoint_dir / "history.json.tmp", history_path) in replace_calls
    assert history_path.exists()
    assert not (checkpoint_dir / "history.json.tmp").exists()


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
    history_after_7 = read_b2b_history_rows(checkpoint_dir / "history.json")
    assert [row["iteration"] for row in history_after_7] == [1, 2, 3, 4, 5, 6, 7]

    # Simulate the crash: the completion save at iteration 7 never made it to
    # disk (box died first) -- only the iter-5 snapshot survived.
    state_path.write_bytes(stale_state_bytes)

    config8 = replace(config5, iterations=8)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config8,
                        base_seed=5, train_state_every=5, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4, 5, 6, 7, 8]
    history_on_disk = read_b2b_history_rows(checkpoint_dir / "history.json")
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


# ---------------------------------------------------------------------------
# Adversarial review round 3
# ---------------------------------------------------------------------------
#
# Finding 1 (high): resume could merge state with unrelated history --
# train_state.pt came from any path, but history.json was always loaded from
# checkpoint_dir with no lineage binding, so resuming run A's state into run
# B's directory silently mixed histories/checkpoints. Fix: a `run_id`
# (uuid4 hex) is generated at fresh-run start and persisted in both
# train_state.pt and history.json (wrapped as {"run_id": ..., "rows": [...]});
# resume requires state.run_id == history.run_id.
#
# Finding 2 (medium): an exhausted target (`next_iteration > config.iterations`)
# resumed as a silent no-op -- fixed to raise instead.

def test_resume_cross_directory_mismatched_run_id_raises(tmp_path) -> None:
    # The exact scenario from Finding 1: two independent runs, each with its
    # own train_state.pt + history.json. Pointing --resume-from-state at run
    # A's state file while resuming inside run B's checkpoint_dir (e.g. a
    # copy/paste mistake) must not silently splice A's lineage into B.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_resume_matching_run_id_succeeds_and_persists(tmp_path) -> None:
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    state_before = torch.load(state_path, map_location="cpu", weights_only=False)
    run_id_before = state_before["run_id"]
    assert run_id_before
    raw_history_before = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history_before["run_id"] == run_id_before

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4]
    state_after = torch.load(state_path, map_location="cpu", weights_only=False)
    assert state_after["run_id"] == run_id_before
    raw_history_after = json.loads((checkpoint_dir / "history.json").read_text())
    assert raw_history_after["run_id"] == run_id_before
    assert [row["iteration"] for row in raw_history_after["rows"]] == [1, 2, 3, 4]


def test_resume_legacy_bare_list_history_and_no_run_id_state_is_compat(tmp_path) -> None:
    # MIGRATION: a state file and history.json written before this fix have
    # no run_id at all (bare-list history.json). That pairing must still be
    # accepted -- both are "pre-run_id" and there is nothing to compare.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    # Downgrade both files to the legacy pre-run_id shape.
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    del state["run_id"]
    torch.save(state, state_path)
    legacy_rows = read_b2b_history_rows(checkpoint_dir / "history.json")
    (checkpoint_dir / "history.json").write_text(json.dumps(legacy_rows))

    config_resumed = replace(config_first, iterations=4)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [1, 2, 3, 4]


def test_resume_run_id_state_with_bare_list_history_raises(tmp_path) -> None:
    # A state file WITH a run_id resuming against a legacy bare-list
    # history.json cannot be confirmed to belong together -- reject rather
    # than silently accepting unverified lineage.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"

    legacy_rows = read_b2b_history_rows(checkpoint_dir / "history.json")
    (checkpoint_dir / "history.json").write_text(json.dumps(legacy_rows))

    config_resumed = replace(config_first, iterations=4)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=2, resume_from_state=state_path)


def test_resume_exhausted_target_raises_with_clear_message(tmp_path) -> None:
    # Finding 2: resuming an iter-N state with --iterations already <= N must
    # raise instead of silently exiting success with nothing trained.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_same_target = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="already satisfied"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_same_target,
                 base_seed=5, resume_from_state=state_path)

    config_lower_target = replace(config_first, iterations=1)
    with pytest.raises(ValueError, match="already satisfied"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_lower_target,
                 base_seed=5, resume_from_state=state_path)


# ---------------------------------------------------------------------------
# Adversarial review round 4
# ---------------------------------------------------------------------------
#
# Finding (high): the round-1 "tolerate corrupt/missing history" recovery
# returned an empty history BEFORE the round-3 run_id comparison could ever
# run, so resuming run A's state.pt into run B's checkpoint_dir whose
# history.json was lost kept B's iter_*.pt files on disk while writing A's
# new checkpoints alongside them -- undetectable later since iteration
# checkpoints didn't carry run_id. Fix: iteration checkpoints now save
# run_id in metadata; a missing/corrupt history.json triggers a scan of
# checkpoint_dir's existing iter_*.pt artifacts (if any) whose metadata
# run_id must all match the resuming state's run_id, or the resume raises
# (mixed-lineage, fail closed) unless --force-history-reset is passed.

def _strip_run_id_from_checkpoint_metadata(path: Path) -> None:
    payload = torch.load(path, map_location="cpu")
    payload.get("metadata", {}).pop("run_id", None)
    torch.save(payload, path)


def test_resume_state_a_into_dir_with_bs_checkpoints_and_no_history_raises(tmp_path) -> None:
    # The exact round-4 scenario: run B's history.json is lost/corrupted, and
    # someone points --resume-from-state at run A's train_state.pt while
    # still inside run B's checkpoint_dir. Pre-fix this silently proceeded
    # (empty history) and clobbered/mixed B's checkpoints with A's lineage.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()  # simulate B's history.json being lost

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_from_a)


def test_resume_matching_run_id_artifacts_with_missing_history_proceeds_with_warning(
        tmp_path, caplog) -> None:
    # Genuine round-1 torn-file recovery: history.json is gone, but the
    # checkpoint_dir's existing iter_*.pt files all carry the SAME run_id as
    # the resuming state -- this is one run's own history being lost, not a
    # lineage mixup, so it must still proceed (with the existing warning).
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    with caplog.at_level(logging.WARNING):
        history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                            base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]
    assert "history.json" in caplog.text


def test_resume_into_relocated_empty_dir_with_missing_history_proceeds(tmp_path) -> None:
    # Relocating a state file into a brand-new, empty checkpoint_dir (no
    # iter_*.pt at all) has nothing on disk to contradict the resume, so it
    # must proceed even though history.json is also missing there.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    source_dir = tmp_path / "source"

    train_b2b(env, model_config, champion_path, source_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = source_dir / "train_state.pt"

    empty_dir = tmp_path / "relocated_empty"
    empty_dir.mkdir()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, empty_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]


def test_force_history_reset_overrides_mixed_lineage_check(tmp_path) -> None:
    # The explicit, documented-as-dangerous escape hatch: --force-history-
    # reset skips ONLY the artifact-lineage check, letting an operator who is
    # certain this is a genuine recovery (not a mixup) proceed anyway.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    dir_a = tmp_path / "run_a"
    dir_b = tmp_path / "run_b"

    train_b2b(env, model_config, champion_path, dir_a, config_first,
             base_seed=5, train_state_every=1)
    train_b2b(env, model_config, champion_path, dir_b, config_first,
             base_seed=5, train_state_every=1)

    state_from_a = dir_a / "train_state.pt"
    (dir_b / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, dir_b, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_from_a,
                        force_history_reset=True)

    assert [row["iteration"] for row in history] == [2]


def test_force_history_reset_does_not_skip_base_seed_check(tmp_path) -> None:
    # --force-history-reset is documented to skip ONLY the artifact-lineage
    # check -- never the config/base_seed checks, which guard against a
    # different failure mode entirely (a genuinely different recipe/schedule).
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="base_seed"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=6, resume_from_state=state_path, force_history_reset=True)


def test_resume_legacy_artifacts_and_legacy_state_missing_history_is_compat(tmp_path) -> None:
    # Pre-run_id artifacts + a pre-run_id state file resuming with a missing
    # history.json must keep today's behavior (proceed with a warning) --
    # both sides predate run_id, so there is nothing to compare.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    _strip_run_id_from_checkpoint_metadata(checkpoint_dir / "iter_001.pt")
    state = torch.load(state_path, map_location="cpu", weights_only=False)
    del state["run_id"]
    torch.save(state, state_path)
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    history = train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=1, resume_from_state=state_path)

    assert [row["iteration"] for row in history] == [2]


def test_resume_run_id_state_with_legacy_artifact_and_missing_history_raises(tmp_path) -> None:
    # A state file WITH a run_id, resuming where the on-disk iter_*.pt
    # artifact predates run_id (no run_id in its metadata) and history.json
    # is also gone, cannot prove lineage -- must raise, not silently accept.
    env, model_config, champion_path, config_first = _b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=1)
    state_path = checkpoint_dir / "train_state.pt"

    _strip_run_id_from_checkpoint_metadata(checkpoint_dir / "iter_001.pt")
    (checkpoint_dir / "history.json").unlink()

    config_resumed = replace(config_first, iterations=2)
    with pytest.raises(ValueError, match="run_id"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, config_resumed,
                 base_seed=5, train_state_every=1, resume_from_state=state_path)


def test_new_checkpoint_metadata_carries_run_id_and_infer_model_config_loads_it(tmp_path) -> None:
    from fh_mahjong_ai.model import infer_model_config

    env, model_config, champion_path, config = _b2b_run_configs(tmp_path, iterations=1)
    checkpoint_dir = tmp_path / "ckpt"

    train_b2b(env, model_config, champion_path, checkpoint_dir, config, base_seed=5)

    saved = torch.load(checkpoint_dir / "iter_001.pt", map_location="cpu")
    assert "run_id" in saved["metadata"]
    assert saved["metadata"]["run_id"]

    recovered = infer_model_config(saved["model"], saved["metadata"])
    assert recovered.event_window == model_config.event_window
