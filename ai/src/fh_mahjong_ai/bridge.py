from __future__ import annotations

import ctypes
import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from .config import EnvConfig
from .generated.proto import game_pb2
from .types import Observation, StepResult, Transition


class BridgeError(RuntimeError):
    """Raised when the environment bridge cannot satisfy a request."""


class MahjongBridge(ABC):
    """Interface implemented by any Go-backed or mock Mahjong environment bridge."""

    def __init__(self, config: EnvConfig) -> None:
        self.config = config
        self.last_reset_result: Optional[StepResult] = None

    @abstractmethod
    def reset(self, seed: Optional[int] = None) -> Observation:
        raise NotImplementedError

    @abstractmethod
    def step(self, action_id: int) -> StepResult:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


@dataclass
class MockState:
    step_index: int = 0
    current_seat: int = 0


class MockMahjongBridge(MahjongBridge):
    """Random-but-deterministic fallback used for local smoke tests."""

    def __init__(self, config: EnvConfig) -> None:
        super().__init__(config)
        self._state = MockState()
        self._rng = np.random.default_rng(config.seed)
        self._current_observation: Optional[Observation] = None

    def reset(self, seed: Optional[int] = None) -> Observation:
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._state = MockState()
        self._current_observation = self._observe()
        self.last_reset_result = StepResult(
            observation=self._current_observation,
            rewards=np.zeros(4, dtype=np.float32),
            terminated=False,
            truncated=False,
            info={"reset": True, "bridge": "mock"},
        )
        return self._current_observation

    def step(self, action_id: int) -> StepResult:
        if self._current_observation is None:
            raise BridgeError("mock bridge must be reset before step()")
        if action_id not in self._current_observation.legal_actions:
            raise BridgeError(
                f"illegal mock action {action_id}; legal={self._current_observation.legal_actions}"
            )

        self._state.step_index += 1
        self._state.current_seat = (self._state.current_seat + 1) % 4

        terminated = self._state.step_index >= self.config.max_steps_per_episode
        rewards = np.zeros(4, dtype=np.float32)
        if terminated:
            rewards = self._rng.normal(loc=0.0, scale=1.0, size=4).astype(np.float32)

        next_observation = self._observe()
        self._current_observation = next_observation
        return StepResult(
            observation=next_observation,
            rewards=rewards,
            terminated=terminated,
            info={"mock_action": action_id, "step_index": self._state.step_index},
        )

    def close(self) -> None:
        return None

    def _observe(self) -> Observation:
        channels, height, width = self.config.plane_shape
        planes = self._rng.random((channels, height, width), dtype=np.float32)
        scalars = self._rng.random((self.config.scalar_features,), dtype=np.float32)
        action_mask = np.zeros((self.config.action_space_size,), dtype=np.int8)

        legal_count = int(self._rng.integers(low=4, high=min(12, self.config.action_space_size)))
        legal_indices = self._rng.choice(self.config.action_space_size, size=legal_count, replace=False)
        action_mask[legal_indices] = 1

        return Observation(
            seat=self._state.current_seat,
            planes=planes,
            scalars=scalars,
            action_mask=action_mask,
            metadata={"step_index": self._state.step_index, "bridge": "mock"},
        )


class FHBytesResult(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("len", ctypes.c_int),
        ("err", ctypes.c_void_p),
    ]


class CtypesGoBridge(MahjongBridge):
    """Go RL bridge loaded from the c-shared library via ctypes."""

    def __init__(self, config: EnvConfig) -> None:
        super().__init__(config)
        self._handle = 0
        self._library = ctypes.CDLL(str(resolve_bridge_library(config)))
        self._configure_signatures()
        self._handle = self._env_new(self._serialize(self._config_message()))
        if self._handle == 0:
            raise BridgeError("FHEnvNew returned an invalid handle")

    def reset(self, seed: Optional[int] = None) -> Observation:
        effective_seed = self.config.seed if seed is None else seed
        request = game_pb2.EnvResetRequest(seed=int(effective_seed), config=self._config_message())
        response = game_pb2.EnvResetResponse()
        response.ParseFromString(self._call_bytes(self._library.FHEnvReset, self._handle, self._serialize(request)))
        observation = self._decode_observation(response.observation)
        self.last_reset_result = StepResult(
            observation=observation,
            rewards=self._decode_rewards(response.rewards),
            terminated=bool(response.terminated),
            truncated=bool(response.truncated),
            info={"reset": True, "bridge": "go"},
        )
        return observation

    def step(self, action_id: int) -> StepResult:
        request = game_pb2.EnvStepRequest(action_id=int(action_id))
        response = game_pb2.EnvStepResponse()
        response.ParseFromString(self._call_bytes(self._library.FHEnvStep, self._handle, self._serialize(request)))
        return StepResult(
            observation=self._decode_observation(response.observation),
            rewards=self._decode_rewards(response.rewards),
            terminated=bool(response.terminated),
            truncated=bool(response.truncated),
            info={},
        )

    def close(self) -> None:
        if getattr(self, "_handle", 0):
            self._library.FHEnvClose(self._handle)
            self._handle = 0

    def __enter__(self) -> "CtypesGoBridge":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def generate_heuristic_trajectories(self, episodes: int, start_seed: int = 1) -> list[Transition]:
        request = game_pb2.TrajectoryRequest(
            episodes=int(episodes),
            start_seed=int(start_seed),
            config=self._config_message(),
        )
        response = game_pb2.TrajectoryDataset()
        response.ParseFromString(self._call_bytes(self._library.FHGenerateHeuristicTrajectory, self._serialize(request)))
        return [self._decode_transition(sample) for sample in response.samples]

    def _configure_signatures(self) -> None:
        self._library.FHEnvNew.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvNew.restype = ctypes.c_uint64

        self._library.FHEnvReset.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvReset.restype = FHBytesResult

        self._library.FHEnvStep.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvStep.restype = FHBytesResult

        self._library.FHEnvClose.argtypes = [ctypes.c_uint64]
        self._library.FHEnvClose.restype = None

        self._library.FHGenerateHeuristicTrajectory.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._library.FHGenerateHeuristicTrajectory.restype = FHBytesResult

        self._library.FHFree.argtypes = [ctypes.c_void_p]
        self._library.FHFree.restype = None

    def _config_message(self) -> game_pb2.EnvConfig:
        message = game_pb2.EnvConfig(
            auto_play_heuristics=bool(self.config.auto_play_heuristics),
            max_decisions=int(self.config.max_steps_per_episode),
        )
        message.learning_seats.extend(int(seat) for seat in self.config.learning_seats)
        return message

    def _serialize(self, message: object) -> bytes:
        if hasattr(message, "SerializeToString"):
            return message.SerializeToString()
        raise BridgeError(f"cannot serialize message of type {type(message)!r}")

    def _call_bytes(self, fn, *args) -> bytes:
        payload = b""
        if args and isinstance(args[-1], (bytes, bytearray)):
            payload = bytes(args[-1])
            args = args[:-1]

        buffer = ctypes.create_string_buffer(payload, len(payload) if payload else 1)
        pointer = ctypes.c_void_p(ctypes.addressof(buffer)) if payload else ctypes.c_void_p()
        result = fn(*args, pointer, len(payload))
        return self._unwrap_bytes_result(result)

    def _unwrap_bytes_result(self, result: FHBytesResult) -> bytes:
        try:
            if result.err:
                message = ctypes.string_at(result.err).decode("utf-8")
                raise BridgeError(message)
            if not result.data or result.len <= 0:
                return b""
            return ctypes.string_at(result.data, result.len)
        finally:
            if result.data:
                self._library.FHFree(result.data)
            if result.err:
                self._library.FHFree(result.err)

    def _decode_observation(self, observation: game_pb2.SeatObservation) -> Observation:
        channels, height, width = self.config.plane_shape
        planes = np.asarray(observation.planes, dtype=np.float32).reshape((channels, height, width))
        scalars = np.asarray(observation.scalars, dtype=np.float32)
        action_mask = np.frombuffer(bytes(observation.action_mask), dtype=np.uint8).astype(np.int8, copy=False)
        if action_mask.size == 0:
            action_mask = np.zeros((self.config.action_space_size,), dtype=np.int8)

        return Observation(
            seat=int(observation.seat),
            planes=planes,
            scalars=scalars,
            action_mask=action_mask,
            metadata={
                "decision_index": int(observation.decision_index),
                "phase": int(observation.phase),
                "active_player": int(observation.active_player),
                "bridge": "go",
            },
        )

    def _decode_rewards(self, rewards: object) -> np.ndarray:
        decoded = np.asarray(rewards, dtype=np.float32)
        if decoded.size == 0:
            return np.zeros(4, dtype=np.float32)
        return decoded

    def _decode_transition(self, sample: game_pb2.TrajectorySample) -> Transition:
        info = {"acting_seat": int(sample.acting_seat), "episode_index": int(sample.episode_index)}
        if sample.terminal_rewards:
            info["terminal_rewards"] = np.asarray(sample.terminal_rewards, dtype=np.float32)
        return Transition(
            observation=self._decode_observation(sample.observation),
            action_id=int(sample.action_id),
            rewards=np.asarray(sample.rewards, dtype=np.float32),
            next_observation=self._decode_observation(sample.next_observation),
            terminated=bool(sample.terminated),
            truncated=bool(sample.truncated),
            info=info,
        )

    def _env_new(self, payload: bytes) -> int:
        buffer = ctypes.create_string_buffer(payload, len(payload) if payload else 1)
        pointer = ctypes.c_void_p(ctypes.addressof(buffer)) if payload else ctypes.c_void_p()
        return int(self._library.FHEnvNew(pointer, len(payload)))


def resolve_bridge_library(config: EnvConfig) -> Path:
    if config.bridge_library_path is not None:
        return config.bridge_library_path

    if env_path := os.getenv("FH_MAHJONG_BRIDGE_LIB"):
        return Path(env_path)

    repo_root = Path(__file__).resolve().parents[3]
    extension = {"darwin": ".dylib", "linux": ".so", "win32": ".dll"}.get(sys.platform, ".so")
    return repo_root / "build" / f"libfh_mahjong_bridge{extension}"


def build_bridge(config: EnvConfig) -> MahjongBridge:
    if config.bridge_kind == "mock":
        return MockMahjongBridge(config)
    if config.bridge_kind == "go":
        return CtypesGoBridge(config)
    raise BridgeError(f"unknown bridge kind: {config.bridge_kind}")
