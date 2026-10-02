from __future__ import annotations

import ctypes
import os
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

from fh_mahjong_ai import bridge as bridge_module
from fh_mahjong_ai.bridge import BridgeError, CtypesGoBridge, CtypesGoBridge as GoMahjongBridge, MockMahjongBridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.generated.proto import game_pb2
from fh_mahjong_ai.types import Observation


class MockMahjongBridgeTest(unittest.TestCase):
    def test_step_requires_reset(self) -> None:
        bridge = MockMahjongBridge(EnvConfig())

        with self.assertRaises(BridgeError):
            bridge.step(0)

    def test_step_validates_against_current_observation(self) -> None:
        config = EnvConfig(action_space_size=8, plane_shape=(1, 1, 1), scalar_features=1)
        bridge = MockMahjongBridge(config)
        observation = bridge.reset(seed=7)
        legal_action = observation.legal_actions[0]

        bridge._observe = lambda: Observation(
            seat=1,
            planes=np.zeros((1, 1, 1), dtype=np.float32),
            scalars=np.zeros((1,), dtype=np.float32),
            action_mask=np.zeros((config.action_space_size,), dtype=np.int8),
            metadata={"bridge": "mock-test"},
        )

        result = bridge.step(legal_action)

        self.assertEqual(result.info["mock_action"], legal_action)
        self.assertIs(result.observation, bridge._current_observation)


class FakeFunction:
    def __init__(self, callback=None, return_value=None) -> None:
        self.callback = callback
        self.return_value = return_value
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        if self.callback is not None:
            return self.callback(*args)
        return self.return_value


class FakeGoLibrary:
    def __init__(self) -> None:
        self._buffers = []
        self.closed_handles = []
        self.last_new_config = None
        self.last_reset_seed = None
        self.FHEnvNew = FakeFunction(callback=self._new)
        self.FHEnvReset = FakeFunction(callback=self._reset)
        self.FHEnvStep = FakeFunction(callback=self._step)
        self.FHEnvEvaluateBranches = FakeFunction(callback=self._evaluate_branches)
        self.FHEnvClose = FakeFunction(callback=self._close)
        self.FHGenerateHeuristicTrajectory = FakeFunction(callback=self._trajectory)
        self.FHFree = FakeFunction(callback=self._free)
        self.FHEnvRouteProbe = FakeFunction(callback=self._route_probe)
        self.route_probe_seats = []

    def _new(self, config_ptr, config_len):
        config = game_pb2.EnvConfig()
        config.ParseFromString(ctypes.string_at(config_ptr, config_len))
        self.last_new_config = config
        return 7

    def _bytes_result(self, payload: bytes) -> bridge_module.FHBytesResult:
        buffer = ctypes.create_string_buffer(payload)
        self._buffers.append(buffer)
        return bridge_module.FHBytesResult(
            data=ctypes.cast(buffer, ctypes.c_void_p).value,
            len=len(payload),
            err=None,
        )

    def _observation(self) -> game_pb2.SeatObservation:
        return game_pb2.SeatObservation(
            seat=0,
            planes=[0.0],
            plane_channels=1,
            plane_height=1,
            plane_width=1,
            scalars=[0.0],
            action_mask=bytes([1, 0]),
            action_space_size=2,
            decision_index=0,
        )

    def _reset(self, handle, request_ptr, request_len):
        request = game_pb2.EnvResetRequest()
        request.ParseFromString(ctypes.string_at(request_ptr, request_len))
        self.last_reset_seed = request.seed
        response = game_pb2.EnvResetResponse(
            observation=self._observation(),
            round_outcome=game_pb2.RoundOutcome(
                is_draw=False,
                winner_seat=0,
                win_type=game_pb2.ACTION_TSUMO,
                total_score=4,
                payouts=[game_pb2.PlayerPayout(seat=0, amount=6)],
            ),
        )
        return self._bytes_result(response.SerializeToString())

    def _step(self, handle, request_ptr, request_len):
        response = game_pb2.EnvStepResponse(
            observation=self._observation(),
            rewards=[0.0, 0.0, 0.0, 0.0],
            round_outcome=game_pb2.RoundOutcome(
                is_draw=False,
                winner_seat=1,
                win_type=game_pb2.ACTION_RON,
                discarder_seat=0,
                total_score=2,
                breakdown=[game_pb2.ScoreEntry(pattern_name="Base Point (坐台)", points=1,
                                               pattern_id="base_point")],
            ),
        )
        return self._bytes_result(response.SerializeToString())

    def _evaluate_branches(self, handle, request_ptr, request_len):
        request = game_pb2.BranchEvaluationRequest()
        request.ParseFromString(ctypes.string_at(request_ptr, request_len))
        response = game_pb2.BranchEvaluationResponse(observation=self._observation())
        for action_id in request.action_ids:
            response.results.append(
                game_pb2.BranchEvaluationResult(
                    action_id=int(action_id),
                    rewards=[float(action_id), 0.0, 0.0, 0.0],
                    terminated=True,
                    decisions=3,
                    round_outcome=game_pb2.RoundOutcome(
                        is_draw=False,
                        winner_seat=0,
                        win_type=game_pb2.ACTION_TSUMO,
                    ),
                )
            )
        return self._bytes_result(response.SerializeToString())

    def _close(self, handle) -> None:
        self.closed_handles.append(int(handle))

    def _trajectory(self, request_ptr, request_len):
        response = game_pb2.TrajectoryDataset()
        return self._bytes_result(response.SerializeToString())

    def _free(self, ptr) -> None:
        return None

    def _route_probe(self, handle, request_ptr, request_len):
        request = game_pb2.RouteProbeRequest()
        if request_len:
            request.ParseFromString(ctypes.string_at(request_ptr, request_len))
        self.route_probe_seats.append(int(request.seat))
        response = game_pb2.RouteProbe(
            seat=request.seat,
            routes=game_pb2.RouteShanten(overall=1, standard=3, seven_pairs=4, independence=1),
            wild_count=1,
            discards=[game_pb2.DiscardRoute(
                action_id=9, is_wild=True,
                after=game_pb2.RouteShanten(overall=1, standard=3, seven_pairs=5, independence=1))],
        )
        return self._bytes_result(response.SerializeToString())


class CtypesGoBridgeTest(unittest.TestCase):
    def _fake_bridge(self, fake_library):
        config = EnvConfig(plane_shape=(1, 1, 1), scalar_features=1, action_space_size=2,
                           bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"))
        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            return CtypesGoBridge(config)

    def test_route_probe_decodes_and_forwards_seat_including_zero(self) -> None:
        fake_library = FakeGoLibrary()
        bridge = self._fake_bridge(fake_library)
        probe = bridge.route_probe(2)
        zero = bridge.route_probe(0)
        bridge.close()

        self.assertEqual(fake_library.route_probe_seats, [2, 0])
        self.assertEqual(probe["seat"], 2)
        self.assertEqual(zero["seat"], 0)
        self.assertEqual(probe["routes"], {"overall": 1, "standard": 3, "seven_pairs": 4, "independence": 1})
        self.assertEqual(probe["wild_count"], 1)
        self.assertEqual(probe["open_meld_count"], 0)
        self.assertEqual(probe["discards"], [{
            "action_id": 9, "is_wild": True,
            "after": {"overall": 1, "standard": 3, "seven_pairs": 5, "independence": 1}}])

    def test_stale_library_loads_and_fails_only_on_route_probe(self) -> None:
        fake_library = FakeGoLibrary()
        del fake_library.FHEnvRouteProbe
        bridge = self._fake_bridge(fake_library)
        bridge.reset(seed=1)
        with self.assertRaisesRegex(BridgeError, "FHEnvRouteProbe"):
            bridge.route_probe(0)
        bridge.close()

    def test_reset_preserves_zero_seed_and_context_manager_closes_handle(self) -> None:
        fake_library = FakeGoLibrary()
        config = EnvConfig(
            plane_shape=(1, 1, 1),
            scalar_features=1,
            action_space_size=2,
            bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"),
        )

        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            with CtypesGoBridge(config) as bridge:
                observation = bridge.reset(seed=0)

        self.assertEqual(fake_library.last_reset_seed, 0)
        self.assertEqual(fake_library.closed_handles, [7])
        self.assertEqual(observation.seat, 0)
        self.assertIsNotNone(bridge.last_reset_result)
        self.assertFalse(bridge.last_reset_result.terminated)
        self.assertEqual(bridge.last_reset_result.info["round_outcome"]["win_type_name"], "ACTION_TSUMO")
        self.assertEqual(bridge.last_reset_result.info["round_outcome"]["payouts"], [{"seat": 0, "amount": 6}])

    def test_step_decodes_round_outcome(self) -> None:
        fake_library = FakeGoLibrary()
        config = EnvConfig(
            plane_shape=(1, 1, 1),
            scalar_features=1,
            action_space_size=2,
            bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"),
        )

        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            bridge = CtypesGoBridge(config)
            result = bridge.step(0)
            bridge.close()

        self.assertEqual(result.info["round_outcome"]["win_type_name"], "ACTION_RON")
        self.assertEqual(result.info["round_outcome"]["winner_seat"], 1)
        self.assertEqual(result.info["round_outcome"]["discarder_seat"], 0)
        self.assertEqual(result.info["round_outcome"]["breakdown"],
                         [{"pattern_id": "base_point", "pattern_name": "Base Point (坐台)", "points": 1}])

    def test_evaluate_branches_decodes_go_results(self) -> None:
        fake_library = FakeGoLibrary()
        config = EnvConfig(
            plane_shape=(1, 1, 1),
            scalar_features=1,
            action_space_size=2,
            bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"),
        )

        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            bridge = CtypesGoBridge(config)
            results = bridge.evaluate_branches([0, 1])
            bridge.close()

        self.assertEqual([result.action_id for result in results], [0, 1])
        self.assertEqual(results[1].rewards.tolist(), [1.0, 0.0, 0.0, 0.0])
        self.assertTrue(results[1].terminated)
        self.assertEqual(results[1].decisions, 3)
        self.assertEqual(results[1].info["round_outcome"]["win_type_name"], "ACTION_TSUMO")

    def test_chongci_config_is_forwarded_to_go_bridge(self) -> None:
        fake_library = FakeGoLibrary()
        config = EnvConfig(
            plane_shape=(1, 1, 1),
            scalar_features=1,
            action_space_size=2,
            bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"),
            match_mode="chongci",
            chongci_starting_score=3000,
            chongci_bust_threshold=-100,
            chongci_max_hands=12,
        )

        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            bridge = CtypesGoBridge(config)
            bridge.close()

        self.assertIsNotNone(fake_library.last_new_config)
        self.assertEqual(fake_library.last_new_config.match_mode, game_pb2.MATCH_MODE_CHONGCI)
        self.assertEqual(fake_library.last_new_config.chongci_config.starting_score, 3000)
        self.assertEqual(fake_library.last_new_config.chongci_config.bust_threshold, -100)
        self.assertEqual(fake_library.last_new_config.chongci_config.max_hands, 12)


def test_envconfig_proto_has_oracle_observation_flag():
    from fh_mahjong_ai.generated.proto import game_pb2
    msg = game_pb2.EnvConfig(oracle_observation=True)
    assert msg.oracle_observation is True
    assert game_pb2.EnvConfig().oracle_observation is False


def test_envconfig_oracle_resolves_plane_shape_and_serializes():
    from fh_mahjong_ai.config import EnvConfig
    # default oracle off -> 39ch, byte-identical default
    assert EnvConfig().oracle_observation is False
    assert EnvConfig().plane_shape == (39, 42, 1)
    # oracle on -> plane_shape auto-resolves to 51ch
    cfg = EnvConfig(oracle_observation=True)
    assert cfg.plane_shape == (51, 42, 1)
    # explicit plane_shape is respected (not overridden)
    cfg2 = EnvConfig(oracle_observation=True, plane_shape=(60, 42, 1))
    assert cfg2.plane_shape == (60, 42, 1)
    # the flag is serialized into the proto EnvConfig message
    msg = GoMahjongBridge.__new__(GoMahjongBridge)
    msg.config = cfg
    built = msg._config_message()
    assert built.oracle_observation is True


def test_envconfig_default_is_39_channels():
    from fh_mahjong_ai.config import EnvConfig
    cfg = EnvConfig()
    assert cfg.plane_shape == (39, 42, 1)
    assert cfg.oracle_observation is False


if __name__ == "__main__":
    unittest.main()


requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


@requires_go_lib
def test_route_probe_reads_the_live_decision_without_changing_it():
    config = EnvConfig(learning_seats=(0, 1, 2, 3), auto_play_heuristics=False)
    with CtypesGoBridge(config) as bridge:
        observation = bridge.reset(seed=71)
        probe = bridge.route_probe(observation.seat)
        discard_ids = [a for a in observation.legal_actions if 5 <= a < 47]
        assert discard_ids, "premise: first decision has discards"
        assert [d["action_id"] for d in probe["discards"]] == discard_ids
        assert probe["seat"] == observation.seat
        assert bridge.route_probe(observation.seat) == probe
        assert bridge.route_probe(0)["seat"] == 0
        assert bridge.route_probe((observation.seat + 1) % 4)["discards"] == []
