# fh-mahjong — Project Context

## Overview
A web-based Mahjong platform implementing **Fenghua (奉化), Zhejiang custom rules** — a regional variant with a complex point-based scoring system, wild tiles (搭), and 35+ special hand patterns. Supports cross-platform PvP, match replays, and a Reinforcement Learning AI pipeline.

## Technology Stack
| Component | Tech |
|-----------|------|
| Core game engine + Backend | **Go** (`core/`, `rules/`) |
| Data serialization | **Protocol Buffers** (`proto/game.proto`) |
| Frontend | React + TypeScript + HTML5 Canvas (planned) |
| AI/RL training | Python + PyTorch (planned) |
| Database | PostgreSQL + Redis (planned) |

## Current Status — Phase 1 Complete, Phase 2 Next
- [x] Protobuf schemas (`proto/game.proto`) — Tile, Meld, PlayerAction, GameState
- [x] `core.RuleEngine` interface (`core/rules.go`)
- [x] `core.Game` state machine (`core/game.go`) — phases Init→Deal→Turn→Interrupt→RoundEnd
- [x] `rules.HometownRuleset` Fenghua implementation (`rules/fh.go`) — DFS/DP backtracking for 35+ patterns
- [x] Unit tests for state machine and ruleset

**Phase 2 (next):** Go WebSocket server, PostgreSQL/Redis schemas, JWT REST API (`/api/v1`).

## Key Files
| File | Purpose |
|------|---------|
| `proto/game.proto` | Single source of truth for all cross-language data structures |
| `core/game.go` | `Game` struct — state machine driver for a single match |
| `core/rules.go` | `RuleEngine` interface — contract every ruleset plugin must satisfy |
| `rules/fh.go` | `HometownRuleset` — full Fenghua scoring and hand evaluation |
| `official_rules.md` | Raw source for Fenghua rules (canonical human-readable reference) |
| `rules.md` | Synthesized rules + Go implementation design (bridge doc) |
| `technical_design.md` | Full system architecture (all four phases) |
| `tasks.md` | Phase-by-phase implementation checklist with completion status |

## Architecture Principles
1. **Plugin ruleset architecture**: `core.Game` is ruleset-agnostic. New rulesets implement `RuleEngine` in `rules/`.
2. **Protobuf-first**: All game state flows as Protobuf between Go backend, TypeScript frontend, and Python AI.
3. **Wasm for prediction**: Go core compiles to `GOOS=js GOARCH=wasm` for zero-latency client-side action validation.
4. **c-shared for RL**: Same Go core compiles as `c-shared` library for Python training via `ctypes`/`cffi`.
5. **Security double-validation**: Client predicts via Wasm; server re-validates every action before mutating state.

## Naming Conventions & Terminology

### Suit Names (use these in all code comments and docs)
| Name | Chinese | Suffix | Range | Proto Constant |
|------|---------|--------|-------|----------------|
| man | 万子 (Characters) | `m` | 1m–9m | `SUIT_CHARACTERS` |
| pin | 筒子 (Dots) | `p` | 1p–9p | `SUIT_DOTS` |
| sou | 索子 (Bamboo) | `s` | 1s–9s | `SUIT_BAMBOO` |
| jihai | 字牌 (Honors) | `z` | 1z–7z | `SUIT_HONORS` |

Jihai values: 1z=East, 2z=South, 3z=West, 4z=North, 5z=Haku(白), 6z=Hatsu(発), 7z=Chun(中)

### Meld Terms
- **chii** (吃): Sequence meld — 3 consecutive tiles of the same suit
- **pon** (碰): Triplet meld — 3 identical tiles
- **kan** (杠): Quad meld — 4 identical tiles; 3 variants: Direct (直杠), Closed (暗杠), Risky (风险杠)

### Other Key Terms
- **Tsumo** (自摸): Win by own drawn tile from wall
- **Ron** (放冲/点炮): Win by claiming another player's discard
- **Wild Tile** (搭): Randomly selected tile type per round; up to 3 copies act as substitutes
- **Tame wild** (还搭): Wild tile used at its natural face value
- **Seat Wind** (位风): Player's wind; East=1, South=2, West=3, North=4
- **Prevailing Wind** (圈风): Round wind; coincides with Seat Wind → Right Wind (正风, +2)
- **Independence** (大大胡/十三不搭): 14 fully disconnected tiles, no melds allowed

### Tile Notation
Write tehai as: `1m2m3m 4p5p6p 7s8s9s 1z1z1z 2z`
NOT as: `C1C2C3 D4D5D6 B7B8B9 H1H1H1 H2` (old notation — do not use)

## Protobuf Schema (proto/game.proto)
- `Suit`: BAMBOO=1, DOTS=2, CHARACTERS=3, HONORS=4 (proto constants — do not rename)
- `Tile`: `{id uint32, suit Suit, value uint32, is_red bool}`
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

## Development Workflow
1. Update `proto/game.proto` first if data structures change
2. Regenerate Go bindings: `protoc --go_out=. --go_opt=paths=source_relative proto/game.proto`
3. Update `core/rules.go` interface if new ruleset methods are needed
4. Implement or update `rules/fh.go` for Fenghua-specific logic
5. Write/update tests in `core/game_test.go` and `rules/fh_test.go`
6. Mark completed items in `tasks.md`

## Running Tests
```bash
go test ./...
```

## Module
`github.com/plasma/fh-mahjong` (Go 1.25, `google.golang.org/protobuf v1.36.11`)
