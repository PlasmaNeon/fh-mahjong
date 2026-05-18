# fh-mahjong-ai

Python RL training stack for Fenghua Mahjong.

This package is the training-side counterpart to the Go simulator in the repository root:

- Go owns rules, legality, state transitions, and scoring.
- Python owns models, replay buffers, checkpoints, and training loops.

The package includes:

- a real `ctypes` bridge for the Go c-shared RL environment
- a mock bridge for local smoke tests when the shared library is unavailable
- a PyTorch policy/value network with masked-action support
- MLflow tracking for training and inference/evaluation runs
- replay and storage utilities
- behavior-cloning / offline warm-start trainer helpers
- generated protobuf bindings shared with the Go bridge

## Intended workflow

1. Build the Go bridge library (`cmd/rlbridge`) as a c-shared target.
2. Collect heuristic self-play trajectories through `CtypesGoBridge.generate_heuristic_trajectories(...)`.
3. Warm-start the model with behavior cloning and inspect the JSON training report.
4. Add online self-play RL on top of the same environment and buffer stack.

## Bridge build

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
```

Set `FH_MAHJONG_BRIDGE_LIB` if the shared library lives somewhere else.

## Environment management

The project pins uv-managed CPython in `ai/.python-version`.

```bash
uv sync --project ai --extra dev
uv run --project ai pytest ai/tests
```

Use uv for Python dependencies and commands in this repo. Avoid non-uv package or environment commands.

## MLflow tracking

Training and inference/evaluation scripts log to local MLflow tracking storage under `ai/mlflow.db` with artifacts in `ai/mlartifacts`.

```bash
uv run --project ai mlflow ui --backend-store-uri sqlite:///$PWD/ai/mlflow.db
```

## Local smoke run

```bash
uv run --project ai fh-mj-selfplay-smoke
```

## Behavior cloning

Generate larger datasets directly as NumPy shards so training can skip the temporary JSONL conversion step:

```bash
uv run --project ai fh-mj-generate-data \
  --episodes 50000 \
  --start-seed 1 \
  --output /tmp/fh-mahjong-runs/heuristic-50000-npz \
  --format npz-shards \
  --chunk-size 1000 \
  --shard-size 50000
```

```bash
uv run --project ai fh-mj-train-bc \
  --data /tmp/fh-mahjong-runs/heuristic-50000-npz \
  --checkpoint-dir /private/tmp/fh-mahjong-rl-step12/checkpoints/bc \
  --report-output /private/tmp/fh-mahjong-rl-step12/reports/bc_training.json \
  --mlflow \
  --epochs 3 \
  --batch-size 64
```

The report records train/validation transition counts, per-epoch losses, exact action agreement, top-3 action agreement, and action-family agreement.

## Reward-trained best checkpoint

Tracked metadata for the current reward-trained best checkpoint lives in:

```bash
ai/checkpoints/best-checkpoints.json
```

The manifest records remote checkpoint paths, duplicate-evaluation metrics, and the BC fallback. It intentionally does not track `.pt` checkpoint binaries.

On the WSL training machine, the current reward-trained best is:

```bash
/root/fh-mahjong-runs/lookahead-bc-50k-20260517-000302/checkpoints/iql_sweep_cql010_bc6_pol010_lr5e6/epoch_002.pt
```

Use `FH_MAHJONG_AI_CHECKPOINT` or `--checkpoint` to override the binary path on another machine.

## Inference/evaluation tracking

```bash
uv run --project ai fh-mj-evaluate \
  --checkpoint /private/tmp/fh-mahjong-rl-step12/checkpoints/bc/epoch_001.pt \
  --data /private/tmp/fh-mahjong-rl-step12/heuristic-50.jsonl \
  --report-output /private/tmp/fh-mahjong-rl-step12/reports/eval.json \
  --mlflow
```

## Serving smoke

Before wiring a checkpoint into a live table, run it through the bridge path. The model chooses from the visible observation/action mask, then the Go bridge validates the returned `action_id`.

```bash
uv run --project ai fh-mj-serving-smoke \
  --checkpoint /root/fh-mahjong-runs/lookahead-bc-50k-20260517-000302/checkpoints/iql_sweep_cql010_bc6_pol010_lr5e6/epoch_002.pt \
  --bridge-kind go \
  --bridge-lib build/libfh_mahjong_bridge.so \
  --episodes 20 \
  --device cuda
```

For a lightweight JSON inference boundary:

```bash
uv run --project ai fh-mj-serve-policy \
  --checkpoint /root/fh-mahjong-runs/lookahead-bc-50k-20260517-000302/checkpoints/iql_sweep_cql010_bc6_pol010_lr5e6/epoch_002.pt \
  --host 127.0.0.1 \
  --port 8765
```

`POST /act` returns an `action_id`. The Go caller must still decode and validate that action against current legal actions before mutating game state.
