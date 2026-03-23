# fh-mahjong-ai

Python RL training stack for Fenghua Mahjong.

This package is the training-side counterpart to the Go simulator in the repository root:

- Go owns rules, legality, state transitions, and scoring.
- Python owns models, replay buffers, checkpoints, and training loops.

The package includes:

- a real `ctypes` bridge for the Go c-shared RL environment
- a mock bridge for local smoke tests when the shared library is unavailable
- a PyTorch policy/value network with masked-action support
- replay and storage utilities
- behavior-cloning / offline warm-start trainer helpers
- generated protobuf bindings shared with the Go bridge

## Intended workflow

1. Build the Go bridge library (`cmd/rlbridge`) as a c-shared target.
2. Collect heuristic self-play trajectories through `CtypesGoBridge.generate_heuristic_trajectories(...)`.
3. Warm-start the model with behavior cloning.
4. Add online self-play RL on top of the same environment and buffer stack.

## Bridge build

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
```

Set `FH_MAHJONG_BRIDGE_LIB` if the shared library lives somewhere else.

## Local smoke run

```bash
cd ai
python3 -m fh_mahjong_ai.scripts.selfplay_smoke
```
