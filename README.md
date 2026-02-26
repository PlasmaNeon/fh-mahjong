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
# Run all tests
go test ./...

# Regenerate Protobuf bindings after proto changes
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
```

## Rules Reference
- [official_rules.md](official_rules.md) — Raw source (Fenghua blog transcription)
- [rules.md](rules.md) — Synthesized scoring reference + Go implementation notes
- [technical_design.md](technical_design.md) — Full architecture document
