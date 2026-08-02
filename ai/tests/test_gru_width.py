import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import EventEncoder, PolicyValueNet
from fh_mahjong_ai.oracle import train_b2b, widen_event_gru
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.storage import load_checkpoint, model_config_metadata, save_checkpoint

_ENV39 = EnvConfig(bridge_kind="mock")

# Reused from test_deep16_rezero.py: a tiny B2b architecture so anchor
# checkpoints in this file build and load fast.
_SMALL = dict(channels=16, residual_blocks=1, plane_feature_dim=32, scalar_hidden_dim=16,
              trunk_hidden_dim=32, value_hidden_dim=16, q_hidden_dim=16)


def _b2b_config(**overrides) -> ModelConfig:
    fields = dict(_SMALL, event_window=8, event_hidden_dim=8, privileged_critic=True, aux_heads=True)
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


# --- Task 2: widen_event_gru warm-start + step-zero parity ---


def test_widen_event_gru_preserves_every_non_event_encoder_tensor(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    anchor_state = torch.load(anchor_path, map_location="cpu")["model"]

    widened = widen_event_gru(anchor_path, new_hidden_dim=16)
    widened_state = widened.state_dict()

    for key, value in anchor_state.items():
        if key.startswith(("event_encoder.gru.", "event_encoder.output_proj.")):
            continue
        assert torch.equal(widened_state[key], value), key


def test_widen_event_gru_gru_old_blocks_and_zero_coupling(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    anchor_state = torch.load(anchor_path, map_location="cpu")["model"]

    h_old, h_new = anchor_config.event_hidden_dim, 16
    widened = widen_event_gru(anchor_path, new_hidden_dim=h_new)
    widened_state = widened.state_dict()

    old_weight_ih = anchor_state["event_encoder.gru.weight_ih_l0"]
    old_weight_hh = anchor_state["event_encoder.gru.weight_hh_l0"]
    old_bias_ih = anchor_state["event_encoder.gru.bias_ih_l0"]
    old_bias_hh = anchor_state["event_encoder.gru.bias_hh_l0"]
    new_weight_ih = widened_state["event_encoder.gru.weight_ih_l0"]
    new_weight_hh = widened_state["event_encoder.gru.weight_hh_l0"]
    new_bias_ih = widened_state["event_encoder.gru.bias_ih_l0"]
    new_bias_hh = widened_state["event_encoder.gru.bias_hh_l0"]

    for gate in range(3):
        old_rows = slice(gate * h_old, (gate + 1) * h_old)
        new_old_rows = slice(gate * h_new, gate * h_new + h_old)
        assert torch.equal(new_weight_ih[new_old_rows, :], old_weight_ih[old_rows, :])
        assert torch.equal(new_bias_ih[new_old_rows], old_bias_ih[old_rows])
        assert torch.equal(new_bias_hh[new_old_rows], old_bias_hh[old_rows])
        assert torch.equal(new_weight_hh[new_old_rows, :h_old], old_weight_hh[old_rows, :])
        assert torch.equal(new_weight_hh[new_old_rows, h_old:],
                           torch.zeros(h_old, h_new - h_old))

    proj_weight = widened_state["event_encoder.output_proj.weight"]
    proj_bias = widened_state["event_encoder.output_proj.bias"]
    assert proj_weight.shape == (h_old, h_new)
    assert torch.equal(proj_weight[:, :h_old], torch.eye(h_old))
    assert torch.equal(proj_weight[:, h_old:], torch.zeros(h_old, h_new - h_old))
    assert torch.equal(proj_bias, torch.zeros(h_old))


def test_widen_event_gru_step_zero_parity(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    anchor = PolicyValueNet(_ENV39, anchor_config)
    load_checkpoint(anchor_path, anchor)
    anchor.eval()

    widened = widen_event_gru(anchor_path, new_hidden_dim=16)
    widened.eval()

    for seed in range(4):
        planes, scalars, mask, events, lengths = _batch(seed=seed)
        with torch.no_grad():
            anchor_features = anchor.encode(planes, scalars, events, lengths)
            widened_features = widened.encode(planes, scalars, events, lengths)
            anchor_logits, anchor_value = anchor(planes, scalars, mask, events=events, event_lengths=lengths)
            widened_logits, widened_value = widened(planes, scalars, mask, events=events, event_lengths=lengths)
            anchor_q, _ = anchor.q_values(planes, scalars, mask)
            widened_q, _ = widened.q_values(planes, scalars, mask)
            anchor_aux = anchor.aux_predictions(anchor_features)
            widened_aux = widened.aux_predictions(widened_features)

        assert torch.equal(anchor_features, widened_features)
        assert torch.equal(anchor_logits, widened_logits)
        assert torch.equal(anchor_value, widened_value)
        assert torch.equal(anchor_q, widened_q)
        for key in ("belief", "dealin", "rank"):
            assert torch.equal(anchor_aux[key], widened_aux[key])
        assert torch.equal(anchor_logits.argmax(dim=-1), widened_logits.argmax(dim=-1))


def test_widen_event_gru_raises_on_new_hidden_not_greater(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    with pytest.raises(RuntimeError, match="new_hidden_dim"):
        widen_event_gru(anchor_path, new_hidden_dim=anchor_config.event_hidden_dim)
    with pytest.raises(RuntimeError, match="new_hidden_dim"):
        widen_event_gru(anchor_path, new_hidden_dim=anchor_config.event_hidden_dim - 1)


def test_widen_event_gru_raises_on_already_widened_anchor_metadata(tmp_path) -> None:
    # event_hidden_dim=16, event_output_dim=8 is a genuinely already-widened
    # anchor (non-dormant projection) per its own metadata claim.
    already_widened_config = _b2b_config(event_hidden_dim=16, event_output_dim=8)
    anchor_path = _save_anchor(tmp_path, already_widened_config)
    with pytest.raises(RuntimeError, match="event_output_dim"):
        widen_event_gru(anchor_path, new_hidden_dim=32)


def test_widen_event_gru_raises_on_anchor_with_undeclared_output_proj_tensors(tmp_path) -> None:
    # Trust the STATE DICT, not the metadata's event_output_dim claim: an
    # anchor whose metadata lies about event_output_dim==0 while its tensors
    # actually carry an event_encoder.output_proj.* key (already widened, or
    # tampered) must still be rejected.
    anchor_config = _b2b_config(event_hidden_dim=8)
    widened_anchor_config = replace(anchor_config, event_output_dim=8, event_hidden_dim=16)
    widened_anchor = PolicyValueNet(_ENV39, widened_anchor_config)
    lying_metadata = model_config_metadata(widened_anchor_config)
    lying_metadata["event_output_dim"] = 0
    lying_metadata["event_hidden_dim"] = 8
    anchor_path = tmp_path / "lying_anchor.pt"
    save_checkpoint(anchor_path, widened_anchor, metadata={"model_config": lying_metadata})

    with pytest.raises(RuntimeError, match="output_proj"):
        widen_event_gru(anchor_path, new_hidden_dim=32)


def test_widen_event_gru_raises_without_model_config_metadata(tmp_path) -> None:
    anchor_path = _save_anchor(tmp_path, _b2b_config(), with_model_config_metadata=False)
    with pytest.raises(RuntimeError, match="model_config"):
        widen_event_gru(anchor_path, new_hidden_dim=16)


def test_widen_event_gru_raises_on_zero_event_window_anchor(tmp_path) -> None:
    anchor_config = _b2b_config(event_window=0, privileged_critic=False, aux_heads=False)
    anchor_path = _save_anchor(tmp_path, anchor_config)
    with pytest.raises(RuntimeError, match="event_window"):
        widen_event_gru(anchor_path, new_hidden_dim=16)


def test_widen_event_gru_raises_on_scalar_feature_drift_against_live_env(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", scalar_features=_ENV39.scalar_features + 1)
    with pytest.raises(RuntimeError, match="scalar_features"):
        widen_event_gru(anchor_path, new_hidden_dim=16, env_config=live_env)


def test_widen_event_gru_matched_env_config_unchanged(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    live_env = EnvConfig(bridge_kind="mock", event_history_window=anchor_config.event_window)
    widened = widen_event_gru(anchor_path, new_hidden_dim=16, env_config=live_env)
    assert widened.model_config.event_hidden_dim == 16
    assert widened.model_config.event_output_dim == anchor_config.event_hidden_dim


def test_train_b2b_widen_event_hidden_and_growth_blocks_mutually_exclusive(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    with pytest.raises(ValueError, match="growth_blocks.*widen_event_hidden|widen_event_hidden.*growth_blocks"):
        train_b2b(env, anchor_config, anchor_path, tmp_path / "ckpt", config,
                 base_seed=5, growth_blocks=2, widen_event_hidden=16)


def test_train_b2b_widen_event_hidden_smoke_saves_metadata(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config = PPOConfig(device="cpu", iterations=1, matches_per_iter=2,
                       max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                       num_workers=1, match_mode="classic")
    history = train_b2b(env, anchor_config, anchor_path, tmp_path / "ckpt", config,
                        base_seed=5, widen_event_hidden=16)
    assert len(history) == 1
    saved = torch.load(tmp_path / "ckpt" / "iter_001.pt", map_location="cpu")
    assert saved["metadata"]["model_config"]["event_hidden_dim"] == 16
    assert saved["metadata"]["model_config"]["event_output_dim"] == anchor_config.event_hidden_dim


def test_train_b2b_cli_help_shows_widen_event_hidden_flag() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b", "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--widen-event-hidden" in result.stdout


def test_train_b2b_cli_rejects_growth_blocks_and_widen_event_hidden_together(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "fh_mahjong_ai.scripts.train_b2b",
         "--champion", "/nonexistent/anchor.pt",
         "--checkpoint-dir", str(tmp_path / "ckpt"),
         "--bridge-kind", "mock",
         "--model-growth-blocks", "2",
         "--widen-event-hidden", "16"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "--model-growth-blocks" in result.stderr
    assert "--widen-event-hidden" in result.stderr


def test_resume_widen_event_hidden_run_round_trips(tmp_path) -> None:
    anchor_config = _b2b_config()
    anchor_path = _save_anchor(tmp_path, anchor_config)

    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=16)
    config_first = PPOConfig(device="cpu", iterations=2, matches_per_iter=2,
                             max_steps_per_episode=16, ppo_epochs=1, minibatch_size=8,
                             num_workers=1, match_mode="classic")
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, anchor_config, anchor_path, checkpoint_dir, config_first,
             base_seed=5, widen_event_hidden=16, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    assert state_path.exists()

    widened_config = replace(anchor_config, event_hidden_dim=16,
                             event_output_dim=anchor_config.event_hidden_dim)
    config_resumed = replace(config_first, iterations=4)

    history = train_b2b(env, widened_config, anchor_path, checkpoint_dir, config_resumed,
                        base_seed=5, train_state_every=2, resume_from_state=state_path)
    assert [row["iteration"] for row in history] == [1, 2, 3, 4]


def test_event_output_dim_zero_leaves_state_dict_keys_unchanged() -> None:
    reference_model = PolicyValueNet(EnvConfig(), ModelConfig())
    reference_keys = set(reference_model.state_dict().keys())

    model = PolicyValueNet(EnvConfig(), ModelConfig(event_output_dim=0))
    keys = set(model.state_dict().keys())

    assert keys == reference_keys
    assert not any(key.startswith("event_encoder.output_proj.") for key in keys)


def test_event_output_dim_narrower_adds_projection_and_encoder_output_width() -> None:
    config = ModelConfig(event_window=8, event_hidden_dim=256, event_output_dim=128)
    model = PolicyValueNet(_ENV39, config)
    keys = set(model.state_dict().keys())

    assert "event_encoder.output_proj.weight" in keys
    assert "event_encoder.output_proj.bias" in keys
    assert model.state_dict()["event_encoder.output_proj.weight"].shape == (128, 256)

    n = 3
    events = torch.zeros(n, 8, dtype=torch.int64)
    lengths = torch.full((n,), 4, dtype=torch.int64)
    out = model.event_encoder(events, lengths)
    assert out.shape == (n, 128)

    channels, height, width = _ENV39.plane_shape
    planes = torch.randn(n, channels, height, width)
    scalars = torch.randn(n, _ENV39.scalar_features)
    action_mask = torch.ones(n, _ENV39.action_space_size)
    logits, value = model(planes, scalars, action_mask, events=events, event_lengths=lengths)
    assert logits.shape == (n, _ENV39.action_space_size)
    assert value.shape == (n,)


def test_event_output_dim_equal_to_hidden_dim_has_no_projection() -> None:
    config = ModelConfig(event_window=8, event_hidden_dim=128, event_output_dim=128)
    model = PolicyValueNet(_ENV39, config)
    keys = set(model.state_dict().keys())

    assert not any(key.startswith("event_encoder.output_proj.") for key in keys)
    assert model.event_encoder.output_proj is None
    assert model.event_encoder.output_dim == 128


@pytest.mark.parametrize("value", [-1, True, ModelConfig.MAX_HIDDEN_DIM + 1])
def test_event_output_dim_out_of_bounds_or_non_int_raises(value) -> None:
    with pytest.raises(ValueError):
        ModelConfig(event_output_dim=value)


def test_event_encoder_projection_applied_before_zero_length_mask() -> None:
    """Regression: the output projection must run before the zero-length
    mask, not after. A nonzero projection bias applied to already-zeroed
    rows would turn "no event history" into `bias` instead of true zeros,
    corrupting the zero-history semantics relied on elsewhere (e.g. the
    batch-level no-events fast path, which emits real zeros)."""
    torch.manual_seed(11)
    embed_dim, hidden_dim, output_dim = 4, 16, 8
    encoder = EventEncoder(embed_dim=embed_dim, hidden_dim=hidden_dim, output_dim=output_dim)
    # Force a nonzero bias so a bug (mask-then-project) would leak into
    # zero-length rows instead of landing on exact zeros.
    with torch.no_grad():
        encoder.output_proj.bias.fill_(0.5)

    window = 6
    n = 4
    events = torch.randint(0, 1 << 16, (n, window), dtype=torch.int64)
    # Rows 0 and 2 have no event history; rows 1 and 3 are populated.
    lengths = torch.tensor([0, 3, 0, 5], dtype=torch.int64)

    out = encoder(events, lengths)
    assert out.shape == (n, output_dim)

    assert torch.equal(out[0], torch.zeros(output_dim))
    assert torch.equal(out[2], torch.zeros(output_dim))

    # Populated rows must match an unmasked reference: gather -> project,
    # with no masking applied (lengths > 0 for these rows).
    ev_type = (events >> 0) & 0x7
    rel_seat = (events >> 4) & 0x3
    face = (events >> 6) & 0x3F
    rel_from = (events >> 12) & 0x3
    tsumogiri = ((events >> 14) & 0x1).float()
    haitei = ((events >> 15) & 0x1).float()
    tokens = (ev_type * 4 + rel_seat) * 64 + face
    side = torch.cat(
        [
            tsumogiri.unsqueeze(-1),
            haitei.unsqueeze(-1),
            torch.nn.functional.one_hot(rel_from, num_classes=4).float(),
        ],
        dim=-1,
    )
    with torch.no_grad():
        x = encoder.embedding(tokens) + encoder.side_proj(side)
        gru_out, _ = encoder.gru(x)
        idx = (lengths - 1).clamp(min=0).view(n, 1, 1).expand(-1, 1, hidden_dim)
        gathered = gru_out.gather(1, idx).squeeze(1)
        unmasked_reference = encoder.output_proj(gathered)

    for row in (1, 3):
        assert torch.allclose(out[row], unmasked_reference[row])


def test_event_output_dim_equal_hidden_collapses_to_identical_state_dict() -> None:
    torch.manual_seed(7)
    baseline_config = ModelConfig(event_window=8, event_hidden_dim=128, event_output_dim=0)
    torch.manual_seed(7)
    baseline_model = PolicyValueNet(_ENV39, baseline_config)

    torch.manual_seed(7)
    projected_config = ModelConfig(event_window=8, event_hidden_dim=128, event_output_dim=128)
    torch.manual_seed(7)
    projected_model = PolicyValueNet(_ENV39, projected_config)

    baseline_state = baseline_model.state_dict()
    projected_state = projected_model.state_dict()

    assert set(baseline_state.keys()) == set(projected_state.keys())
    for key, value in baseline_state.items():
        assert torch.equal(value, projected_state[key]), key
