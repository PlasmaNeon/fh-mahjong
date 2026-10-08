# fh-mahjong-ai

The Python RL stack for Fenghua Mahjong. Go owns rules, legality, state transitions, and scoring;
Python owns models, rollout collection, training, evaluation, and policy serving.

- Design: [`../docs/ai-player.md`](../docs/ai-player.md)
- Measurement and promotion: [`../docs/ai-evaluation.md`](../docs/ai-evaluation.md)
- Results so far: [`../docs/ai-findings.md`](../docs/ai-findings.md)
- Commands and invariants: [`CLAUDE.md`](CLAUDE.md); per-module reference: [`MODULES.md`](MODULES.md)

## Setup

uv manages the interpreter (`ai/.python-version`, CPython 3.12). Use uv for every Python command.

```bash
uv sync --project ai --extra dev
uv run --project ai pytest ai/tests
```

Build the Go bridge library:

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge   # .so on Linux
```

Set `FH_MAHJONG_BRIDGE_LIB` if it lives elsewhere. `fh-mj-selfplay-smoke` runs the package end to
end on the mock bridge.

## Training path

1. Heuristic data: `fh-mj-generate-data --format npz-shards`.
2. Behavior cloning: `fh-mj-train-bc`.
3. Self-play PPO: `fh-mj-train-b2b` (event history, privileged critic, auxiliary heads).
4. Gate: `fh-mj-evaluate --duplicate-seats`, then `fh-mj-compare`.

MLflow is opt-in (`--mlflow`) and writes to `ai/mlflow.db` and `ai/mlartifacts`:

```bash
uv run --project ai mlflow ui --backend-store-uri sqlite:///$PWD/ai/mlflow.db
```

## Checkpoints

- `checkpoints/best-checkpoints.json` — the manifest. `current_chongci_reward_trained_best` is the
  served champion; `gate_qualified_research_champion` the strongest checkpoint committed to the
  repo. Paths in it are training-box paths.
- `checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt` — the served checkpoint, baked into
  `Dockerfile.deploy`. Replace it and the Dockerfile's `--checkpoint` in the same PR.
- `checkpoints/anchors/b2b-anchor075-restart-iter075.pt` — the research champion, used as a
  training anchor; not served.

## Serving

`fh-mj-serve-policy` is a JSON HTTP server (`/act`, `/evaluate`, `/healthz`, `/reload`,
`/warmup`). It returns an `action_id`; the Go caller validates it against the legal actions.

```bash
uv run --project ai fh-mj-serve-policy \
  --checkpoint ai/checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --host 127.0.0.1 --port 8765
```

- `go run ./cmd/server` autostarts it for the private-room RL seat. Set `FH_MAHJONG_AI_CHECKPOINT`
  to a local file, because the manifest holds training-box paths.
- Serve greedy (no `--sample-*` flags). Add `--symmetry-average suits` to serve the suit-averaged
  policy.
- `/evaluate` (post-game review) is disabled unless `--evaluate-token` or `FH_MJ_EVALUATE_TOKEN`
  is set; the backend sends the same value as `POLICY_SERVER_TOKEN`.
- Route public-queue bots through the server with `AI_BOT_POLICY_URL=http://127.0.0.1:8765/act`.

Before serving a new checkpoint run `fh-mj-serving-parity` (hard gate) and `fh-mj-serving-smoke`.
The live Go integration test:

```bash
FH_MAHJONG_REMOTE_POLICY_TEST_URL=http://127.0.0.1:8765/act \
  go test ./internal/api -run TestAdvanceAutomatedSeatsWithLiveRemotePolicy -count=1
```

To serve from the GPU box, start it with `--host 0.0.0.0 --device cuda` and tunnel the port:

```bash
ssh -fN -L 8765:127.0.0.1:8765 <box>
curl http://127.0.0.1:8765/healthz
```
