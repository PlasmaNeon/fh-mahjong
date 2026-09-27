# fh-mahjong-ai

Python RL stack for Fenghua Mahjong. Go owns rules, legality, state transitions, and scoring;
Python owns models, rollout collection, replay storage, checkpoints, training, evaluation, and
policy serving. See [CLAUDE.md](CLAUDE.md) for commands and invariants and
[MODULES.md](MODULES.md) for per-module detail.

## Setup

The project pins uv-managed CPython in `ai/.python-version`. Use uv for every Python command.

```bash
uv sync --project ai --extra dev
uv run --project ai pytest ai/tests
```

Build the Go bridge library (`cmd/rlbridge`) as a c-shared target:

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge   # .so on Linux
```

Set `FH_MAHJONG_BRIDGE_LIB` if the library lives elsewhere. `fh-mj-selfplay-smoke` runs the
package end to end on the mock bridge.

## Training path

1. Generate heuristic data (`fh-mj-generate-data --format npz-shards`) and warm-start with
   behavior cloning (`fh-mj-train-bc`).
2. Train online with self-play PPO: `fh-mj-train-b2b` (event history, privileged critic,
   auxiliary heads) is the current trainer; `fh-mj-train-ppo` and the oracle trainers are the
   earlier stages.
3. Gate with duplicate-seat evaluation (`fh-mj-evaluate --duplicate-seats`) and compare with
   `fh-mj-compare`. Promotion rules are in [CLAUDE.md](CLAUDE.md#promotion-discipline).

MLflow tracking is opt-in (`--mlflow`) and writes to `ai/mlflow.db` / `ai/mlartifacts`:

```bash
uv run --project ai mlflow ui --backend-store-uri sqlite:///$PWD/ai/mlflow.db
```

## Checkpoints

- `ai/checkpoints/best-checkpoints.json` — promotion manifest (training-box paths and gate
  results). `current_chongci` resolves the served champion; `current` resolves the classic-mode
  checkpoint.
- `ai/checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt` — the served champion, baked
  into `Dockerfile.deploy`.
- `ai/checkpoints/anchors/` — training anchors, never served.

Override the binary path with `--checkpoint` or `FH_MAHJONG_AI_CHECKPOINT`.

## Serving

`fh-mj-serve-policy` is a JSON HTTP server (`/act`, `/evaluate`, `/healthz`, `/reload`,
`/warmup`). It returns an `action_id`; the Go caller decodes and validates it against the current
legal actions before mutating game state.

```bash
uv run --project ai fh-mj-serve-policy \
  --checkpoint ai/checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --host 127.0.0.1 --port 8765
```

`go run ./cmd/server` autostarts this server locally for the private-room RL agent. The manifest
holds training-box paths, so set `FH_MAHJONG_AI_CHECKPOINT` to a local file (e.g. the deploy
checkpoint above) or the child exits at load. To route
matchmaking-queue bots through a policy server instead of the heuristic bot:

```bash
AI_BOT_POLICY_URL=http://127.0.0.1:8765/act go run ./cmd/server
```

Before serving a new checkpoint, run `fh-mj-serving-parity` (hard gate) and
`fh-mj-serving-smoke`. The live Go integration test runs against a serving endpoint:

```bash
FH_MAHJONG_REMOTE_POLICY_TEST_URL=http://127.0.0.1:8765/act \
  go test ./internal/api -run TestAdvanceAutomatedSeatsWithLiveRemotePolicy -count=1
```

### Serving from a remote GPU box

Start the server on the box with `--host 0.0.0.0 --device cuda`, then tunnel the port if it is
not directly reachable:

```bash
ssh -fN -L 8765:127.0.0.1:8765 <box>
curl http://127.0.0.1:8765/healthz
```
