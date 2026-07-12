"""GoSearchPool: ctypes wrapper over the FHSearchPool* FFI exports.

Mirrors `GoEnvPool` (in `envpool.py`) line-for-line: same ctypes signature
config, `_call_bytes` decode helper, `np.frombuffer` observation decode, and
handle lifecycle. The search pool clones a live env's current decision point
into K determinized clones (see `SearchPoolNewRequest` in game.proto) and is
stepped with the same `EnvPoolStepRequest`/`EnvPoolStepResponse` messages as
`GoEnvPool`, with one addition: a slot's `SlotState` may carry a non-terminal
`round_outcome`, meaning the round ended mid-search and the observation is the
next hand's first decision state. `SearchStepResult.round_ended` surfaces that
per slot so callers (MCTS/rollout code) can treat it as a round boundary
rather than a terminal state.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from .bridge import BridgeError, CtypesGoBridge, FHBytesResult
from .envpool import PoolCommand, PoolStepResult, SlotMeta, _empty_result
from .generated.proto import game_pb2

__all__ = ["GoSearchPool", "SearchStepResult", "PoolCommand", "SlotMeta", "PoolStepResult"]


@dataclass(frozen=True)
class SearchStepResult(PoolStepResult):
    round_ended: dict[int, bool] = field(default_factory=dict)


class GoSearchPool:
    """ctypes wrapper over the FHSearchPool* exports (one FFI call per round)."""

    def __init__(self, bridge: CtypesGoBridge, clones: int, seed: int, max_rollout_decisions: int) -> None:
        if clones < 1:
            raise ValueError("clones must be >= 1")
        self.env_config = bridge.config
        self.clones = int(clones)
        self._handle = 0
        self._library = bridge.library
        self._configure_signatures()
        request = game_pb2.SearchPoolNewRequest(
            clones=self.clones,
            seed=int(seed),
            max_rollout_decisions=int(max_rollout_decisions),
        )
        self._handle = self._library.FHSearchPoolNew(
            ctypes.c_uint64(bridge.handle), *self._payload_args(request.SerializeToString())
        )
        if self._handle == 0:
            raise BridgeError("FHSearchPoolNew returned an invalid handle")

    def step(self, commands: Sequence[PoolCommand]) -> SearchStepResult:
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
        raw = self._call_bytes(self._library.FHSearchPoolStep, self._handle,
                               request.SerializeToString())
        response = game_pb2.EnvPoolStepResponse()
        response.ParseFromString(raw)

        metas: list[SlotMeta] = []
        round_ended: dict[int, bool] = {}
        live_slots: list[int] = []
        for state in response.slots:
            slot = int(state.slot)
            metas.append(SlotMeta(
                slot=slot,
                seat=int(state.seat),
                terminated=bool(state.terminated),
                truncated=bool(state.truncated),
                step_rewards=np.asarray(state.step_rewards, dtype=np.float32),
                has_observation=bool(state.has_observation),
                error=str(state.error),
            ))
            round_ended[slot] = bool(state.HasField("round_outcome")) and not bool(state.terminated)
            if state.has_observation:
                live_slots.append(slot)
        rows = len(live_slots)
        if rows == 0:
            empty = _empty_result(self.env_config, metas)
            return SearchStepResult(
                slots=empty.slots, planes=empty.planes, scalars=empty.scalars,
                action_masks=empty.action_masks, row_of_slot=empty.row_of_slot,
                round_ended=round_ended,
            )
        channels, height, width = (int(response.plane_channels), int(response.plane_height),
                                   int(response.plane_width))
        planes = np.frombuffer(response.planes, dtype="<f4").reshape(rows, channels, height, width)
        scalars = np.frombuffer(response.scalars, dtype="<f4").reshape(rows, int(response.scalar_count))
        masks = np.frombuffer(response.action_masks, dtype=np.uint8).astype(np.int8, copy=False)
        masks = masks.reshape(rows, int(response.action_space_size))
        return SearchStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            row_of_slot={slot: i for i, slot in enumerate(live_slots)},
            round_ended=round_ended,
        )

    def close(self) -> None:
        if getattr(self, "_handle", 0):
            self._library.FHSearchPoolClose(self._handle)
            self._handle = 0

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # --- plumbing (mirrors GoEnvPool conventions in envpool.py) ---

    def _configure_signatures(self) -> None:
        self._library.FHSearchPoolNew.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHSearchPoolNew.restype = ctypes.c_uint64
        self._library.FHSearchPoolStep.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHSearchPoolStep.restype = FHBytesResult
        self._library.FHSearchPoolClose.argtypes = [ctypes.c_uint64]
        self._library.FHSearchPoolClose.restype = None
        self._library.FHFree.argtypes = [ctypes.c_void_p]
        self._library.FHFree.restype = None

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
