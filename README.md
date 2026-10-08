# fh-mahjong

A web Mahjong platform for the **Fenghua (奉化), Zhejiang** rules — wild tiles (搭), flowers, kong
bonuses, Independence hands (大大胡), and 35+ scoring patterns — with a reinforcement-learning
agent you can seat at the table.

## Features

- **Fenghua rules engine** — a ruleset-agnostic Go state machine with the Fenghua ruleset as a
  plugin: wilds, flowers, dead wall and haitei, every scoring pattern, classic and Chongci (冲刺,
  bust-out) match modes. Payout liabilities (包) are not implemented.
- **Online play** — public matchmaking, private tables with AI seats, reconnects, and
  server-authoritative legality with per-seat hidden-information redaction.
- **Replays and AI review** — every completed match is saved as a paipu; the replay viewer shows
  the AI's recommendation, per-action payout estimates, and deal-in risk for each decision. You can
  also upload a paipu for private review.
- **Tools** — a scoring calculator and a shanten calculator.
- **RL agent** — PPO self-play on the Go core (compiled as a c-shared library), served to the
  game through a Python policy server. English and Simplified Chinese UI.

## Quick start

```bash
docker-compose up -d             # Postgres
go run ./cmd/server              # backend on :8080
cd web && npm install && npm run dev   # frontend on http://localhost:3000
```

Tests: `go test ./...`, `cd web && npm test`, `uv run --project ai pytest ai/tests`.

### RL agent seat

`go run ./cmd/server` starts the local policy server (`uv run --project ai fh-mj-serve-policy`)
in the background; private rooms show an **RL Agent** seat once it is healthy. Point it at the
deployed checkpoint:

```bash
FH_MAHJONG_AI_CHECKPOINT=ai/checkpoints/deploy/selfplay-deep4-student-iter275-39ch.pt \
  go run ./cmd/server
```

Set `RL_AGENT_AUTOSTART=0` to opt out. For the full containerized stack:

```bash
RL_CHECKPOINT_FILE=deploy/selfplay-deep4-student-iter275-39ch.pt docker compose --profile full up
```

Swap models without restarting anything:

```bash
uv run --project ai fh-mj-reload-policy --status
uv run --project ai fh-mj-reload-policy --checkpoint /path/to/other.pt
```

A failed load keeps the current model serving.

## Project structure

```
proto/      Protobuf schema shared by Go, TypeScript, and Python
internal/   Go packages: engine, rules, api, storage, bot, rl, review, tiles
cmd/        server, play (terminal match), wasm, rlbridge (c-shared), rlpaipu, rlsmoke
web/        React 19 + TypeScript frontend
ai/         Python RL package (training, evaluation, serving)
docs/       Reference documentation
```

## Documentation

- [Architecture](docs/architecture.md) — how the engine, server, bots, and frontend fit together
- [AI player design](docs/ai-player.md) — observation, model, training, serving
- [AI evaluation](docs/ai-evaluation.md) and [AI findings](docs/ai-findings.md) — how strength is
  measured and what has been learned
- [Replay and AI review](docs/replay-review.md)
- [Fenghua rules](docs/rules/official-rules.md) and [their implementation](docs/rules/rules.md)
- [`ai/README.md`](ai/README.md) — working with the Python package
- Per-directory `CLAUDE.md` files — package-level reference

## Status

Playable end to end and deployed on Zeabur, with the RL agent served by a separate policy
service. Not yet built: payout
liabilities, ratings and leaderboards, blob storage for replays (paipu live in Postgres), and
multi-instance matchmaking (the queue is in-process).
