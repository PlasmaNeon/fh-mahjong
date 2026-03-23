# ai/

> Python reinforcement learning package for Fenghua Mahjong.

## Overview

This directory contains the Python-side RL stack. Go remains the authoritative simulator; Python owns model definition, data loading, checkpointing, and training orchestration. The package now supports both a mock bridge for smoke tests and a real `ctypes` bridge to the Go c-shared library.

## Key Files

- **pyproject.toml** — Python package metadata and dependencies for the RL stack.
- **src/fh_mahjong_ai/config.py** — Dataclass configs for environment, model, training, and self-play.
- **src/fh_mahjong_ai/types.py** — Shared observation, transition, and bridge result types.
- **src/fh_mahjong_ai/bridge.py** — Abstract bridge contract, mock bridge, and `CtypesGoBridge` implementation for the Go RL library.
  - `MockMahjongBridge` retains the last emitted observation so `step()` validates actions against the real current legal-action mask instead of sampling a fresh one.
  - `CtypesGoBridge` owns the Go-side handle lifecycle and supports `close()`, context-manager usage, and best-effort cleanup in `__del__`.
- **src/fh_mahjong_ai/env.py** — Thin environment wrapper around the bridge.
- **src/fh_mahjong_ai/model.py** — PyTorch policy/value network for masked-action Mahjong decisions.
- **src/fh_mahjong_ai/policies.py** — Random and torch-backed policy adapters.
- **src/fh_mahjong_ai/buffer.py** — Replay buffer and tensor conversion helpers.
- **src/fh_mahjong_ai/storage.py** — Checkpoint and JSONL transition persistence helpers.
- **src/fh_mahjong_ai/trainer.py** — Self-play collection and behavior-cloning/offline warm-start trainer utilities.
- **src/fh_mahjong_ai/scripts/selfplay_smoke.py** — Mock-bridge smoke runner that exercises the package end to end.
- **tests/test_bridge.py** — `unittest` coverage for the mock bridge reset/step contract and action-mask validation behavior.
- **src/fh_mahjong_ai/generated/proto/game_pb2.py** — Generated Python protobuf bindings shared with the Go RL bridge.

## Architecture Notes

- `EnvConfig` defaults now match the real Go bridge (`39 x 42 x 1` observations, 29 scalars, 204 discrete actions).
- `MockMahjongBridge` remains available for smoke tests, but `bridge_kind="go"` is now the default for real bridge work.
- The Python package stays compatible with Python 3.9 by avoiding `dataclass(slots=True)` in the scaffold types/configs.
- All action selection assumes the fixed 204-action catalog supplied by the Go bridge.
- Heuristic trajectory samples preserve per-step rewards in `rewards` and attach round-outcome targets separately in `terminal_rewards` for warm-start consumers.
- The first implemented training loop is behavior cloning / offline warm-start. Online RL can layer on top of the same environment, replay, and checkpoint utilities.
