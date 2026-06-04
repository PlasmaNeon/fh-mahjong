# RL Agent as a Per-Seat Option in the Private Room

**Date:** 2026-06-02
**Status:** Approved design, ready for implementation planning

## Goal

Let a private-room host assign a **trained RL agent** to a seat, alongside the
existing rule-based **Heuristic** bot. The option is always shown so hosts know
it exists, but it is **disabled** until the trained-policy endpoint is reachable.

## Background

The pieces for serving a trained agent already exist:

- `ai/.../scripts/serve_policy.py` serves a checkpoint over JSON HTTP
  (`POST /act` with `{seat, planes, scalars, action_mask}` →
  `{action_id, value, ...}`, plus `GET /healthz`). Checkpoints resolve through
  `ai/checkpoints/best-checkpoints.json`.
- `bot/remote/http_policy.go` (`HTTPPolicy`) sends exactly that request shape,
  parses exactly that response, and falls back to the heuristic policy
  per-decision on any failure.
- `AI_BOT_POLICY_URL` already points the Go server at that endpoint. Today it is
  used **only** for matchmaking bots, applied room-wide via
  `Matchmaker.BotPolicyFactory` / `WithBotPolicy`.

The gap: the private-room path builds each seat's policy with
`bot.NewPolicy(difficulty)` (`api/matchmaker.go` start loop and
`api/private_tables.go` seat validation), and `bot.NewPolicy` only knows
`DIFFICULTY_HEURISTIC`. In a private room, `policyForSeat` checks per-seat
`SeatPolicies` before the room-wide `BotPolicy`, so even with
`AI_BOT_POLICY_URL` set, private-room bots always play heuristic. There is no
way to pick the trained agent per seat.

## Decisions

- **Name:** UI label **"RL Agent"**, proto enum `DIFFICULTY_RL`.
- **Availability:** **Always shown, disabled when unavailable.** The "Add AI ·
  RL Agent" button always appears (so hosts know the option exists) but is
  greyed out and unclickable until the trained policy endpoint is reachable; the
  seat endpoint still rejects RL assignment while unavailable. Availability is a
  server-wide capability, not per-room.
- **Default endpoint + health check (enabled by default):** The RL endpoint
  defaults to `http://127.0.0.1:8765/act` (serve_policy.py's default) when
  `AI_BOT_POLICY_URL` is unset, so the option works out of the box in local
  dev. Availability is determined by a cached probe of the endpoint's
  `GET /healthz`, so defaulting the URL is safe even when no model server is
  running — the option simply stays hidden until one is up.
- **Matchmaking unchanged:** The local default applies **only** to the
  private-room RL agent. Room-wide matchmaking bots (`BotPolicyFactory`) remain
  gated on an explicit `AI_BOT_POLICY_URL` and are unaffected.
- **Graceful start:** Match start builds the RL seat's remote policy
  unconditionally (it falls back to heuristic per-decision). The health gate
  applies to UI visibility and seat assignment, not to starting a match, so a
  transient outage never blocks an already-configured match.

## Design

### 1. Proto — one new enum value

```proto
enum Difficulty {
  DIFFICULTY_UNSPECIFIED = 0;
  DIFFICULTY_HEURISTIC   = 1;
  DIFFICULTY_RL          = 2;  // trained RL agent, served via remote HTTP policy
}
```

Regenerate Go and TS bindings per `proto/AGENTS.md`:

- Go: `protoc --go_out=. --go_opt=paths=source_relative proto/game.proto`
- TS: `web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o
  web/src/proto/game.js proto/game.proto` then
  `web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js`
  (verify `game.Difficulty.DIFFICULTY_RL` is present in the bindings the
  frontend imports).

### 2. Backend — difficulty-aware seat-policy resolver

Add to `Matchmaker`:

- `SeatPolicyResolver func(pb.Difficulty) (bot.Policy, error)` — when nil,
  defaults to `bot.NewPolicy` (heuristic-only).
- `RLAgentAvailable func() bool` — a health-checked probe (nil = unavailable)
  consulted through the nil-safe `rlAgentAvailable()` helper.

Provide a single internal helper the matchmaker uses everywhere a seat policy is
built or validated:

```go
func (m *Matchmaker) resolveSeatPolicy(d pb.Difficulty) (bot.Policy, error) {
    if m.SeatPolicyResolver != nil {
        return m.SeatPolicyResolver(d)
    }
    return bot.NewPolicy(d)
}
```

In `cmd/server/main.go`, the RL endpoint is `AI_BOT_POLICY_URL` if set, else the
local default `http://127.0.0.1:8765/act`. A resolver is always installed:

- `DIFFICULTY_RL` → `remote.NewHTTPPolicy(url)` (heuristic fallback built in).
- everything else → `bot.NewPolicy(d)`.

`RLAgentAvailable` is wired to `remote.NewHealthChecker(url).Healthy`, a cached
probe of `GET /healthz`. The room-wide `BotPolicyFactory` (matchmaking bots)
stays gated on an explicit `AI_BOT_POLICY_URL` and is left nil otherwise.

### 2a. Backend — health checker (`bot/remote/health.go`)

`HealthChecker` derives the `/healthz` URL from the `/act` endpoint, probes it
with a short timeout, and caches the result for a few seconds. `Healthy()` is
nil-safe and concurrency-safe. A connection-refused result is immediate, so the
default endpoint costs nothing when no model server is running.

### 3. Backend — wire the resolver into the private-room paths

- **Start loop** (`api/matchmaker.go`): use `m.resolveSeatPolicy(s.Difficulty)`.
  An RL seat is built unconditionally (graceful — the remote policy falls back
  per-decision), so a transient outage never blocks match start.
- **Seat validation** (`api/private_tables.go handlePrivateTableSeat`): an RL
  seat is rejected with 400 (`errRLAgentUnavailable`) unless
  `rlAgentAvailable()` is currently true; other difficulties are validated via
  `resolveSeatPolicy`.

Existing matchmaking behavior (room-wide `BotPolicyFactory`) is unchanged.

### 4. Backend — capabilities endpoint

New public route `GET /api/v1/config` returning:

```json
{ "rlAgentAvailable": true }
```

sourced from the matchmaker's health-checked `rlAgentAvailable()`. Public (no
auth), alongside the other public `/api/v1` routes. This is what tells the
frontend whether to enable or disable the option.

### 5. Frontend — surface the option and label seats correctly

- `web/src/pages/Table.tsx`: poll `/api/v1/config` every 10s, hold
  `rlAgentAvailable` in state, pass it down to each `SeatCard`. Polling means the
  option enables/disables live as the model server comes up or goes down.
- `web/src/pages/SeatCard.tsx`:
  - `difficultyOptions` always includes both `Heuristic` and `RL Agent`; the
    `RL Agent` entry carries `disabled: !rlAgentAvailable`. The map renders an
    "Add AI · RL Agent" button next to "Add AI · Heuristic", greyed out with an
    explanatory tooltip while unavailable.
  - Fix the seat display, which currently hardcodes `AI · Heuristic`, to show
    the seat's actual difficulty (`AI · Heuristic` / `AI · RL Agent`).

## Data Flow

1. Host opens room → `Table.tsx` polls `/api/v1/config` → learns
   `rlAgentAvailable`.
2. `SeatCard` shows "Add AI · Heuristic" always; "Add AI · RL Agent" always, but
   disabled while unavailable (enables/disables live via polling).
3. Host clicks the enabled "Add AI · RL Agent" → `POST /rooms/:id/seat` with
   `difficulty = DIFFICULTY_RL` → server confirms `rlAgentAvailable()` and
   stores the seat as a bot with that difficulty.
4. Host hits Start → matchmaker builds that seat's policy via
   `resolveSeatPolicy(DIFFICULTY_RL)` → remote HTTP policy → trained checkpoint,
   with heuristic fallback if a call fails.

## Error Handling

- RL requested while unavailable → `/seat` returns 400. (The button is disabled
  in that case anyway.)
- Endpoint down at start → the seat is still built; the remote policy plays
  heuristic per-decision. Start is never blocked.
- Endpoint down mid-match → existing per-decision heuristic fallback in
  `bot/remote/http_policy.go` takes over; the match never stalls.
- Model server comes up or goes down while the host is in the room → the 10s
  `/api/v1/config` poll enables/disables the option live, no refresh needed.

## Testing

- **Go**
  - `resolveSeatPolicy` returns a remote policy for `DIFFICULTY_RL` when a
    resolver is installed, and an error when it is not.
  - `handlePrivateTableSeat` accepts `DIFFICULTY_RL` only when RL is available;
    rejects with 400 otherwise.
  - `GET /api/v1/config` reflects the RL-available flag in both states.
  - Existing `bot.NewPolicy` / heuristic tests unchanged.
- **Frontend**
  - `SeatCard` always renders the "RL Agent" button, disabled when
    `rlAgentAvailable` is false.
  - Seat label renders the correct text per difficulty.

### 6. Backend — autostart the policy server (`cmd/server/policy_autostart.go`)

So the RL agent connects on boot without a separate manual step, the Go server
launches the Python policy server as a managed child process when it is using
the local default endpoint:

- `maybeStartPolicyServer(url)` runs `uv run --project ai fh-mj-serve-policy`
  (overridable via `RL_AGENT_SERVE_CMD`), appending `--host`/`--port` derived
  from the RL endpoint URL and `--checkpoint-id` from `RL_AGENT_CHECKPOINT_ID`
  when set. The child runs in its own process group.
- It is best-effort: disabled when `RL_AGENT_AUTOSTART=0`, skipped when the
  launcher binary (`uv`) is absent or `AI_BOT_POLICY_URL` is set (operator runs
  their own server), and never fatal. On any failure the RL option just stays
  disabled, governed by the health check.
- `installSignalCleanup` terminates the child process group on SIGINT/SIGTERM so
  a Ctrl-C never orphans uv/python.
- The existing health check + 10s frontend poll flip the option to enabled a few
  seconds after the model finishes loading.

**Caveat:** autostart targets local/dev runs where `uv` and the `ai/` project
are present. The production Docker image is Go-only (no Python), so the child
won't launch there — use the containerized policy service below instead.

### 7. Containerized full stack (`ai/Dockerfile`, `docker-compose.yml`)

For a fully wired container stack, a `policy` service runs the Python policy
server and the Go `server` service is pointed at it:

- `ai/Dockerfile` — `python:3.12-slim` + `uv sync --frozen` from `ai/uv.lock`;
  entrypoint `fh-mj-serve-policy --host 0.0.0.0 --port 8765`. The checkpoint is
  **not** baked in (the repo only ships the manifest, which references
  training-box paths); compose mounts a host checkpoint dir and passes
  `--manifest`/`--checkpoint`.
- `docker-compose.yml` — `policy` (profile `rl`/`full`) mounts
  `${RL_CHECKPOINT_DIR}` → `/checkpoints:ro`, has a `/healthz` healthcheck, and
  publishes 8765. `server` (profile `full`) builds the Go image and sets
  `RL_AGENT_POLICY_URL=http://policy:8765/act` + `RL_AGENT_AUTOSTART=0`. The
  default `docker compose up` is unchanged (db + redis only);
  `docker compose --profile full up` brings up the wired stack.
- A new env var **`RL_AGENT_POLICY_URL`** points only the RL path at a dedicated
  policy server, independent of `AI_BOT_POLICY_URL` — so matchmaking-bot behavior
  stays unchanged. Endpoint precedence: `RL_AGENT_POLICY_URL` →
  `AI_BOT_POLICY_URL` → local default (the only case that autostarts).
- `.dockerignore` keeps build contexts lean (excludes `node_modules`, venvs,
  mlflow runs) while preserving `web/dist` for the Go `//go:embed`.

### 8. Model hot-reload (`serve_policy.py`)

The policy server holds the active policy in a thread-safe `PolicyHolder` and
exposes `POST /reload` (`{"checkpoint": "/path.pt"}` or `{"checkpoint_id": ...}`)
to swap the served model at runtime — no process or backend restart. Readers
(`/act`, `/healthz`) take the current reference lock-free; a reload only swaps in
the new policy after it loads successfully, so a bad path or architecture
mismatch returns 400 and leaves the previous model serving. `/healthz` reports
the active checkpoint and step.

A thin CLI client, `fh-mj-reload-policy` (`scripts/reload_policy.py`, stdlib-only,
no torch), wraps this: `--status` shows the active model and `--checkpoint`/
`--checkpoint-id` swap it via `/reload`.

## Out of Scope

- A separate trained endpoint for the private room (reuses `AI_BOT_POLICY_URL`).
- Per-room or per-user RL availability (capability is server-wide).
- Choosing among multiple checkpoints from the UI (the served checkpoint is set
  when `serve_policy.py` starts).
- Standing up new serving infrastructure (already exists).
- In-process (Go-native) inference; the model still runs as a Python process,
  now supervised by the Go server in local/dev runs.
