import pytest
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import EventEncoder, PolicyValueNet

_ENV39 = EnvConfig(bridge_kind="mock")


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
