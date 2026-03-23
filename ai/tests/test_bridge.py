from __future__ import annotations

import ctypes
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from fh_mahjong_ai import bridge as bridge_module
from fh_mahjong_ai.bridge import BridgeError, CtypesGoBridge, MockMahjongBridge
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
        self.last_reset_seed = None
        self.FHEnvNew = FakeFunction(return_value=7)
        self.FHEnvReset = FakeFunction(callback=self._reset)
        self.FHEnvStep = FakeFunction(callback=self._step)
        self.FHEnvClose = FakeFunction(callback=self._close)
        self.FHGenerateHeuristicTrajectory = FakeFunction(callback=self._trajectory)
        self.FHFree = FakeFunction(callback=self._free)

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
        response = game_pb2.EnvResetResponse(observation=self._observation())
        return self._bytes_result(response.SerializeToString())

    def _step(self, handle, request_ptr, request_len):
        response = game_pb2.EnvStepResponse(observation=self._observation(), rewards=[0.0, 0.0, 0.0, 0.0])
        return self._bytes_result(response.SerializeToString())

    def _close(self, handle) -> None:
        self.closed_handles.append(int(handle))

    def _trajectory(self, request_ptr, request_len):
        response = game_pb2.TrajectoryDataset()
        return self._bytes_result(response.SerializeToString())

    def _free(self, ptr) -> None:
        return None


class CtypesGoBridgeTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
