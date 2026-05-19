# Chongci Match Mode

## Context

The platform's match loop today is "endless hands": `core.Game` deals a hand,
plays it out, records the round result, and — once all four players press
Ready — calls `startNextRound()` which picks a fresh random dealer and deals
again. There is no concept of a "match end"; sessions only stop when a player
disconnects or the operator kills the room. Player scores are initialized to
a hardcoded `25000` in `core.NewGame` and persist across hands.

Chongci ("冲刺") is a meta-game mode layered on top of the existing Fenghua
ruleset. It models a bust-out tournament: every player starts with a small
configurable stack (default 2000), hands run consecutively, the winner of
each hand becomes dealer of the next, and the match terminates as soon as
any player's stack drops to or below a configurable threshold (default 0)
or a configurable hand-cap is reached.

Chongci does not change tile rules or per-hand scoring — those stay
delegated to the `RuleEngine` plugin. It changes who deals, how players
start, and when the match terminates.

## Goals

- A "Chongci" match-mode flag exists end-to-end (proto, engine, API,
  frontend) alongside the current default mode.
- Hosts of private tables can pick Chongci and customize starting score,
  bust threshold, and hand-cap.
- A new public matchmaking queue (`queue:chongci-fh`) offers Chongci with
  fixed defaults (starting score 2000, threshold 0, hand-cap 50).
- The engine is the single source of truth for dealer succession,
  end-of-match detection, and final standings. The API and frontend just
  observe and broadcast.
- Default classic mode is unchanged. Existing matches behave exactly as
  before with no migration step.

## Non-Goals

- No new tile-scoring rules. Fenghua hometown rules govern each hand
  exactly as today.
- No "rematch with same players" button. End-of-match overlay has a single
  `Leave` action.
- No mid-hand bust trigger. The bust check runs only after a hand's
  payouts have been applied.
- No double-ron handling. Fenghua's `ResolveInterruptPriority` already
  returns a single winner; that winner becomes next dealer.
- No spectator / observer support for Chongci specifically (no observer
  view exists today).
- No localization. Chongci-specific strings ship in English; a later i18n
  pass will pick them up.
- No customizable settings on the public queue. Players who want custom
  settings use private tables.

## User-Facing Flow

### Private table (host-driven)

1. Host opens `/table/:tableId` and is auto-seated at seat 0 (existing
   behavior).
2. A new "Match Mode" section above the seat cards offers a radio:
   `Classic` (default) | `Chongci`.
3. Selecting `Chongci` reveals three inputs:
   - `Starting points` (default 2000, range [100, 1_000_000])
   - `Bust threshold` (default 0, must be `< starting_points` and `>=
     -1_000_000`)
   - `Max hands` (default 50, range [0, 200]; `0` displays as "No limit")
4. Friends or AI fill the remaining three seats (existing flow).
5. Host clicks `Start Match`. The match runs as today, except:
   - All four players start at the configured starting score.
   - The first hand's dealer is random (as today).
   - Each subsequent hand's dealer is the previous hand's winner; on a
     draw, the current dealer keeps the seat (renchan, no honba bonus).
   - As soon as a hand's payouts leave any player at or below the bust
     threshold — or the hand-cap is reached — the match terminates and a
     final-standings overlay appears for every participant.
6. The overlay shows ranked final scores with `Leave` returning to lobby.

### Public queue (defaults)

1. Lobby exposes a second "Quick Match — Chongci" button.
2. Clicking it enqueues the player on `queue:chongci-fh` (parallel to the
   existing `queue:hometown`).
3. When four players are matched, a Chongci match is constructed with
   `{starting_score: 2000, bust_threshold: 0, max_hands: 50}`.
4. The in-game and end-of-match experience is identical to the private-
   table Chongci flow.

## Architecture

### Proto (`proto/game.proto`)

```proto
enum MatchMode {
  MATCH_MODE_UNSPECIFIED = 0;
  MATCH_MODE_CLASSIC = 1;   // Endless hands, random dealer per hand (today)
  MATCH_MODE_CHONGCI = 2;   // Bust-out match, dealer succession to winner
}

message ChongciConfig {
  int32 starting_score = 1;   // Default 2000 on public queue
  int32 bust_threshold = 2;   // Match ends when any player score <= this
  uint32 max_hands = 3;       // 0 = unbounded
}

message PlayerStanding {
  uint32 seat = 1;
  uint32 rank = 2;            // 1-based; tied players share rank
  int32 final_score = 3;
  int32 net_change = 4;       // final_score - starting_score
}

message MatchEndResult {
  string reason = 1;          // "bust" | "hand_cap"
  uint32 final_hand_num = 2;
  repeated PlayerStanding standings = 3;  // length 4, sorted by score desc
}

enum GamePhase {
  // ...existing values...
  PHASE_MATCH_END = 5;        // Terminal; no further hands will start
}

message GameState {
  // ...existing fields...
  MatchMode match_mode = 21;
  ChongciConfig chongci_config = 22;     // set iff match_mode == CHONGCI
  MatchEndResult match_end_result = 23;  // set iff phase == PHASE_MATCH_END
}
```

`PrivateTableState` (from the prior private-tables spec) gains two fields:
`match_mode` and `chongci_config`, populated by the registry whenever the
host changes them.

Regenerate Go and TypeScript bindings per the project's documented
`protoc` commands.

### Engine (`core/game.go`)

**Parameterized `NewGame`.** Replace the hardcoded `Score: 25000` with a
caller-provided starting score:

```go
type MatchOptions struct {
    Mode          pb.MatchMode      // default MATCH_MODE_CLASSIC
    ChongciConfig *pb.ChongciConfig // required iff Mode == CHONGCI
}

func NewGame(matchID string, rules RuleEngine, opts MatchOptions) *Game
```

For `MATCH_MODE_CLASSIC` (the zero value), starting score remains `25000`
to preserve current behavior. For `MATCH_MODE_CHONGCI`, every player
starts at `opts.ChongciConfig.StartingScore` and the validated config is
copied onto `g.State.ChongciConfig`.

All existing callers (tests, RL env, API matchmaker for classic queue)
pass `MatchOptions{}` to keep current behavior.

**Next-dealer override.** Add a counterpart to the existing
`wallSeedOverride` so the API/engine can deterministically set the next
hand's dealer:

```go
type Game struct {
    // ...existing fields...
    nextDealerOverride *uint32  // consumed once by dealTiles()
}

func (g *Game) SetNextDealer(seat uint32) { g.nextDealerOverride = &seat }
```

In `dealTiles()`, before the existing `dealer := mt.GenU32() % 4` line:

```go
var dealer uint32
if g.nextDealerOverride != nil {
    dealer = *g.nextDealerOverride
    g.nextDealerOverride = nil
} else {
    dealer = mt.GenU32() % 4
}
```

**Round-end → next-hand transition.** Every site that currently writes
`g.State.PlayerReady = []bool{false, false, false, false}` is replaced
with a call to a new `finalizeRoundEnd()`:

```go
func (g *Game) finalizeRoundEnd() {
    if g.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
        if g.State.RoundResult != nil {
            if g.State.RoundResult.IsDraw {
                g.SetNextDealer(g.currentDealerSeat())  // renchan
            } else {
                g.SetNextDealer(g.State.RoundResult.WinnerSeat)
            }
        }
        if g.shouldEndChongciMatch() {
            g.State.Phase = pb.GamePhase_PHASE_MATCH_END
            g.State.MatchEndResult = g.computeMatchEndResult()
            g.recordMatchEnd()
            return
        }
    }
    g.State.PlayerReady = []bool{false, false, false, false}
}

func (g *Game) shouldEndChongciMatch() bool {
    cfg := g.State.ChongciConfig
    for _, p := range g.State.Players {
        if p.Score <= cfg.BustThreshold {
            return true
        }
    }
    if cfg.MaxHands > 0 && g.State.HandNum >= cfg.MaxHands {
        return true
    }
    return false
}
```

`currentDealerSeat()` returns the seat whose `SeatWind == 1` (East).
`computeMatchEndResult()` sorts seats by score descending and assigns
1-based ranks, with tied players sharing the same rank (e.g.
`{1, 1, 3, 3}` if both pairs are tied). `recordMatchEnd()` writes the
result into the paipu footer (one-line schema addition; not load-bearing
for this design).

`startNextRound()` is unchanged in body — it only runs when
`finalizeRoundEnd()` chose not to end the match. The dealer override
already in place is consumed inside `dealTiles()`.

**Action gating.** `handleReadyAction` returns an error if
`g.State.Phase == PHASE_MATCH_END`. `Rules.GetValidActions` is wrapped by
the engine to return an empty list in that phase, so no further player
input is solicited.

**RL env.** `EnvStepResponse.terminated` and `EnvResetResponse.terminated`
become `true` when `phase == PHASE_MATCH_END`. Classic-mode trajectories
continue to be non-terminating, matching today's behavior.

### Private-table registry (`api/`)

Extend the existing `PrivateTable` struct:

```go
type PrivateTable struct {
    TableID       string
    HostUserID    uint
    Seats         [4]SeatConfig
    State         string
    MatchID       string

    MatchMode     pb.MatchMode        // CLASSIC if unset
    ChongciConfig *pb.ChongciConfig   // non-nil iff MatchMode == CHONGCI

    mu            sync.Mutex
}
```

`PrivateTableState` (the JSON broadcast on `lobby_update`) gains
`match_mode` and `chongci_config`, matching the proto.

### REST endpoints (`api/`)

The existing `/join`, `GET`, `/seat`, and `/start` endpoints are unchanged
in shape. One new endpoint is added:

| Method | Path | Body | Notes |
|--------|------|------|-------|
| `POST` | `/api/v1/private-tables/:tableId/mode` | `{mode: "classic" \| "chongci", chongci_config?: {starting_score, bust_threshold, max_hands}}` | Host only (403 otherwise). Only allowed while `state == "configuring"` (409 otherwise). Validates and stores; broadcasts `lobby_update`. |

Validation (400 on failure):

- `mode == "chongci"` requires `chongci_config`.
- `starting_score` ∈ [100, 1_000_000].
- `bust_threshold` < `starting_score` and ≥ -1_000_000.
- `max_hands` ∈ [0, 200] (0 means unbounded).

Two new typed sentinels join the existing set in `private_tables.go`:

- `ErrModeLocked` → `409` ("cannot change mode after match has started").
- `ErrChongciConfigInvalid` → `400` (carries the specific failing field
  in the error body).

`/start` reads `MatchMode` and `ChongciConfig` off the registry and
builds the `MatchOptions` passed to `core.NewGame`. Seat-policy plumbing
and `RoomBind` dispatch are unchanged.

### Public queue (`api/matchmaker.go`)

The existing `JoinQueue(userID, ruleset)` already keys by ruleset string.
A new ruleset key `"chongci-fh"` is registered alongside `"hometown"`,
and `cmd/server` starts a `StartQueueWatcher("chongci-fh")` for it.

`createMatch` gains an internal lookup that maps the queue key to
`MatchOptions`:

- `"hometown"` → `MatchOptions{Mode: CLASSIC}` (call sites unchanged).
- `"chongci-fh"` → `MatchOptions{Mode: CHONGCI, ChongciConfig:
  defaultChongciConfig()}` where defaults are `{starting_score: 2000,
  bust_threshold: 0, max_hands: 50}`.

`models.Match.Ruleset` stores the queue key (`"hometown"` or
`"chongci-fh"`) — sufficient to identify the mode on replay reload.

### Room (`api/room.go`)

`Room` already relays engine state to the Hub on each phase change.
Adding `PHASE_MATCH_END` requires one new behavior: the room is
deregistered from active routing after a 30-second grace window (so
clients can render the final standings before any reconnect 404s).

`ActivePrivateTable` / `activePrivateTables` cleanup is moved to the end
of that window. Existing replay persistence path is unchanged.

### Frontend — `Table.tsx`

A new "Match Mode" section is added above the seat cards:

- Radio (`Classic` / `Chongci`) — host editable, others read-only.
- When `Chongci` is selected, three number inputs appear: `Starting
  points`, `Bust threshold`, `Max hands` (with `0` rendered as "No
  limit").
- Edits call `POST /api/v1/private-tables/:tableId/mode`; validation
  errors surface via the existing toast helper.
- Locked once `state === "started"`.

The existing `lobby_update` listener already replaces local state on
each broadcast — `match_mode` and `chongci_config` ride along on the
existing channel.

### Frontend — lobby (`Lobby.tsx`)

A new "Quick Match — Chongci" button alongside the existing "Quick
Match" button. Clicking it calls the existing matchmaking-join endpoint
with `ruleset: "chongci-fh"`. Same waiting-for-players experience as
classic public matchmaking.

### Frontend — in-match HUD (`Game.tsx`)

The score panel already displays each player's current score. For
Chongci matches:

- Under the hand-counter, add a small badge showing `Chongci · start
  2000 · bust ≤ 0 · cap 50` (values pulled from `state.chongci_config`;
  `cap N` becomes `no cap` when `max_hands == 0`).
- Score cells get a subtle red treatment when a player's score has
  fallen below the starting score and is closer to `bust_threshold`
  than to `starting_score`. Player affordance only; no engine
  implication.

### Frontend — `MatchEndOverlay.tsx`

A new component rendered when `state.phase === PHASE_MATCH_END`:

- Modal layered over the table (table dimmed in the background).
- Title reflects `match_end_result.reason`: "Match Over — Bust" or
  "Match Over — Hand cap reached".
- A 4-row table sorted by `rank`: rank badge, name (or `AI — Heuristic`
  for bot seats), `final_score`, `net_change` (green for positive, red
  for negative).
- Footer: `Leave` button routes to `/lobby`. No rematch button.
- Reconnection: a tab refresh during the overlay hits the existing state
  fetch endpoint, which returns `phase: PHASE_MATCH_END` with the
  populated `match_end_result`, and the overlay re-renders identically.

## Data Flow Summary

```
Host opens /table/X, picks "Chongci", sets starting_score=2000
    └─> POST /private-tables/X/mode
        └─> Registry validates, stores MatchMode + ChongciConfig
        └─> lobby_update broadcast (match_mode, chongci_config)

Host clicks Start (seats filled)
    └─> POST /private-tables/X/start
        └─> Matchmaker builds MatchOptions from registry
        └─> core.NewGame(rules, opts) — all seats start at 2000
        └─> Room dispatched to Hub; first hand begins (random dealer)

Hand ends in a win by seat 2
    └─> Engine applies payouts, sets RoundResult
    └─> finalizeRoundEnd:
        ├─> SetNextDealer(2)
        ├─> shouldEndChongciMatch() == false
        └─> PlayerReady armed for next hand

(All four players ack ready)
    └─> startNextRound → dealTiles consumes nextDealerOverride=2
        └─> Seat 2 deals as East; hand 2 begins

Hand 7 ends with seat 0's score = -300
    └─> finalizeRoundEnd:
        ├─> SetNextDealer(winner)  (not consumed — no further hands)
        ├─> shouldEndChongciMatch() == true (bust)
        ├─> Phase = PHASE_MATCH_END
        └─> MatchEndResult populated, paipu footer written
    └─> Room broadcasts final GameState
        └─> Each client renders MatchEndOverlay
        └─> Room deregistered after 30s grace
```

## Error Handling

- `POST /mode` with invalid config → `400` with structured error body
  identifying the failing field; frontend surfaces as toast.
- `POST /mode` after match has started → `409` (`ErrModeLocked`).
- `POST /mode` by non-host → `403`.
- `POST /start` with `MatchMode == CHONGCI` but no `ChongciConfig` →
  `400` (should be unreachable; defensive).
- `handleReadyAction` while `phase == PHASE_MATCH_END` → error (engine);
  frontend hides the ready button on this phase so the user can't trigger
  it normally.
- Concurrent host mode-changes are serialized by the existing
  `PrivateTable.mu`. The next `lobby_update` corrects any stale
  optimistic UI.
- Disconnect during a Chongci match: existing reconnect path returns the
  current `GameState` (including `MatchMode`, `ChongciConfig`, and
  `MatchEndResult` if applicable). No special handling.

## Testing

### Engine (`core/`)

- `NewGame(opts{Mode: CHONGCI, ChongciConfig: {StartingScore: N, ...}})`
  → all four players start at `N`.
- `NewGame(opts{})` → all four players start at `25000` (classic
  behavior preserved).
- `SetNextDealer(seat)` is consumed exactly once by the next `dealTiles`
  call; a subsequent deal randomizes again.
- Dealer succession on win: simulate a hand where seat 2 wins by tsumo →
  hand 2 dealer == seat 2.
- Dealer succession on draw: simulate an exhaustive draw with dealer at
  seat 1 → hand 2 dealer == seat 1 (renchan).
- `finalizeRoundEnd` transitions to `PHASE_MATCH_END` with
  `reason == "bust"` when any score drops ≤ threshold.
- `finalizeRoundEnd` transitions to `PHASE_MATCH_END` with
  `reason == "hand_cap"` when `HandNum >= MaxHands`.
- Standings computation: all-distinct, two-way tie (1st-1st-3rd-4th),
  four-way tie (1st-1st-1st-1st).
- `handleReadyAction` errors when phase is `PHASE_MATCH_END`.

### API (`api/`)

- Host can set mode = chongci with a valid config; non-host gets 403;
  invalid configs each yield 400 with the specific failing field.
- `POST /mode` after `state == "started"` returns 409.
- `POST /start` with Chongci mode constructs a game whose
  `State.ChongciConfig` matches the registry and whose players start at
  the configured score.
- Public queue `chongci-fh`: four enqueues produce a match with
  `MatchMode == CHONGCI` and the default `ChongciConfig`.
- End-to-end (room-bot test): four heuristic bots with
  `starting_score = 50, bust_threshold = 0`; assert `PHASE_MATCH_END`
  within a bounded number of hands; assert `Reason == "bust"`, exactly
  one player ≤ 0, ranks are well-formed.
- Hand-cap test: `max_hands = 1`; after one hand, assert
  `Reason == "hand_cap"`.

### Frontend

No new automated test framework. Manual verification:

- Single-tab solo flow: 1 human + 3 AI Chongci match driven to bust;
  standings overlay renders with correct ranks.
- Two-tab mixed flow: 2 humans + 2 AI; host configures Chongci settings;
  both tabs see the same lobby_update; non-host tab cannot edit mode or
  settings (controls absent).
- Reload during `state == "configuring"` restores mode + config.
- Reload during `phase == PHASE_MATCH_END` restores the standings
  overlay.
- Public Chongci queue: four browser tabs each click "Quick Match —
  Chongci"; match starts with default config (`2000 / 0 / 50`) shown in
  the in-match HUD.

## Migration

- The `core.NewGame` signature changes from `NewGame(matchID, rules)` to
  `NewGame(matchID, rules, opts MatchOptions)`. All existing call sites
  are updated in the same change set to pass `MatchOptions{}`.
- `models.Match.Ruleset` gains a new accepted value (`"chongci-fh"`); no
  schema change since the column is already a free-form string.
- No data migration is required for existing matches; they were
  recorded with `Ruleset == "hometown"` and replay back with classic
  semantics.

## Future Extensions (out of scope here)

- Localized strings (Chinese for "Chongci", "bust", etc.).
- "Rematch" button on the standings overlay (re-seats same players into
  a fresh match — requires Hub-side flow).
- Multiple preset public queues (e.g. Chongci 1000 / 5000), or
  player-driven matchmaker bucketing.
- Stat tracking across Chongci matches (win/loss rate, average finishing
  rank per user).
- Spectator/observer support for in-progress Chongci matches.
