# internal/api/

> REST API + WebSocket server — authentication, game rooms, matchmaking, and real-time state sync.

## Overview

This package implements the network layer: HTTP routes via Gin, WebSocket connections via gorilla/websocket, database-backed cookie sessions, and the room/matchmaker orchestration that connects players to game instances. All game mutations are delegated to `engine.Game`.

## Key Files

- **server.go** — Gin HTTP server setup and route registration:
  - Public: `/api/v1/auth/register`, `/api/v1/auth/login`
  - Session: `GET /api/v1/auth/session`, `DELETE /api/v1/auth/session`
  - Public tool routes: `/api/v1/tools/calc`, `/api/v1/tools/shanten`, `/api/v1/replays/:matchId`, `GET /api/v1/matches/:matchId/review` (pure cache lookup — never builds a report, never calls the policy server), `/api/v1/ws`
  - Protected routes (30-day session cookie required; mutations also require `X-CSRF-Token`):
    - `PATCH /api/v1/users/me` — update unique username and/or email
    - `GET /api/v1/users/me/replays` — cursor-paginated completed paipu owned by the current account; malformed, aborted, active, and unowned matches are excluded
    - `POST /api/v1/rooms` — explicitly create a private table and seat its host
    - `/api/v1/rooms/:roomId` (GET) — read current seat config.
    - `/api/v1/rooms/:roomId/join` (POST) — claim a seat.
    - `/api/v1/rooms/:roomId/seat` (POST, host-only) — assign or clear an AI seat.
    - `/api/v1/rooms/:roomId/start` (POST, host-only) — launch the match.
    - `/api/v1/rooms/:roomId/mode` (POST, host-only) — set classic/chongci match mode. Private tables **default to chongci** (`newConfiguringTable`, shared `defaultChongciConfig`: 2000 start / bust at 0 / 50-hand cap). Both modes must reach `PHASE_MATCH_END` to persist as `completed` and appear under `/users/me/replays`, so `matchOptionsForPrivateTable` maps **classic → a single-hand match** (`classicSingleHandConfig`: start 0 / no bust / `MaxHands` 1 — "a 1-hand chongci") and **chongci → its host config**. The engine keeps `MatchMode == CLASSIC` for classic tables (random dealer, chongci UI hidden), but the cap config makes it terminate after one hand. (Uncapped classic — the public `fenghua` queue, nil `ChongciConfig` — is still endless and does not list.)
    - `POST /api/v1/matches/:matchId/review` (host of a match, or anyone with a valid session — no per-match ownership check) — build (or serve the cached) review report; see review.go below. Moved into this protected group in round 21 (Finding 1): unauthenticated, it let any caller with a match id spam `?force=1` and drive unbounded authenticated `/evaluate` load against the policy server, which is shared with live RL agent traffic. Guests are authenticated users in this app, so this is not a login-wall — it just requires a session.
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
  - `persistMatch()` stamps the paipu v2 header via `Recorder.SetMatchMeta` before
    marshaling: `status`/`completionReason` (`match_end` at natural
    `PHASE_MATCH_END`; otherwise `aborted` with `drained` (server-drain, see the
    `drained` atomic.Bool set by `markDrained()`) or `abandoned`), `placements`,
    `serverCommit` (`ServerCommit`, see `buildinfo.go`), `matchMode`/`chongci`,
    `rulesetVersion: "fenghua-v1"` (hardcoded — bump by hand if the ruleset
    changes shape), and the version trio `eventContractVersion`
    (`rl.EventContractV1`) / `protoEnumsRevision` (`engine.ProtoEnumsRevision`) /
    `actionCatalogVersion` (`rl.ActionCatalogVersion`). Called once per
    `persistMatch` run (idempotent on `SetMatchMeta`, so a snapshot-then-Finalize
    double-persist just overwrites the same fields).
- **room_bot.go** — Automated-seat ("bot") driving for a `Room` (same package, split out of room.go for focus):
  - `advanceAutomatedSeats()` / `advanceAutomatedSeatsN()` — Play through missing-seat turns, interrupt responses, and round-end `READY` actions, with a circuit-breaker (`maxAutomatedSeatIterations`) to avoid runaway automation loops
  - `botWorkPending()` / `maybeScheduleBotTick()` — Decide when a paced bot step is due and arm a single delayed tick, keeping the room loop responsive to reconnects
  - `isAutomatedSeat()`, `sleepBotThink()`, `policyForSeat()` — seat automation predicate, human-pace delay, and the per-seat → room-default → heuristic policy fallback (`fallbackHeuristicPolicy`)
  - Every automated-seat call site type-asserts the resolved policy for `bot.ContextPolicy` first (`ChooseActionCtx`), falling back to the legacy `bot.Policy.ChooseAction` only when it isn't implemented. `buildDecisionContext(seat)` (room-lock held) snapshots the atomic decision: `r.Engine.State`, the seat, a room-owned monotonic `policyDecisionIndex` counter, and a **copy** of `r.Engine.PublicEvents()` (raw, unwindowed — each policy applies its own declared event window when it encodes for `/act`, per the DecisionContext design in `internal/bot`)

- **cmd/server/main.go (consumer, not in this package)** — the `RL_AGENT_POLICY_URL`/`RL_AGENT_EVENT_WINDOW` family: `RL_AGENT_SHADOW_POLICY_URL` + `RL_AGENT_SHADOW_EVENT_WINDOW` (default 128, capped at `rl.MaxEventHistoryWindow`) wrap the resolved RL primary in a `bot.ShadowPolicy` per RL seat; see `internal/bot/AGENTS.md` for the wrapper itself.

- **room_decisions.go** — Paipu v2 supervision-trace capture (spec:
  `docs/superpowers/specs/2026-08-09-paipu-v2-provenance-design.md` §2-3). This
  is the single choke point where every explicit decision passes AND
  provenance is known; the engine (`internal/engine/paipu.go`) stays
  provenance-blind and just stores the rows.
  - `snapshotDecision(seat, action)` — called BEFORE `Engine.ProcessPlayerAction`:
    enumerates the PRE-action legal catalog IDs (`rl.LegalActions`) and encodes
    the chosen action's catalog id (`rl.EncodeAction`); either failing sets
    `snapErr` (never blocks play, just marks `legalIdsError` on the row).
  - `recordDecision(seat, snap, prov)` — called AFTER the action succeeds;
    builds an `engine.PaipuDecision` and appends it via `Engine.Recorder.RecordDecision`.
  - `chooseSeatAction(seat)` — asks the seat's policy for an action, preferring
    `bot.ProvenanceContextPolicy` > `bot.ContextPolicy` > legacy `bot.Policy`,
    and returns the decision's `bot.DecisionProvenance` alongside it
    (`humanProvenance()`/`heuristicProvenance()` for the fixed non-remote labels).
  - **Capture rules**: every explicit player action (discard, claim, win,
    flower choice, haitei accept/refuse) and every explicit/inferred pass is
    traced, at both `room.go`'s human action path (`traced := ... != ACTION_READY`)
    and `room_bot.go`'s automated-seat loop. `ACTION_READY` acks (round-flow
    control, not gameplay) and timeout-driven auto-resolutions are **excluded** —
    they are forced, not decisions.
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
  - **Cache policy (round 21, Finding 2)**: with a DB present, an unforced POST first resolves the CURRENTLY-SERVED checkpoint via `HTTPPolicyClient.CurrentCheckpointSha256()` (GET `/healthz`, in client.go). When that sha is known, the lookup is an exact `(matchID, checkpoint_id=sha)` row: a hit serves it as-is (even if a different checkpoint was reviewed for this match more recently — a rollback re-serves the old champion's own row without rebuilding); a miss builds fresh, recording the new row under that sha. When the sha can't be resolved (healthz unreachable, or a legacy policy server that predates `checkpoint_sha256`), this falls back to the newest cached `MatchReview` row by `created_at` — documented choice: a stale row is better than erroring a read-mostly endpoint over a healthz hiccup; a build that's actually needed still hits the same unreachable server and 502s below. `?force=1` always builds fresh regardless. A fresh build upserts on `(MatchID, CheckpointID=reviewCacheCheckpointID(report))` — the report's own `CheckpointSha256` when known, else `CheckpointPath` (round 18): same champion re-reviewing overwrites its own row in place; a new champion (different `CheckpointID`) adds a new row so old champions' reports survive until pruned. DB nil (dev mode) → every POST builds fresh and nothing is cached; GET always 404s. `storage.MatchReview` has no `UpdatedAt` field, so the legacy newest-row fallback path does not refresh any timestamp on a cache hit — noted, not fixed, since the exact-sha lookup is the primary fix and makes this path secondary.
  - **Concurrency (round 21, Finding 1)**: every actual build (forced, or a cache miss) runs through `Server.reviewBuildGroup`, an `x/sync/singleflight.Group` keyed on `matchID` — concurrent requests for the SAME match id share one in-flight build and its result instead of each firing their own policy-server batch. `buildReviewOutcome` additionally acquires `Server.reviewBuildSem`, a server-wide semaphore of size `reviewBuildConcurrencyLimit` (2), so even distinct match ids can't stack up unbounded concurrent builds against the policy server and starve live `/act` traffic.
  - `reviewEventWindow(policyURL)` resolves the `event_window` of the checkpoint served at `POLICY_SERVER_URL` (passed in as `policyURL`). **`REVIEW_EVENT_WINDOW`, not `RL_AGENT_EVENT_WINDOW`, is the env var that governs this** (adversarial round 7, Finding 2) — `POLICY_SERVER_URL` may be a genuinely different server/checkpoint than the one `RL_AGENT_POLICY_URL`/`AI_BOT_POLICY_URL`/`RL_AGENT_EVENT_WINDOW` describe in `cmd/server/main.go`, and blindly inheriting `RL_AGENT_EVENT_WINDOW` would silently mis-speak review's own wire contract whenever the two diverge. Resolution order: (1) `REVIEW_EVENT_WINDOW` set → always wins, parsed via `parseReviewEventWindowEnv` (unset/empty → fallback below; unparseable or `> rl.MaxEventHistoryWindow` → rejected outright to 0, never clamped, never falls through to (2)); (2) `REVIEW_EVENT_WINDOW` unset → inherit `RL_AGENT_EVENT_WINDOW` ONLY when `policyURL` is empty, or equals the resolved RL endpoint (`RL_AGENT_POLICY_URL`, else `AI_BOT_POLICY_URL` — the same fallback chain `cmd/server`'s `rlEndpointURL` uses, minus the local-default case, which review never hits); otherwise logs the mismatch and defaults to 0. The resolved value is threaded into both `review.NewHTTPPolicyClientWithToken(policyURL, eventWindow, policyToken)` and `review.BuildReport(&paipu, client, eventWindow)` — they must always agree, since one encodes the observations and the other enriches the `/evaluate` payload from them.
  - **`POLICY_SERVER_TOKEN` (adversarial round 19)**: read directly in `handlePostReview` alongside `POLICY_SERVER_URL` and passed to `review.NewHTTPPolicyClientWithToken` as the third argument. `serve_policy.py`'s `/evaluate` is disabled entirely (403) unless launched with `--evaluate-token`/`FH_MJ_EVALUATE_TOKEN`, so this env var must be set to the SAME value on the backend or every review request gets a 403 from the policy server — surfaced here as the existing **502** `policy server evaluation failed` path (not a new status code; the 403's detail is logged server-side via the same `log.Printf`, never returned to the caller). Unset here (empty string) attaches no `Authorization` header at all (`HTTPPolicyClient`'s zero-value token behavior) — only viable against a policy server that likewise has no evaluate token configured.
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
  - **RL warmup admission gate** — `WarmRLEndpoints func(ctx) error` (wired by `cmd/server` to a `remote.WarmupManager`) is invoked from `StartPrivateTable` before any seat policy or Room is constructed, but ONLY for tables that seat at least one `DIFFICULTY_RL` bot. It blocks up to `rlWarmupBudget` (25s, covering primary + shadow) until every configured policy endpoint has taken a real forward pass. A warmup error FAILS the start with `ErrRLWarmupFailed` (handler → `503`, table stays `configuring` so the host can simply retry) — an RL room must never silently degrade to the heuristic because the model server was cold. Tables with no RL seat never call the hook at all.
    - **Lock discipline (load-bearing)** — the warm runs with `table.mu` RELEASED: `StartPrivateTable` validates cheaply under the lock (`validateStartLocked` + seat signature), unlocks, warms, then re-acquires and RE-VALIDATES. Holding the lock across a ~25s warm would block that table's join/seat/state handlers and serialize repeated Start clicks. If the table was reconfigured meanwhile, the seat-signature check fails the start with `ErrPrivateTableChangedDuringStart` (handler → `409`, retryable).
    - **Sanitized 503** — the wrapped warmup detail can name the internal policy endpoint, so `handlePrivateTableStart` responds with the `ErrRLWarmupFailed` sentinel text only; the full error is logged server-side by `warmRLEndpoints`.
    - Env: `RL_AGENT_SHADOW_POLICY_TOKEN` (`cmd/server`) carries the candidate service's `FH_MJ_EVALUATE_TOKEN`, which token-gates its `/warmup`; `RL_AGENT_WARMUP_TTL` re-warms after the configured interval (**default 15m**, `0` = warm once per process).

- **middleware.go** — Session-cookie lookup, expiry/revocation checks, current-user resolution, and constant-time CSRF validation

- **buildinfo.go** — `ServerCommit` (default `"unknown"`), stamped at build
  time via `-ldflags "-X .../internal/api.ServerCommit=$(git rev-parse --short HEAD)"`;
  read into every persisted paipu's v2 `serverCommit` field (`room.go`'s
  `persistMatch`). The repo's `Dockerfile` accepts a `GIT_COMMIT` build ARG and
  passes it through this ldflag; **Zeabur's build does not currently supply
  `GIT_COMMIT`**, so production paipu show `serverCommit: "unknown"` until the
  deploy config is updated to pass it.

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
- **Trusted read path for training (spec §9).** `loadPaipuJSON`'s fallback
  chain (in-memory store → `paipu_records` → legacy `Match.PaipuJSON` →
  checked-in fixtures) exists to serve `handleGetPaipu`/the review API to
  players and is reachable via `handleUploadPaipu`, which is **admin-writable**
  and, by construction, outranks the DB on read (the in-memory/`paipu_records`
  entries are checked first). Any future training-data extraction pipeline
  MUST read only server-recorded `matches.paipu_json` rows directly from
  Postgres — never this chain — or an admin-supplied paipu could silently
  poison a training set. This is a documentation-only rule for now (spec
  says "enforced when the extractor is built"); nothing in this package
  currently builds that extractor.

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
