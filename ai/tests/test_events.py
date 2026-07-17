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


def test_go_pool_config_message_carries_window():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool

    config = EnvConfig(bridge_kind="go", event_history_window=128)

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


def test_inprocess_pool_carries_event_histories():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import InProcessEnvPool, PoolCommand

    config = EnvConfig(bridge_kind="mock", event_history_window=16, seed=3)
    pool = InProcessEnvPool(config, slots=2)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=3), PoolCommand(slot=1, reset_seed=4)])
        rows = sum(1 for m in result.slots if m.has_observation)
        assert len(result.event_histories) == rows
        for row in result.event_histories:
            assert row.dtype == np.uint32
            assert 0 < row.size <= 16
            for event in decode_history(row):
                assert 0 <= event.type <= 7
    finally:
        pool.close()


def test_inprocess_pool_window_zero_has_empty_event_rows():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import InProcessEnvPool, PoolCommand

    pool = InProcessEnvPool(EnvConfig(bridge_kind="mock", seed=3), slots=1)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=3)])
        rows = sum(1 for m in result.slots if m.has_observation)
        assert len(result.event_histories) == rows
        assert all(row.size == 0 for row in result.event_histories)
    finally:
        pool.close()


def _synthetic_pool_response(window, rows_events, game_pb2, config):
    """Build an EnvPoolStepResponse with valid planes/scalars/masks for
    len(rows_events) rows plus the flat event buffers under test."""
    import struct

    channels, height, width = config.plane_shape
    rows = len(rows_events)
    response = game_pb2.EnvPoolStepResponse(
        plane_channels=channels,
        plane_height=height,
        plane_width=width,
        scalar_count=config.scalar_features,
        action_space_size=config.action_space_size,
        event_history_window=window,
        planes=b"\x00" * (4 * rows * channels * height * width),
        scalars=b"\x00" * (4 * rows * config.scalar_features),
        action_masks=b"\x00" * (rows * config.action_space_size),
    )
    counts = b""
    hist = b""
    for events in rows_events:
        counts += struct.pack("<I", len(events))
        hist += b"".join(struct.pack("<I", e) for e in events)
        hist += b"\x00" * (4 * (window - len(events)))
    response.event_counts = counts
    response.event_histories = hist
    for i in range(rows):
        slot = response.slots.add()
        slot.slot = i
        slot.has_observation = True
    return response


def test_go_pool_decode_synthetic_buffers():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=4)

    class _Stub:
        env_config = config

    # Row 0's first event packs to 0x0 (a VALID event: self draw of face 0)
    # — the ambiguity case that forces explicit counts.
    response = _synthetic_pool_response(4, [[0x0, 0x140], [0x8B7, 0x32A3, 0xFE0]], game_pb2, config)
    result = GoEnvPool._decode_response(_Stub(), response)
    assert [row.tolist() for row in result.event_histories] == [[0x0, 0x140], [0x8B7, 0x32A3, 0xFE0]]

    # count > window must raise loudly.
    bad = _synthetic_pool_response(4, [[1, 2]], game_pb2, config)
    bad.event_counts = (5).to_bytes(4, "little")
    with pytest.raises(Exception, match="count|window"):
        GoEnvPool._decode_response(_Stub(), bad)

    # buffer-size mismatch must raise loudly.
    short = _synthetic_pool_response(4, [[1, 2]], game_pb2, config)
    short.event_histories = short.event_histories[:-4]
    with pytest.raises(Exception, match="event"):
        GoEnvPool._decode_response(_Stub(), short)


def test_go_pool_stale_bridge_window_mismatch_raises():
    from fh_mahjong_ai.bridge import BridgeError
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=8)

    class _Stub:
        env_config = config

    stale = _synthetic_pool_response(0, [], game_pb2, config)
    stale.event_history_window = 0
    slot = stale.slots.add()
    slot.slot = 0
    slot.has_observation = True
    stale.planes = b"\x00" * (4 * 39 * 42 * 1)
    stale.scalars = b"\x00" * (4 * config.scalar_features)
    stale.action_masks = b"\x00" * config.action_space_size
    with pytest.raises(BridgeError, match="predates"):
        GoEnvPool._decode_response(_Stub(), stale)


def test_go_pool_ffi_event_rows_match_single_env():
    from fh_mahjong_ai.bridge import build_bridge, resolve_bridge_library
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool, PoolCommand

    config = EnvConfig(bridge_kind="go", event_history_window=16, seed=21,
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False,
                       max_steps_per_episode=200)
    if not resolve_bridge_library(config).exists():
        pytest.skip("Go bridge library not built")

    single = build_bridge(config)
    pool = GoEnvPool(config, slots=1)
    try:
        obs = single.reset(seed=21)
        result = pool.step([PoolCommand(slot=0, reset_seed=21)])
        compared = 0
        for _ in range(60):
            if not result.slots[0].has_observation:
                break
            row = result.event_histories[result.row_of_slot[0]]
            assert row.tolist() == obs.event_history.tolist()
            if row.size > 0:
                compared += 1
            action = obs.legal_actions[0]
            step = single.step(action)
            result = pool.step([PoolCommand(slot=0, action_id=action)])
            if step.terminated or step.truncated:
                break
            obs = step.observation
        assert compared >= 5, "premise: too few nonempty comparisons"
    finally:
        pool.close()
        single.close()


def test_search_pool_decode_carries_event_rows():
    # GoSearchPool must decode through the SHARED GoEnvPool path: event rows,
    # validation, and the stale-bridge handshake included. (A duplicated
    # decode previously dropped events on exactly the search path.)
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.generated.proto import game_pb2
    from fh_mahjong_ai.searchpool import SearchStepResult

    config = EnvConfig(bridge_kind="go", event_history_window=4)

    class _Stub:
        env_config = config

    response = _synthetic_pool_response(4, [[0x140], [0x0, 0x8B7]], game_pb2, config)
    # Mark slot 1 as a round-boundary bootstrap row.
    response.slots[1].round_outcome.is_draw = True

    stub = _Stub()
    # Drive the decode path directly (step() itself needs FFI): replicate its
    # tail — shared decode + round_ended overlay.
    from fh_mahjong_ai.envpool import GoEnvPool

    inner = GoEnvPool._decode_response(stub, response)
    round_ended = {
        int(state.slot): bool(state.HasField("round_outcome")) and not bool(state.terminated)
        for state in response.slots
    }
    result = SearchStepResult(
        slots=inner.slots, planes=inner.planes, scalars=inner.scalars,
        action_masks=inner.action_masks, event_histories=inner.event_histories,
        row_of_slot=inner.row_of_slot, round_ended=round_ended,
    )
    assert [row.tolist() for row in result.event_histories] == [[0x140], [0x0, 0x8B7]]
    assert result.round_ended == {0: False, 1: True}

    # Tripwire: step() must decode through the shared path — a re-duplicated
    # inline decode is exactly how events got dropped on the search path.
    import inspect

    from fh_mahjong_ai.searchpool import GoSearchPool

    assert "_decode_response" in inspect.getsource(GoSearchPool.step)
