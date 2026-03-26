# ai/

> Python reinforcement learning package for Fenghua Mahjong.

## Overview

This directory contains the Python-side RL stack. Go remains the authoritative simulator; Python owns model definition, data loading, checkpointing, and training orchestration. The package is structured so it can start with a mock bridge for smoke tests and later swap in a real Go-backed environment bridge without changing trainer code.

## Key Files

- **pyproject.toml** — Python package metadata and dependencies for the RL stack.
- **src/fh_mahjong_ai/config.py** — Dataclass configs for environment, model, training, and self-play.
- **src/fh_mahjong_ai/types.py** — Shared observation, transition, and bridge result types.
- **src/fh_mahjong_ai/bridge.py** — Abstract bridge contract plus a mock implementation for smoke tests before the Go RL bridge exists.
  - `MockMahjongBridge` now retains the last emitted observation so `step()` validates actions against the real current legal-action mask instead of sampling a fresh one.
- **src/fh_mahjong_ai/env.py** — Thin environment wrapper around the bridge.
- **src/fh_mahjong_ai/model.py** — PyTorch policy/value network for masked-action Mahjong decisions.
- **src/fh_mahjong_ai/policies.py** — Random and torch-backed policy adapters.
- **src/fh_mahjong_ai/buffer.py** — Replay buffer and tensor conversion helpers.
- **src/fh_mahjong_ai/storage.py** — Checkpoint and JSONL transition persistence helpers.
- **src/fh_mahjong_ai/trainer.py** — Self-play collection and behavior-cloning/offline warm-start trainer utilities.
- **src/fh_mahjong_ai/scripts/selfplay_smoke.py** — Mock-bridge smoke runner that exercises the package end to end.
- **tests/test_bridge.py** — `unittest` coverage for the mock bridge reset/step contract and action-mask validation behavior.

## Architecture Notes

- The real Go RL bridge is intentionally not implemented here yet; `MockMahjongBridge` exists so model/trainer code can be developed and tested independently.
- The Python package stays compatible with Python 3.9 by avoiding `dataclass(slots=True)` in the scaffold types/configs.
- All action selection assumes a fixed discrete action space with a legal-action mask supplied by the Go bridge.
- The first implemented training loop is behavior cloning / offline warm-start. Online RL can layer on top of the same environment, replay, and checkpoint utilities.
