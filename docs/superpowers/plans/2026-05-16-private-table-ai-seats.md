# Private Table — AI Seats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the host of a private table fill empty seats with AI opponents (per-seat difficulty) and start a match without waiting for four humans, in the same `/table/:tableId` waiting room.

**Architecture:** Replace the queue-based private-table flow with a slot-based `PrivateTable` registry on `Matchmaker`. The host configures four seat slots (human or AI) and clicks Start; the server constructs a `Room` whose per-seat `SeatPolicies` map drives any AI seats through the existing `advanceAutomatedSeats()` loop. The frontend `Table.tsx` becomes a state-driven seat-config screen, synced via the existing `lobby_update` WebSocket channel.

**Tech Stack:** Go (Gin, gorilla/websocket, protobuf), TypeScript (React, Vite), Protocol Buffers.

**Spec:** [docs/superpowers/specs/2026-05-15-private-table-ai-seats-design.md](../specs/2026-05-15-private-table-ai-seats-design.md)

---

## File Structure

**Created:**
- `bot/factory.go` — `NewPolicy(pb.Difficulty)` factory.
- `bot/factory_test.go` — factory unit tests.
- `api/private_tables.go` — `PrivateTable` registry + REST handlers.
- `api/private_tables_test.go` — REST + registry integration tests.
- `web/src/pages/SeatCard.tsx` — single seat-card component for the waiting room.

**Modified:**
- `proto/game.proto` — adds `Difficulty` enum, `SeatConfig`, `PrivateTableState`.
- `proto/game.pb.go` — regenerated.
- `web/src/proto/game.js`, `web/src/proto/game.d.ts` — regenerated.
- `bot/heuristic.go` — no behavior change; `NewHeuristicPolicy` retained for direct callers.
- `api/room.go` — `Room.BotPolicy` replaced by `Room.SeatPolicies map[uint32]bot.Policy`; `advanceAutomatedSeats` picks per seat; `registerPaipuPlayers` includes difficulty in placeholder names.
- `api/matchmaker.go` — adds `privateTables` map and lifecycle helpers; removes `JoinPrivateTable` and `StartPrivateTableWatcher`.
- `api/server.go` — replaces `/api/v1/matchmaking/private` registration with the new `/api/v1/private-tables/...` routes.
- `api/room_bot_test.go` — updates references from `room.BotPolicy = …` to `room.SeatPolicies` semantics.
- `web/src/pages/Table.tsx` — rewritten as seat-config screen.
- `web/src/pages/AGENTS.md` — updated description of `Table.tsx`.
- `api/AGENTS.md` — updates room/matchmaker descriptions.
- `bot/AGENTS.md` — adds `factory.go`.

**Deleted from code (not from history):**
- `api/private_table_test.go` — replaced by `api/private_tables_test.go` (the old queue-based tests don't apply to the new flow).
- `Matchmaker.JoinPrivateTable`, `Matchmaker.StartPrivateTableWatcher`, and the queue keys `table:*`.

---

## Task 1: Add proto `Difficulty` enum, `SeatConfig`, `PrivateTableState`

**Files:**
- Modify: `proto/game.proto`

- [ ] **Step 1: Add the new enum and messages**

Append these definitions to `proto/game.proto` near the existing top-level entities (after the `ActionType` block is a natural spot):

```proto
// ---------------------------------------------------------
// Private Table Configuration
// ---------------------------------------------------------

enum Difficulty {
  DIFFICULTY_UNSPECIFIED = 0;
  DIFFICULTY_HEURISTIC = 1;
}

message SeatConfig {
  // "empty" | "human" | "bot"
  string kind = 1;

  // Populated only when kind == "human".
  uint32 user_id = 2;
  string username = 3;

  // Populated only when kind == "bot".
  Difficulty difficulty = 4;
}

message PrivateTableState {
  string table_id = 1;
  uint32 host_user_id = 2;
  // Exactly four entries, indexed 0-3 by seat.
  repeated SeatConfig seats = 3;
  // "configuring" | "started"
  string state = 4;
  // Empty until state == "started".
  string match_id = 5;
}
```

- [ ] **Step 2: Regenerate Go bindings**

Run from the repo root:

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go \
  --go_out=. --go_opt=paths=source_relative proto/game.proto
```

Expected: `proto/game.pb.go` is updated; `go build ./...` still succeeds.

- [ ] **Step 3: Regenerate TypeScript bindings**

Run from the repo root:

```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

Expected: both files updated; `cd web && npm run build` (run later) will still pass.

- [ ] **Step 4: Build to confirm no regression**

```bash
go build ./...
```

Expected: exit code 0, no errors.

- [ ] **Step 5: Commit**

```bash
git add proto/game.proto proto/game.pb.go web/src/proto/game.js web/src/proto/game.d.ts
git commit -m "proto: add Difficulty enum, SeatConfig, PrivateTableState"
```

---

## Task 2: Add `bot.NewPolicy(difficulty)` factory

**Files:**
- Create: `bot/factory.go`
- Create: `bot/factory_test.go`
- Modify: `bot/AGENTS.md`

- [ ] **Step 1: Write the failing test**

Create `bot/factory_test.go`:

```go
package bot

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestNewPolicyHeuristic(t *testing.T) {
	policy, err := NewPolicy(pb.Difficulty_DIFFICULTY_HEURISTIC)
	if err != nil {
		t.Fatalf("NewPolicy(HEURISTIC) returned error: %v", err)
	}
	if policy == nil {
		t.Fatal("NewPolicy(HEURISTIC) returned nil policy")
	}
	if _, ok := policy.(*HeuristicPolicy); !ok {
		t.Fatalf("expected *HeuristicPolicy, got %T", policy)
	}
}

func TestNewPolicyUnspecifiedRejected(t *testing.T) {
	if _, err := NewPolicy(pb.Difficulty_DIFFICULTY_UNSPECIFIED); err == nil {
		t.Fatal("expected error for DIFFICULTY_UNSPECIFIED")
	}
}

func TestNewPolicyUnknownRejected(t *testing.T) {
	if _, err := NewPolicy(pb.Difficulty(99)); err == nil {
		t.Fatal("expected error for unknown difficulty value")
	}
}
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
go test ./bot/ -run TestNewPolicy -v
```

Expected: build error — `NewPolicy` undefined.

- [ ] **Step 3: Implement the factory**

Create `bot/factory.go`:

```go
package bot

import (
	"fmt"

	pb "github.com/plasma/fh-mahjong/proto"
)

// NewPolicy returns the bot Policy implementation for the given difficulty.
// Returns an error for DIFFICULTY_UNSPECIFIED or unknown values so callers
// (e.g. the REST seat handler) can surface a 400 instead of silently
// installing a wrong policy.
func NewPolicy(d pb.Difficulty) (Policy, error) {
	switch d {
	case pb.Difficulty_DIFFICULTY_HEURISTIC:
		return NewHeuristicPolicy(), nil
	default:
		return nil, fmt.Errorf("bot: unsupported difficulty %v", d)
	}
}
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
go test ./bot/ -run TestNewPolicy -v
```

Expected: all three tests pass.

- [ ] **Step 5: Update `bot/AGENTS.md`**

Read the existing file first. Add a `factory.go` bullet beneath the `heuristic.go` and `heuristic_test.go` bullets:

```markdown
- **factory.go** — `NewPolicy(pb.Difficulty)` selects the policy implementation for a seat. Returns an error for unsupported / unspecified difficulty values. Used by `api.Matchmaker` when assembling per-seat policies for a `Room`.
- **factory_test.go** — Coverage for heuristic resolution and rejection of unspecified/unknown difficulty values.
```

- [ ] **Step 6: Commit**

```bash
git add bot/factory.go bot/factory_test.go bot/AGENTS.md
git commit -m "bot: add NewPolicy(difficulty) factory"
```

---

## Task 3: Refactor `Room.BotPolicy` → `Room.SeatPolicies`

**Files:**
- Modify: `api/room.go`
- Modify: `api/room_bot_test.go`
- Modify: `api/AGENTS.md`

- [ ] **Step 1: Replace the `BotPolicy` field with a per-seat map**

In `api/room.go`, locate the `Room` struct (currently at lines 25-47) and replace the `BotPolicy bot.Policy` line. The struct should now contain:

```go
type Room struct {
	ID             string
	PrivateTableID string
	Hub            *Hub
	DB             *gorm.DB
	MatchRecord    *models.Match
	OnShutdown     func()

	Engine     *core.Game
	// SeatPolicies maps a seat index (0-3) to the bot Policy used when that
	// seat is automated (no connected client). Populated at Room construction
	// from the host's PrivateTable seat config. Seats not present in this
	// map fall back to bot.HeuristicPolicy{} (defensive only).
	SeatPolicies map[uint32]bot.Policy
	Seats        map[uint32]*Client // maps 0-3 to active WS connections
	PaipuStore      func(matchID, paipuJSON string) // in-memory fallback when DB is nil
	lastStoredRound uint32

	TileObfuscationMap map[uint32]uint32 // maps real tile IDs to fake IDs for redacting closed hands

	ActionQueue      chan ClientAction
	Shutdown         chan bool
	InterruptChan    chan bool
	TimerResolveChan chan bool // timer goroutine signals main loop to resolve interrupts
	interruptTmr     *time.Timer
	interruptEpoch   uint64 // incremented each interrupt cycle to prevent stale goroutines
}
```

- [ ] **Step 2: Update `NewRoom` to initialize `SeatPolicies` as an empty map**

In `api/room.go`, the `NewRoom` function currently initializes `BotPolicy: bot.NewHeuristicPolicy()`. Replace that line so the constructor becomes:

```go
func NewRoom(matchID string, hub *Hub, db *gorm.DB) *Room {
	ruleset := &rules.HometownRuleset{}

	obfMap := make(map[uint32]uint32)
	fakeIDs := rand.Perm(144)
	for i := 0; i < 144; i++ {
		obfMap[uint32(i)] = uint32(fakeIDs[i]) + 1000
	}

	room := &Room{
		ID:                 matchID,
		Hub:                hub,
		DB:                 db,
		Engine:             core.NewGame(matchID, ruleset),
		SeatPolicies:       make(map[uint32]bot.Policy),
		Seats:              make(map[uint32]*Client),
		TileObfuscationMap: obfMap,
		ActionQueue:        make(chan ClientAction),
		Shutdown:           make(chan bool),
		InterruptChan:      make(chan bool, 1),
		TimerResolveChan:   make(chan bool, 1),
	}

	room.Engine.Recorder = core.NewPaipuRecorder(matchID, "hometown")

	return room
}
```

- [ ] **Step 3: Add a `policyForSeat` helper and route both bot call-sites through it**

Still in `api/room.go`, add after `isAutomatedSeat`:

```go
// policyForSeat returns the bot policy for an automated seat. Configured
// seats use the difficulty-derived policy set at room construction; any seat
// missing from the map defensively falls back to the heuristic baseline so
// the engine never stalls due to a config bug.
func (r *Room) policyForSeat(seat uint32) bot.Policy {
	if p, ok := r.SeatPolicies[seat]; ok && p != nil {
		return p
	}
	return bot.NewHeuristicPolicy()
}
```

Then in `advanceAutomatedSeats`, replace the two `r.BotPolicy.ChooseAction(...)` call-sites:

```go
// In the PHASE_PLAYER_TURN case:
action := r.policyForSeat(seat).ChooseAction(r.Engine.State, seat)

// In the PHASE_WAIT_DISCARDS case:
action := r.policyForSeat(seat).ChooseAction(r.Engine.State, seat)
```

- [ ] **Step 4: Update `registerPaipuPlayers` to include difficulty in bot names**

In `api/room.go`, replace the existing `registerPaipuPlayers` body so the placeholder bot name includes the difficulty when configured:

```go
func (r *Room) registerPaipuPlayers() {
	if r.Engine == nil || r.Engine.Recorder == nil {
		return
	}

	for seat := uint32(0); seat < 4; seat++ {
		if client, ok := r.Seats[seat]; ok && client != nil {
			r.Engine.Recorder.AddPlayer(seat, client.Username, client.UserID)
			continue
		}

		name := fmt.Sprintf("Bot %d", seat+1)
		if _, configured := r.SeatPolicies[seat]; configured {
			name = fmt.Sprintf("Bot %d (Heuristic)", seat+1)
		}
		r.Engine.Recorder.AddPlayer(seat, name, 0)
	}
}
```

(The display name only varies by difficulty kind today; when more difficulties land, this helper can dispatch on the policy's reported label.)

- [ ] **Step 5: Update `api/room_bot_test.go` to populate `SeatPolicies` instead of `BotPolicy`**

Search the file for `room.BotPolicy =` and `BotPolicy:`. Each assignment must be replaced with a `SeatPolicies` setup that mirrors the previous intent.

For example, the existing line `room.BotPolicy = stubPolicy{}` (around line 80) becomes:

```go
stub := stubPolicy{}
room.SeatPolicies = map[uint32]bot.Policy{0: stub, 1: stub, 2: stub, 3: stub}
```

If the test file uses any other `BotPolicy` reference, apply the same transformation. Add `"github.com/plasma/fh-mahjong/bot"` to the imports if needed.

The `TestRegisterPaipuPlayersIncludesBotSeats` test currently expects placeholder names `"Bot 1"`, `"Bot 3"`, `"Bot 4"`. With the difficulty-aware change above, these become `"Bot 1"` etc. when `SeatPolicies` is empty (no AI configured) and `"Bot 1 (Heuristic)"` etc. when populated. The current test does not populate `SeatPolicies`, so its expectations are unchanged. Verify this by running the test after the refactor.

- [ ] **Step 6: Run the bot-related room tests**

```bash
go test ./api/ -run TestAdvanceAutomatedSeats -v
go test ./api/ -run TestRegisterPaipuPlayersIncludesBotSeats -v
go test ./api/ -run TestNewRoomInitializesPaipuRecorder -v
```

Expected: all pass.

- [ ] **Step 7: Run the full Go test suite to catch any other references to `BotPolicy`**

```bash
go test ./...
```

Expected: all pass. If anything still references `BotPolicy`, fix it the same way.

- [ ] **Step 8: Update `api/AGENTS.md`**

In the `room.go` section, locate the existing `BotPolicy` bullet and replace it with:

```markdown
  - `SeatPolicies` — maps each automated seat (0-3) to its bot policy. Populated by the matchmaker from the host's `PrivateTable` seat config. A defensive fallback to `HeuristicPolicy{}` keeps the engine running if a seat is missing from the map.
```

- [ ] **Step 9: Commit**

```bash
git add api/room.go api/room_bot_test.go api/AGENTS.md
git commit -m "api: per-seat bot policies on Room"
```

---

## Task 4: Add `PrivateTable` registry to `Matchmaker`

**Files:**
- Create: `api/private_tables.go`
- Modify: `api/matchmaker.go`

- [ ] **Step 1: Create the registry file with type definitions**

Create `api/private_tables.go`:

```go
package api

import (
	"errors"
	"fmt"
	"sync"

	pb "github.com/plasma/fh-mahjong/proto"
)

// SeatConfig mirrors pb.SeatConfig for in-memory mutation. JSON marshalling
// uses field names that match the proto, so the WebSocket lobby_update
// payload is interchangeable between Go and TypeScript.
type SeatConfig struct {
	Kind       string        `json:"kind"`                 // "empty" | "human" | "bot"
	UserID     uint          `json:"userId,omitempty"`     // human
	Username   string        `json:"username,omitempty"`   // human
	Difficulty pb.Difficulty `json:"difficulty,omitempty"` // bot
}

// PrivateTable holds the configuration of a /table/:tableId waiting room
// before the actual match Room is constructed.
type PrivateTable struct {
	mu sync.Mutex

	TableID    string
	HostUserID uint
	Seats      [4]SeatConfig
	State      string // "configuring" | "started"
	MatchID    string // populated when State == "started"
}

// newConfiguringTable returns a table with all four seats empty.
func newConfiguringTable(tableID string, hostUserID uint) *PrivateTable {
	return &PrivateTable{
		TableID:    tableID,
		HostUserID: hostUserID,
		State:      "configuring",
	}
}

// claimNextHumanSeat assigns the user to the lowest empty seat. Returns the
// seat index. Returns an error if the user is already seated or no empty
// human-allowed seat exists.
func (t *PrivateTable) claimNextHumanSeat(userID uint, username string) (uint32, error) {
	for i, s := range t.Seats {
		if s.Kind == "human" && s.UserID == userID {
			return uint32(i), nil // idempotent
		}
	}
	for i, s := range t.Seats {
		if s.Kind == "" || s.Kind == "empty" {
			t.Seats[i] = SeatConfig{
				Kind:     "human",
				UserID:   userID,
				Username: username,
			}
			return uint32(i), nil
		}
	}
	return 0, errors.New("no empty seat available")
}

// setSeat applies a host seat-config change. The target seat must not be
// held by a human (you can only mutate empty or bot seats).
func (t *PrivateTable) setSeat(seat uint32, kind string, difficulty pb.Difficulty) error {
	if seat > 3 {
		return fmt.Errorf("seat %d out of range", seat)
	}
	current := t.Seats[seat]
	if current.Kind == "human" {
		return errors.New("cannot overwrite a human-held seat")
	}
	switch kind {
	case "empty":
		t.Seats[seat] = SeatConfig{Kind: "empty"}
	case "bot":
		t.Seats[seat] = SeatConfig{Kind: "bot", Difficulty: difficulty}
	default:
		return fmt.Errorf("unsupported seat kind %q", kind)
	}
	return nil
}

// canStart returns nil if all four seats are non-empty.
func (t *PrivateTable) canStart() error {
	for i, s := range t.Seats {
		if s.Kind == "" || s.Kind == "empty" {
			return fmt.Errorf("seat %d is empty", i)
		}
	}
	return nil
}

// normalize fills any zero-value seats with the explicit "empty" kind so
// every serialized payload has four well-formed entries.
func (t *PrivateTable) normalize() {
	for i, s := range t.Seats {
		if s.Kind == "" {
			t.Seats[i] = SeatConfig{Kind: "empty"}
		}
	}
}

// toProto converts the in-memory table to a wire-ready proto message.
// Caller must hold t.mu.
func (t *PrivateTable) toProto() *pb.PrivateTableState {
	t.normalize()
	seats := make([]*pb.SeatConfig, 4)
	for i, s := range t.Seats {
		sc := &pb.SeatConfig{Kind: s.Kind}
		switch s.Kind {
		case "human":
			sc.UserId = uint32(s.UserID)
			sc.Username = s.Username
		case "bot":
			sc.Difficulty = s.Difficulty
		}
		seats[i] = sc
	}
	return &pb.PrivateTableState{
		TableId:    t.TableID,
		HostUserId: uint32(t.HostUserID),
		Seats:      seats,
		State:      t.State,
		MatchId:    t.MatchID,
	}
}

// SnapshotProto returns a proto state snapshot, acquiring t.mu for the
// duration of the read. Use this from any caller that does NOT already
// hold the lock (e.g. the broadcast helper running after a mutation
// handler released the lock via defer).
func (t *PrivateTable) SnapshotProto() *pb.PrivateTableState {
	t.mu.Lock()
	defer t.mu.Unlock()
	return t.toProto()
}
```

- [ ] **Step 2: Add the registry to `Matchmaker`**

In `api/matchmaker.go`, locate the `Matchmaker` struct (currently at lines 88-97) and add the new fields:

```go
type Matchmaker struct {
	Queue *InMemoryQueue
	DB    *gorm.DB
	Hub   *Hub

	PaipuStore func(matchID, paipuJSON string)

	privateTablesMu     sync.RWMutex
	activePrivateTables map[string]ActivePrivateTable

	configuringMu     sync.Mutex
	configuringTables map[string]*PrivateTable
}
```

Update `NewMatchmaker` to initialize the new map:

```go
func NewMatchmaker(queue *InMemoryQueue, db *gorm.DB, hub *Hub) *Matchmaker {
	return &Matchmaker{
		Queue:               queue,
		DB:                  db,
		Hub:                 hub,
		activePrivateTables: make(map[string]ActivePrivateTable),
		configuringTables:   make(map[string]*PrivateTable),
	}
}
```

- [ ] **Step 3: Add registry accessor methods on `Matchmaker`**

Append these methods to `api/matchmaker.go`:

```go
// JoinOrCreatePrivateTable claims a seat for the given user. If the table
// does not exist, the user becomes the host at seat 0. If the user is
// already seated, this is a no-op.
//
// Returns a snapshot of the table state for the caller. The caller is
// expected to broadcast a lobby_update afterward.
func (m *Matchmaker) JoinOrCreatePrivateTable(tableID string, userID uint, username string) (*PrivateTable, error) {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()

	table, ok := m.configuringTables[tableID]
	if !ok {
		table = newConfiguringTable(tableID, userID)
		m.configuringTables[tableID] = table
	}

	table.mu.Lock()
	defer table.mu.Unlock()

	if table.State != "configuring" {
		return nil, errors.New("table is no longer accepting players")
	}

	if _, err := table.claimNextHumanSeat(userID, username); err != nil {
		return nil, err
	}
	table.normalize()
	return table, nil
}

// GetConfiguringPrivateTable returns the live table struct (locked by
// caller via Mutate) or nil if no such table exists in the "configuring"
// state.
func (m *Matchmaker) GetConfiguringPrivateTable(tableID string) *PrivateTable {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()
	return m.configuringTables[tableID]
}

// MutatePrivateTable runs fn under the table lock. Returns the table for
// snapshotting after fn returns successfully.
func (m *Matchmaker) MutatePrivateTable(tableID string, fn func(t *PrivateTable) error) (*PrivateTable, error) {
	table := m.GetConfiguringPrivateTable(tableID)
	if table == nil {
		return nil, errors.New("table not found")
	}
	table.mu.Lock()
	defer table.mu.Unlock()
	if err := fn(table); err != nil {
		return nil, err
	}
	return table, nil
}

// removeConfiguringTable drops the table from the configuring registry.
// Called after a successful start once the match has been dispatched.
func (m *Matchmaker) removeConfiguringTable(tableID string) {
	m.configuringMu.Lock()
	defer m.configuringMu.Unlock()
	delete(m.configuringTables, tableID)
}
```

Add `"errors"` to the imports of `api/matchmaker.go` if it isn't already present.

- [ ] **Step 4: Remove the old queue-based private table flow**

In `api/matchmaker.go`, delete:

- the entire `JoinPrivateTable` method (currently lines 127-152)
- the entire `StartPrivateTableWatcher` method (currently lines 231-251)

`createMatch` stays — it is reused by `StartPrivateTable` in the next task and by `StartQueueWatcher`.

- [ ] **Step 5: Verify the package still compiles**

```bash
go build ./...
```

Expected: exit code 0. Some callers (the old `handleJoinPrivate` route, the old test file) will still reference removed code — that's fine; subsequent tasks remove those references.

If the build complains about an undefined `JoinPrivateTable`, leave that for Task 6 (server routes). If the build complains about `private_table_test.go` references, leave that for Task 7.

If unrelated build errors appear, fix them inline before moving on.

- [ ] **Step 6: Commit**

```bash
git add api/private_tables.go api/matchmaker.go
git commit -m "api: PrivateTable registry on Matchmaker"
```

---

## Task 5: Add `StartPrivateTable` lifecycle method on `Matchmaker`

**Files:**
- Modify: `api/matchmaker.go`

- [ ] **Step 1: Implement the start lifecycle**

Append to `api/matchmaker.go`:

```go
import (
	"github.com/plasma/fh-mahjong/bot"
)
```

(merge with the existing import block).

Then add the method:

```go
// StartPrivateTable validates host + seat fullness, constructs the Room
// with per-seat bot policies, persists the match, and dispatches the room
// via the Hub. Returns the table snapshot (with State == "started" and
// MatchID populated) on success.
func (m *Matchmaker) StartPrivateTable(tableID string, requesterUserID uint) (*PrivateTable, error) {
	table := m.GetConfiguringPrivateTable(tableID)
	if table == nil {
		return nil, errors.New("table not found")
	}

	table.mu.Lock()
	defer table.mu.Unlock()

	if table.State != "configuring" {
		return nil, errors.New("table already started")
	}
	if requesterUserID != table.HostUserID {
		return nil, errors.New("only the host can start the match")
	}
	if err := table.canStart(); err != nil {
		return nil, err
	}

	seatPolicies := make(map[uint32]bot.Policy)
	var humanUserIDs []uint
	for i, s := range table.Seats {
		seat := uint32(i)
		switch s.Kind {
		case "human":
			humanUserIDs = append(humanUserIDs, s.UserID)
		case "bot":
			policy, err := bot.NewPolicy(s.Difficulty)
			if err != nil {
				return nil, fmt.Errorf("seat %d: %w", i, err)
			}
			seatPolicies[seat] = policy
		default:
			return nil, fmt.Errorf("seat %d is %s, expected human or bot", i, s.Kind)
		}
	}

	matchID := uuid.New().String()

	match := models.Match{
		ID:        matchID,
		Status:    "in_progress",
		StartTime: time.Now(),
		Ruleset:   "hometown",
	}
	if m.DB != nil {
		if err := m.DB.Create(&match).Error; err != nil {
			return nil, fmt.Errorf("persist match: %w", err)
		}
	} else {
		log.Printf("Database disabled, skipping match persistence for %s", matchID)
	}

	room := NewRoom(matchID, m.Hub, m.DB)
	room.PaipuStore = m.PaipuStore
	room.PrivateTableID = tableID
	room.SeatPolicies = seatPolicies
	room.OnShutdown = func() {
		m.unregisterActivePrivateTable(tableID)
	}

	m.registerActivePrivateTable(tableID, matchID, humanUserIDs)

	table.State = "started"
	table.MatchID = matchID

	m.Hub.BindRoom <- RoomBind{
		UserIDs: humanUserIDs,
		Room:    room,
	}

	// Drop the configuring entry now that the room owns the match lifecycle.
	go m.removeConfiguringTable(tableID)

	return table, nil
}
```

Add `"fmt"`, `"log"`, `"time"`, `"github.com/google/uuid"`, and `"github.com/plasma/fh-mahjong/models"` to the imports if any are missing (most should already be there).

- [ ] **Step 2: Verify the package compiles**

```bash
go build ./...
```

Expected: any remaining errors should be in `api/server.go` and `api/private_table_test.go` (Tasks 6 and 7). If the new code has its own compile error, fix it inline.

- [ ] **Step 3: Commit**

```bash
git add api/matchmaker.go
git commit -m "api: Matchmaker.StartPrivateTable lifecycle"
```

---

## Task 6: Wire REST endpoints + WebSocket broadcasts

**Files:**
- Modify: `api/server.go`
- Modify: `api/private_tables.go` (add handlers here; keep `server.go` lean)

- [ ] **Step 1: Add handler methods to `api/private_tables.go`**

Append to `api/private_tables.go`:

```go
import (
	"encoding/json"
	"net/http"

	"github.com/gin-gonic/gin"
	"google.golang.org/protobuf/encoding/protojson"
)
```

(merge with the existing import block at the top of the file).

Then add the handlers:

```go
// broadcastPrivateTable serializes the table to the proto JSON shape and
// fans it out via Hub.LobbyBroadcast. The frontend listens for
// `type: "lobby_update"` JSON messages and updates its seat state.
//
// Uses SnapshotProto so the marshal happens under the table lock; any
// caller that already holds the lock should release it before calling
// this helper (the registry methods return after `defer Unlock`, so the
// typical handler flow is safe).
func (s *Server) broadcastPrivateTable(table *PrivateTable) {
	if s.Hub == nil {
		return
	}
	statePB := table.SnapshotProto()
	stateJSON, err := protojson.MarshalOptions{EmitUnpopulated: true, UseEnumNumbers: true}.Marshal(statePB)
	if err != nil {
		return
	}
	envelope := struct {
		Type  string          `json:"type"`
		Table string          `json:"table"`
		State json.RawMessage `json:"state"`
	}{
		Type:  "lobby_update",
		Table: table.TableID,
		State: stateJSON,
	}
	payload, err := json.Marshal(envelope)
	if err != nil {
		return
	}
	go func() { s.Hub.LobbyBroadcast <- payload }()
}

func (s *Server) handlePrivateTableJoin(c *gin.Context) {
	userID, _ := c.Get("userID")
	username, _ := c.Get("username")
	tableID := c.Param("tableId")
	if tableID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "tableId is required"})
		return
	}

	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}

	if activeTable, isActive, isParticipant := s.Matchmaker.IsPrivateTableParticipant(tableID, userID.(uint)); isActive {
		if isParticipant {
			c.JSON(http.StatusOK, gin.H{"status": "active", "table": tableID, "matchId": activeTable.MatchID})
			return
		}
		c.JSON(http.StatusConflict, gin.H{"error": "This private table is already in an active game", "status": "active", "table": tableID, "matchId": activeTable.MatchID})
		return
	}

	table, err := s.Matchmaker.JoinOrCreatePrivateTable(tableID, userID.(uint), username.(string))
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableGet(c *gin.Context) {
	tableID := c.Param("tableId")
	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}
	table := s.Matchmaker.GetConfiguringPrivateTable(tableID)
	if table == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "table not found"})
		return
	}
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableSeat(c *gin.Context) {
	userID, _ := c.Get("userID")
	tableID := c.Param("tableId")

	var req struct {
		Seat       uint32        `json:"seat"`
		Kind       string        `json:"kind"`
		Difficulty pb.Difficulty `json:"difficulty"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	table, err := s.Matchmaker.MutatePrivateTable(tableID, func(t *PrivateTable) error {
		if t.HostUserID != userID.(uint) {
			return errHostOnly
		}
		if t.State != "configuring" {
			return errors.New("table already started")
		}
		if req.Kind == "bot" {
			if _, perr := bot.NewPolicy(req.Difficulty); perr != nil {
				return perr
			}
		}
		return t.setSeat(req.Seat, req.Kind, req.Difficulty)
	})
	if err != nil {
		status := http.StatusBadRequest
		if errors.Is(err, errHostOnly) {
			status = http.StatusForbidden
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

func (s *Server) handlePrivateTableStart(c *gin.Context) {
	userID, _ := c.Get("userID")
	tableID := c.Param("tableId")

	table, err := s.Matchmaker.StartPrivateTable(tableID, userID.(uint))
	if err != nil {
		status := http.StatusBadRequest
		switch err.Error() {
		case "only the host can start the match":
			status = http.StatusForbidden
		case "table not found":
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}

var errHostOnly = errors.New("only the host can modify seats")

// marshalPrivateTableJSON snapshots the table under its lock and returns
// the proto-JSON encoding. Safe to call from any handler regardless of
// whether the caller currently holds the lock — the registry mutate
// helpers release the lock before returning, so this path never blocks
// indefinitely.
func marshalPrivateTableJSON(t *PrivateTable) []byte {
	data, err := protojson.MarshalOptions{EmitUnpopulated: true, UseEnumNumbers: true}.Marshal(t.SnapshotProto())
	if err != nil {
		return []byte(`{"error":"failed to marshal table state"}`)
	}
	return data
}
```

Add `"github.com/plasma/fh-mahjong/bot"` to the imports if it isn't already present.

(`MutatePrivateTable` already locks the table; the inline `t.mu.Lock()` in `handlePrivateTableGet` exists because we're reading directly without the mutate helper.)

- [ ] **Step 2: Register the routes in `api/server.go`**

In `api/server.go` `setupRoutes`, find the `protected` group (currently around line 70) and replace its contents:

```go
protected := v1.Group("/")
protected.Use(AuthMiddleware())
{
	protected.GET("/users/me", s.handleGetMe)
	protected.POST("/matchmaking/join", s.handleJoinQueue)

	protected.GET("/private-tables/:tableId", s.handlePrivateTableGet)
	protected.POST("/private-tables/:tableId/join", s.handlePrivateTableJoin)
	protected.POST("/private-tables/:tableId/seat", s.handlePrivateTableSeat)
	protected.POST("/private-tables/:tableId/start", s.handlePrivateTableStart)
}
```

(The old `/matchmaking/private` route is removed.)

Then delete the old `handleJoinPrivate` function (currently lines 307-350) from `api/server.go`.

- [ ] **Step 3: Build and verify**

```bash
go build ./...
```

Expected: build succeeds. If `api/private_table_test.go` still fails to compile, that's expected — Task 7 handles it.

If anything else fails, fix it inline.

- [ ] **Step 4: Commit**

```bash
git add api/private_tables.go api/server.go
git commit -m "api: private-table REST endpoints and lobby broadcasts"
```

---

## Task 7: Replace the old private-table integration tests

**Files:**
- Delete: `api/private_table_test.go`
- Create: `api/private_tables_test.go`

- [ ] **Step 1: Delete the old test file**

```bash
git rm api/private_table_test.go
```

- [ ] **Step 2: Write the new failing integration tests**

Create `api/private_tables_test.go`:

```go
package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	pb "github.com/plasma/fh-mahjong/proto"
)

func privateTableAuthToken(t *testing.T, userID uint, username string) string {
	t.Helper()

	token := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{
		"sub":      userID,
		"username": username,
		"exp":      time.Now().Add(time.Hour).Unix(),
	})
	tokenString, err := token.SignedString(jwtSecret)
	if err != nil {
		t.Fatalf("failed to sign test token: %v", err)
	}
	return tokenString
}

func doPrivateTableRequest(t *testing.T, server *Server, method, path, token string, body any) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()

	var payload []byte
	if body != nil {
		var err error
		payload, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal body: %v", err)
		}
	}

	req := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	recorder := httptest.NewRecorder()
	server.Router.ServeHTTP(recorder, req)

	var parsed map[string]any
	if recorder.Body.Len() > 0 {
		_ = json.Unmarshal(recorder.Body.Bytes(), &parsed)
	}
	return recorder, parsed
}

func newPrivateTableTestServer() *Server {
	hub := NewHub()
	go hub.Run()
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)
	return NewServer(nil, hub, matchmaker)
}

func TestPrivateTableJoinAssignsHost(t *testing.T) {
	server := newPrivateTableTestServer()

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got, _ := body["hostUserId"].(float64); uint(got) != 101 {
		t.Fatalf("expected host 101, got %#v", body["hostUserId"])
	}
	seats, _ := body["seats"].([]any)
	if len(seats) != 4 {
		t.Fatalf("expected 4 seats, got %d", len(seats))
	}
	first, _ := seats[0].(map[string]any)
	if first["kind"] != "human" || uint(first["userId"].(float64)) != 101 {
		t.Fatalf("expected seat 0 = alice, got %#v", first)
	}
}

func TestPrivateTableSecondJoinClaimsNextSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 102, "bob"), map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
	seats, _ := body["seats"].([]any)
	second, _ := seats[1].(map[string]any)
	if second["kind"] != "human" || uint(second["userId"].(float64)) != 102 {
		t.Fatalf("expected seat 1 = bob, got %#v", second)
	}
}

func TestPrivateTableHostSetsBotSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", privateTableAuthToken(t, 101, "alice"), map[string]any{
		"seat":       1,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
	})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	seats, _ := body["seats"].([]any)
	second, _ := seats[1].(map[string]any)
	if second["kind"] != "bot" {
		t.Fatalf("expected seat 1 kind=bot, got %#v", second)
	}
}

func TestPrivateTableNonHostCannotMutateSeat(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 102, "bob"), map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", privateTableAuthToken(t, 102, "bob"), map[string]any{
		"seat":       2,
		"kind":       "bot",
		"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
	})
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-host, got %d", recorder.Code)
	}
}

func TestPrivateTableStartRejectsEmptySeats(t *testing.T) {
	server := newPrivateTableTestServer()
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400 when seats not full, got %d", recorder.Code)
	}
}

func TestPrivateTableStartWithThreeBots(t *testing.T) {
	server := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 101, "alice")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", hostToken, map[string]any{})

	for _, seat := range []uint32{1, 2, 3} {
		recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", hostToken, map[string]any{
			"seat":       seat,
			"kind":       "bot",
			"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
		})
		if recorder.Code != http.StatusOK {
			t.Fatalf("seat %d setup failed: %d", seat, recorder.Code)
		}
	}

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", hostToken, map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if body["state"] != "started" {
		t.Fatalf("expected state=started, got %#v", body["state"])
	}
	if body["matchId"] == "" || body["matchId"] == nil {
		t.Fatalf("expected matchId to be set, got %#v", body["matchId"])
	}
}

func TestPrivateTableStartRejectsNonHost(t *testing.T) {
	server := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 101, "alice")
	otherToken := privateTableAuthToken(t, 102, "bob")
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", hostToken, map[string]any{})
	doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", otherToken, map[string]any{})
	for _, seat := range []uint32{2, 3} {
		doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/seat", hostToken, map[string]any{
			"seat":       seat,
			"kind":       "bot",
			"difficulty": int(pb.Difficulty_DIFFICULTY_HEURISTIC),
		})
	}

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/start", otherToken, map[string]any{})
	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-host start, got %d", recorder.Code)
	}
}

func TestPrivateTableJoinReturnsActiveForExistingParticipant(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})

	recorder, body := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 101, "alice"), map[string]any{})
	if recorder.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", recorder.Code)
	}
	if body["status"] != "active" || body["matchId"] != "match-123" {
		t.Fatalf("expected active+match-123, got %#v", body)
	}
}

func TestPrivateTableJoinRejectsOutsiderForActiveTable(t *testing.T) {
	server := newPrivateTableTestServer()
	server.Matchmaker.registerActivePrivateTable("test-room", "match-123", []uint{101, 102, 103, 104})

	recorder, _ := doPrivateTableRequest(t, server, http.MethodPost, "/api/v1/private-tables/test-room/join", privateTableAuthToken(t, 999, "eve"), map[string]any{})
	if recorder.Code != http.StatusConflict {
		t.Fatalf("expected 409, got %d", recorder.Code)
	}
}
```

- [ ] **Step 3: Run the new tests**

```bash
go test ./api/ -run TestPrivateTable -v
```

Expected: all tests pass. If any fail, read the failure and fix the handler or registry inline.

- [ ] **Step 4: Run the full Go suite**

```bash
go test ./...
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/private_tables_test.go
git commit -m "api: integration tests for private-table seat config"
```

---

## Task 8: Update `api/AGENTS.md` and remove the matchmaker private-table watcher reference

**Files:**
- Modify: `api/AGENTS.md`

- [ ] **Step 1: Read and update**

Read `api/AGENTS.md`. Update the matchmaker section so it reflects the new flow:

- Remove the `StartPrivateTableWatcher` bullet.
- Remove the bullet about queue-based private tables.
- Add: "Tracks `configuringTables` (host + 4-seat config) and exposes `JoinOrCreatePrivateTable`, `MutatePrivateTable`, and `StartPrivateTable`. The first joiner of a `tableId` becomes the host; only the host can mutate seats or start the match."

Update the `server.go` section to list the new routes:

- Add: "`/private-tables/:tableId` (GET) — read current seat config. `/private-tables/:tableId/join` (POST) — claim a seat. `/private-tables/:tableId/seat` (POST, host-only) — assign or clear an AI seat. `/private-tables/:tableId/start` (POST, host-only) — launch the match."
- Remove the mention of `/matchmaking/private` and `handleJoinPrivate`.

Update the architecture notes section near the bottom: change the `lobby_update` mention so it documents the new envelope:

- Replace: "Listens for JSON `lobby_update` socket messages for the current `tableId` while the room is filling" with "WS `lobby_update` envelopes for private tables now carry the full `PrivateTableState` as JSON, so the waiting room renders seat assignments directly from each broadcast."

- [ ] **Step 2: Commit**

```bash
git add api/AGENTS.md
git commit -m "docs(api): document private-table seat-config endpoints"
```

---

## Task 9: Rewrite `Table.tsx` for seat configuration

**Files:**
- Create: `web/src/pages/SeatCard.tsx`
- Modify: `web/src/pages/Table.tsx`
- Modify: `web/src/pages/AGENTS.md`

- [ ] **Step 1: Create the seat card component**

Create `web/src/pages/SeatCard.tsx`:

```tsx
import { game } from '../proto/game';

type SeatConfig = game.ISeatConfig;
type Difficulty = game.Difficulty;

export interface SeatCardProps {
    seatIndex: number;
    seat: SeatConfig;
    isHost: boolean;
    canEdit: boolean;
    hostUserId: number;
    onAssignBot: (seat: number, difficulty: Difficulty) => void;
    onClearSeat: (seat: number) => void;
}

const DIFFICULTY_OPTIONS: Array<{ value: Difficulty; label: string }> = [
    { value: game.Difficulty.DIFFICULTY_HEURISTIC, label: 'Heuristic' },
];

const SEAT_LABEL = ['East', 'South', 'West', 'North'];

export default function SeatCard(props: SeatCardProps) {
    const { seatIndex, seat, isHost, canEdit, hostUserId, onAssignBot, onClearSeat } = props;

    const isHumanHost = seat.kind === 'human' && Number(seat.userId ?? 0) === hostUserId;

    return (
        <div className="rounded-2xl border border-emerald-300/16 bg-slate-950/70 p-5">
            <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.18em] text-emerald-200/70">
                <span>Seat {seatIndex + 1} · {SEAT_LABEL[seatIndex]}</span>
                {isHumanHost && <span className="rounded-full border border-amber-300/40 px-2 py-0.5 text-amber-200">Host</span>}
            </div>

            <div className="mt-3 text-base font-semibold text-emerald-100">
                {seat.kind === 'human' && <>{seat.username || `Player ${seat.userId ?? ''}`}</>}
                {seat.kind === 'bot' && <>AI · Heuristic</>}
                {(seat.kind === 'empty' || !seat.kind) && <span className="text-slate-400">Waiting for player…</span>}
            </div>

            {canEdit && (seat.kind === 'empty' || !seat.kind) && (
                <div className="mt-3 flex flex-wrap gap-2">
                    {DIFFICULTY_OPTIONS.map(opt => (
                        <button
                            key={opt.value}
                            type="button"
                            onClick={() => onAssignBot(seatIndex, opt.value)}
                            className="rounded-full border border-cyan-300/30 bg-cyan-900/40 px-3 py-1 text-xs uppercase tracking-[0.16em] text-cyan-100 hover:bg-cyan-800/50"
                        >
                            Add AI · {opt.label}
                        </button>
                    ))}
                </div>
            )}

            {canEdit && seat.kind === 'bot' && (
                <div className="mt-3 flex flex-wrap gap-2">
                    <button
                        type="button"
                        onClick={() => onClearSeat(seatIndex)}
                        className="rounded-full border border-rose-300/30 bg-rose-900/40 px-3 py-1 text-xs uppercase tracking-[0.16em] text-rose-100 hover:bg-rose-800/50"
                    >
                        Remove AI
                    </button>
                </div>
            )}

            {isHost && !canEdit && (
                <div className="mt-3 text-[11px] uppercase tracking-[0.16em] text-slate-500">Only the host can change seats.</div>
            )}
        </div>
    );
}
```

- [ ] **Step 2: Rewrite `Table.tsx`**

Replace the entire contents of `web/src/pages/Table.tsx`:

```tsx
import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSocket } from '../contexts/SocketContext';
import { useGameState } from '../contexts/GameContext';
import { getApiUrl } from '../config';
import { clearPrivateRoomSession, loadPrivateRoomSession, savePrivateRoomSession } from './privateRoomSession';
import SeatCard from './SeatCard';
import { game } from '../proto/game';

type PrivateTableState = game.IPrivateTableState;
type Difficulty = game.Difficulty;

export default function Table() {
    const { tableId } = useParams();
    const [username, setUsername] = useState(() => loadPrivateRoomSession(tableId)?.username ?? '');
    const [guestToken, setGuestToken] = useState('');
    const [joining, setJoining] = useState(false);
    const [error, setError] = useState('');
    const [tableState, setTableState] = useState<PrivateTableState | null>(null);

    const navigate = useNavigate();
    const { isConnected, connect, socket } = useSocket();
    const { gameState } = useGameState();

    const myUserId = useMyUserId(guestToken);

    useEffect(() => {
        if (gameState && gameState.matchId) {
            navigate(`/game/${gameState.matchId}`);
        }
    }, [gameState, navigate]);

    useEffect(() => {
        const stored = loadPrivateRoomSession(tableId);
        if (stored && !isConnected) {
            setGuestToken(stored.token);
            setUsername(stored.username);
            connect(stored.token);
        }
    }, [connect, isConnected, tableId]);

    const fetchTableState = useCallback(async () => {
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}`), {
                headers: { Authorization: `Bearer ${guestToken}` },
            });
            if (res.ok) {
                setTableState(await res.json());
            }
        } catch (err) {
            console.error('fetch table state failed', err);
        }
    }, [guestToken, tableId]);

    useEffect(() => { fetchTableState(); }, [fetchTableState]);

    useEffect(() => {
        if (!socket || !isConnected) return;

        const handle = (e: MessageEvent) => {
            if (typeof e.data !== 'string') return;
            try {
                const data = JSON.parse(e.data);
                if (data.type === 'lobby_update' && data.table === tableId && data.state) {
                    setTableState(data.state as PrivateTableState);
                    if (data.state.state === 'started' && data.state.matchId) {
                        navigate(`/game/${data.state.matchId}`);
                    }
                }
            } catch (err) {
                // ignore non-JSON / non-lobby payloads
            }
        };

        socket.addEventListener('message', handle);
        return () => socket.removeEventListener('message', handle);
    }, [socket, isConnected, tableId, navigate]);

    const performJoin = useCallback(async (token: string) => {
        if (!tableId) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/join`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
                body: JSON.stringify({}),
            });
            const data = await res.json().catch(() => ({}));
            if (res.status === 409) {
                setError(data.error || 'This private table is already in an active game.');
                return;
            }
            if (!res.ok) {
                setError(data.error || 'Failed to join private table');
                return;
            }
            if (data.status === 'active' && data.matchId) {
                navigate(`/game/${data.matchId}`);
                return;
            }
            setTableState(data as PrivateTableState);
        } catch (err: any) {
            setError(err.message || 'Failed to join private table');
        }
    }, [navigate, tableId]);

    const handleGuestJoin = async () => {
        if (!username.trim() || !tableId) return;
        setError('');
        setJoining(true);
        try {
            const authRes = await fetch(getApiUrl('/api/v1/auth/guest'), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username }),
            });
            const authData = await authRes.json();
            if (!authRes.ok) throw new Error(authData.error || 'Guest auth failed');

            setGuestToken(authData.token);
            savePrivateRoomSession({
                tableId,
                token: authData.token,
                username: authData.user?.username || username.trim(),
            });
            connect(authData.token);
            await performJoin(authData.token);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setJoining(false);
        }
    };

    const mutateSeat = useCallback(async (seat: number, kind: 'bot' | 'empty', difficulty?: Difficulty) => {
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/seat`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({ seat, kind, difficulty: difficulty ?? game.Difficulty.DIFFICULTY_UNSPECIFIED }),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to update seat');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to update seat');
        }
    }, [guestToken, tableId]);

    const handleStart = async () => {
        if (!tableId || !guestToken) return;
        try {
            const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/start`), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
                body: JSON.stringify({}),
            });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                setError(data.error || 'Failed to start match');
            }
        } catch (err: any) {
            setError(err.message || 'Failed to start match');
        }
    };

    if (!guestToken) {
        return (
            <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
                <div className="mx-auto flex min-h-screen w-full max-w-2xl flex-col items-center justify-center px-6 py-10">
                    <div className="w-full rounded-[28px] border border-emerald-300/20 bg-slate-950/70 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)]">
                        <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Private Table</p>
                        <h1 className="mt-2 text-3xl font-black uppercase tracking-[0.12em] text-emerald-100">Join Table {tableId}</h1>
                        <p className="mt-4 text-sm leading-7 text-slate-300">Pick a display name to enter as a guest.</p>
                        <input
                            value={username}
                            onChange={e => setUsername(e.target.value)}
                            placeholder="Your name"
                            className="mt-6 w-full rounded-2xl border border-emerald-300/20 bg-slate-900/60 px-4 py-3 text-sm text-emerald-100 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-400/40"
                        />
                        {error && <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">{error}</div>}
                        <button
                            onClick={handleGuestJoin}
                            disabled={joining || !username.trim()}
                            className="mt-6 w-full rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            {joining ? 'Joining…' : 'Join Table'}
                        </button>
                    </div>
                </div>
            </div>
        );
    }

    const seats = tableState?.seats ?? [];
    const hostUserId = Number(tableState?.hostUserId ?? 0);
    const iAmHost = myUserId !== null && myUserId === hostUserId;
    const allSeatsFilled = seats.length === 4 && seats.every(s => s.kind === 'human' || s.kind === 'bot');

    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
            <div className="mx-auto flex min-h-screen w-full max-w-4xl flex-col px-6 py-10">
                <header className="mb-6 flex items-center justify-between">
                    <div>
                        <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Private Table</p>
                        <h1 className="mt-1 text-3xl font-black uppercase tracking-[0.12em] text-emerald-100">Table {tableId}</h1>
                    </div>
                    {iAmHost && (
                        <button
                            onClick={handleStart}
                            disabled={!allSeatsFilled}
                            className="rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            Start Match
                        </button>
                    )}
                </header>

                {error && <div className="mb-4 rounded-2xl border border-rose-400/30 bg-rose-950/30 px-4 py-3 text-sm text-rose-100">{error}</div>}

                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {seats.map((seat, i) => (
                        <SeatCard
                            key={i}
                            seatIndex={i}
                            seat={seat}
                            isHost={iAmHost}
                            canEdit={iAmHost && seat.kind !== 'human'}
                            hostUserId={hostUserId}
                            onAssignBot={(s, d) => mutateSeat(s, 'bot', d)}
                            onClearSeat={s => mutateSeat(s, 'empty')}
                        />
                    ))}
                </div>

                {iAmHost && !allSeatsFilled && (
                    <p className="mt-6 text-sm text-slate-300">Fill every seat with a player or AI before starting.</p>
                )}
                {!iAmHost && (
                    <p className="mt-6 text-sm text-slate-300">The host configures the table. You'll join automatically when the match begins.</p>
                )}
            </div>
        </div>
    );
}

function useMyUserId(token: string): number | null {
    const [userId, setUserId] = useState<number | null>(null);
    useEffect(() => {
        if (!token) { setUserId(null); return; }
        const parts = token.split('.');
        if (parts.length !== 3) { setUserId(null); return; }
        try {
            const payload = JSON.parse(atob(parts[1].replace(/-/g, '+').replace(/_/g, '/')));
            const sub = typeof payload.sub === 'number' ? payload.sub : Number(payload.sub);
            setUserId(Number.isFinite(sub) ? sub : null);
        } catch {
            setUserId(null);
        }
    }, [token]);
    return userId;
}

// Side-effect import retained so the navigate/clearPrivateRoomSession imports
// match build expectations.
const _unused = clearPrivateRoomSession;
void _unused;
```

(The `_unused` lines are placeholders only if a linter complains. If `clearPrivateRoomSession` isn't used elsewhere in this file, remove the import entirely instead.)

- [ ] **Step 3: Run frontend type-check / build**

```bash
cd web && npm run build
```

Expected: build succeeds. Common failure modes:

- Type mismatch on `seat.kind` (proto string types are nullable in TS) → cast / default as in the file above.
- Missing `useMyUserId` export → keep it as the local helper at the bottom of the file.

If the build fails, fix inline before moving on.

- [ ] **Step 4: Update `web/src/pages/AGENTS.md`**

In the `Table.tsx` bullet, replace its body with:

```markdown
- **Table.tsx** — Private-table seat configuration screen for `/table/:tableId`:
  - Reads/POSTs `/api/v1/private-tables/:tableId/...` for join, get, seat mutation, and start
  - Renders four `SeatCard` components; the host (first joiner) sees per-empty-seat AI controls and a "Start Match" button enabled when all seats are filled
  - Subscribes to `lobby_update` envelopes carrying the full `PrivateTableState` JSON and re-renders on every broadcast
  - On `state === 'started'`, redirects everyone to `/game/:matchId`
  - Uses tab-scoped private-room session storage for guest-token reconnects (unchanged)
```

And add a new bullet:

```markdown
- **SeatCard.tsx** — Single seat-card component. Renders waiting/human/bot states; if `canEdit` is true, shows "Add AI · Heuristic" buttons for empty seats and a "Remove AI" button for bot seats. Pure presentation; all mutations bubble up to `Table.tsx`.
```

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/Table.tsx web/src/pages/SeatCard.tsx web/src/pages/AGENTS.md
git commit -m "web: private-table seat-configuration screen"
```

---

## Task 10: Manual end-to-end verification

**Files:** none — this is a manual check.

- [ ] **Step 1: Start backend + frontend**

```bash
go run ./cmd/server &
cd web && npm run dev
```

- [ ] **Step 2: Solo flow (1 human + 3 AI)**

In a single browser tab:
- Visit `http://localhost:3000/create-room`, copy/open the generated link.
- Join the table as a guest. You should land on the seat-config screen with yourself at seat 0 and three "Waiting for player…" seats.
- Click "Add AI · Heuristic" on each of seats 1, 2, 3.
- "Start Match" should enable. Click it.
- You should redirect to `/game/:matchId`. The bots should play their turns automatically.

- [ ] **Step 3: Mixed flow (2 humans + 2 AI)**

Open two browser tabs (use a private/incognito window for the second so localStorage is separate):
- Tab A creates a table and joins as host (claims seat 0).
- Tab B opens the same `/table/:tableId` and joins as a different guest (claims seat 1).
- In tab A, assign AI to seats 2 and 3.
- Tab B should see all seat changes update live (no refresh) and should NOT see any AI controls.
- In tab A, click "Start Match". Both tabs should redirect to `/game/:matchId`.
- Verify both humans see the game and the two AI seats play automatically.

- [ ] **Step 4: Restart flow**

- Reload tab A in the middle of seat configuration. The seat state should restore (server is source of truth, GET on mount returns it).

- [ ] **Step 5: Note any UI defects**

Record any issues. Minor styling polish is acceptable to fix inline; behavioral bugs become an immediate follow-up commit.

- [ ] **Step 6: If the verification surfaced fixes, commit them**

```bash
git add -A
git commit -m "web: post-verification polish on private-table flow"
```

(Skip if there's nothing to commit.)

---

## Final verification

- [ ] **Step 1: Full Go test suite**

```bash
go test ./...
```

Expected: all pass.

- [ ] **Step 2: Frontend build**

```bash
cd web && npm run build
```

Expected: build succeeds with no type errors.

- [ ] **Step 3: Confirm `git status` is clean**

```bash
git status
```

Expected: nothing to commit, working tree clean.

---

## Out of scope (do not implement here)

- RL difficulty variants. Add a new `Difficulty` value + a `bot.NewPolicy` case when a trained checkpoint exists.
- Localized difficulty labels (Chinese/English toggle on seat cards).
- Kicking a human participant from a seat.
- Reassigning seat order / wind choice.
- Public-matchmaking changes (`/api/v1/matchmaking/join` is untouched).
