"""Env-pool abstraction: lockstep-round stepping of many envs behind one interface.

`GoEnvPool` drives the Go env pool over batched FFI (one call per round, flat
observation buffers). `InProcessEnvPool` loops ordinary bridges in-process and
serves as the test / CPU-exactness path. Pools never self-reset a slot: the
caller owns the seed schedule.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .bridge import BridgeError, FHBytesResult, build_bridge, resolve_bridge_library
from .config import EnvConfig
from .generated.proto import game_pb2


@dataclass(frozen=True)
class PoolCommand:
    slot: int
    action_id: Optional[int] = None
    reset_seed: Optional[int] = None
    # Neither set -> skip (no-op for that slot).


@dataclass(frozen=True)
class SlotMeta:
    slot: int
    seat: int
    terminated: bool
    truncated: bool
    step_rewards: np.ndarray
    has_observation: bool
    error: str = ""


@dataclass(frozen=True)
class PoolStepResult:
    slots: list[SlotMeta]
    planes: np.ndarray        # (rows, C, H, W) float32
    scalars: np.ndarray       # (rows, S) float32
    action_masks: np.ndarray  # (rows, A) int8
    event_histories: list[np.ndarray] = field(default_factory=list)  # per-row uint32, TRUE length
    row_of_slot: dict[int, int] = field(default_factory=dict)


def _empty_result(env_config: EnvConfig, slots: list[SlotMeta]) -> PoolStepResult:
    channels, height, width = env_config.plane_shape
    return PoolStepResult(
        slots=slots,
        planes=np.zeros((0, channels, height, width), dtype=np.float32),
        scalars=np.zeros((0, env_config.scalar_features), dtype=np.float32),
        action_masks=np.zeros((0, env_config.action_space_size), dtype=np.int8),
        event_histories=[],
        row_of_slot={},
    )


class InProcessEnvPool:
    """Loops `slots` ordinary bridges (mock or go) behind the pool interface."""

    def __init__(self, env_config: EnvConfig, slots: int) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        self.env_config = env_config
        self.slots = int(slots)
        self._bridges = [build_bridge(env_config) for _ in range(self.slots)]

    def step(self, commands: Sequence[PoolCommand]) -> PoolStepResult:
        metas: list[SlotMeta] = []
        obs_rows: list[tuple[int, np.ndarray, np.ndarray, np.ndarray, int, np.ndarray]] = []
        for command in sorted(commands, key=lambda c: c.slot):
            slot = int(command.slot)
            if slot >= self.slots:
                raise ValueError(f"slot {slot} out of range (pool has {self.slots})")
            bridge = self._bridges[slot]
            if command.reset_seed is not None:
                observation = bridge.reset(seed=int(command.reset_seed))
                result = bridge.last_reset_result
                rewards = np.asarray(result.rewards if result is not None else [], dtype=np.float32)
                terminated = bool(result.terminated) if result is not None else False
                truncated = bool(result.truncated) if result is not None else False
            elif command.action_id is not None:
                result = bridge.step(int(command.action_id))
                observation = result.observation
                rewards = np.asarray(result.rewards, dtype=np.float32)
                terminated, truncated = bool(result.terminated), bool(result.truncated)
            else:  # skip
                metas.append(SlotMeta(slot, 0, False, False,
                                      np.zeros(0, np.float32), False))
                continue
            has_obs = not (terminated or truncated)
            seat = int(observation.seat) if has_obs else 0
            metas.append(SlotMeta(slot, seat, terminated, truncated, rewards, has_obs))
            if has_obs:
                obs_rows.append((
                    slot,
                    np.asarray(observation.planes, dtype=np.float32),
                    np.asarray(observation.scalars, dtype=np.float32),
                    np.asarray(observation.action_mask, dtype=np.int8),
                    seat,
                    np.asarray(observation.event_history, dtype=np.uint32),
                ))
        if not obs_rows:
            return _empty_result(self.env_config, metas)
        row_of_slot = {slot: i for i, (slot, *_rest) in enumerate(obs_rows)}
        return PoolStepResult(
            slots=metas,
            planes=np.stack([r[1] for r in obs_rows]),
            scalars=np.stack([r[2] for r in obs_rows]),
            action_masks=np.stack([r[3] for r in obs_rows]),
            event_histories=[r[5] for r in obs_rows],
            row_of_slot=row_of_slot,
        )

    def close(self) -> None:
        for bridge in self._bridges:
            close = getattr(bridge, "close", None)
            if callable(close):
                close()
        self._bridges = []


class GoEnvPool:
    """ctypes wrapper over the FHEnvPool* exports (one FFI call per round)."""

    def __init__(self, env_config: EnvConfig, slots: int) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        self.env_config = env_config
        self.slots = int(slots)
        self._handle = 0
        self._library = ctypes.CDLL(str(resolve_bridge_library(env_config)))
        self._configure_signatures()
        request = game_pb2.EnvPoolNewRequest(config=self._config_message(), slots=self.slots)
        self._handle = self._library.FHEnvPoolNew(*self._payload_args(request.SerializeToString()))
        if self._handle == 0:
            raise BridgeError("FHEnvPoolNew returned an invalid handle")

    def step(self, commands: Sequence[PoolCommand]) -> PoolStepResult:
        request = game_pb2.EnvPoolStepRequest()
        for command in commands:
            slot_command = request.commands.add()
            slot_command.slot = int(command.slot)
            if command.reset_seed is not None:
                slot_command.reset_seed = int(command.reset_seed)
            elif command.action_id is not None:
                slot_command.action_id = int(command.action_id)
            else:
                slot_command.skip = True
        raw = self._call_bytes(self._library.FHEnvPoolStep, self._handle,
                               request.SerializeToString())
        response = game_pb2.EnvPoolStepResponse()
        response.ParseFromString(raw)
        return self._decode_response(response)

    def _decode_response(self, response) -> PoolStepResult:
        metas: list[SlotMeta] = []
        live_slots: list[int] = []
        for state in response.slots:
            metas.append(SlotMeta(
                slot=int(state.slot),
                seat=int(state.seat),
                terminated=bool(state.terminated),
                truncated=bool(state.truncated),
                step_rewards=np.asarray(state.step_rewards, dtype=np.float32),
                has_observation=bool(state.has_observation),
                error=str(state.error),
            ))
            if state.has_observation:
                live_slots.append(int(state.slot))
        rows = len(live_slots)
        requested_window = int(self.env_config.event_history_window)
        if rows > 0 and requested_window > 0 and int(response.event_history_window) != requested_window:
            raise BridgeError(
                f"pool returned event_history_window={int(response.event_history_window)} "
                f"but the client requested {requested_window} — the Go bridge library predates "
                "pool event history; rebuild it (go build -buildmode=c-shared ./cmd/rlbridge)"
            )
        if rows == 0:
            return _empty_result(self.env_config, metas)
        channels, height, width = (int(response.plane_channels), int(response.plane_height),
                                   int(response.plane_width))
        planes = np.frombuffer(response.planes, dtype="<f4").reshape(rows, channels, height, width)
        scalars = np.frombuffer(response.scalars, dtype="<f4").reshape(rows, int(response.scalar_count))
        masks = np.frombuffer(response.action_masks, dtype=np.uint8).astype(np.int8, copy=False)
        masks = masks.reshape(rows, int(response.action_space_size))

        event_histories: list[np.ndarray] = []
        window = int(response.event_history_window)
        if window > 0:
            counts = np.frombuffer(response.event_counts, dtype="<u4")
            if counts.size != rows:
                raise BridgeError(f"event_counts has {counts.size} rows, expected {rows}")
            flat = np.frombuffer(response.event_histories, dtype="<u4")
            if flat.size != rows * window:
                raise BridgeError(
                    f"event_histories has {flat.size} uint32s, expected rows*window={rows * window}"
                )
            grid = flat.reshape(rows, window)
            for i in range(rows):
                count = int(counts[i])
                if count > window:
                    raise BridgeError(f"row {i} event count {count} exceeds window {window}")
                event_histories.append(grid[i, :count].copy())
        else:
            event_histories = [np.zeros(0, dtype=np.uint32) for _ in range(rows)]

        return PoolStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            event_histories=event_histories,
            row_of_slot={slot: i for i, slot in enumerate(live_slots)},
        )

    def close(self) -> None:
        if getattr(self, "_handle", 0):
            self._library.FHEnvPoolClose(self._handle)
            self._handle = 0

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # --- plumbing (mirrors CtypesGoBridge conventions in bridge.py) ---

    def _configure_signatures(self) -> None:
        self._library.FHEnvPoolNew.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvPoolNew.restype = ctypes.c_uint64
        self._library.FHEnvPoolStep.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvPoolStep.restype = FHBytesResult
        self._library.FHEnvPoolClose.argtypes = [ctypes.c_uint64]
        self._library.FHEnvPoolClose.restype = None
        self._library.FHFree.argtypes = [ctypes.c_void_p]
        self._library.FHFree.restype = None

    def _config_message(self) -> game_pb2.EnvConfig:
        config = self.env_config
        message = game_pb2.EnvConfig(
            auto_play_heuristics=bool(config.auto_play_heuristics),
            max_decisions=int(config.max_steps_per_episode),
        )
        message.learning_seats.extend(int(seat) for seat in config.learning_seats)
        message.oracle_observation = bool(config.oracle_observation)
        message.event_history_window = int(config.event_history_window)
        if config.match_mode == "chongci":
            message.match_mode = game_pb2.MATCH_MODE_CHONGCI
            message.chongci_config.starting_score = int(config.chongci_starting_score)
            message.chongci_config.bust_threshold = int(config.chongci_bust_threshold)
            message.chongci_config.max_hands = int(config.chongci_max_hands)
        else:
            message.match_mode = game_pb2.MATCH_MODE_CLASSIC
        return message

    def _payload_args(self, payload: bytes):
        buffer = ctypes.create_string_buffer(payload, len(payload) if payload else 1)
        pointer = ctypes.c_void_p(ctypes.addressof(buffer)) if payload else ctypes.c_void_p()
        # Keep the buffer alive for the duration of the call via the tuple.
        self._last_buffer = buffer
        return pointer, len(payload)

    def _call_bytes(self, fn, handle, payload: bytes) -> bytes:
        pointer, length = self._payload_args(payload)
        result = fn(handle, pointer, length)
        try:
            if result.err:
                raise BridgeError(ctypes.string_at(result.err).decode("utf-8"))
            if not result.data or result.len <= 0:
                return b""
            return ctypes.string_at(result.data, result.len)
        finally:
            if result.data:
                self._library.FHFree(result.data)
            if result.err:
                self._library.FHFree(result.err)


def make_selfplay_pool(env_config: EnvConfig, ppo_config, slots: int):
    """Build the all-4 self-play EnvConfig (mirrors collect_selfplay_rollouts)
    and return the right pool implementation for the bridge kind."""
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=ppo_config.max_steps_per_episode,
        match_mode=ppo_config.match_mode,
        oracle_observation=env_config.oracle_observation,
        event_history_window=env_config.event_history_window,
    )
    if cfg.bridge_kind == "go":
        return GoEnvPool(cfg, slots)
    return InProcessEnvPool(cfg, slots)
