# fh-mahjong

A cross-platform Mahjong game platform implementing **Fenghua (奉化), Zhejiang custom rules** — a regional variant with rich scoring, wild tiles, and 35+ special hand patterns.

## Features
- **Custom Fenghua Rules**: Full implementation of Fenghua Mahjong rules including wild tiles (搭), independence hands (大大胡), and complex payout liabilities.
- **Plugin Ruleset Architecture**: The `engine.Game` state machine is ruleset-agnostic. New rulesets implement the `RuleEngine` interface without touching the game loop.
- **Cross-Platform Web**: React/TypeScript frontend with WebAssembly for zero-latency client-side validation.
- **Match Replays**: Every match serialized to Protobuf binary streams for replay and AI analysis.
- **RL AI Pipeline**: Go core compiles as a C-shared library for high-speed Python/PyTorch self-play training.

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Game engine + server | Go 1.25 (goroutines, Gin, gorilla/websocket) |
| Serialization | Protocol Buffers |
| Frontend | React 19 + TypeScript + Vite, TailwindCSS, Framer Motion |
| Client validation | Go → WebAssembly + protobufjs |
| AI training | Python 3.12 + PyTorch (uv-managed) |
| Database | PostgreSQL (GORM) |

## Project Structure
```
fh-mahjong/
├── proto/          # Protobuf schemas (game.proto) — source of truth for all types
├── internal/       # Go library packages (module-private)
│   ├── engine/     #   Game state machine and RuleEngine interface
│   ├── rules/      #   Fenghua ruleset plugin (+ shanten/)
│   ├── api/        #   REST + WebSocket server
│   ├── storage/    #   GORM database models
│   ├── bot/        #   Heuristic bot policies (+ remote/)
│   ├── rl/         #   RL environment wrapper and action catalog
│   ├── review/     #   Post-game review: paipu → decisions → champion critique
│   └── tiles/      #   Shared tile key/index/clone helpers
├── cmd/            # Entry points: server, cli, wasm, rlbridge, rlpaipu, rlsmoke
├── web/            # React frontend (features/, table/, theme/, …)
├── ai/             # Python RL training pipeline
├── docs/           # Reference docs
│   ├── rules/
│   │   ├── official-rules.md  # Raw Fenghua rule source
│   │   └── rules.md           # Rules + Go implementation design
│   └── rl-papers/  # RL paper reports, study roadmap, implementation takeaways
└── worklog/        # Process record: specs/, plans/, rl-experiment/
```

> Per-directory `CLAUDE.md` files are the authoritative, up-to-date reference for
> each package's architecture.

## Status
**Playable end-to-end.** The core game, backend, and web client are all functional, and a trained RL agent can take a seat.

**Working:**
- **Engine & rules** — Protobuf schemas, ruleset-agnostic game state machine, and the full Fenghua ruleset (wild tiles, flowers, kong bonuses, 35+ patterns, wait-pattern scoring) with DFS/DP hand evaluation.
- **Backend** — Gin REST API with revocable HttpOnly cookie sessions, CSRF/origin protection, account-only private rooms, gorilla WebSocket rooms, replay logging, and multi-round play.
- **Frontend** — React 19 client: lobby and play (`/`, `/play`, `/room/new`, `/room/:roomId`, `/match/:matchId`), accounts (`/login`, `/account`), a replay viewer with post-game review (`/replay`, `/replay/:matchId`), and the `/tools/*` workbenches (scoring calculator, shanten, dev pages). Client-side move validation via the Go → WASM bridge.
- **AI / RL** — Python RL package (`ai/`) with self-play data generation, BC/AWBC/IQL/offline-Q and PPO training, an MLflow-tracked pipeline, the `internal/rl` environment wrapper + 204-action catalog, the `cmd/rlbridge` c-shared bridge, a deterministic heuristic bot, and an HTTP-served RL agent seat with heuristic fallback.

**Partial / future:** blob storage for replays (paipu currently lives in PostgreSQL text columns), Redis-backed matchmaking (only needed if the server ever runs multi-instance; matchmaking is in-memory today), ELO/leaderboards, and broader deployment work.

## Quick Start
```bash
# 1. Start the database container
docker-compose up -d

# 2. Start the Go WebSocket server
go run ./cmd/server

# 3. Start the React frontend (in a separate terminal)
cd web && npm run dev

# Run all tests
go test ./...
cd web && npm test

# Regenerate Go Protobuf bindings after proto changes
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go \
  --go_out=. --go_opt=paths=source_relative proto/game.proto
```

Proto changes also need the TypeScript and Python bindings regenerated — see
[CLAUDE.md](CLAUDE.md#proto-regeneration) for those commands and the mandatory
`--null-semantics` flag. `make dev` runs the backend with an all-hands debug
god-view; never set that flag in a deployed environment.

### Private-room RL agent

The private room offers a trained **RL Agent** seat alongside the heuristic bot.
Running `go run ./cmd/server` autostarts the local policy server
(`uv run --project ai fh-mj-serve-policy`); the option enables itself once the
model is healthy. Set `RL_AGENT_AUTOSTART=0` to opt out.

For the full containerized stack, provide a checkpoint and use the `full`
profile:
```bash
RL_CHECKPOINT_DIR=/abs/path/to/checkpoints RL_CHECKPOINT_FILE=epoch_006.pt \
  docker compose --profile full up
```
The model checkpoint is not in the repo — point `RL_CHECKPOINT_DIR` at a host
directory containing your `.pt` file (see `.env.example`).

**Switch models without restarting.** The policy server hot-swaps its checkpoint
at runtime — no restart of the server or the Go backend. Use the CLI:
```bash
# show the model currently being served
uv run --project ai fh-mj-reload-policy --status

# switch to a different checkpoint
uv run --project ai fh-mj-reload-policy --checkpoint /path/to/other.pt
```
(or `POST /reload {"checkpoint": "/path.pt"}` directly). A failed load — bad path
or weights incompatible with the current model architecture — returns an error
and keeps the current model serving.

## Rules Reference
- [official-rules.md](docs/rules/official-rules.md) — Raw source (Fenghua blog transcription)
- [rules.md](docs/rules/rules.md) — Synthesized scoring reference + Go implementation notes
