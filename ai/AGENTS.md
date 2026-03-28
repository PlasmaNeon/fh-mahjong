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
- **src/fh_mahjong_ai/data.py** — Episode grouping (`split_episodes`) and terminal-reward backfill (`backfill_returns`) utilities for trajectory post-processing.
- **src/fh_mahjong_ai/evaluate.py** — Offline action-agreement scoring and online live-play evaluation against the heuristic baseline.
- **src/fh_mahjong_ai/buffer.py** — Replay buffer with terminal-reward-aware value targets.
- **src/fh_mahjong_ai/storage.py** — Checkpoint and JSONL transition persistence helpers (handles numpy arrays in info dicts).
- **src/fh_mahjong_ai/trainer.py** — Self-play collection and behavior-cloning trainer utilities.
- **src/fh_mahjong_ai/scripts/selfplay_smoke.py** — Mock-bridge smoke runner that exercises the package end to end.
- **src/fh_mahjong_ai/scripts/generate_data.py** — CLI: generate heuristic trajectories → JSONL via the Go bridge (or mock fallback).
- **src/fh_mahjong_ai/scripts/train_bc.py** — CLI: behavior cloning training with logging, checkpointing, and resume support.
- **src/fh_mahjong_ai/scripts/evaluate.py** — CLI: evaluate a checkpoint offline (action agreement) and/or online (live play).
- **src/fh_mahjong_ai/scripts/run_pipeline.py** — CLI: orchestrate generate → train → evaluate in one command.
- **tests/test_bridge.py** — `unittest` coverage for the mock bridge reset/step contract and action-mask validation behavior.
- **tests/test_data.py** — Tests for episode grouping and terminal-reward backfill.
- **tests/test_buffer.py** — Tests for terminal-reward-aware replay buffer sampling.
- **tests/test_generate_data.py** — Tests for heuristic data generation (mock bridge path).
- **tests/test_train_bc.py** — Tests for BC training loop and checkpoint resume.
- **tests/test_evaluate.py** — Tests for offline and online evaluation functions.
- **tests/test_pipeline_e2e.py** — End-to-end pipeline integration test (mock bridge).
- **src/fh_mahjong_ai/generated/proto/game_pb2.py** — Generated Python protobuf bindings shared with the Go RL bridge.

## Architecture Notes

- `EnvConfig` defaults now match the real Go bridge (`39 x 42 x 1` observations, 29 scalars, 204 discrete actions).
- `MockMahjongBridge` remains available for smoke tests, but `bridge_kind="go"` is now the default for real bridge work.
- The Python package stays compatible with Python 3.9 by avoiding `dataclass(slots=True)` in the scaffold types/configs.
- All action selection assumes the fixed 204-action catalog supplied by the Go bridge.
- Heuristic trajectory samples preserve per-step rewards in `rewards` and attach round-outcome targets separately in `terminal_rewards` for warm-start consumers.
- The first implemented training loop is behavior cloning / offline warm-start. Online RL can layer on top of the same environment, replay, and checkpoint utilities.
