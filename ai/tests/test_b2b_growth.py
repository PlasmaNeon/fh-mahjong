"""B2b model growth: dormant ReZero residual blocks stacked onto an anchor
(`grow_b2b_model`), the config validation that guards the surgery, and the
growth-lap telemetry and CLI flags.

Split out of the file that used to be test_deep16_rezero.py; the crash-resume
half stayed behind in test_b2b_resume.py."""

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, ReZeroResidualBlock
from fh_mahjong_ai.oracle import grow_b2b_model, train_b2b
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import load_checkpoint, model_config_metadata, save_checkpoint
from conftest import MOCK_ENV, b2b_model_config, b2b_run_configs, save_b2b_anchor


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


# Adversarial round 17: residual_blocks<=64 and growth_blocks<=64 are each
# individually bounded, but nothing stopped them composing -- e.g.
# residual_blocks=64 + growth_blocks=64 = 128 total blocks (~9GiB fp32),
# accepted by ModelConfig and constructed by infer_model_config's shape
# cross-check, defeating the checkpoint-loading memory guard. The 64 ceiling
# must be a TOTAL depth budget: residual_blocks + growth_blocks <= 64.
def test_residual_plus_growth_blocks_at_individual_caps_raises() -> None:
    with pytest.raises(ValueError, match="residual_blocks.*growth_blocks|growth_blocks.*residual_blocks"):
        ModelConfig(residual_blocks=64, growth_blocks=64)


def test_residual_plus_growth_blocks_within_combined_cap_ok() -> None:
    config = ModelConfig(residual_blocks=60, growth_blocks=4)
    assert config.residual_blocks == 60
    assert config.growth_blocks == 4


def test_residual_plus_growth_blocks_over_combined_cap_raises() -> None:
    with pytest.raises(ValueError, match="residual_blocks.*growth_blocks|growth_blocks.*residual_blocks"):
        ModelConfig(residual_blocks=4, growth_blocks=61)


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
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    anchor_state = torch.load(anchor_path, map_location="cpu")["model"]

    grown = grow_b2b_model(anchor_path, growth_blocks=3)
    grown_state = grown.state_dict()

    for key, value in anchor_state.items():
        assert torch.equal(grown_state[key], value), key
    for i in range(3):
        assert grown_state[f"growth.{i}.alpha"].item() == 0.0


def test_grow_b2b_model_step_zero_parity(tmp_path) -> None:
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    anchor = PolicyValueNet(MOCK_ENV, anchor_config)
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
    anchor_path = save_b2b_anchor(tmp_path, b2b_model_config(), with_model_config_metadata=False)
    with pytest.raises(RuntimeError, match="model_config"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_already_grown_anchor(tmp_path) -> None:
    anchor_path = save_b2b_anchor(tmp_path, b2b_model_config(growth_blocks=2))
    with pytest.raises(RuntimeError, match="grow"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_anchor_with_undeclared_growth_tensors(tmp_path) -> None:
    # Adversarial round 13, medium finding: an anchor whose STATE DICT
    # already carries growth.*.alpha tensors (nonzero alpha, i.e. genuinely
    # trained growth) but whose metadata LIES about growth_blocks==0 must
    # still be rejected -- trusting the metadata claim instead of the state
    # dict would load those tensors into a "fresh" growth run undetected,
    # breaking the step-0 warm-start parity invariant.
    anchor_config = b2b_model_config(growth_blocks=1)
    grown_anchor = PolicyValueNet(MOCK_ENV, anchor_config)
    with torch.no_grad():
        grown_anchor.growth[0].alpha.fill_(0.7)
    lying_metadata = model_config_metadata(anchor_config)
    lying_metadata["growth_blocks"] = 0
    anchor_path = tmp_path / "lying_anchor.pt"
    save_checkpoint(anchor_path, grown_anchor, metadata={"model_config": lying_metadata})

    with pytest.raises(RuntimeError, match="growth block"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_lying_growth_blocks_claim_without_state_keys(tmp_path) -> None:
    # Adversarial round 18, medium finding: the INVERSE of round 13's lying
    # anchor above. Here metadata claims growth_blocks=2 (already grown) but
    # the state dict carries NO growth.* keys at all -- a stripped grown
    # checkpoint. The old guard only rejected `derived_growth_blocks != 0`,
    # so this case (claim > 0, derived == 0) sailed through undetected and
    # was then silently treated as a valid growth_blocks=0 anchor safe to
    # grow further, discarding the metadata's own claim that it was already
    # grown. The claim and the state-dict-derived count must both be 0 (or
    # must agree) to proceed.
    anchor_config = b2b_model_config(growth_blocks=0)
    lying_metadata = model_config_metadata(anchor_config)
    lying_metadata["growth_blocks"] = 2
    anchor_path = save_b2b_anchor(tmp_path, anchor_config,
                               model_config_metadata_override=lying_metadata)

    with pytest.raises(RuntimeError, match="growth_blocks"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_mismatched_trunk_shape(tmp_path) -> None:
    anchor_config = b2b_model_config()
    lying_metadata = model_config_metadata(anchor_config)
    lying_metadata["trunk_hidden_dim"] = anchor_config.trunk_hidden_dim * 2
    anchor_path = save_b2b_anchor(tmp_path, anchor_config, model_config_metadata_override=lying_metadata)
    with pytest.raises(RuntimeError):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_doctored_channels_claim(tmp_path) -> None:
    # The anchor's REAL net is built at channels=32, but its metadata lies
    # and claims channels=16 (the SMALL_MODEL default). grow_b2b_model constructs
    # its grown net from the metadata claim alone
    # (`PolicyValueNet(anchor_env_config, grown_config)`), so a wrong claim
    # here would build a differently-shaped net than the anchor's own
    # tensors before load_compatible_checkpoint ever gets a chance to catch
    # the drift -- must raise up front, before any construction.
    real_config = b2b_model_config(channels=32)
    lying_metadata = model_config_metadata(real_config)
    lying_metadata["channels"] = 16
    anchor_path = save_b2b_anchor(tmp_path, real_config, model_config_metadata_override=lying_metadata)

    with pytest.raises(RuntimeError, match="channels"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_raises_on_doctored_residual_blocks_claim(tmp_path) -> None:
    # Same class of gap, for residual_blocks: the anchor's REAL net has 2
    # plane_blocks, but metadata claims 1.
    real_config = b2b_model_config(residual_blocks=2)
    lying_metadata = model_config_metadata(real_config)
    lying_metadata["residual_blocks"] = 1
    anchor_path = save_b2b_anchor(tmp_path, real_config, model_config_metadata_override=lying_metadata)

    with pytest.raises(RuntimeError, match="residual_blocks"):
        grow_b2b_model(anchor_path, growth_blocks=3)


def test_grow_b2b_model_same_shape_happy_path_unaffected_by_dim_check(tmp_path) -> None:
    # Honest metadata (claim matches the anchor's own tensor shapes) must
    # still grow successfully -- the new pre-surgery cross-check is not a
    # blanket rejection.
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    grown = grow_b2b_model(anchor_path, growth_blocks=3)
    assert grown.model_config.growth_blocks == 3


def test_grow_b2b_model_ignores_env_config_mismatch_when_not_passed(tmp_path) -> None:
    # Backward-compat: callers that don't pass env_config (e.g. exercising
    # grow_b2b_model in isolation with no "live env" to check against) get
    # the old unchecked behavior.
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    grown = grow_b2b_model(anchor_path, growth_blocks=3)
    assert grown.model_config.growth_blocks == 3


def test_grow_b2b_model_raises_on_scalar_feature_drift_against_live_env(tmp_path) -> None:
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", scalar_features=MOCK_ENV.scalar_features + 1)
    with pytest.raises(RuntimeError, match="scalar_features"):
        grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)


def test_grow_b2b_model_raises_on_action_space_drift_against_live_env(tmp_path) -> None:
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", action_space_size=MOCK_ENV.action_space_size + 10)
    with pytest.raises(RuntimeError, match="action_space_size"):
        grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)


def test_grow_b2b_model_matched_env_config_unchanged(tmp_path) -> None:
    # Live env_config matches what the anchor was actually built under (39ch
    # mock, default scalar/action-space sizes, matching event_window) — the
    # cross-check must be a no-op.
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", event_history_window=anchor_config.event_window)
    grown = grow_b2b_model(anchor_path, growth_blocks=3, env_config=live_env)
    assert grown.model_config.growth_blocks == 3


def test_train_b2b_growth_raises_on_stale_anchor_env_config_drift(tmp_path) -> None:
    # The finding this guards: train_b2b's growth_blocks>0 routing must
    # cross-check the anchor's construction shapes against the LIVE
    # env_config collection will run under, not silently build a model
    # shaped to a stale anchor while collection runs on a different env.
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)

    live_env = EnvConfig(bridge_kind="mock", event_history_window=anchor_config.event_window,
                         oracle_observation=True, max_steps_per_episode=16,
                         scalar_features=MOCK_ENV.scalar_features + 1)
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
    anchor_config = b2b_model_config()
    model = PolicyValueNet(MOCK_ENV, anchor_config)
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
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)

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

    model_config = b2b_model_config(growth_blocks=2)
    model = PolicyValueNet(MOCK_ENV, model_config)
    assert _growth_alpha_mean_abs(model) == pytest.approx(0.0)  # ReZero alphas init to 0

    with torch.no_grad():
        model.growth[0].alpha.fill_(0.5)
    # mean(|0.5|, |0.0|) over the two growth blocks.
    assert _growth_alpha_mean_abs(model) == pytest.approx(0.25)


def test_growth_alpha_mean_abs_none_without_growth_blocks() -> None:
    from fh_mahjong_ai.oracle import _growth_alpha_mean_abs

    model_config = b2b_model_config()  # growth_blocks=0 (default)
    model = PolicyValueNet(MOCK_ENV, model_config)
    assert _growth_alpha_mean_abs(model) is None


def test_train_b2b_history_includes_growth_alpha_telemetry(tmp_path) -> None:
    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)

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
    env, model_config, champion_path, config = b2b_run_configs(tmp_path, iterations=1)

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


def test_train_b2b_cli_help_shows_allow_bridge_mismatch_flag() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--allow-bridge-mismatch" in result.stdout


def test_train_b2b_cli_help_shows_accept_legacy_unpinned_state_flag() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--accept-legacy-unpinned-state" in result.stdout


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

    anchor_config = b2b_model_config()
    anchor_path = save_b2b_anchor(tmp_path, anchor_config)
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
