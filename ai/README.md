# fh-mahjong-ai

Python RL scaffold for Fenghua Mahjong.

This package is the training-side counterpart to the Go simulator in the repository root:

- Go owns rules, legality, state transitions, and scoring.
- Python owns models, replay buffers, checkpoints, and training loops.

The initial package includes:

- a bridge abstraction for the future Go RL environment
- a mock bridge for local smoke tests
- a PyTorch policy/value network with masked-action support
- replay and storage utilities
- behavior-cloning / offline warm-start trainer helpers

## Intended workflow

1. Replace the mock bridge with a Go-backed bridge.
2. Collect heuristic self-play trajectories.
3. Warm-start the model with behavior cloning.
4. Add online self-play RL on top of the same environment and buffer stack.

## Local smoke run

```bash
cd ai
python3 -m fh_mahjong_ai.scripts.selfplay_smoke
```
