from __future__ import annotations

import unittest

import numpy as np

from fh_mahjong_ai.bridge import BridgeError, MockMahjongBridge
from fh_mahjong_ai.config import EnvConfig
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


if __name__ == "__main__":
    unittest.main()
