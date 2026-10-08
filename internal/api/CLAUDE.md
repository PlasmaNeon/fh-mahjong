# internal/api/

> REST + WebSocket server: auth, rooms, matchmaking, automated seats, persistence, replay and
> review APIs. All game mutations go through `engine.Game`.

Overview and configuration table: [`docs/architecture.md`](../../docs/architecture.md). Review
pipeline: [`docs/replay-review.md`](../../docs/replay-review.md).

## Routes (`server.go`)

| Access | Routes |
|---|---|
| Public | `POST /auth/register`, `POST /auth/login`, `GET /config`, `POST /tools/calc`, `POST /tools/shanten`, `GET /replays/:matchId`, `GET /matches/:matchId/review` (cache read only), `GET /ws` |
| Session | `GET`/`DELETE /auth/session` |
| Admin | `POST /replays/:matchId` (needs `X-Admin-Secret` = `ADMIN_SECRET`; 403 when unset) |
| Signed in (mutations need `X-CSRF-Token`) | `GET`/`PATCH /users/me`, `GET /users/me/replays`, `POST /matchmaking/join`/`leave`, `POST /rooms`, `GET /rooms/:id`, `POST /rooms/:id/{join,seat,start,mode}`, `POST /matches/:id/review`, `/replay-imports[...]`, `/matches/:id/study`, `/review-jobs/:id` |

All routes sit under `/api/v1`. With `web/dist/index.html` present, unmatched non-API `GET`/`HEAD`
routes serve the SPA shell; asset paths (`/assets/`, `/Regular_shortnames/`, static extensions)
never fall back to it and return the file or 404.

## Key files

- **auth.go**, **middleware.go**, **cors.go** — username/email + bcrypt login, opaque 30-day
  HttpOnly session cookie (only its SHA-256 stored), constant-time CSRF check, exact
  `FRONTEND_ORIGINS` allowlist shared by HTTP and WebSocket.
- **ws.go**, **ws_client.go** — cookie-authenticated, origin-checked upgrade; the `Hub` owns
  `UserRooms`. `WritePump` sends one frame per message (text and binary never batched) with a
  fresh deadline each.
- **room.go** — `Room`: four seats and one `engine.Game` on a single goroutine
  (`ActionQueue` → `ProcessPlayerAction` → `BroadcastState`), the interrupt timer, per-seat
  redaction, reconnect grace, and `persistMatch`.
- **room_bot.go** — automated seats: any seat without a connected human plays through its
  policy (seat override → room default → heuristic), with a human-paced delay and a circuit
  breaker. Prefers `bot.ContextPolicy` and builds a `DecisionContext` with a copy of the raw
  public event log.
- **room_decisions.go** — the paipu v2 decision trace. `snapshotDecision` captures the pre-action
  legal catalog ids and chosen id; `recordDecision` appends the row after the action succeeds;
  `chooseSeatAction` returns the policy's provenance. Every explicit action and pass is traced;
  `READY` acks and timeout auto-resolutions are not.
- **matchmaker.go**, **queue.go**, **private_tables.go** — in-process queues (`fenghua`,
  `chongci-fh`; idempotent join, `409 match_forming` on a late leave) and the private-table
  lifecycle (create → join/seat → mode → start → active). Private tables default to Chongci
  (2000 / bust 0 / 50 hands); classic private tables run as a one-hand match so they reach
  `MATCH_END` and list in history. An RL seat triggers endpoint warmup before start. An active
  table maps `tableId → matchId + participants`, so participants rejoin and outsiders get 409.
  WebSocket `lobby_update` envelopes carry the full `PrivateTableState` JSON under `room`.
- **paipu.go**, **replay_history.go** — paipu read path (`loadPaipuJSON`: in-memory store →
  `paipu_records` → `matches.paipu_json` → checked-in fixtures) and the cursor-paginated account
  replay list (completed, owned matches only).
- **review.go**, **review_ratelimit.go** — policy report build/cache (see below).
- **replay_imports.go**, **replay_study.go** — private paipu imports (≤ 10 MiB, deduplicated per
  account) and resumable study jobs (30-minute budget, 90-second renewable lease, cancel/resume;
  each attempt has its own worker id so a cancelled worker cannot overwrite a resumed one).
- **calc.go**, **shanten.go** — stateless calculator endpoints, isolated from rooms so rules bugs
  reproduce without a match.
- **buildinfo.go** — `ServerCommit`, stamped via `-ldflags` from the Dockerfile's `GIT_COMMIT`
  build arg (Zeabur does not pass it, so production paipu record `unknown`).
- **response.go** — `respondError` / `abortError`, the single `{"error": msg}` shape.

## Invariants

- **Redaction fails closed.** `redactedStateForSeat` hides other seats' concealed tiles behind
  fake ids (≥ 1000, `SUIT_UNKNOWN`) re-randomized per recipient per broadcast, drops their
  `valid_actions` and `shanten`, and clears `wall_seed`. Hands reveal at `ROUND_END`/`MATCH_END`.
  Discards keep real ids. Only `MAHJONG_DEV_REVEAL_HANDS=1` (`make dev`) disables it — never in a
  container or deployment.
- **Persistence.** `persistMatch` runs once at room shutdown with retries: status `completed` at
  `MATCH_END`, otherwise `aborted` (`drained` or `abandoned`), the in-progress hand kept via
  `Snapshot`. It stamps the paipu v2 header, reconciles each RL seat's label with the checkpoints
  that actually served it (`reconcileRLPolicyIDs`), and writes `MatchPlayer` rows. SIGTERM drains
  active rooms (`DrainActiveRooms`); new starts during a drain get 503.
- **Seats.** Close code `4000` releases a human seat immediately; an ordinary disconnect keeps it
  for the grace period. When the last human leaves, the room shuts down instead of playing on
  bot-only. Rooms send `UnbindRoom` on shutdown so the Hub never rejoins a dead room.
- **RL warmup gate.** `StartPrivateTable` warms every configured policy endpoint (25 s budget)
  with the table lock released, then re-validates the seat config. Warmup failure → 503 (table
  stays configuring); a config change meanwhile → 409. The 503 body never names the endpoint.
- **Review cache.** `POST /matches/:id/review` resolves the served checkpoint sha from `/healthz`
  and reads the `(match, sha)` row; a miss builds and stores under that sha; an unknown sha falls
  back to the newest row. `?force=1` always rebuilds. Builds are single-flighted per match and
  limited to two at once. Status codes: 503 no `POLICY_SERVER_URL`, 404 no paipu, 422
  unreviewable paipu, 502 policy-server failure (including a 403 because `POLICY_SERVER_TOKEN`
  does not match the server's `FH_MJ_EVALUATE_TOKEN`).
- **Review event window.** `REVIEW_EVENT_WINDOW` wins; otherwise `RL_AGENT_EVENT_WINDOW` is
  inherited only when `POLICY_SERVER_URL` names the same service as the RL endpoint. An invalid
  value means 0, never a clamp. The encoder and the client must use the same window.
- **Training reads.** Any future training-data extractor must read server-recorded
  `matches.paipu_json` from Postgres directly — never `loadPaipuJSON`, which an admin upload can
  override.
- The interrupt timer is armed at 1 hour (disabled for UI testing); its goroutine calls
  `ResolveInterrupts()` directly, outside the room loop.
- Use the shared `tiles` package for face keys, indices, and clones.

## Tests

`room_remote_test.go` has a skipped-by-default live test: set
`FH_MAHJONG_REMOTE_POLICY_TEST_URL=http://127.0.0.1:8765/act` with a policy server running.
`replay_study_test.go` has an opt-in browser harness (`FH_REVIEW_BROWSER=1`, SQLite at
`/tmp/fh-review-browser.sqlite`, a real policy server); CI skips it.
