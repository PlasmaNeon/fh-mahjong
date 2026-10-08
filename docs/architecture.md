# Architecture

How the pieces of fh-mahjong fit together. Per-package detail lives in each directory's
`CLAUDE.md`; the rules themselves are in [`rules/rules.md`](rules/rules.md); the AI is in
[`ai-player.md`](ai-player.md).

## System map

```
 Browser (React, web/)                         Python (ai/)
   │  REST /api/v1/*  (cookie + CSRF)            fh-mj-serve-policy  ◄── checkpoints
   │  WS   /api/v1/ws (binary GameState)            ▲ /act /evaluate /healthz /warmup /reload
   ▼                                                │ JSON
 Go server (cmd/server)                             │
   internal/api ── Hub, Matchmaker, Room ───────────┤ internal/bot/remote (HTTPPolicy)
        │            │                              │
        │            └─ automated seats ── internal/bot (heuristic, shadow)
        ▼
   internal/engine.Game ◄── RuleEngine ── internal/rules (Fenghua)
        │                                   └─ rules/shanten
        ├─ PaipuRecorder ──► internal/storage (Postgres via GORM)
        └─ PublicEvents ──► internal/rl (observation, action catalog)
                                 ▲
   cmd/rlbridge (c-shared) ──────┘  ◄── ctypes ── ai/ training, evaluation
```

Protocol Buffers (`proto/game.proto`) define every cross-language structure: game state, actions,
results, and the RL bridge messages. Go, TypeScript (`web/src/proto/`) and Python
(`ai/src/fh_mahjong_ai/generated/`) bindings are generated from it.

## Dependency rules

| Rule | Why |
|---|---|
| `internal/engine` never imports `internal/rules` | The state machine is ruleset-agnostic; rules plug in through `engine.RuleEngine`. |
| `internal/tiles` imports only `proto` | Every package can use it without import cycles. `engine` does not use it. |
| `internal/rl` wraps `engine.Game`; it never re-implements rules | One legality and transition authority. |
| `internal/bot/remote` is separate from `internal/bot` | `rl` imports `bot`; remote policies need `rl`'s encoders. |
| Python returns an `action_id`; Go decodes it against the current legal set | The model is never a second rules implementation. |

## Game engine (`internal/engine`)

`engine.Game` owns one match as a `*pb.GameState` and is the only thing that mutates it.
Callers drive it through `ProcessPlayerAction(seat, action)` and `ResolveInterrupts()`.

**Phases.** `PHASE_INIT → PHASE_DEAL → PHASE_PLAYER_TURN ⇄ PHASE_WAIT_DISCARDS → PHASE_ROUND_END`,
then either the next round or the terminal `PHASE_MATCH_END`.

**Wall.** 144 tiles (136 suited/honor + 8 unique flowers), shuffled by an MT19937 that reproduces
Tenhou's shuffle exactly (`mt19937.go`, fixture in `testdata/`). Two dice pick the dead-wall
(wangpai) size and the wild indicator. Normal draws stop at the dead wall; kan and flower
replacement draws come from the back. A replacement draw that crosses into the live wall marks
the index consumed so the front draw skips it.

**Turn flow.**
1. The active seat draws. Non-wild flowers auto-reveal and draw a replacement.
2. The seat discards, declares a kan, or wins by tsumo. Legal actions come from
   `RuleEngine.GetValidActions` and ship in `PlayerState.valid_actions`.
3. A discard opens `PHASE_WAIT_DISCARDS`. Each other seat with a legal call
   (`GetValidInterrupts`) responds or passes. The window resolves once every eligible seat has
   responded or the room's timer fires. Priority: ron > kan > pon > chii, ties by ascending seat.
   The room arms that timer at 1 hour (`armInterruptTimer`, disabled for UI testing), so in
   practice a window waits for every response.
4. The last drawable tile (haitei) is offered with accept/refuse. Refusing ends the hand drawn.

**Match modes.**
- **Classic** — one hand at a time, random dealer each hand, no terminal state. Private tables
  cap it at one hand so it reaches `PHASE_MATCH_END` and persists.
- **Chongci (冲刺)** — a bust-out match: everyone starts at a configured stack (default 2000), the
  hand winner deals next (the dealer repeats on a draw), and the match ends when a seat drops to the
  bust threshold (default 0) or the hand cap (default 50) is reached. Private tables default to
  Chongci; the public queue `chongci-fh` uses the defaults.

The prevailing wind (圈风) is always East.

**Side channels.**
- `PublicEvents()` — an always-on per-round log of public events (draw, discard, calls, kans,
  flowers). The RL encoder renders it per observer; draw faces of other seats are masked at
  encode time.
- `Recorder` (`PaipuRecorder`) — optional paipu capture at the same call sites.
- `CloneForBranch()` and `RedealUnseen()` — isolated copies for RL what-if rollouts and search;
  a redeal reshuffles everything the acting seat cannot see and recomputes interrupt eligibility.

## Rules (`internal/rules`)

`FenghuaRuleset` implements `RuleEngine`: wall composition, legal actions and interrupts,
interrupt priority, hand evaluation, and payouts.

- Hand evaluation scores three exclusive routes — Independence (大大胡/十三不搭), Seven Pairs, and
  Standard (4 melds + pair) — and keeps the best. Shapes need
  `len(concealed) + 3·len(openMelds) == 14`.
- Wilds (搭) are jokers only in the concealed hand. In discards, calls, and open melds they are
  face-value tiles.
- Ron needs ≥ 4 points; tsumo has no minimum. Tsumo: each loser pays S×2. Ron: the discarder pays
  S×2 and the other two pay S×1.
- Every score line is a `pb.ScoreEntry` built with `rules.NewScoreEntry(id, points)`. Logic and
  localization key off the stable `pattern_id`; never rename one.
- `rules/shanten` computes route-by-route shanten, useful tiles, and discard options with wild
  support. It feeds the shanten tool, the heuristic bot, and the RL observation.

Payout liabilities (包) are not implemented.

## Server (`internal/api`, `cmd/server`)

**Request flow.** Client → WebSocket → `Room.ActionQueue` → `engine.Game.ProcessPlayerAction` →
`BroadcastState`. Each `Room` runs one goroutine, so game state needs no lock. The `Hub` maps
users to rooms.

**Matchmaking.** `Matchmaker` holds an in-process queue per ruleset (`fenghua`, `chongci-fh`)
and groups four players into a `Room`. Private tables have a separate lifecycle: create →
join/seat (host assigns AI seats) → set mode → start → active (reconnects rejoin by `tableId`).
There is no Redis; the server is single-process.

**Automated seats.** Any seat without a connected human is played by a policy, resolved per seat →
room default → heuristic. Bots act through the same `ProcessPlayerAction` path as humans, with a
human-paced delay.

**Hidden information.** Broadcasts are redacted per recipient by default: other seats' concealed
tiles become fake ids (≥ 1000, `SUIT_UNKNOWN`, re-randomized every broadcast), `valid_actions`
and `shanten` are dropped, and `wall_seed` is cleared. Hands are revealed at round end.
`MAHJONG_DEV_REVEAL_HANDS=1` (`make dev`) disables redaction for local debugging only.

**Persistence.** On room shutdown `persistMatch` writes the `Match` row (status `completed` at
`PHASE_MATCH_END`, otherwise `aborted`), the paipu JSON, and `MatchPlayer` rows (seat, score,
placement, seat-composition labels). SIGTERM drains active rooms so redeploys persist in-flight
matches. Only completed matches list under `/users/me/replays`.

**Paipu v2.** Each round carries a decision trace: one row per player decision with the legal
catalog ids, the chosen id, the source (`human`, `remote`, `fallback`, `heuristic`), and for
remote decisions the serving checkpoint's sha256. The header records status, placements, server
commit, match mode, and contract versions. `internal/api/room_decisions.go` is the single
capture point; the engine stores rows without knowing provenance. Training extraction must read
`matches.paipu_json` from Postgres directly, never the replay API (an admin can upload paipu).

**Auth.** Username or email + password (bcrypt). Login sets a 30-day opaque HttpOnly session
cookie (only its SHA-256 is stored); mutations require the `X-CSRF-Token` returned with the
session. Origins are checked against `FRONTEND_ORIGINS` for both HTTP and WebSocket.

**Configuration.**

| Variable | Effect |
|---|---|
| `DATABASE_URL` | Postgres DSN (default: the docker-compose database on `localhost:5433`) |
| `FRONTEND_ORIGINS`, `TRUSTED_PROXIES` | CORS/WebSocket origin allowlist; trusted proxies (default none) |
| `ADMIN_SECRET` | Enables admin paipu upload |
| `RL_AGENT_POLICY_URL`, `RL_AGENT_EVENT_WINDOW` | Private-room RL seat endpoint and its event window |
| `RL_AGENT_AUTOSTART`, `RL_AGENT_SERVE_CMD`, `RL_AGENT_CHECKPOINT_ID` | Local policy-server autostart (on by default for the localhost endpoint) |
| `RL_AGENT_SHADOW_POLICY_URL`, `RL_AGENT_SHADOW_EVENT_WINDOW`, `RL_AGENT_SHADOW_POLICY_TOKEN` | Shadow candidate that mirrors RL decisions without affecting play |
| `RL_AGENT_WARMUP_TTL` | Re-warm interval for policy endpoints (default 15m) |
| `AI_BOT_POLICY_URL`, `AI_BOT_EVENT_WINDOW` | Route public-queue bot seats through a policy server |
| `POLICY_SERVER_URL`, `POLICY_SERVER_TOKEN`, `REVIEW_EVENT_WINDOW` | Post-game review backend |
| `MAHJONG_DEV_REVEAL_HANDS` | Local god-view; never in a deployment |

## Bot seats and serving (`internal/bot`, `internal/bot/remote`)

- `bot.Policy` (`ChooseAction(state, seat)`) is the base contract. `ContextPolicy` adds a
  `DecisionContext` (state, seat, decision index, a copy of the public event log), and
  `ProvenanceContextPolicy` also returns where the decision came from (for paipu v2).
- `HeuristicPolicy` is deterministic and shanten-driven. It plays empty seats, `cmd/play`
  opponents, and the opponents in RL evaluation.
- `remote.HTTPPolicy` encodes the observation (with the event window the served checkpoint
  declares), POSTs `/act`, and decodes the returned `action_id` through `rl.DecodeActionID`.
  Any failure — timeout, bad JSON, illegal id, contract mismatch — falls back to the heuristic
  and is counted.
- The RL seat is health-gated: `/api/v1/config` reports `rlAgentAvailable` from the policy
  server's `/healthz`. A private table with an RL seat warms every endpoint (`/warmup`) before it
  starts and refuses to start (503) if warmup fails.
- `ShadowPolicy` runs a candidate model beside the primary on a background worker, records
  agreement and latency, and never affects the action.

## Post-game review (`internal/review`)

`ExtractDecisions` replays a paipu round by round through a fresh `engine.Game`, verifies every
recorded action is legal, and emits each decision point with the observation the champion would
have seen. `BuildReport` batches those observations to the policy server's `/evaluate` and returns
per-decision action probabilities and per-seat summaries. Divergence between the paipu and the
engine aborts the review; there is no best-effort mode. `BuildStudy` adds per-candidate payout
evaluations over sampled worlds and public-information risk estimates, run as resumable
background jobs. Reports are cached per (match, checkpoint sha).

## Frontend (`web/`)

- React 19 + Vite. Route pages live in `web/src/features/*` (`auth`, `lobby`, `game`,
  `replay`, `calc`, `shanten`, `dev`).
- Providers nest `AuthProvider → SocketProvider → GameProvider`. The socket receives binary
  `GameState` frames; `GameContext` decodes them with protobufjs.
- Live play and replay both render through one presenter, `web/src/table/TableBoard.tsx`, on a
  fixed 1600×900 stage scaled as a unit (`table/stage/`).
- The client never computes legality: buttons come from `PlayerState.valid_actions`.
- `web/src/theme/` holds the design tokens and primitives; `web/src/i18n/` the English and
  Simplified Chinese resources (reviewer UI adds Japanese, Korean, Russian).
- Dev-only pages `/tools/table-sample` and `/tools/round-result` render real components against
  mock data.

## RL bridge (`internal/rl`, `cmd/rlbridge`)

`rl.Env` turns `engine.Game` into a step-to-next-decision environment with seeded resets, the
fixed 204-action catalog, and the seat-relative observation encoder. `EnvPool` steps many envs per
FFI call and returns flat observation buffers; `SearchPool` builds determinized clones of one
decision point. `cmd/rlbridge` exports these as a c-shared library over protobuf bytes. Details
are in [`ai-player.md`](ai-player.md).

## Deployment

- **Single service.** The root `Dockerfile` builds `web/dist`, embeds it (`web/embed.go`), and
  serves the SPA from the Go binary for non-API routes. Pass `GIT_COMMIT` as a build arg to stamp
  paipu with the server commit.
- **Zeabur (production).** Services: the Go backend (root `Dockerfile`), Postgres, and `policy`
  (`ai/Dockerfile.deploy`, CPU torch, the checkpoint in `ai/checkpoints/deploy/` baked in, served
  greedy, private network only). Pushing to `main` redeploys every git-linked service. A
  `policy-candidate` service serves the research champion for shadow comparison.
- **docker-compose.** `db` by default; `--profile rl` adds the policy server; `--profile full`
  adds the production server image.

## Tests and CI

`.github/workflows/ci.yml` runs `gofmt -l .`, `go vet ./...`, `go test ./...`, and in `web/`
`npx tsc` and `npx vitest run`. The Python suite (`uv run --project ai pytest ai/tests`) is not in
CI; run it locally for `ai/` changes.
