# internal/api/

> REST API + WebSocket server — authentication, game rooms, matchmaking, and real-time state sync.

## Overview

This package implements the network layer: HTTP routes via Gin, WebSocket connections via gorilla/websocket, database-backed cookie sessions, and the room/matchmaker orchestration that connects players to game instances. All game mutations are delegated to `engine.Game`.

## Key Files

- **server.go** — Gin HTTP server setup and route registration:
  - Public: `/api/v1/auth/register`, `/api/v1/auth/login`
  - Session: `GET /api/v1/auth/session`, `DELETE /api/v1/auth/session`
  - Public tool routes: `/api/v1/tools/calc`, `/api/v1/tools/shanten`, `/api/v1/replays/:matchId`, `/api/v1/matches/:matchId/review`, `/api/v1/ws`
  - Protected routes (30-day session cookie required; mutations also require `X-CSRF-Token`):
    - `PATCH /api/v1/users/me` — update unique username and/or email
    - `GET /api/v1/users/me/replays` — cursor-paginated completed paipu owned by the current account; malformed, aborted, active, and unowned matches are excluded
    - `POST /api/v1/rooms` — explicitly create a private table and seat its host
    - `/api/v1/rooms/:roomId` (GET) — read current seat config.
    - `/api/v1/rooms/:roomId/join` (POST) — claim a seat.
    - `/api/v1/rooms/:roomId/seat` (POST, host-only) — assign or clear an AI seat.
    - `/api/v1/rooms/:roomId/start` (POST, host-only) — launch the match.
    - `/api/v1/rooms/:roomId/mode` (POST, host-only) — set classic/chongci match mode. Private tables **default to chongci** (`newConfiguringTable`, shared `defaultChongciConfig`: 2000 start / bust at 0 / 50-hand cap). Both modes must reach `PHASE_MATCH_END` to persist as `completed` and appear under `/users/me/replays`, so `matchOptionsForPrivateTable` maps **classic → a single-hand match** (`classicSingleHandConfig`: start 0 / no bust / `MaxHands` 1 — "a 1-hand chongci") and **chongci → its host config**. The engine keeps `MatchMode == CLASSIC` for classic tables (random dealer, chongci UI hidden), but the cap config makes it terminate after one hand. (Uncapped classic — the public `fenghua` queue, nil `ChongciConfig` — is still endless and does not list.)
  - Optional SPA/static serving from `web/dist` for single-service production deploys
  - Production SPA asset mounts use explicit `GET`/`HEAD` file handlers for `/assets` and `/Regular_shortnames` so built JS/CSS/SVG requests resolve to real files instead of falling through to `index.html`
  - Trusted proxy configuration via `TRUSTED_PROXIES` (defaults to trusting none)
  - CORS configuration

- **auth.go** — Username/email + password auth backed by opaque revocable sessions. Login/register/session return `{user, csrfToken}` and set an HttpOnly cookie; no credential is serialized in JSON or stored by frontend JavaScript
- **cors.go** — Exact `FRONTEND_ORIGINS` allowlist, credentialed CORS, and the shared HTTP/WebSocket origin policy

- **ws.go** — Cookie-authenticated, origin-checked WebSocket upgrade and client management:
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
  - `closeSeatPolicies()` — called from `finishShutdown` before the matchmaker regains control: closes every distinct `closeableBotPolicy` (currently only `bot.ShadowPolicy`, via its `Close()`) across `SeatPolicies` + the room-wide `BotPolicy`, pointer-deduped so a policy installed both as a seat override and the room default is only closed once. Each room's `ShadowPolicy` instances are unique to that room (constructed fresh per RL seat in `Matchmaker.StartPrivateTable`), so this is the sole owner responsible for stopping their worker goroutines; the wrapped shadow/primary policies themselves are never touched (they may be long-lived and shared across rooms).
  - `ActionQueue` channel — Serializes player actions
  - `Run()` — Main goroutine: processes actions, broadcasts state, manages interrupt timer
  - `BroadcastState()` — Serializes `GameState` Protobuf to all connected players
  - Replay recording (appends state snapshots to binary blob)
- **room_bot.go** — Automated-seat ("bot") driving for a `Room` (same package, split out of room.go for focus):
  - `advanceAutomatedSeats()` / `advanceAutomatedSeatsN()` — Play through missing-seat turns, interrupt responses, and round-end `READY` actions, with a circuit-breaker (`maxAutomatedSeatIterations`) to avoid runaway automation loops
  - `botWorkPending()` / `maybeScheduleBotTick()` — Decide when a paced bot step is due and arm a single delayed tick, keeping the room loop responsive to reconnects
  - `isAutomatedSeat()`, `sleepBotThink()`, `policyForSeat()` — seat automation predicate, human-pace delay, and the per-seat → room-default → heuristic policy fallback (`fallbackHeuristicPolicy`)
  - Every automated-seat call site type-asserts the resolved policy for `bot.ContextPolicy` first (`ChooseActionCtx`), falling back to the legacy `bot.Policy.ChooseAction` only when it isn't implemented. `buildDecisionContext(seat)` (room-lock held) snapshots the atomic decision: `r.Engine.State`, the seat, a room-owned monotonic `policyDecisionIndex` counter, and a **copy** of `r.Engine.PublicEvents()` (raw, unwindowed — each policy applies its own declared event window when it encodes for `/act`, per the DecisionContext design in `internal/bot`)

- **cmd/server/main.go (consumer, not in this package)** — the `RL_AGENT_POLICY_URL`/`RL_AGENT_EVENT_WINDOW` family: `RL_AGENT_SHADOW_POLICY_URL` + `RL_AGENT_SHADOW_EVENT_WINDOW` (default 128, capped at `rl.MaxEventHistoryWindow`) wrap the resolved RL primary in a `bot.ShadowPolicy` per RL seat; see `internal/bot/AGENTS.md` for the wrapper itself.

- **paipu.go** — Read-only paipu API:
  - `handleGetPaipu()` — Loads persisted paipu JSON for a completed match and returns it as raw JSON
  - Local-dev fallback: serves checked-in `testdata/paipu/<matchId>.json` fixtures when no in-memory/DB record exists, which keeps replay pages usable without a populated database
  - Only queries the legacy `matches` table for canonical UUID match IDs; per-hand IDs like `match-1` skip the UUID-only lookup to avoid noisy Postgres cast errors
- **replay_history.go** — Account-owned replay index:
  - `GET /api/v1/users/me/replays?cursor=&limit=` requires the session cookie, defaults to 20 rows, caps at 50, and orders by `(end_time, match_id)` descending
  - Cursors are opaque base64url values containing the last completion time and match ID, so equal timestamps paginate without duplicates
  - Summaries combine relational ownership/result fields from `MatchPlayer` with historical player names and round counts from validated `PaipuJSON`; public `GET /replays/:matchId` remains unchanged

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
  - `reviewEventWindow()` reads `RL_AGENT_EVENT_WINDOW` (same env family as `RL_AGENT_POLICY_URL`/`RL_AGENT_CHECKPOINT_ID` in `cmd/server/main.go`) — the `event_window` of the checkpoint served at `POLICY_SERVER_URL`; unset/empty/unparseable → 0 (no event history, byte-identical to pre-Task-6 review behavior). The same value is threaded into both `review.NewHTTPPolicyClient(policyURL, eventWindow)` and `review.BuildReport(&paipu, client, eventWindow)` — they must always agree, since one encodes the observations and the other enriches the `/evaluate` payload from them.
  - See `internal/review/` for `BuildReport`/`ExtractDecisions`/`HTTPPolicyClient` and `internal/storage/db.go` for the `MatchReview` model.

- **client.go** — Individual player WebSocket connection:
  - `Client` struct — UserID, Send channel, WebSocket conn
  - `ReadPump()` / `WritePump()` — Goroutine message loops; queued JSON and protobuf payloads are written as separate text/binary frames with a fresh deadline per frame

- **matchmaker.go** — Player queue and pairing:
  - `Matchmaker` struct — Queue of waiting clients
  - Matchmaking joins are idempotent per user/ruleset. `POST /api/v1/matchmaking/leave` atomically removes a waiting user and returns `409 match_forming` when the watcher already claimed the entry.
  - Groups 4 players into a `Room`
  - `BotPolicyFactory` creates one automated-seat policy per new room; the server uses this to enable remote AI bots without sharing policy state across matches
  - Tracks `configuringTables` and exposes separate `CreatePrivateTable`, `JoinPrivateTable`, `MutatePrivateTable`, and `StartPrivateTable` operations. Join never creates missing state
  - Tracks active private tables by `tableId` so the same `/table/:tableId` link cannot accidentally start a second game while the first one is still running
  - Lets returning players from the original 4 receive an `"active"` private-table response with the current `matchId` instead of being re-queued

- **middleware.go** — Session-cookie lookup, expiry/revocation checks, current-user resolution, and constant-time CSRF validation

- **response.go** — `respondError(c, status, msg)` / `abortError(c, status, msg)` — the single point for the API's `{"error": msg}` response shape. Handlers use `respondError` (`c.JSON`); middleware uses `abortError` (`c.AbortWithStatusJSON`, short-circuits the chain). Responses that carry extra keys beyond `error` stay inline.

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
- The Hub exclusively owns `UserRooms`. Rooms send `UnbindRoom` when their event loop shuts down so later WebSocket connections do not attempt to rejoin a dead room; cleanup removes only entries still pointing at that exact room.
- Seats with no connected `Room.Seats` entry are treated as automated seats and act through the same authoritative engine path instead of being hard-coded to `PASS`.
- Replay persistence has three outputs: the binary protobuf replay blob (`ReplayURL`), the structured paipu JSON (`PaipuJSON`), and relational `MatchPlayer` rows (seat labels + final score + placement, written by `persistMatchPlayers`). `persistMatch` runs once on room shutdown (with bounded retries for transient DB failures): status is `completed` at natural `PHASE_MATCH_END`, `aborted` otherwise — the in-progress hand is kept via `PaipuRecorder.Snapshot` (nil result). Before writing, `reconcileRLPolicyIDs` replaces each RL seat's match-start policy label with the checkpoints that actually served its /act responses and records remote/fallback/automated decision counts. An explicit table exit uses WebSocket close code `4000` and releases that human seat immediately; an ordinary disconnect retains its seat for the reconnect grace period. Once the final human seat is released, the room shuts down instead of allowing a bot-only match to continue. `Room.Done` is closed after persistence; `Matchmaker.DrainActiveRooms(timeout)` uses it on SIGINT/SIGTERM (cmd/server) so a redeploy persists in-flight matches instead of orphaning `in_progress` rows; the drain flips a `draining` flag atomic with room registration (`registerActiveRoom` refuses admission and the refused start deletes its Match row — `StartPrivateTable` returns 503).
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
