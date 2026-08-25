# fh-mahjong

> A web-based Mahjong platform implementing Fenghua (奉化) Zhejiang custom rules with wild tiles, 35+ hand patterns, and complex point-based scoring.

## Overview

This project implements a full-stack Mahjong game with a plugin-based ruleset architecture. The Go backend drives the game state machine and scoring engine; the React/TypeScript frontend renders the tabletop UI; Protocol Buffers serialize all game state across languages. The architecture supports future RL AI training via WASM and c-shared compilation targets.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Game Engine | Go 1.25 |
| Serialization | Protocol Buffers (protobuf 1.36.11) |
| HTTP/WS Server | Gin + gorilla/websocket |
| Auth | 30-day opaque cookie sessions + bcrypt + CSRF |
| Database | PostgreSQL 15, GORM |
| Frontend | React 19, TypeScript, Vite 7 |
| Styling | TailwindCSS 4 |
| Animation | Framer Motion 12 |
| Client Validation | Go → WASM + protobufjs |

## Module Map

```
fh-mahjong/
├── ai/             Python RL package (training loop, model code, replay buffers, bridge abstraction)
├── proto/          Protobuf schemas (single source of truth)
├── internal/
│   ├── engine/     Game state machine + RuleEngine interface
│   ├── rules/      Fenghua ruleset plugin (scoring, hand eval)
│   ├── api/        REST API + WebSocket server
│   ├── storage/    GORM database models (User, Match)
│   ├── bot/        Deterministic heuristic bot policies for empty seats, CLI play, and RL bootstrapping
│   │   └── remote/ HTTP client driving an external Python policy server as a bot seat
│   ├── rl/         Deterministic RL environment wrapper, observation encoder, and action catalog
│   ├── review/     Paipu → decision reconstruction → champion policy critique (post-game review)
│   └── tiles/      Shared low-level tile helpers (keying, cloning) used across engine/rules/bot/rl
├── cmd/
│   ├── server/     Production HTTP server entry point
│   ├── cli/        CLI debugging tool
│   ├── wasm/       WebAssembly build target
│   ├── rlbridge/   c-shared bridge entry point for Python RL
│   ├── rlpaipu/    Debug CLI writing replay-viewer-compatible paipu JSON
│   └── rlsmoke/    Paipu-v2 rollout-gate smoke driver against a live server
└── web/            React frontend application
    └── src/
        ├── contexts/   Auth + Socket + Game state providers
        ├── features/   Feature folders owning their routes (auth, lobby, calc, shanten, replay, game, dev)
        ├── table/      Shared tabletop presenter for live play and replay
        ├── theme/      Rainy Mahjong Club design system (tokens, base CSS, primitives)
        ├── i18n/       English + Simplified Chinese resources and locale detection
        ├── hooks/      Custom hooks (WASM loader, stage layout)
        ├── utils/      Tile utilities and the shared tile value-model
        └── proto/      Auto-generated JS/TS Protobuf bindings
├── docs/           Reference documentation (Fenghua rules, RL paper reports, refactoring notes)
└── worklog/        Process record — design specs, implementation plans, runbooks, experiment logs
```

There is no `web/src/pages/` — route pages live inside `web/src/features/*` since the 2026-06-27 reorg.

`docs/` vs `worklog/`: `docs/` describes the product (how the system and the rules work);
`worklog/` records the process (why a change was made and in what order). Process records
moved out of `docs/superpowers/` on 2026-08-21 — see `worklog/CLAUDE.md`.

## Key Files

| File | Purpose |
|------|---------|
| `proto/game.proto` | Single source of truth for all cross-language data structures |
| `internal/engine/game.go` | `Game` struct — state machine driver for a single match |
| `internal/engine/rules.go` | `RuleEngine` interface — contract every ruleset plugin must satisfy |
| `internal/rules/fh.go` | `FenghuaRuleset` — full Fenghua scoring and hand evaluation |
| `internal/bot/heuristic.go` | Deterministic shanten-driven baseline bot used by CLI, empty seats, and RL bootstrapping |
| `internal/rl/env.go` | Deterministic reset/step wrapper that advances the Go engine to the next RL decision point |
| `internal/rl/action.go` | Fixed 204-action catalog and Go action encoder/decoder for RL |
| `cmd/rlbridge/main.go` | c-shared bridge exposing protobuf-based `reset`, `step`, and heuristic trajectory export |
| `ai/src/fh_mahjong_ai/model.py` | Python PyTorch policy/value network scaffold for RL training |
| `docs/rules/official-rules.md` | Raw source for Fenghua rules (canonical human-readable reference) |
| `docs/rules/rules.md` | Synthesized rules + Go implementation design (bridge doc) |

## Architecture Principles

1. **Plugin Ruleset**: `engine.Game` is ruleset-agnostic. Rulesets implement `RuleEngine` in `internal/rules/`. `internal/engine` must never import `internal/rules/`.
2. **Protobuf-First**: All game state flows as Protobuf between Go backend, TypeScript frontend, and Python AI.
3. **Double Validation**: Client predicts via WASM; server re-validates every action.
4. **Phase Lifecycle**: INIT → DEAL → PLAYER_TURN → WAIT_DISCARDS → ROUND_END.
5. **WASM for prediction**: Go core compiles to `GOOS=js GOARCH=wasm` for zero-latency client-side action validation.
6. **c-shared for RL**: Same Go core compiles as `c-shared` library for Python training via `ctypes`/`cffi`.

## Shared Utilities

- `docs/refactoring-notes.md` — shared `tiles` (Go) and `tileModel.ts` (web) modules; where the de-duplicated tile-key/index/clone logic now lives.

## Naming Conventions & Terminology

### Suit Names (use these in all code comments and docs)
| Name | Chinese | Suffix | Range | Proto Constant |
|------|---------|--------|-------|----------------|
| man | 万子 (Characters) | `m` | 1m–9m | `SUIT_MAN` = 3 |
| pin | 筒子 (Dots) | `p` | 1p–9p | `SUIT_PIN` = 2 |
| sou | 索子 (Bamboo) | `s` | 1s–9s | `SUIT_SOU` = 1 |
| jihai | 字牌 (Honors) | `z` | 1z–7z | `SUIT_JIHAI` = 4 |
| flower | 花牌 (Flowers) | — | 1–8 | `SUIT_FLOWER` = 5 |

The proto uses the *Japanese-derived* suit names (`SUIT_MAN`/`SUIT_PIN`/`SUIT_SOU`/`SUIT_JIHAI`), not the English glosses. There is no `SUIT_CHARACTERS`/`SUIT_DOTS`/`SUIT_BAMBOO`/`SUIT_HONORS`.

Jihai values: 1z=East, 2z=South, 3z=West, 4z=North, 5z=Haku(白), 6z=Hatsu(発), 7z=Chun(中)
Flower values: 1=Spring(春), 2=Summer(夏), 3=Autumn(秋), 4=Winter(冬), 5=Plum(梅), 6=Orchid(兰), 7=Chrysanthemum(菊), 8=Bamboo(竹). Each flower is unique (1 copy, not 4).

### Meld Terms
- **chii** (吃): Sequence meld — 3 consecutive tiles of the same suit
- **pon** (碰): Triplet meld — 3 identical tiles
- **kan** (杠): Quad meld — 4 identical tiles; 3 variants: Direct (直杠), Closed (暗杠), Risky (风险杠)

### Other Key Terms
- **Tsumo** (自摸): Win by own drawn tile from wall
- **Ron** (放冲/点炮): Win by claiming another player's discard
- **Wild Tile** (搭): Randomly selected tile indicator per round. 
  - If a standard tile, the other 3 copies act as wilds. 
  - If a flower tile, the other 3 flowers in its group (Seasons 1-4 or Plants 5-8) act as wilds and are kept safely in the hand.
- **Tame wild** (还搭): Wild tile used at its natural face value
- **Wangpai** (王牌): Dead wall. Determined by dice roll (2-12 stacks from the end). Normal draws stop before this zone; only Kong/Flower draws access it.
- **Haitei** (海底): The last drawable tile (under the wild indicator). Player may accept or refuse before drawing. If accepted: Tsumo or Discard only; interrupts limited to Ron. If refused: ryuukyoku.
- **Dice Roll**: Two dice rolled at round start. Sum determines number of wangpai stacks. Wild indicator = top tile of innermost wangpai stack.
- **Seat Wind** (位风): Player's wind; East=1, South=2, West=3, North=4
- **Prevailing Wind** (圈风): Round wind; coincides with Seat Wind → Right Wind (正风, +2)
- **Independence** (大大胡/十三不搭): 14 fully disconnected tiles, no melds allowed

### Tile Notation
Write tehai as: `1m2m3m 4p5p6p 7s8s9s 1z1z1z 2z`
NOT as: `C1C2C3 D4D5D6 B7B8B9 H1H1H1 H2` (old notation — do not use)

## Protobuf Schema (proto/game.proto)

- `Suit`: `SUIT_SOU`=1, `SUIT_PIN`=2, `SUIT_MAN`=3, `SUIT_JIHAI`=4, `SUIT_FLOWER`=5 (proto constants — do not rename)
- `Tile`: `{id uint32, suit Suit, value uint32, is_red bool}` — IDs 0-135 for standard tiles, 136-143 for flowers. **Tile id `0` is a real tile (the first 1s), never a sentinel** — optional tile-id fields must be proto `optional` so unset decodes as null
- `ActionType`: `ACTION_DRAW`=1, `DISCARD`=2, `CHII`=3, `PON`=4, `KAN`=5, `TSUMO`=6, `RON`=7, `PASS`=8, `FLOWER_REVEAL`=9, `READY`=10, `ACCEPT_HAITEI`=11
- `GamePhase`: INIT → DEAL → PLAYER_TURN → WAIT_DISCARDS → ROUND_END, plus the terminal `PHASE_MATCH_END`
- `GameState`: match_id, phase, active_player, players[4], wall_count, wild_tiles, prevailing_wind, round_result, player_ready
- `PlayerState`: closed_hand, open_melds, discards, seat_wind, flower_melds, kong bonus flags
- `ScoreEntry`: `{pattern_name string, points int32, pattern_id string}` — one entry per scoring pattern. Build **only** via `rules.NewScoreEntry(id, points)`; logic and localization key off the stable `pattern_id`, never the display-only `pattern_name`. Never rename an existing `pattern_id` (replays and clients persist them)
- `PlayerPayout`: `{seat uint32, amount int32}` — negative=pays, positive=receives
- `RoundResult`: winner_seat, win_type, discarder_seat, winning_hand, winning_melds, win_tile, breakdown[], total_score, payouts[], is_draw
- RL bridge messages: `EnvConfig`, `SeatObservation`, `EnvResetRequest/Response`, `EnvStepRequest/Response`, `TrajectoryRequest`, `TrajectorySample`, `TrajectoryDataset`

Note: the proto uses `ACTION_CHII`/`ACTION_PON`/`ACTION_KAN` — the same chii/pon/kan terms as the docs. There is no `ACTION_CHOW`/`ACTION_PONG`/`ACTION_KONG`.

## Scoring Summary (Fenghua Rules)

- **Minimum to win**: Ron requires ≥4 points total; Tsumo has no minimum
- **Payout**: Tsumo → each of 3 losers pays (S×2); Ron → discarder pays (S×2), other two pay (S×1)
- **Base point** (坐台): Always +1. Tsumo: +1. Common win (朋胡): +1.
- Wild tile scoring: 0 wilds (+1), 1 wild (+1), 2 wilds (+2), 3 normal wilds (+150), 3 flower wilds (+300)
- Full scoring reference: `docs/rules/official-rules.md` and `docs/rules/rules.md`

## Core Development Workflow

1. **Proto first**: If any data structures change, update `proto/game.proto` and regenerate bindings before touching Go code.
   ```bash
   protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
   ```
2. **Interface before implementation**: If new ruleset capabilities are needed, update the `RuleEngine` interface in `internal/engine/rules.go` first, then implement in `internal/rules/fh.go`.
3. **Test everything in the rules package**: Hand evaluation logic in `internal/rules/fh.go` must have a corresponding test case in `internal/rules/fh_test.go`.
4. **State machine is ruleset-agnostic**: `internal/engine/game.go` must never import `internal/rules/`. All ruleset logic flows through the `RuleEngine` interface.
5. **Run the CI gates before marking done.** `.github/workflows/ci.yml` hard-fails on any of these:
   ```bash
   gofmt -l .        # must print nothing
   go vet ./...
   go test ./...
   cd web && npx tsc && npx vitest run
   ```
6. **Update CLAUDE.md**: When modifying code in any directory, update that directory's `CLAUDE.md` to reflect the changes (new files, renamed exports, changed architecture, etc.).

## Per-directory docs: CLAUDE.md and AGENTS.md

Every directory carries a `CLAUDE.md` (the real file) plus an `AGENTS.md` **symlink**
pointing at it, so Claude Code and Codex both auto-load the same content.

- **Edit `CLAUDE.md`.** Editing `AGENTS.md` also works — it resolves to the same file —
  but write the real name.
- **Never replace an `AGENTS.md` symlink with a regular file.** Two real files drift, and
  the two tools would then read different docs for the same directory.
- New directory ⇒ create `CLAUDE.md`, then `ln -s CLAUDE.md AGENTS.md` beside it.

## Proto Regeneration

Go bindings:
```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
```

TypeScript/JS bindings (from project root):
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

Python bindings:
```bash
mkdir -p ai/src/fh_mahjong_ai/generated
protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
```

`--null-semantics` is required so `optional` proto3 fields decode as `null` when unset — important for `drawn_tile_id` (can be `0` = tile 1m).

## Running

```bash
go test ./...                    # Run all Go tests
make run                         # Start backend server on :8080 (production-equivalent)
make dev                         # Same, but with the all-hands debug god-view
cd web && npm run dev            # Start frontend dev server on :3000
cd web && npm test               # Run frontend tests (vitest)
```

**Use the package form `go run ./cmd/server`, never `go run cmd/server/main.go`.** `cmd/server`
is a multi-file package; the file form omits `policy_autostart.go` and fails to compile with
`undefined: maybeStartPolicyServer`. The `Makefile` targets already use the correct form.

`make dev` sets `MAHJONG_DEV_REVEAL_HANDS=1`, which disables the fail-closed opponent-hand
redaction in `internal/api/room.go`. Never set that flag in a deployed environment.

Python RL package (always via uv, per `docs/CLAUDE.md`):
```bash
uv sync --project ai --extra dev
uv run --project ai <command>
```

Default local development split:
- Frontend app: `http://localhost:3000`
- Calculator page: `http://localhost:3000/calc`
- Example table route: `http://localhost:3000/table/test-room`
- Backend API: `http://localhost:8080/api/v1`

Notes:
- Vite proxies `/api` and WebSocket traffic from `:3000` to the Go backend on `:8080`.
- `GET /api/v1/calc` in a browser will return 404 because the calculator endpoint is `POST`-only.
- For single-service production deploys, build `web/dist` first; `web/embed.go` embeds it and the Go server serves that SPA for non-API routes. Production deploys on Zeabur build via the root `Dockerfile` (there is no `zeabur.json`).

## Module

`github.com/plasma/fh-mahjong` (Go 1.25, `google.golang.org/protobuf v1.36.11`)
