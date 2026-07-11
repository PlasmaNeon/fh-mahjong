# internal/api/

> REST API + WebSocket server — authentication, game rooms, matchmaking, and real-time state sync.

## Overview

This package implements the network layer: HTTP routes via Gin, WebSocket connections via gorilla/websocket, JWT authentication, and the room/matchmaker orchestration that connects players to game instances. It is stateless with respect to game logic — all game mutations are delegated to `engine.Game`.

## Key Files

- **server.go** — Gin HTTP server setup and route registration:
  - Public: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/guest`
  - Public tool routes: `/api/v1/tools/calc`, `/api/v1/tools/shanten`, `/api/v1/replays/:matchId`, `/api/v1/matches/:matchId/review`, `/api/v1/ws`
  - Protected routes (JWT required):
    - `PATCH /api/v1/users/me` — update email/display name; returns fresh token
    - `/api/v1/rooms/:roomId` (GET) — read current seat config.
    - `/api/v1/rooms/:roomId/join` (POST) — claim a seat.
    - `/api/v1/rooms/:roomId/seat` (POST, host-only) — assign or clear an AI seat.
    - `/api/v1/rooms/:roomId/start` (POST, host-only) — launch the match.
    - `/api/v1/rooms/:roomId/mode` (POST, host-only) — set classic/chongci match mode.
  - Optional SPA/static serving from `web/dist` for single-service production deploys
  - Production SPA asset mounts use explicit `GET`/`HEAD` file handlers for `/assets` and `/Regular_shortnames` so built JS/CSS/SVG requests resolve to real files instead of falling through to `index.html`
  - Trusted proxy configuration via `TRUSTED_PROXIES` (defaults to trusting none)
  - CORS configuration

- **auth.go** — JWT authentication handlers (email+password auth; email is the unique identity, `Username` is the display name):
  - `Register()` — Create account keyed by email (normalized to lowercase); bcrypt password hash; auto-logs in and returns `AuthResponse` (201)
  - `Login()` — Authenticate by email+password; returns `AuthResponse` (200)
  - `UpdateMe()` — `PATCH /api/v1/users/me` (protected): updates email and/or display name; email uniqueness is checked excluding self → **409** on conflict; **404** if no DB row; always returns a fresh 72h token in `AuthResponse` (200) so the `username` JWT claim stays current
  - `GuestLogin()` — Anonymous play with auto-generated credentials (unchanged)

- **ws.go** — WebSocket upgrade and client management:
  - `Hub` struct — Manages all active WebSocket clients
  - `HandleWebSocket()` — Upgrades HTTP → WS, creates `Client`
  - Binary Protobuf message protocol

- **room.go** — Single match room orchestration:
  - `Room` struct — 4 `Client` seats + 1 `engine.Game` engine
  - `BotPolicy` — room-wide default automated-seat policy. Injected via `WithBotPolicy()` for server-wide swaps (e.g. remote AI for all seats).
  - `WithBotPolicy()` — room option for injecting a non-default automated-seat policy while keeping the heuristic default
  - `SeatPolicies` — per-seat override map. Populated by the matchmaker from the host's `PrivateTable` seat config; falls through to `BotPolicy` (then heuristic) when a seat is missing.
  - `SeatInfos` — per-seat composition map (`SeatInfo{Kind, Name, UserID, Difficulty, PolicyID}`) captured by the matchmaker at match start. Drives paipu player labelling (`registerPaipuPlayers`): human seats are attributed via `SeatInfos`/`SeatOwners` (authoritative for the whole match — a reserved-but-offline human is still recorded as its owner, never as a bot), bot seats record their true difficulty ("heuristic"/"rl") and, for RL, the serving checkpoint identity (`Matchmaker.RLPolicyIdentity`, from the policy `/healthz`).
  - Initializes `engine.PaipuRecorder` and registers all 4 seats at room start so paipu exports always have complete, labelled player metadata
  - `ActionQueue` channel — Serializes player actions
  - `Run()` — Main goroutine: processes actions, broadcasts state, manages interrupt timer
  - `BroadcastState()` — Serializes `GameState` Protobuf to all connected players
  - Replay recording (appends state snapshots to binary blob)
- **room_bot.go** — Automated-seat ("bot") driving for a `Room` (same package, split out of room.go for focus):
  - `advanceAutomatedSeats()` / `advanceAutomatedSeatsN()` — Play through missing-seat turns, interrupt responses, and round-end `READY` actions, with a circuit-breaker (`maxAutomatedSeatIterations`) to avoid runaway automation loops
  - `botWorkPending()` / `maybeScheduleBotTick()` — Decide when a paced bot step is due and arm a single delayed tick, keeping the room loop responsive to reconnects
  - `isAutomatedSeat()`, `sleepBotThink()`, `policyForSeat()` — seat automation predicate, human-pace delay, and the per-seat → room-default → heuristic policy fallback (`fallbackHeuristicPolicy`)

- **paipu.go** — Read-only paipu API:
  - `handleGetPaipu()` — Loads persisted paipu JSON for a completed match and returns it as raw JSON
  - Local-dev fallback: serves checked-in `testdata/paipu/<matchId>.json` fixtures when no in-memory/DB record exists, which keeps replay pages usable without a populated database
  - Only queries the legacy `matches` table for canonical UUID match IDs; per-hand IDs like `match-1` skip the UUID-only lookup to avoid noisy Postgres cast errors

- **review.go** — Post-game review report API, cached via `storage.MatchReview`:
  - `(*Server) loadPaipuJSON(matchID) (string, bool)` — shared paipu source chain extracted from `paipu.go` (in-memory store → `paipu_records` → legacy `Match.PaipuJSON` UUID-guarded lookup → checked-in fixtures), reused by both `handleGetPaipu` and the review handlers so behavior stays identical between the two APIs.
  - `GET /api/v1/matches/:matchId/review` — cache-only lookup: DB nil or no cached row → **404**; otherwise **200** with the newest cached report's raw JSON (`c.Data`, `application/json`).
  - `POST /api/v1/matches/:matchId/review` — build-or-cached:
    - `POLICY_SERVER_URL` env var unset → **503** `{"error":"reviewer unavailable"}` (no reviewer configured; checked before any paipu lookup).
    - No paipu found for `matchId` (via `loadPaipuJSON`) → **404**.
    - Paipu JSON fails to unmarshal, or `review.BuildReport` fails with `errors.Is(err, review.ErrUnreviewable)` (decision-reconstruction/extraction failure) → **422** `{"error":"unreviewable paipu: ..."}`.
    - Policy server call itself fails (network error, non-2xx, etc., NOT `ErrUnreviewable`) → **502**.
    - Otherwise **200** with the report JSON (built fresh or served from cache).
  - **Cache policy**: with a DB present, an unforced POST returns the newest cached `MatchReview` for the match (by `created_at`) without calling the policy server at all — pass `?force=1` to force a fresh build. A fresh build upserts on `(MatchID, CheckpointID=report.CheckpointPath)`: same champion re-reviewing overwrites its own row in place; a new champion (different `CheckpointID`) adds a new row so old champions' reports survive until pruned. DB nil (dev mode) → every POST builds fresh and nothing is cached; GET always 404s.
  - See `internal/review/` for `BuildReport`/`ExtractDecisions`/`HTTPPolicyClient` and `internal/storage/db.go` for the `MatchReview` model.

- **client.go** — Individual player WebSocket connection:
  - `Client` struct — UserID, Send channel, WebSocket conn
  - `ReadPump()` / `WritePump()` — Goroutine message loops; queued JSON and protobuf payloads are written as separate text/binary frames with a fresh deadline per frame

- **matchmaker.go** — Player queue and pairing:
  - `Matchmaker` struct — Queue of waiting clients
  - Groups 4 players into a `Room`
  - `BotPolicyFactory` creates one automated-seat policy per new room; the server uses this to enable remote AI bots without sharing policy state across matches
  - Tracks `configuringTables` (host + 4-seat config) and exposes `JoinOrCreatePrivateTable`, `MutatePrivateTable`, and `StartPrivateTable`. The first joiner of a `tableId` becomes the host; only the host can mutate seats or start the match.
  - Tracks active private tables by `tableId` so the same `/table/:tableId` link cannot accidentally start a second game while the first one is still running
  - Lets returning players from the original 4 receive an `"active"` private-table response with the current `matchId` instead of being re-queued

- **middleware.go** — JWT token validation middleware for protected routes

- **calc.go** — Hand evaluation API endpoint (stateless scoring calculator):
  - Accepts structured calculator payloads: closed hand, win tile, single wild tile type, open melds, flower melds, winds, tsumo/ron, and kong bonus flags
  - Open meld rows can carry per-kan kong flags; repeated flag selections across multiple kan melds are counted and stacked in the calculator response
  - Validates meld shapes, hand size, tile copy limits, and wind ranges before scoring
  - Translates request data into proto `GameState` / `PlayerState` / `Meld` values with unique tile IDs
  - Returns `canWin`, total score, score breakdown, and a normalized debug summary for the frontend

- **calc_test.go** — Calculator API coverage:
  - Request validation failures
  - Tsumo / Ron calculator responses
  - Wild tile translation and scoring
  - Open meld called-tile preservation
  - Flower meld and kong-flag propagation into the evaluation state

- **room_bot_test.go** — Automated-seat room coverage:
  - Missing seats advance through legal bot actions
  - `NewRoom()` initializes paipu recording for match replay export
  - Round-end automation marks bot seats ready and can advance all-bot tables into the next round
  - Paipu player registration includes placeholder bot seats alongside connected humans
  - `room_remote_test.go` contains a skipped-by-default live remote-policy integration test; set `FH_MAHJONG_REMOTE_POLICY_TEST_URL=http://127.0.0.1:8765/act` when a Python policy server is running

## Architecture Notes

- All game actions flow: Client → WebSocket → Room.ActionQueue → engine.Game.ProcessPlayerAction() → BroadcastState()
- The room processes actions sequentially via a single goroutine (no mutex needed for game state).
- Seats with no connected `Room.Seats` entry are treated as automated seats and act through the same authoritative engine path instead of being hard-coded to `PASS`.
- Replay persistence has three outputs: the binary protobuf replay blob (`ReplayURL`), the structured paipu JSON (`PaipuJSON`), and relational `MatchPlayer` rows (seat labels + final score + placement, written by `persistMatchPlayers`). `persistMatch` runs once on room shutdown: status is `completed` at natural `PHASE_MATCH_END`, `aborted` otherwise (partial paipu is still written). `Room.Done` is closed after persistence; `Matchmaker.DrainActiveRooms(timeout)` uses it on SIGINT/SIGTERM (cmd/server) so a redeploy persists in-flight matches instead of orphaning `in_progress` rows.
- The interrupt timer runs in a separate goroutine and calls `ResolveInterrupts()` directly — potential race condition to be aware of.
- State broadcast is per-player redacted **by default (fail closed)** via `redactedStateForSeat`. Redaction is on for every client unless an operator explicitly sets `MAHJONG_DEV_REVEAL_HANDS=1` (`revealAllHands`), the local debug god-view that sends the raw master with every hand visible — never set it in a deployed environment. There is no deploy-specific opt-in; a missing/misconfigured env var stays redacted. The god-view is reached ONLY by running the backend with the flag explicitly — use `make dev` (go run). Never set it in a container/compose config: the docker-compose `server` service runs the production Dockerfile image and intentionally leaves redaction on, and Zeabur builds via the Dockerfile, which never sets it. For every *other* seat the closed hand + drawn tile are obfuscated (real id → fake id ≥ 1000, suit `SUIT_UNKNOWN`, so the frontend renders tile backs), `shanten` is zeroed, and `valid_actions` is dropped (its meld tiles would expose the concealed tiles backing a pon/chii/kan). The top-level `wall_seed` is cleared for everyone (it deterministically reconstructs the entire deal). Once a round/match ends (`PHASE_ROUND_END`/`PHASE_MATCH_END`, see `handsRevealed`) opponents' hands are revealed (`concealHands=false`) so players see the result.
- The obfuscation map is re-randomized **per recipient per broadcast** (`newTileObfuscation`, generated inside `redactedStateForSeat`), not a per-match/per-deal map. No fake id persists across broadcasts, which defeats (1) cross-turn tracking of a concealed tile by its stable fake id and (2) de-anonymizing the map by correlating a revealed discard with the fake id that left an opponent's hand. Opponent hands are anonymous backs, so the frontend keys them by hand slot, not by the volatile fake id (see `web/src/table/seat/ClosedHand.tsx`).
- Opponent **discards keep their real ids and faces** (public the moment made). Per-broadcast rotation means a real discard id can never be correlated to a concealed fake id (real < 144, fake ≥ 1000), so discards are not obfuscated. The client animates an opponent discard from a random hand slot (tedashi) or the drawn slot (tsumogiri) using the public `last_discard_from_drawn` flag — decoupled from real tile position — rather than tracking the discard back to a hand tile by id.
- Private tables are now a two-stage concept: `tableId` is the shareable waiting-room key, and once 4 players are ready the server records an active `tableId -> matchId + participant set` mapping so reconnects can rejoin the live room while non-participants are rejected.
- WS `lobby_update` envelopes for rooms now carry the full `PrivateTableState` as JSON under a `room` key (the waiting-room id), so the waiting room renders seat assignments directly from each broadcast.
- `/api/v1/tools/calc` is intentionally isolated from room/game orchestration so rules bugs can be reproduced without creating a live match.
- When `web/dist/index.html` exists, unmatched non-API `GET`/`HEAD` routes fall back to the frontend SPA shell so routes like `/tools/calc` and `/room/new` work behind the Go server.
- Asset-like paths (`/assets/...`, `/Regular_shortnames/...`, and common static-file extensions) must never use the SPA fallback; they return the real file or `404`.
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/internal/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.

- **server_test.go** — SPA/static serving regression coverage:
  - Built JS asset requests return JavaScript, not `index.html`
  - Missing asset requests return `404`, not the SPA shell

- **review_test.go** — Review API coverage (in-memory sqlite + `httptest` stub policy server mirroring `internal/review/report_test.go`'s uniform-probs-over-legal-mask stub):
  - No `POLICY_SERVER_URL` → 503 `{"error":"reviewer unavailable"}`
  - Build against the checked-in `testdata/paipu/review-fixture.json` fixture (generated via `cmd/rlpaipu -seed 7`) → 200, `MatchReview` row persisted; a second POST hits the cache (no extra stub requests); GET returns the same cached body
  - Policy server unreachable → 502
  - GET for an unknown match → 404
  - A paipu with no rounds → 422 (`review.ErrUnreviewable`)

- **private_tables_test.go** — Seat-config + lifecycle regression coverage:
  - First joiner is assigned host at seat 0; subsequent joiners claim the next empty seat
  - Host can set/clear a bot seat; non-host gets 403
  - `/start` rejects empty seats (400) and non-host callers (403)
  - 1-human + 3-bot start path constructs an active private table and registers the host as a participant
  - Returning participants on an active table get `"active"` with the existing `matchId`; outsiders get 409
