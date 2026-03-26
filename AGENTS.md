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
| Auth | JWT + bcrypt |
| Database | PostgreSQL 15, GORM |
| Cache | Redis 7 |
| Frontend | React 19, TypeScript, Vite 7 |
| Styling | TailwindCSS 4 |
| Animation | Framer Motion 12 |
| Client Validation | Go → WASM + protobufjs |

## Module Map

```
fh-mahjong/
├── ai/             Python RL package (training loop, model code, replay buffers, bridge abstraction)
├── bot/            Deterministic heuristic bot policies for empty seats, CLI play, and RL bootstrapping
├── proto/          Protobuf schemas (single source of truth)
├── core/           Game state machine + RuleEngine interface
├── rules/          Fenghua ruleset plugin (scoring, hand eval)
├── models/         GORM database models (User, Match)
├── api/            REST API + WebSocket server
├── cmd/
│   ├── server/     Production HTTP server entry point
│   ├── cli/        CLI debugging tool
│   └── wasm/       WebAssembly build target
└── web/            React frontend application
    └── src/
        ├── contexts/   Socket + Game state providers
        ├── pages/      Route pages (Login, Lobby, Game, Calc)
        ├── hooks/      Custom hooks (WASM loader)
        ├── utils/      Tile utilities
        └── proto/      Auto-generated JS/TS Protobuf bindings
```

## Key Files

| File | Purpose |
|------|---------|
| `proto/game.proto` | Single source of truth for all cross-language data structures |
| `core/game.go` | `Game` struct — state machine driver for a single match |
| `core/rules.go` | `RuleEngine` interface — contract every ruleset plugin must satisfy |
| `rules/fh.go` | `HometownRuleset` — full Fenghua scoring and hand evaluation |
| `bot/heuristic.go` | Deterministic shanten-driven baseline bot used by CLI, empty seats, and RL bootstrapping |
| `ai/src/fh_mahjong_ai/model.py` | Python PyTorch policy/value network scaffold for RL training |
| `official_rules.md` | Raw source for Fenghua rules (canonical human-readable reference) |
| `rules.md` | Synthesized rules + Go implementation design (bridge doc) |
| `technical_design.md` | Full 4-phase system architecture |
| `tasks.md` | Phase-by-phase implementation checklist with completion status |

## Architecture Principles

1. **Plugin Ruleset**: `core.Game` is ruleset-agnostic. Rulesets implement `RuleEngine` in `rules/`.
2. **Protobuf-First**: All game state flows as Protobuf between Go backend, TypeScript frontend, and Python AI.
3. **Double Validation**: Client predicts via WASM; server re-validates every action.
4. **Phase Lifecycle**: INIT → DEAL → PLAYER_TURN → WAIT_DISCARDS → ROUND_END.
5. **WASM for prediction**: Go core compiles to `GOOS=js GOARCH=wasm` for zero-latency client-side action validation.
6. **c-shared for RL**: Same Go core compiles as `c-shared` library for Python training via `ctypes`/`cffi`.

## Naming Conventions & Terminology

### Suit Names (use these in all code comments and docs)
| Name | Chinese | Suffix | Range | Proto Constant |
|------|---------|--------|-------|----------------|
| man | 万子 (Characters) | `m` | 1m–9m | `SUIT_CHARACTERS` |
| pin | 筒子 (Dots) | `p` | 1p–9p | `SUIT_DOTS` |
| sou | 索子 (Bamboo) | `s` | 1s–9s | `SUIT_BAMBOO` |
| jihai | 字牌 (Honors) | `z` | 1z–7z | `SUIT_HONORS` |
| flower | 花牌 (Flowers) | — | 1–8 | `SUIT_FLOWER` |

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

- `Suit`: BAMBOO=1, DOTS=2, CHARACTERS=3, HONORS=4, FLOWER=5 (proto constants — do not rename)
- `Tile`: `{id uint32, suit Suit, value uint32, is_red bool}` — IDs 0-135 for standard tiles, 136-143 for flowers
- `ActionType`: DRAW, DISCARD, CHOW, PONG, KONG, TSUMO, RON, PASS, FLOWER_REVEAL, READY
- `GamePhase`: INIT → DEAL → PLAYER_TURN → WAIT_DISCARDS → ROUND_END
- `GameState`: match_id, phase, active_player, players[4], wall_count, wild_tiles, prevailing_wind, round_result, player_ready
- `PlayerState`: closed_hand, open_melds, discards, seat_wind, flower_melds, kong bonus flags
- `ScoreEntry`: `{pattern_name string, points int32}` — one entry per scoring pattern
- `PlayerPayout`: `{seat uint32, amount int32}` — negative=pays, positive=receives
- `RoundResult`: winner_seat, win_type, discarder_seat, winning_hand, winning_melds, win_tile, breakdown[], total_score, payouts[], is_draw

Note: Proto enum names (CHOW, PONG, KONG) are kept as-is in generated code. Use chii/pon/kan only in comments and documentation.

## Scoring Summary (Fenghua Rules)

- **Minimum to win**: Ron requires ≥4 points total; Tsumo has no minimum
- **Payout**: Tsumo → each of 3 losers pays (S×2); Ron → discarder pays (S×2), other two pay (S×1)
- **Base point** (坐台): Always +1. Tsumo: +1. Common win (朋胡): +1.
- Wild tile scoring: 0 wilds (+1), 1 wild (+1), 2 wilds (+2), 3 normal wilds (+150), 3 flower wilds (+300)
- Full scoring reference: `official_rules.md` and `rules.md`

## Core Development Workflow

1. **Proto first**: If any data structures change, update `proto/game.proto` and regenerate bindings before touching Go code.
   ```bash
   protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
   ```
2. **Interface before implementation**: If new ruleset capabilities are needed, update the `RuleEngine` interface in `core/rules.go` first, then implement in `rules/fh.go`.
3. **Test everything in the rules package**: Hand evaluation logic in `rules/fh.go` must have a corresponding test case in `rules/fh_test.go`.
4. **State machine is ruleset-agnostic**: `core/game.go` must never import `rules/`. All ruleset logic flows through the `RuleEngine` interface.
5. **Run tests before marking done**:
   ```bash
   go test ./...
   ```
6. **Update AGENTS.md**: When modifying code in any directory, update that directory's `AGENTS.md` to reflect the changes (new files, renamed exports, changed architecture, etc.).

## Proto Regeneration

Go bindings:
```bash
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
```

TypeScript/JS bindings (from project root):
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

`--null-semantics` is required so `optional` proto3 fields decode as `null` when unset — important for `drawn_tile_id` (can be `0` = tile 1m).

## Running

```bash
go test ./...                    # Run all Go tests
go run cmd/server/main.go        # Start backend server on :8080
cd web && npm run dev            # Start frontend dev server on :3000
```

Default local development split:
- Frontend app: `http://localhost:3000`
- Calculator page: `http://localhost:3000/calc`
- Example table route: `http://localhost:3000/table/test-room`
- Backend API: `http://localhost:8080/api/v1`

Notes:
- Vite proxies `/api` and WebSocket traffic from `:3000` to the Go backend on `:8080`.
- `GET /api/v1/calc` in a browser will return 404 because the calculator endpoint is `POST`-only.
- For single-service production deploys (for example root `zeabur.json`), build `web/dist` first; the Go server will serve that SPA for non-API routes when the bundle is present.

## Module

`github.com/plasma/fh-mahjong` (Go 1.25, `google.golang.org/protobuf v1.36.11`)
