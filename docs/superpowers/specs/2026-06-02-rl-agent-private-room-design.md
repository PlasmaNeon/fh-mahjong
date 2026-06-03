# RL Agent as a Per-Seat Option in the Private Room

**Date:** 2026-06-02
**Status:** Approved design, ready for implementation planning

## Goal

Let a private-room host assign a **trained RL agent** to a seat, alongside the
existing rule-based **Heuristic** bot. The option appears only when the server
is configured with a trained-policy endpoint.

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
- **Availability:** **Hide unless available.** The option is only offered (and
  only accepted by the seat endpoint) when the server has a trained endpoint
  configured. Availability is a server-wide capability, not per-room.
- **Endpoint reuse:** Reuse the existing `AI_BOT_POLICY_URL` as the single
  switch. The RL seat and matchmaking bots point at the same trained endpoint;
  no separate private-room endpoint.

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
- A way to report whether RL is available (e.g. `RLAgentAvailable() bool`),
  true iff a trained endpoint is configured.

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

In `cmd/server/main.go`, when `AI_BOT_POLICY_URL` is set, install a resolver:

- `DIFFICULTY_RL` → `remote.NewHTTPPolicy(url)` (heuristic fallback built in).
- everything else → `bot.NewPolicy(d)`.

and mark RL as available. When the env var is unset, leave `SeatPolicyResolver`
nil (heuristic-only) and RL unavailable. This mirrors the existing
`BotPolicyFactory` injection pattern and keeps `bot.NewPolicy` pure.

### 3. Backend — wire the resolver into the private-room paths

- **Start loop** (`api/matchmaker.go`, currently `bot.NewPolicy(s.Difficulty)`):
  use `m.resolveSeatPolicy(s.Difficulty)`. A seat asking for RL is wired to the
  remote policy when configured, errors otherwise.
- **Seat validation** (`api/private_tables.go handlePrivateTableSeat`, currently
  `bot.NewPolicy(req.Difficulty)`): use `s.Matchmaker.resolveSeatPolicy(...)`.
  An RL seat is accepted only when RL is available; otherwise the handler
  returns 400.

Existing matchmaking behavior (room-wide `BotPolicyFactory` from
`AI_BOT_POLICY_URL`) is unchanged.

### 4. Backend — capabilities endpoint

New public route `GET /api/v1/config` returning:

```json
{ "rlAgentAvailable": true }
```

sourced from the matchmaker's RL-available signal. Public (no auth), alongside
the other public `/api/v1` routes. This is what lets the frontend hide the
option when no endpoint is configured.

### 5. Frontend — surface the option and label seats correctly

- `web/src/pages/Table.tsx`: fetch `/api/v1/config` once on mount, hold
  `rlAgentAvailable` in state, pass it down to each `SeatCard`.
- `web/src/pages/SeatCard.tsx`:
  - `DIFFICULTY_OPTIONS` always includes `{ value: HEURISTIC, label: 'Heuristic' }`;
    includes `{ value: DIFFICULTY_RL, label: 'RL Agent' }` only when
    `rlAgentAvailable`. The existing map renders an "Add AI · RL Agent" button
    next to "Add AI · Heuristic".
  - Fix the seat display, which currently hardcodes `AI · Heuristic`, to show
    the seat's actual difficulty (`AI · Heuristic` / `AI · RL Agent`).

## Data Flow

1. Host opens room → `Table.tsx` fetches `/api/v1/config` → learns
   `rlAgentAvailable`.
2. `SeatCard` shows "Add AI · Heuristic" always; "Add AI · RL Agent" only when
   available.
3. Host clicks "Add AI · RL Agent" → `POST /rooms/:id/seat` with
   `difficulty = DIFFICULTY_RL` → server validates via `resolveSeatPolicy` (ok
   because RL available) → seat stored as a bot with that difficulty.
4. Host hits Start → matchmaker builds that seat's policy via
   `resolveSeatPolicy(DIFFICULTY_RL)` → remote HTTP policy → trained checkpoint,
   with heuristic fallback if a call fails.

## Error Handling

- RL requested while unavailable → `/seat` returns 400. (The button is not shown
  in that case anyway.)
- Trained endpoint down mid-match → existing per-decision heuristic fallback in
  `bot/remote/http_policy.go` takes over; the match never stalls.

## Testing

- **Go**
  - `resolveSeatPolicy` returns a remote policy for `DIFFICULTY_RL` when a
    resolver is installed, and an error when it is not.
  - `handlePrivateTableSeat` accepts `DIFFICULTY_RL` only when RL is available;
    rejects with 400 otherwise.
  - `GET /api/v1/config` reflects the RL-available flag in both states.
  - Existing `bot.NewPolicy` / heuristic tests unchanged.
- **Frontend**
  - `SeatCard` renders the "RL Agent" button only when `rlAgentAvailable`.
  - Seat label renders the correct text per difficulty.

## Out of Scope

- A separate trained endpoint for the private room (reuses `AI_BOT_POLICY_URL`).
- Per-room or per-user RL availability (capability is server-wide).
- Choosing among multiple checkpoints from the UI (the served checkpoint is set
  when `serve_policy.py` starts).
- Standing up new serving infrastructure (already exists).
