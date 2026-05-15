# Private Table — AI Seats

## Context

The platform supports two paths to a match today: public matchmaking
(`/api/v1/matchmaking/join`, waits for 4 humans) and private tables
(`/api/v1/matchmaking/join-table`, also waits for 4 humans in a per-`tableId`
queue, watched by `StartPrivateTableWatcher`). A heuristic bot already exists
(`bot/heuristic.go`) and `Room.advanceAutomatedSeats()` already drives any
seat with no connected client through that bot — but there is no entry point
for a player to actually start a match against bots without first finding
three other humans.

This spec adds AI seats as a first-class concept in the private-table flow.
The same `/table/:tableId` waiting room becomes a configuration screen: any
of the four seats can be a human (waiting to join) or an AI (chosen by the
host with a difficulty). Public matchmaking is untouched.

## Goals

- A single player can start a match by filling the other three seats with AI.
- A mixed table (e.g. 2 humans + 2 AI) is equally supported.
- The AI policy is selectable per seat, behind a `Difficulty` enum so a future
  RL policy can replace the heuristic without changing any UI, REST, or room
  wiring code.
- The waiting-room UX is unified: there is no separate "practice" route.

## Non-Goals

- No RL policy implementation. The enum has a single member
  (`DIFFICULTY_HEURISTIC`) at ship time. RL slots are added later when a
  trained checkpoint exists.
- Public matchmaking flow is unchanged.
- No seat-wind selection, no wall-seed input, no ruleset selector.
- No kicking of human participants. Host can only modify empty or AI seats.

## User-Facing Flow

1. Player opens `/create-room`, generates a shareable URL (existing behavior).
2. Player navigates to `/table/:tableId`. They become the **host** (first
   joiner of that `tableId`) and are auto-seated at seat 0.
3. The waiting room renders four seat cards. Seats 1–3 are `empty`.
4. As friends open the same URL, they claim the lowest empty human-allowed
   seat. All participants see live updates.
5. The host can convert any empty seat to AI via "Add AI ▾" (difficulty
   dropdown: Heuristic). The host can change difficulty on an existing AI
   seat or remove it back to empty.
6. Non-host participants see seat state read-only.
7. Once all four seats are filled (any mix of human + AI), the host's "Start
   Match" button enables. Clicking it creates the underlying `Room`, binds
   the human participants via the Hub, and broadcasts a `state: "started"`
   update. Every participant's client redirects to `/game/:matchId`.
8. The match itself runs through the existing engine + bot loop — AI seats
   are driven by `advanceAutomatedSeats()` exactly as empty seats are today.

## Architecture

### Proto (`proto/game.proto`)

New enum and messages used by both REST responses and the WebSocket
`lobby_update` payload.

```proto
enum Difficulty {
  DIFFICULTY_UNSPECIFIED = 0;
  DIFFICULTY_HEURISTIC = 1;
}

message SeatConfig {
  string kind = 1;              // "empty" | "human" | "bot"
  uint32 user_id = 2;           // populated when kind == "human"
  string username = 3;          // populated when kind == "human"
  Difficulty difficulty = 4;    // populated when kind == "bot"
}

message PrivateTableState {
  string table_id = 1;
  uint32 host_user_id = 2;
  repeated SeatConfig seats = 3;  // exactly 4
  string state = 4;               // "configuring" | "started"
  string match_id = 5;            // empty until state == "started"
}
```

Regenerate Go and TypeScript bindings per the project's documented `protoc`
commands. Python bindings are not touched.

### Bot policy factory (`bot/`)

`Room.BotPolicy` is currently a single `bot.Policy` applied to every empty
seat. Replace with a per-seat lookup so each AI seat can use a different
policy in the future.

- Add a thin Go-side `Difficulty` type (alias of `pb.Difficulty`) so the
  `bot` package does not import server-only code.
- Add a factory:
  ```go
  func NewPolicy(d pb.Difficulty) (Policy, error)
  ```
  Today it returns `&HeuristicPolicy{}` for `DIFFICULTY_HEURISTIC` and
  `(nil, err)` for every other value (including `UNSPECIFIED`).
- Existing `NewHeuristicPolicy()` stays for the rare callers (tests, CLI)
  that want the concrete type.

### Private-table registry (`api/`)

The per-`tableId` Redis-style queue (`InMemoryQueue` key `table:<id>`) and
the `StartPrivateTableWatcher` polling loop are **removed**. They are
replaced with an explicit slot-based registry on `Matchmaker`:

```go
type PrivateTable struct {
    TableID     string
    HostUserID  uint
    Seats       [4]SeatConfig         // kind/userId/username/difficulty
    State       string                // "configuring" | "started"
    MatchID     string                // set on start
    mu          sync.Mutex
}
```

A new `Matchmaker.privateTables map[string]*PrivateTable` (separate from the
existing `activePrivateTables` map, which keeps tracking running matches for
reconnect routing). Lifecycle:

- `configuring`: created on first join, mutated by the host's seat changes.
- `started`: `MatchID` populated, `ActivePrivateTable` registered, `Room`
  dispatched to the Hub. Entry stays in the map only long enough to handle
  the final broadcast, then is removed.

`SeatConfig` is the Go mirror of the proto message (the JSON broadcast on
`lobby_update` uses the proto's JSON shape).

### REST endpoints (`api/`)

All routes are JWT-protected. The `/api/v1/matchmaking/join-table` route is
removed; new routes take its place.

| Method | Path | Body | Notes |
|--------|------|------|-------|
| `POST` | `/api/v1/private-tables/:tableId/join` | `{}` | First caller becomes host and claims seat 0. Subsequent humans claim the lowest empty seat. Idempotent for callers already seated (returns current state). Returns `PrivateTableState`. |
| `GET`  | `/api/v1/private-tables/:tableId` | — | Returns current `PrivateTableState`. Used on mount/reconnect. 404 if the table doesn't exist. |
| `POST` | `/api/v1/private-tables/:tableId/seat` | `{seat: 0-3, kind: "empty" \| "bot", difficulty?: Difficulty}` | Host only (403 otherwise). 400 if the target seat is held by a human. `bot` requires a valid difficulty; the handler validates via `bot.NewPolicy`. Returns updated state and broadcasts `lobby_update`. |
| `POST` | `/api/v1/private-tables/:tableId/start` | `{}` | Host only. 400 if any seat is `empty` or the table is already `started`. Creates the `Room`, marks `state: "started"`, broadcasts a final update with `match_id`. |

Every state-changing endpoint, on success, pushes a `lobby_update` JSON
message (existing channel, existing frontend listener) carrying the full
`PrivateTableState`.

### Room construction

`Matchmaker.startPrivateTable(tableID)`:

1. Lock the `PrivateTable`. Verify caller is host, state is `configuring`,
   all four seats are non-empty.
2. Build `seatPolicies := map[uint32]bot.Policy{}`. For each AI seat, call
   `bot.NewPolicy(seat.Difficulty)`; abort with 400 on factory error.
3. Generate `matchID`. Persist `models.Match` (as today).
4. Construct the `Room`:
   - `Engine`, `Hub`, `DB`, `TileObfuscationMap`, channels: unchanged.
   - `SeatPolicies` field replaces `BotPolicy`.
   - `Seats` map starts empty; populated by `Hub.BindRoom` for humans.
5. Register `ActivePrivateTable` with the human user IDs (reconnect routing
   stays correct for the in-progress match).
6. Dispatch `Hub.BindRoom <- RoomBind{UserIDs: humanUserIDs, Room: room}`.
7. Mark the registry entry `state = "started"`, store `MatchID`, broadcast
   the final `lobby_update`. Remove the registry entry after broadcast.

`Room.advanceAutomatedSeats()` keeps its current shape. A seat is
"automated" iff `r.Seats[seat]` is unset; the policy used for that seat is
`r.SeatPolicies[seat]`. If a configured AI seat is missing from
`SeatPolicies` (shouldn't happen — defensive only), the room logs and falls
back to `HeuristicPolicy{}`.

`registerPaipuPlayers()` includes the difficulty in the placeholder bot
display name (e.g. `"Bot 2 (Heuristic)"`) so replays show what the human
was up against.

### Frontend — `Table.tsx`

Replace the current "waiting for 4 players" view with state-driven seat
config.

- **Mount**: `GET /api/v1/private-tables/:tableId`. If 404, call
  `POST .../join`. Persist the returned state into a `useState`.
- **Live updates**: subscribe to `lobby_update` for the current `tableId`.
  Payload is `PrivateTableState` JSON. Replace local state on each tick.
- **Redirect**: when `state === "started"`, navigate to
  `/game/:match_id` (same as today).

Seat cards (four, fixed positions matching the existing table layout):

- `empty`: "Waiting for player". If viewer is host, "Add AI ▾" dropdown
  (Heuristic only at ship time).
- `human`: username, plus "Host" badge if `user_id === host_user_id`.
- `bot`: "AI — Heuristic". If viewer is host, "Change ▾" and "Remove"
  controls.

Footer (host only):

- "Start Match" button. Disabled until all four seats are non-empty. Calls
  `POST .../start`; the redirect is driven by the broadcast `state:
  "started"`, not the response.

`CreateRoom.tsx` is unchanged. `privateRoomSession.ts` is unchanged — it
only persists reconnect identity, not table contents.

## Data Flow Summary

```
Host opens /table/X
    └─> POST /private-tables/X/join
        └─> Matchmaker creates PrivateTable, host=seat0
        └─> lobby_update broadcast
            └─> All participants render seat cards

Host configures seat 1 = AI Heuristic
    └─> POST /private-tables/X/seat
        └─> Matchmaker validates host, mutates seat
        └─> lobby_update broadcast

Friend opens /table/X
    └─> POST /private-tables/X/join (claims seat 2)
    └─> lobby_update broadcast

Host clicks Start (after seats 0,1,2,3 all non-empty)
    └─> POST /private-tables/X/start
        └─> Matchmaker builds SeatPolicies
        └─> Creates Room, persists Match, dispatches BindRoom
        └─> lobby_update broadcast with state=started, match_id
            └─> Each client navigates to /game/<match_id>

Live match
    └─> Existing engine loop
        └─> advanceAutomatedSeats() picks SeatPolicies[seat] per AI seat
```

## Error Handling

- `bot.NewPolicy(UNSPECIFIED)` or unknown difficulty → 400 from the seat or
  start endpoint, surfaced as a toast in the frontend.
- Non-host attempts seat/start → 403. Frontend disables the controls but
  the server is the source of truth.
- Start with any empty seat → 400.
- Concurrent host actions: each `PrivateTable` has a mutex; mutations are
  serialized. Stale optimistic UI is corrected by the next `lobby_update`.
- WebSocket disconnect while configuring: state is server-held, so a
  reconnect + `GET` recovers cleanly.

## Testing

### Bot (`bot/`)

- `NewPolicy(DIFFICULTY_HEURISTIC)` returns a usable `*HeuristicPolicy`.
- `NewPolicy(DIFFICULTY_UNSPECIFIED)` returns an error.
- `NewPolicy(<unknown int>)` returns an error.

### API (`api/`)

Integration tests in the spirit of `private_table_test.go` and
`room_bot_test.go`:

- First joiner becomes host at seat 0; second joiner claims seat 1.
- Host can set/clear an AI seat; non-host gets 403.
- Cannot start with any empty seat (400).
- 1 human + 3 AI: start succeeds, `Room` runs to round end through
  `advanceAutomatedSeats`.
- 2 humans + 2 AI: start succeeds, both humans are bound via Hub, both
  AI seats use the configured difficulties.
- `lobby_update` carries the full seat state after each mutation.
- Removed: the queue-based `JoinPrivateTable` and `StartPrivateTableWatcher`
  tests. Replaced by registry-based equivalents.

### Frontend

No new automated test framework. Manual verification:

- Single-tab solo flow (1 human + 3 AI start to game).
- Two-tab mixed flow (2 humans + 2 AI, with host configuring from tab A).
- Non-host tab cannot mutate seats (controls absent).
- Reload during configuring restores the same state.

## Migration

- The old `/api/v1/matchmaking/join-table` endpoint and the
  `StartPrivateTableWatcher` polling loop are deleted in the same change
  set. The new `/api/v1/private-tables/...` routes replace them.
- `Room.BotPolicy` field is removed in favor of `Room.SeatPolicies`. Tests
  that previously set `BotPolicy` are updated to populate `SeatPolicies`.
- `activePrivateTables` (reconnect routing) is unchanged.

## Future Extensions (out of scope here)

- Adding `DIFFICULTY_RL_*` values: append to the proto enum, register them
  in `bot.NewPolicy`, and the frontend dropdown picks them up.
- Difficulty display localization (Chinese/English) on the seat card.
- Letting the host swap their own seat order (seat-wind choice).
