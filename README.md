# fh-mahjong

A cross-platform Mahjong game platform implementing **Fenghua (奉化), Zhejiang custom rules** — a regional variant with rich scoring, wild tiles, and 35+ special hand patterns.

## Features
- **Custom Hometown Rules**: Full implementation of Fenghua Mahjong rules including wild tiles (搭), independence hands (大大胡), and complex payout liabilities.
- **Plugin Ruleset Architecture**: The `core.Game` state machine is ruleset-agnostic. New rulesets implement the `RuleEngine` interface without touching the game loop.
- **Cross-Platform Web**: Planned React/TypeScript frontend with WebAssembly for zero-latency client-side validation.
- **Match Replays**: Every match serialized to Protobuf binary streams for replay and AI analysis.
- **RL AI Pipeline**: Go core compiles as a C-shared library for high-speed Python/PyTorch self-play training.

## Tech Stack
| Layer | Technology |
|-------|-----------|
| Game engine + server | Go (goroutines, WebSockets) |
| Serialization | Protocol Buffers |
| Frontend | React + TypeScript + HTML5 Canvas |
| AI training | Python + PyTorch |
| Database | PostgreSQL + Redis |
| Blob storage | S3 / filesystem |

## Project Structure
```
fh-mahjong/
├── proto/          # Protobuf schemas (game.proto) — source of truth for all types
├── core/           # Game state machine and RuleEngine interface
├── rules/          # Fenghua (hometown) ruleset plugin
├── CLAUDE.md       # Claude Code project context (auto-loaded)
├── official_rules.md  # Raw Fenghua rule source
├── rules.md           # Rules + Go implementation design
├── technical_design.md # Full system architecture
└── tasks.md           # Phase-by-phase implementation checklist
```

## Status
**Phase 1 complete** — Core definitions, Protobuf schemas, game state machine, Fenghua ruleset with DFS/DP hand evaluation, and unit tests all pass.

**Phase 2 in progress** — Go WebSocket server, PostgreSQL/Redis, REST API.

## Quick Start
```bash
# 1. Start database and redis containers
docker-compose up -d

# 2. Start the Go WebSocket server
go run ./cmd/server

# 3. Start the React frontend (in a separate terminal)
cd web && npm run dev

# Run all tests
go test ./...

# Regenerate Protobuf bindings after proto changes
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
```

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

## Rules Reference
- [official_rules.md](official_rules.md) — Raw source (Fenghua blog transcription)
- [rules.md](rules.md) — Synthesized scoring reference + Go implementation notes
- [technical_design.md](technical_design.md) — Full architecture document
