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
