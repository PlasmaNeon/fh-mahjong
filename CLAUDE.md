# fh-mahjong

> A web Mahjong platform for the Fenghua (奉化) Zhejiang rules — wild tiles, flowers, 35+
> scoring patterns — with a self-play RL agent.

The Go backend runs the game state machine and scoring; the React frontend renders the table;
Protocol Buffers carry all state between Go, TypeScript, and Python. The same Go core builds as a
`c-shared` library that the Python RL stack (`ai/`) trains against.

Start with [`docs/architecture.md`](docs/architecture.md) for how the pieces fit and
[`docs/ai-player.md`](docs/ai-player.md) for the AI. Each directory's `CLAUDE.md` holds
package-level detail.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Game engine, server | Go 1.25, Gin, gorilla/websocket |
| Serialization | Protocol Buffers (`google.golang.org/protobuf` 1.36.11, protobufjs) |
| Auth | 30-day opaque HttpOnly cookie sessions, bcrypt, CSRF tokens |
| Database | PostgreSQL 15 via GORM |
| Frontend | React 19, TypeScript, Vite 7, TailwindCSS 4, Framer Motion 12 |
| AI | Python 3.12, PyTorch, uv |

## Module map

```
fh-mahjong/
├── proto/          Protobuf schema (single source of truth)
├── internal/
│   ├── engine/     Game state machine + RuleEngine interface
│   ├── rules/      Fenghua ruleset plugin (+ shanten/)
│   ├── api/        REST + WebSocket server, rooms, matchmaking, persistence, review API
│   ├── storage/    GORM models and migrations
│   ├── bot/        Heuristic bot, policy interfaces, shadow wrapper (+ remote/ HTTP policy client)
│   ├── rl/         RL environment, observation encoder, 204-action catalog, env/search pools
│   ├── review/     Paipu → decisions → policy report and replay study
│   └── tiles/      Shared tile keys, indices, wild sets, clones
├── cmd/            server, play, wasm, rlbridge, rlpaipu, rlsmoke
├── web/            React frontend (route pages in src/features/*; no src/pages/)
├── ai/             Python RL package: training, evaluation, serving
└── docs/           Reference docs: architecture, AI design/evaluation/findings, rules, papers
```

`worklog/` (plans, runbooks, experiment logs) is local and gitignored. Durable conclusions go
into `docs/`.

Shared helpers (Go `tiles`, web `utils/tileModel.ts`, and the rest) are listed in the owning
package's `CLAUDE.md` — extend them, never re-implement them. Look-alike code that must stay
separate is noted there too.

## Key files

| File | Purpose |
|------|---------|
| `proto/game.proto` | Every cross-language data structure |
| `internal/engine/game.go` | `Game` — the state machine for one match |
| `internal/engine/rule_engine.go` | `RuleEngine` — the contract a ruleset implements |
| `internal/rules/fh.go` | `FenghuaRuleset` — hand evaluation, scoring, legality |
| `internal/bot/heuristic.go` | Deterministic shanten-driven bot (empty seats, `cmd/play`, RL opponents) |
| `internal/rl/env.go`, `action.go`, `observation.go` | RL environment, action catalog, observation encoder |
| `cmd/rlbridge/main.go` | c-shared bridge: env, env pool, search pool, trajectory export |
| `ai/src/fh_mahjong_ai/model.py` | PyTorch policy/value network |
| `docs/rules/official-rules.md` | Canonical human-readable Fenghua rules |
| `docs/rules/rules.md` | Synthesized rules and their Go implementation |

## Architecture invariants

1. **Plugin ruleset.** `internal/engine` never imports `internal/rules`; rules plug in through
   `RuleEngine`.
2. **Protobuf first.** Data-structure changes start in `proto/game.proto`.
3. **Server-authoritative.** The server computes each seat's legal actions
   (`PlayerState.valid_actions`) and re-validates every submitted action. A policy server returns
   an `action_id` that Go decodes against the current legal set. `cmd/wasm` builds the ruleset
   for WebAssembly, but the frontend does not load it.
4. **Phases.** INIT → DEAL → PLAYER_TURN ⇄ WAIT_DISCARDS → ROUND_END, plus terminal MATCH_END.
5. **Hidden information.** Broadcasts are redacted per seat by default; the deployed AI sees
   only public information and its own hand.

## Terminology

### Suits

| Name | Chinese | Suffix | Range | Proto constant |
|------|---------|--------|-------|----------------|
| man | 万子 (Characters) | `m` | 1m–9m | `SUIT_MAN` = 3 |
| pin | 筒子 (Dots) | `p` | 1p–9p | `SUIT_PIN` = 2 |
| sou | 索子 (Bamboo) | `s` | 1s–9s | `SUIT_SOU` = 1 |
| jihai | 字牌 (Honors) | `z` | 1z–7z | `SUIT_JIHAI` = 4 |
| flower | 花牌 (Flowers) | — | 1–8 | `SUIT_FLOWER` = 5 |

The proto uses these Japanese-derived names; there is no `SUIT_CHARACTERS`/`SUIT_DOTS`/
`SUIT_BAMBOO`/`SUIT_HONORS`.

Jihai: 1z East, 2z South, 3z West, 4z North, 5z Haku (白), 6z Hatsu (発), 7z Chun (中).
Flowers: 1 Spring (春), 2 Summer (夏), 3 Autumn (秋), 4 Winter (冬), 5 Plum (梅), 6 Orchid (兰),
7 Chrysanthemum (菊), 8 Bamboo (竹); one copy each.

### Melds and play
- **chii** (吃) — run of 3 in one suit; **pon** (碰) — triplet; **kan** (杠) — quad: direct (直杠),
  closed (暗杠), or risky/upgraded (风险杠). The proto uses `ACTION_CHII`/`ACTION_PON`/`ACTION_KAN`.
- **Tsumo** (自摸) — win on your own draw. **Ron** (放冲/点炮) — win on another player's discard.
- **Wild tile** (搭) — chosen per round by an indicator. A standard indicator makes the other 3
  copies of that face wild; a flower indicator makes the other 3 flowers of its group (1–4 or
  5–8) wild, and those stay in the hand. Wilds are jokers only in the concealed hand.
- **Tame wild** (还搭) — a wild used at face value.
- **Wangpai** (王牌) — the dead wall: 2–12 stacks from the end by dice sum. Only kan and flower
  replacement draws use it. The wild indicator is the top tile of its innermost stack.
- **Haitei** (海底) — the last drawable tile. The player may accept (then only tsumo or discard;
  others may only ron) or refuse (the hand is drawn).
- **Seat wind** (位风) East=1…North=4. **Prevailing wind** (圈风) is always East; a pung of the
  matching wind is Right Wind (正风, +2).
- **Independence** (大大胡/十三不搭) — 14 mutually disconnected tiles, no melds.
- **Chongci** (冲刺) — the bust-out match mode (start 2000, bust at 0, 50-hand cap).

### Notation
Write hands as `1m2m3m 4p5p6p 7s8s9s 1z1z1z 2z`, never the old `C1C2C3 D4D5D6 …`.

## Protobuf essentials

- `Tile {id, suit, value, is_red}`: ids 0–135 standard, 136–143 flowers. **Tile id `0` is a real
  tile (the first 1s), never a sentinel.** Optional tile-id fields must be proto `optional` so
  unset decodes as null.
- `ScoreEntry {pattern_name, points, pattern_id}`: build only with
  `rules.NewScoreEntry(id, points)`. Logic and localization key off `pattern_id`; never rename
  one (replays and clients persist them).
- `PlayerPayout {seat, amount}`: negative pays, positive receives.

## Scoring summary

- Ron needs ≥ 4 points; tsumo has no minimum.
- Payout: tsumo → each loser pays S×2; ron → discarder pays S×2, the other two S×1.
- Always +1 base (坐台); tsumo +1; Common Win (朋胡) +1.
- Wilds: 0 → +1, 1 → +1, 2 → +2, three normal wilds +150, three flower wilds +300.
- Payout liabilities (包) are not implemented.
- Full reference: `docs/rules/official-rules.md`, `docs/rules/rules.md`.

## Development workflow

1. **Proto first.** Change `proto/game.proto`, then regenerate Go, TypeScript, and Python
   bindings (commands below) before touching code.
2. **Interface before implementation.** New ruleset capabilities go into `RuleEngine` first,
   then `internal/rules/fh.go`.
3. **Test the rules.** Hand-evaluation logic in `internal/rules/fh.go` gets a case in
   `internal/rules/fh_test.go`.
4. **Run the CI gates before calling work done** (`.github/workflows/ci.yml` fails on any):
   ```bash
   gofmt -l .        # must print nothing
   go vet ./...
   go test ./...
   cd web && npx tsc && npx vitest run
   ```
   CI does not run Python; for `ai/` changes run `uv run --project ai pytest ai/tests`.
5. **Keep docs current.** A change in a directory updates that directory's `CLAUDE.md`; a
   design-level change updates the matching file in `docs/`.
6. **Refactor safely.**
   - Split a file in two commits — a pure rename, then the extraction — so `git log --follow`
     pairs both halves; prove the move is pure by reassembling the bodies and diffing.
   - Gate engine-touching Go changes on a seeded-paipu differential: `cmd/rlpaipu` over fixed
     seeds must stay byte-identical.
   - Gate model or serving changes on `fh-mj-serving-parity --in-process` against the committed
     champion.
   - Do word-boundary renames in Python, not BSD `sed` (no `\b`; it silently matches nothing).

## Per-directory docs: CLAUDE.md and AGENTS.md

Source directories carry a `CLAUDE.md` (the real file) and an `AGENTS.md` symlink to it, so
Claude Code and Codex read the same content.

- Edit `CLAUDE.md`.
- Never replace an `AGENTS.md` symlink with a regular file; the two would drift.
- New directory ⇒ create `CLAUDE.md`, then `ln -s CLAUDE.md AGENTS.md` beside it.

## Proto regeneration

Go:
```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
```

TypeScript (from the repo root):
```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```
`--null-semantics` is required so unset `optional` fields decode as `null` (e.g. `drawn_tile_id`,
where `0` is a real tile).

Python (needs a protoc that emits protobuf 6.x gencode; see `proto/CLAUDE.md`):
```bash
protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
```

## Running

```bash
docker-compose up -d             # Postgres on localhost:5433
make run                         # backend on :8080, opponent hands redacted (production-equivalent)
make dev                         # same, with the all-hands debug god-view
cd web && npm run dev            # frontend on :3000 (proxies /api and WebSocket to :8080)
go test ./...
cd web && npm test
```

- Use the package form `go run ./cmd/server`, never `go run cmd/server/main.go`: the file form
  omits `policy_autostart.go` and fails with `undefined: maybeStartPolicyServer`.
- `make dev` sets `MAHJONG_DEV_REVEAL_HANDS=1`, which disables opponent-hand redaction. Never set
  it in a deployed environment.
- Python is always run through uv: `uv sync --project ai --extra dev`, then
  `uv run --project ai <command>`.
- `POST /api/v1/tools/calc` is POST-only; a browser `GET` returns 404.
- Pages: app `http://localhost:3000`, calculator `/tools/calc`, private room `/room/new`, API
  `http://localhost:8080/api/v1`.
- Production builds through the root `Dockerfile`: `web/dist` is embedded (`web/embed.go`) and
  the Go server serves the SPA for non-API routes. Zeabur deploys from it; there is no
  `zeabur.json`.

## Module

`github.com/plasma/fh-mahjong` (Go 1.25)
