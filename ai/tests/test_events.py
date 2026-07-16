import numpy as np
import pytest

from fh_mahjong_ai.events import (
    EVENT_DISCARD,
    EVENT_DRAW,
    EVENT_FLOWER,
    EVENT_PON,
    FACE_UNKNOWN,
    Event,
    decode_event,
    decode_history,
    encode_event,
    event_to_token,
)

# The IDENTICAL golden vector as internal/rl/eventcodec_test.go — the two
# tests pin the cross-language bit layout. Change one, change both.
GOLDEN = [
    (0x00000140, Event(EVENT_DRAW, 0, 5, 0, False, False)),
    (0x00000FE0, Event(EVENT_DRAW, 2, FACE_UNKNOWN, 0, False, False)),
    (0x00004A51, Event(EVENT_DISCARD, 1, 41, 0, True, False)),
    (0x000032A3, Event(EVENT_PON, 2, 10, 3, False, False)),
    (0x00008000, Event(EVENT_DRAW, 0, 0, 0, False, True)),
    (0x000008B7, Event(EVENT_FLOWER, 3, 34, 0, False, False)),
]


def test_golden_vector_decode():
    for packed, expected in GOLDEN:
        assert decode_event(packed) == expected


def test_golden_vector_roundtrip():
    for packed, event in GOLDEN:
        assert encode_event(event) == packed
        assert decode_event(encode_event(event)) == event


def test_reserved_bits_rejected():
    with pytest.raises(ValueError, match="reserved"):
        decode_event(0x00010000)


def test_decode_history_order():
    packed = np.asarray([p for p, _ in GOLDEN], dtype=np.uint32)
    events = decode_history(packed)
    assert [e.type for e in events] == [e.type for _, e in GOLDEN]


def test_event_to_token_bounds():
    tokens = {event_to_token(e) for _, e in GOLDEN}
    assert all(0 <= t < 8 * 4 * 64 for t in tokens)
    # Distinct (type, seat, face) triples get distinct tokens.
    assert len(tokens) == len({(e.type, e.rel_seat, e.face) for _, e in GOLDEN})


def test_env_config_window_field():
    from fh_mahjong_ai.config import EnvConfig

    config = EnvConfig(bridge_kind="mock", event_history_window=128)
    assert config.event_history_window == 128
    assert EnvConfig(bridge_kind="mock").event_history_window == 0


def test_mock_bridge_emits_wellformed_history():
    from fh_mahjong_ai.bridge import build_bridge
    from fh_mahjong_ai.config import EnvConfig

    config = EnvConfig(bridge_kind="mock", event_history_window=16, seed=3)
    bridge = build_bridge(config)
    obs = bridge.reset(seed=3)
    assert obs.event_history.dtype == np.uint32
    assert 0 < obs.event_history.size <= 16
    for event in decode_history(obs.event_history):
        assert 0 <= event.type <= 7
        assert 0 <= event.rel_seat <= 3

    # Window 0: empty array, decode yields nothing.
    off = build_bridge(EnvConfig(bridge_kind="mock", seed=3))
    assert off.reset(seed=3).event_history.size == 0


def test_env_pools_reject_event_history_window():
    # Flat pool rows drop event history (Spec B2 extends the layout); both
    # Python pool constructors must fail fast — and _config_message must
    # still serialize the true value so the Go-side guard is never bypassed.
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import InProcessEnvPool, make_selfplay_pool

    config = EnvConfig(bridge_kind="mock", event_history_window=128)
    with pytest.raises(ValueError, match="event history"):
        InProcessEnvPool(config, slots=2)

    class _PPO:
        max_steps_per_episode = 64
        match_mode = "classic"

    with pytest.raises(ValueError, match="event history"):
        make_selfplay_pool(config, _PPO(), slots=2)


def test_go_pool_config_message_carries_window():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool

    config = EnvConfig(bridge_kind="go", event_history_window=128)
    with pytest.raises(ValueError, match="event history"):
        GoEnvPool(config, slots=2)

    # The serializer itself must carry the true value (defense in depth for
    # the Go-side FHEnvPoolNew guard): call it unbound on a stub.
    class _Stub:
        env_config = config

    message = GoEnvPool._config_message(_Stub())
    assert message.event_history_window == 128


def test_stale_bridge_window_mismatch_raises():
    # A pre-B1 Go library ignores the unknown config field and echoes
    # event_history_window=0; the decoder must fail loudly, not silently
    # run without the configured input.
    from fh_mahjong_ai.bridge import BridgeError, CtypesGoBridge
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=8)

    class _Stub:
        pass

    stub = _Stub()
    stub.config = config

    channels, height, width = config.plane_shape
    stale = game_pb2.SeatObservation(
        seat=0,
        planes=[0.0] * (channels * height * width),
        scalars=[0.0] * config.scalar_features,
        action_mask=bytes(config.action_space_size),
        event_history_window=0,  # stale bridge: field unknown, defaults to 0
    )
    with pytest.raises(BridgeError, match="predates"):
        CtypesGoBridge._decode_observation(stub, stale)

    # A matching window decodes fine.
    fresh = game_pb2.SeatObservation(
        seat=0,
        planes=[0.0] * (channels * height * width),
        scalars=[0.0] * config.scalar_features,
        action_mask=bytes(config.action_space_size),
        event_history=[0x140],
        event_history_window=8,
    )
    obs = CtypesGoBridge._decode_observation(stub, fresh)
    assert obs.event_history.tolist() == [0x140]

    # Window 0 clients accept anything (dormant path untouched).
    stub.config = EnvConfig(bridge_kind="go")
    obs = CtypesGoBridge._decode_observation(stub, stale)
    assert obs.event_history.size == 0
