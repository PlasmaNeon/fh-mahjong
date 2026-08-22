# Spec B1: Public Event History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture the public event stream (draws/discards/calls/reveals) in the Go engine and render it, observer-relative and information-legal, as packed uint32s in `SeatObservation` — dormant by default.

**Architecture:** An always-on `[]PublicEvent` slice on `engine.Game`, appended at the exact call sites that feed `PaipuRecorder` (but never nil-guarded), truncated at round start, value-copied by `CloneForBranch`, untouched by `RedealUnseen`. `internal/rl` renders the last W events per observer into a documented bit layout when `EnvConfig.event_history_window > 0`; at 0 the observation is byte-identical to today. Python mirrors the bit layout in a new `events.py`; the bridge surfaces the array; a shared golden vector pins the layout across languages.

**Tech Stack:** Go 1.25 (`internal/engine`, `internal/rl`), Protocol Buffers (proto/game.proto → Go + Python + TS), Python 3.12 + numpy (`ai/`).

**Spec:** `worklog/specs/2026-07-15-spec-b1-event-history-design.md` (approved). Branch: `claude/spec-b1-events` (exists, off main @ 8c38ac5).

## Global Constraints

- `event_history_window = 0` (the default everywhere) must produce BYTE-IDENTICAL `SeatObservation` messages — regression-tested like the oracle phases.
- Proto changes are append-only: `SeatObservation` fields 12/13, `EnvConfig` field 7. Regenerate Go AND Python AND TS (exact commands in Task 2; Python MUST use `grpc_tools.protoc` per proto/AGENTS.md).
- `internal/engine/game.go` must never import `internal/rules` (tests needing both live in `internal/rl` or an external test package).
- No model or training changes — that is Spec B2.
- Bit layout (single source of truth, mirrored Go/Python, reserved bits must be zero):
  `bits 0-3 type (0=DRAW,1=DISCARD,2=CHII,3=PON,4=KAN_OPEN,5=KAN_CLOSED,6=KAN_UPGRADE,7=FLOWER) | bits 4-5 actor seat relative to observer | bits 6-11 face (0-41 per tileFaceIndex42, 63=UNKNOWN) | bits 12-13 from-seat relative (calls only, else 0) | bit 14 tsumogiri | bit 15 haitei | bits 16-31 zero`.
- After Go changes: `go vet ./... && go test ./...`. After Python changes: `uv run --project ai pytest`. After proto changes: TS regen + `cd web && npx tsc --noEmit`.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- AGENTS.md updates for touched dirs fold into the task that touches them (Task 5 verifies).

---

### Task 1: Engine — PublicEventLog capture

**Files:**
- Create: `internal/engine/events.go`
- Create: `internal/engine/events_test.go`
- Modify: `internal/engine/game.go` (Game struct ~line 20; dealTiles ~163; initial flowers ~388; draws ~526, ~641, ~768; discard ~824; kans ~925-939; claims ~1104-1108)
- Modify: `internal/engine/clone.go` (CloneForBranch ~12)
- Modify: `internal/engine/AGENTS.md`

**Interfaces:**
- Produces (Tasks 3 depends on these exact names):
  - `type PublicEventType uint8` with constants `EventDraw=0, EventDiscard=1, EventChii=2, EventPon=3, EventKanOpen=4, EventKanClosed=5, EventKanUpgrade=6, EventFlower=7`.
  - `type PublicEvent struct { Type PublicEventType; Seat uint32; Face int16; FromSeat int32; Flags uint8 }` with flag bits `EventFlagTsumogiri uint8 = 1 << 0`, `EventFlagHaitei uint8 = 1 << 1`. `Face` is a `tileFaceIndex42`-style index, -1 when the source had no face; `FromSeat` is the absolute discarder for CHII/PON/KAN_OPEN, -1 otherwise.
  - `func (g *Game) PublicEvents() []PublicEvent` — the current round's log, oldest first (read-only contract; callers must not mutate).
  - `func FaceIndex42(tile *pb.Tile) (int, bool)` — exported face-index helper in events.go (engine-local mirror of rl's `tileFaceIndex42`; same mapping: man 0-8, pin 9-17, sou 18-26, jihai 27-33, flower 34-41).

- [ ] **Step 1: Write the failing unit tests**

Create `internal/engine/events_test.go` (package `engine` — mechanics only, no rules import):

```go
package engine

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestPublicEventLogAppendAndAccessor(t *testing.T) {
	g := &Game{State: &pb.GameState{}}
	g.logEvent(PublicEvent{Type: EventDraw, Seat: 1, Face: 5})
	g.logEvent(PublicEvent{Type: EventDiscard, Seat: 1, Face: 5, Flags: EventFlagTsumogiri})
	events := g.PublicEvents()
	if len(events) != 2 {
		t.Fatalf("want 2 events, got %d", len(events))
	}
	if events[0].Type != EventDraw || events[1].Type != EventDiscard {
		t.Fatalf("wrong order/types: %+v", events)
	}
	if events[1].Flags&EventFlagTsumogiri == 0 {
		t.Fatalf("tsumogiri flag lost")
	}
}

func TestPublicEventLogClearedByResetRoundEvents(t *testing.T) {
	g := &Game{State: &pb.GameState{}}
	g.logEvent(PublicEvent{Type: EventDraw, Seat: 0, Face: 3})
	g.resetRoundEvents()
	if len(g.PublicEvents()) != 0 {
		t.Fatalf("log not cleared at round start")
	}
}

func TestCloneCopiesEventLogByValue(t *testing.T) {
	g := &Game{State: &pb.GameState{Players: []*pb.PlayerState{{}, {}, {}, {}}}}
	g.logEvent(PublicEvent{Type: EventPon, Seat: 2, Face: 10, FromSeat: 0})
	clone := g.CloneForBranch()
	clone.logEvent(PublicEvent{Type: EventDraw, Seat: 3, Face: -1})
	if len(g.PublicEvents()) != 1 {
		t.Fatalf("clone append leaked into parent: parent has %d events", len(g.PublicEvents()))
	}
	if len(clone.PublicEvents()) != 2 {
		t.Fatalf("clone missing inherited event: has %d", len(clone.PublicEvents()))
	}
	// Mutating the parent's backing array must not show in the clone.
	g.publicEvents[0].Face = 11
	if clone.PublicEvents()[0].Face != 10 {
		t.Fatalf("clone shares backing array with parent")
	}
}

func TestFaceIndex42Mapping(t *testing.T) {
	cases := []struct {
		tile *pb.Tile
		want int
		ok   bool
	}{
		{&pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}, 0, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 9}, 17, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}, 18, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: 7}, 33, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: 8}, 41, true},
		{nil, 0, false},
	}
	for i, c := range cases {
		got, ok := FaceIndex42(c.tile)
		if ok != c.ok || (ok && got != c.want) {
			t.Fatalf("case %d: got (%d,%v) want (%d,%v)", i, got, ok, c.want, c.ok)
		}
	}
}
```

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/engine/ -run 'TestPublicEvent|TestClone|TestFaceIndex42' -v`
Expected: compile FAIL (`undefined: PublicEvent` etc.).

- [ ] **Step 3: Implement events.go**

Create `internal/engine/events.go`:

```go
package engine

import (
	pb "github.com/plasma/fh-mahjong/proto"
)

// PublicEventType enumerates the public event vocabulary rendered into RL
// observations. Values are wire-stable: they are bit-packed into uint32s
// shared with Python (ai/src/fh_mahjong_ai/events.py) — never renumber.
type PublicEventType uint8

const (
	EventDraw       PublicEventType = 0
	EventDiscard    PublicEventType = 1
	EventChii       PublicEventType = 2
	EventPon        PublicEventType = 3
	EventKanOpen    PublicEventType = 4
	EventKanClosed  PublicEventType = 5
	EventKanUpgrade PublicEventType = 6
	EventFlower     PublicEventType = 7
)

const (
	EventFlagTsumogiri uint8 = 1 << 0
	EventFlagHaitei    uint8 = 1 << 1
)

// PublicEvent is one entry of the per-round public event log. The engine
// stores TRUE faces (own draws included); information legality (masking
// opponents' draw faces) is enforced at observation-encode time, not here.
type PublicEvent struct {
	Type     PublicEventType
	Seat     uint32 // absolute seat; made observer-relative at encode time
	Face     int16  // FaceIndex42 index, -1 = none (e.g. a draw whose face is not public)
	FromSeat int32  // absolute discarder for CHII/PON/KAN_OPEN; -1 otherwise
	Flags    uint8
}

// FaceIndex42 maps a tile to the 42-face index used across the RL stack
// (man 0-8, pin 9-17, sou 18-26, jihai 27-33, flower 34-41).
func FaceIndex42(tile *pb.Tile) (int, bool) {
	if tile == nil {
		return 0, false
	}
	switch tile.Suit {
	case pb.Suit_SUIT_MAN:
		if tile.Value >= 1 && tile.Value <= 9 {
			return int(tile.Value - 1), true
		}
	case pb.Suit_SUIT_PIN:
		if tile.Value >= 1 && tile.Value <= 9 {
			return 9 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_SOU:
		if tile.Value >= 1 && tile.Value <= 9 {
			return 18 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_JIHAI:
		if tile.Value >= 1 && tile.Value <= 7 {
			return 27 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_FLOWER:
		if tile.Value >= 1 && tile.Value <= 8 {
			return 34 + int(tile.Value-1), true
		}
	}
	return 0, false
}

func faceOf(tile *pb.Tile) int16 {
	if idx, ok := FaceIndex42(tile); ok {
		return int16(idx)
	}
	return -1
}

// logEvent appends to the current round's public event log. Unlike the paipu
// Recorder this is ALWAYS on — RL envs never attach a recorder but do need
// the public record.
func (g *Game) logEvent(event PublicEvent) {
	g.publicEvents = append(g.publicEvents, event)
}

// resetRoundEvents truncates the log at round start (round context lives in
// the observation scalars; history is per-round by design).
func (g *Game) resetRoundEvents() {
	g.publicEvents = g.publicEvents[:0]
}

// PublicEvents returns the current round's public event log, oldest first.
// Callers must treat it as read-only.
func (g *Game) PublicEvents() []PublicEvent {
	return g.publicEvents
}
```

Add the field to the Game struct in `internal/engine/game.go` (after `interruptQueue` block, with the other private state):

```go
	// Per-round public event log (always on; see events.go). Cleared at
	// round start, value-copied by CloneForBranch.
	publicEvents []PublicEvent
```

In `internal/engine/clone.go`, inside `CloneForBranch`'s struct literal (alongside `interruptQueue: cloneInterruptQueue(...)`), add:

```go
		publicEvents: append([]PublicEvent(nil), g.publicEvents...),
```

- [ ] **Step 4: Run unit tests**

Run: `go test ./internal/engine/ -run 'TestPublicEvent|TestClone|TestFaceIndex42' -v`
Expected: PASS (4 tests). `TestCloneCopiesEventLogByValue` needs `CloneForBranch` to tolerate the minimal Game — if it panics on nil fields, construct the game in that test via `NewGame("clone-events", nil, MatchOptions{})` instead and skip `Start()`; the assertion logic stays identical.

- [ ] **Step 5: Wire capture into game.go**

At each site below, add the `logEvent` call adjacent to (NOT inside) the `if g.Recorder != nil` block, so capture is unconditional. Exact insertions:

Round start — in `dealTiles` immediately before the `if g.Recorder != nil {` that calls `StartRound` (~line 290):

```go
	g.resetRoundEvents()
```

Initial flowers (~388, next to `RecordInitialFlower`):

```go
			g.logEvent(PublicEvent{Type: EventFlower, Seat: seat, Face: faceOf(flower), FromSeat: -1})
```

Front draw (~526, next to `RecordDraw`):

```go
	g.logEvent(PublicEvent{Type: EventDraw, Seat: seat, Face: faceOf(drawnTile), FromSeat: -1})
```

Replacement/dead-wall draw (~641, next to its `RecordDraw`): same line as above (`drawnTile` is in scope there too).

Haitei accept (~768, next to `RecordHaiteiAccept`):

```go
	g.logEvent(PublicEvent{Type: EventDraw, Seat: seat, Face: faceOf(drawnTile), FromSeat: -1, Flags: EventFlagHaitei})
```

Discard (~824, next to `RecordDiscard`) — tsumogiri = discarding the tile just drawn:

```go
	discardFlags := uint8(0)
	if player.DrawnTileId != nil && uint32(*player.DrawnTileId) == action.Tile.Id {
		discardFlags = EventFlagTsumogiri
	}
	g.logEvent(PublicEvent{Type: EventDiscard, Seat: seat, Face: faceOf(action.Tile), FromSeat: -1, Flags: discardFlags})
```

IMPORTANT ordering: place this BEFORE any code in the discard handler that clears `player.DrawnTileId`, and verify `player` is the discarder's `*pb.PlayerState` in scope (it is — the same handler reads `player.Discards`). If the local variable is named differently at that site, use the actual name.

Kans (~925-939, next to the respective Record calls):

```go
				g.logEvent(PublicEvent{Type: EventKanUpgrade, Seat: seat, Face: faceOf(action.MeldTiles[0]), FromSeat: -1})
```
```go
				g.logEvent(PublicEvent{Type: EventKanClosed, Seat: seat, Face: faceOf(action.MeldTiles[0]), FromSeat: -1})
```
```go
			g.logEvent(PublicEvent{Type: EventFlower, Seat: seat, Face: faceOf(action.MeldTiles[0]), FromSeat: -1})
```

Claims (~1104-1108, next to RecordChii/RecordPon/RecordOpenKan; `winnerSeat`, `discarder` and the claimed `g.State.ActiveDiscard` are in scope):

```go
				g.logEvent(PublicEvent{Type: EventChii, Seat: winnerSeat, Face: faceOf(g.State.ActiveDiscard), FromSeat: int32(discarder)})
```
```go
				g.logEvent(PublicEvent{Type: EventPon, Seat: winnerSeat, Face: faceOf(g.State.ActiveDiscard), FromSeat: int32(discarder)})
```
```go
				g.logEvent(PublicEvent{Type: EventKanOpen, Seat: winnerSeat, Face: faceOf(g.State.ActiveDiscard), FromSeat: int32(discarder)})
```

CAUTION: at the claim sites, log BEFORE `ActiveDiscard` is nilled (the Record* calls there already read the claimed tiles — mirror their position). Tsumo/Ron/HaiteiRefuse get NO events (spec: win events end the round; refuse carries ~no information).

- [ ] **Step 6: Run the full engine + rl suites**

Run: `go vet ./internal/engine/ ./internal/rl/ && go test ./internal/engine/ ./internal/rl/`
Expected: PASS — capture is additive; nothing reads the log yet.

- [ ] **Step 7: Update internal/engine/AGENTS.md**

Add one bullet describing events.go: always-on per-round `PublicEventLog` at the paipu hook sites, cleared in `dealTiles`, value-copied by `CloneForBranch`, left untouched by `RedealUnseen` (all entries public), rendered into observations by `internal/rl` (Spec B1).

- [ ] **Step 8: Commit**

```bash
git add internal/engine/events.go internal/engine/events_test.go internal/engine/game.go internal/engine/clone.go internal/engine/AGENTS.md
git commit -m "feat(engine): always-on per-round public event log

Captured at the paipu hook call sites (never nil-guarded), cleared at round
start, value-copied by CloneForBranch. Spec B1 groundwork: internal/rl will
render this observer-relative into SeatObservation.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Proto fields + trilingual regen

**Files:**
- Modify: `proto/game.proto` (EnvConfig ~field 6, SeatObservation ~field 11)
- Regenerate: `proto/game.pb.go`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`

**Interfaces:**
- Produces: `pb.EnvConfig.EventHistoryWindow uint32` (Go) / `event_history_window` (Python), `pb.SeatObservation.EventHistory []uint32` + `EventHistoryWindow uint32`.

- [ ] **Step 1: Edit proto/game.proto**

In `message EnvConfig`, after `bool oracle_observation = 6;`:

```proto
  // Number of public events rendered into SeatObservation.event_history
  // (observer-relative, packed uint32s; see internal/rl/eventcodec.go).
  // 0 (default) disables the field entirely — byte-identical observations.
  uint32 event_history_window = 7;
```

In `message SeatObservation`, after `uint32 active_player = 11;`:

```proto
  // Packed public events, oldest first, observer-relative. Bit layout owned
  // by internal/rl/eventcodec.go and mirrored in ai/.../events.py. Empty
  // unless EnvConfig.event_history_window > 0.
  repeated uint32 event_history = 12;
  // The window W this env was configured with (0 = disabled).
  uint32 event_history_window = 13;
```

- [ ] **Step 2: Regenerate all three languages**

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
uv run --project ai python -m grpc_tools.protoc --python_out=ai/src/fh_mahjong_ai/generated --proto_path=. proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

(If protoc-gen-go is missing, `go install google.golang.org/protobuf/cmd/protoc-gen-go@latest` first. NEVER use bare `protoc --python_out` — proto/AGENTS.md: the 35.x line emits incompatible 7.x gencode.)

- [ ] **Step 3: Verify all three builds**

```bash
go build ./... && go vet ./...
uv run --project ai python -c "from fh_mahjong_ai.generated.proto import game_pb2; o = game_pb2.SeatObservation(event_history=[1,2], event_history_window=128); print(len(o.event_history))"
cd web && npx tsc --noEmit && cd ..
```
Expected: builds clean; Python prints `2`.

- [ ] **Step 4: Verify Go+Python suites unaffected**

Run: `go test ./... && uv run --project ai pytest`
Expected: all PASS (fields are dormant).

- [ ] **Step 5: Commit**

```bash
git add proto/game.proto proto/game.pb.go ai/src/fh_mahjong_ai/generated web/src/proto/game.js web/src/proto/game.d.ts
git commit -m "feat(proto): event_history fields on SeatObservation + EnvConfig (dormant)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: RL — observer-relative rendering + env plumbing + behavioral tests

**Files:**
- Create: `internal/rl/eventcodec.go`
- Create: `internal/rl/eventcodec_test.go`
- Modify: `internal/rl/observation.go` (encodeObservation ~24, EncodeObservation ~177, emptyObservation ~181)
- Modify: `internal/rl/env.go` (every `encodeObservation`/`emptyObservation` call site — grep them)
- Modify: `internal/rl/AGENTS.md`

**Interfaces:**
- Consumes: `engine.PublicEvent`, `engine.PublicEventType`, `Event*` constants, `engine.EventFlagTsumogiri/Haitei`, `g.PublicEvents()` (Task 1); proto fields (Task 2).
- Produces:
  - `func packPublicEvent(event engine.PublicEvent, observer uint32) uint32` — the bit layout's Go encoder (UNKNOWN face masking included).
  - `func renderEventHistory(events []engine.PublicEvent, observer uint32, window uint32) []uint32` — last `window` events, oldest first; nil when window==0.
  - `encodeObservation(state, seat, decisionIndex, oracle, events []engine.PublicEvent, window uint32)` — internal signature change; exported `EncodeObservation` keeps its current 3-arg signature (passes `nil, 0`).
  - Bit-layout constants: `eventTypeBits=4`... (see implementation) and `EventFaceUnknown = 63`.

- [ ] **Step 1: Write the failing codec tests**

Create `internal/rl/eventcodec_test.go`:

```go
package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
)

// The golden vector pinning the bit layout. ai/tests/test_events.py carries
// the IDENTICAL (packed, fields) pairs — change one, change both.
var eventGoldenVector = []struct {
	event    engine.PublicEvent
	observer uint32
	packed   uint32
}{
	// Own draw, face 5 visible, observer 1 == actor 1 -> rel seat 0.
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 1, Face: 5, FromSeat: -1}, 1, 0x0000_0140},
	// Opponent draw: observer 0 sees actor 2 (rel 2), face MASKED -> 63.
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 2, Face: 5, FromSeat: -1}, 0, 0x0000_0FE0},
	// Tsumogiri discard by right neighbor (actor 1, observer 0), face 41.
	{engine.PublicEvent{Type: engine.EventDiscard, Seat: 1, Face: 41, FromSeat: -1, Flags: engine.EventFlagTsumogiri}, 0, 0x0000_4A51},
	// Pon by across (actor 2) from left (seat 3), observer 0, face 10.
	{engine.PublicEvent{Type: engine.EventPon, Seat: 2, Face: 10, FromSeat: 3}, 0, 0x0000_32A3},
	// Haitei draw by self, face 0 (a real face: 1m).
	{engine.PublicEvent{Type: engine.EventDraw, Seat: 3, Face: 0, FromSeat: -1, Flags: engine.EventFlagHaitei}, 3, 0x0000_8000},
	// Flower reveal by left neighbor (actor 3, observer 0), face 34.
	{engine.PublicEvent{Type: engine.EventFlower, Seat: 3, Face: 34, FromSeat: -1}, 0, 0x0000_08B7},
}

func TestPackPublicEventGoldenVector(t *testing.T) {
	for i, c := range eventGoldenVector {
		got := packPublicEvent(c.event, c.observer)
		if got != c.packed {
			t.Fatalf("golden %d: packed 0x%08X, want 0x%08X (event %+v observer %d)", i, got, c.packed, c.event, c.observer)
		}
		if got>>16 != 0 {
			t.Fatalf("golden %d: reserved bits set: 0x%08X", i, got)
		}
	}
}

func TestRenderEventHistoryWindowAndOrder(t *testing.T) {
	events := make([]engine.PublicEvent, 10)
	for i := range events {
		events[i] = engine.PublicEvent{Type: engine.EventDiscard, Seat: uint32(i % 4), Face: int16(i), FromSeat: -1}
	}
	rendered := renderEventHistory(events, 0, 4)
	if len(rendered) != 4 {
		t.Fatalf("window 4: got %d", len(rendered))
	}
	// Last 4 events, oldest first: faces 6,7,8,9.
	for i, packed := range rendered {
		face := (packed >> 6) & 0x3F
		if face != uint32(6+i) {
			t.Fatalf("truncation order wrong at %d: face %d want %d", i, face, 6+i)
		}
	}
	if renderEventHistory(events, 0, 0) != nil {
		t.Fatalf("window 0 must render nil")
	}
	if got := renderEventHistory(events[:2], 0, 8); len(got) != 2 {
		t.Fatalf("short log: got %d want 2", len(got))
	}
}

func TestRelativeSeatRendering(t *testing.T) {
	event := engine.PublicEvent{Type: engine.EventDiscard, Seat: 2, Face: 7, FromSeat: -1}
	for observer := uint32(0); observer < 4; observer++ {
		packed := packPublicEvent(event, observer)
		rel := (packed >> 4) & 0x3
		want := (2 + 4 - observer) % 4
		if rel != want {
			t.Fatalf("observer %d: rel seat %d want %d", observer, rel, want)
		}
	}
}
```

Golden `packed` values are computed from the layout: `type | rel<<4 | face<<6 | from<<12 | tsumogiri<<14 | haitei<<15`. Worked examples: golden[0]: type 0, rel 0, face 5 → 5<<6 = 0x140. golden[1]: type 0, rel 2 → 0x20, face 63 → 63<<6 = 0xFC0 → 0xFE0. golden[2]: type 1, rel 1 → 0x10, face 41<<6 = 0xA40, tsumogiri 1<<14 = 0x4000 → 0x4A51. golden[3]: type 3, rel 2 → 0x20, face 10<<6 = 0x280, from rel (3-0)=3 → 3<<12 = 0x3000 → 0x32A3. golden[4]: type 0, rel 0, face 0, haitei 1<<15 = 0x8000. golden[5]: type 7, rel 3 → 0x30, face 34<<6 = 0x880 → 0x8B7.

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/rl/ -run 'TestPackPublicEvent|TestRenderEventHistory|TestRelativeSeat' -v`
Expected: compile FAIL (`undefined: packPublicEvent`).

- [ ] **Step 3: Implement eventcodec.go**

Create `internal/rl/eventcodec.go`:

```go
package rl

import (
	"github.com/plasma/fh-mahjong/internal/engine"
)

// Packed public-event bit layout — the single source of truth, mirrored
// verbatim in ai/src/fh_mahjong_ai/events.py. Wire-stable: never reorder.
//
//	bits  0-3  event type (engine.PublicEventType)
//	bits  4-5  actor seat RELATIVE to observer (0=self,1=right,2=across,3=left)
//	bits  6-11 face index 0-41; 63 = unknown (masked opponent draw)
//	bits 12-13 from-seat RELATIVE to observer (calls only; 0 otherwise)
//	bit  14    tsumogiri flag
//	bit  15    haitei flag
//	bits 16-31 reserved, always zero
const (
	eventSeatShift = 4
	eventFaceShift = 6
	eventFromShift = 12
	eventTsumogiriBit = 1 << 14
	eventHaiteiBit    = 1 << 15

	// EventFaceUnknown is the face sentinel for information-illegal faces
	// (an opponent's draw) and absent faces.
	EventFaceUnknown = 63
)

func relativeSeatTo(observer, seat uint32) uint32 {
	return (seat + 4 - observer) % 4
}

// packPublicEvent renders one engine event for one observer. Information
// legality lives HERE: a DRAW's face is visible only to the drawing seat.
func packPublicEvent(event engine.PublicEvent, observer uint32) uint32 {
	face := uint32(EventFaceUnknown)
	if event.Face >= 0 && int(event.Face) < 42 {
		face = uint32(event.Face)
	}
	if event.Type == engine.EventDraw && event.Seat != observer {
		face = EventFaceUnknown
	}

	packed := uint32(event.Type) & 0xF
	packed |= relativeSeatTo(observer, event.Seat) << eventSeatShift
	packed |= face << eventFaceShift
	if event.FromSeat >= 0 {
		packed |= relativeSeatTo(observer, uint32(event.FromSeat)) << eventFromShift
	}
	if event.Flags&engine.EventFlagTsumogiri != 0 {
		packed |= eventTsumogiriBit
	}
	if event.Flags&engine.EventFlagHaitei != 0 {
		packed |= eventHaiteiBit
	}
	return packed
}

// renderEventHistory packs the last `window` events, oldest first.
// window == 0 returns nil: the observation stays byte-identical to pre-B1.
func renderEventHistory(events []engine.PublicEvent, observer uint32, window uint32) []uint32 {
	if window == 0 || len(events) == 0 {
		return nil
	}
	start := 0
	if len(events) > int(window) {
		start = len(events) - int(window)
	}
	out := make([]uint32, 0, len(events)-start)
	for _, event := range events[start:] {
		out = append(out, packPublicEvent(event, observer))
	}
	return out
}
```

- [ ] **Step 4: Run codec tests**

Run: `go test ./internal/rl/ -run 'TestPackPublicEvent|TestRenderEventHistory|TestRelativeSeat' -v`
Expected: PASS. If a golden value disagrees, re-derive by hand from the layout — fix the CODE or the hand computation, never fudge the constant to match the code.

- [ ] **Step 5: Thread history through encodeObservation**

In `internal/rl/observation.go`:

1. Change the internal signature (line ~24):

```go
func encodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64, oracle bool, events []engine.PublicEvent, window uint32) (*pb.SeatObservation, error) {
```

(add `"github.com/plasma/fh-mahjong/internal/engine"` to imports.)

2. At the end of the function, where the `*pb.SeatObservation` is assembled, add to the struct literal:

```go
		EventHistory:       renderEventHistory(events, seat, window),
		EventHistoryWindow: window,
```

3. Exported wrapper (line ~177) keeps its signature:

```go
func EncodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64) (*pb.SeatObservation, error) {
	return encodeObservation(state, seat, decisionIndex, false, nil, 0)
}
```

4. `emptyObservation` (line ~181) gains the same two params and sets `EventHistoryWindow: window` with nil `EventHistory`:

```go
func emptyObservation(state *pb.GameState, decisionIndex uint64, oracle bool, window uint32) *pb.SeatObservation {
```

5. Update every caller: `grep -n "encodeObservation(\|emptyObservation(" internal/rl/*.go`. In `env.go`, pass `e.game.PublicEvents(), e.config.EventHistoryWindow` (and `e.config.EventHistoryWindow` to emptyObservation). In `searchpool.go`, the clone encodes via its own env's game — same expression on the clone env. `normalizeConfig` needs no change if it copies the whole proto config (verify it carries `EventHistoryWindow` through — it does if it clones the message; if it builds field-by-field, add the field).

6. Also update the ONE other production caller of the 4-arg internal form if any exists outside internal/rl (grep the repo for `encodeObservation(` — it is package-private, so only internal/rl compiles against it).

- [ ] **Step 6: Write the behavioral tests**

Append to `internal/rl/eventcodec_test.go`:

```go
func newSeededHistoryEnv(t *testing.T, seed uint64, window uint32) *Env {
	t.Helper()
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		EventHistoryWindow: window,
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	return env
}

// Dormant byte-parity: at window=0 the marshaled observation must be
// byte-identical to one with the event fields force-cleared (i.e. the
// fields are entirely absent from the wire).
func TestDormantWindowByteParity(t *testing.T) {
	env := newSeededHistoryEnv(t, 42, 0)
	rng := rand.New(rand.NewSource(42))
	obs := env.lastObservationForTest()
	for step := 0; obs != nil && step < 200; step++ {
		raw, err := proto.Marshal(obs)
		if err != nil {
			t.Fatalf("marshal: %v", err)
		}
		cleared := proto.Clone(obs).(*pb.SeatObservation)
		cleared.EventHistory = nil
		cleared.EventHistoryWindow = 0
		clearedRaw, err := proto.Marshal(cleared)
		if err != nil {
			t.Fatalf("marshal cleared: %v", err)
		}
		if !bytes.Equal(raw, clearedRaw) {
			t.Fatalf("step %d: window=0 observation carries event bytes", step)
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
}

// Information legality + own-draw visibility over a full random match.
func TestEventHistoryInformationLegality(t *testing.T) {
	env := newSeededHistoryEnv(t, 7, 128)
	rng := rand.New(rand.NewSource(7))
	obs := env.lastObservationForTest()
	checkedOwnDraw := false
	for step := 0; obs != nil && step < 3000; step++ {
		for _, packed := range obs.EventHistory {
			if packed>>16 != 0 {
				t.Fatalf("reserved bits set: 0x%08X", packed)
			}
			evType := packed & 0xF
			rel := (packed >> 4) & 0x3
			face := (packed >> 6) & 0x3F
			if evType == uint32(engine.EventDraw) {
				if rel != 0 && face != EventFaceUnknown {
					t.Fatalf("LEAK: observer %d sees opponent draw face %d (packed 0x%08X)", obs.Seat, face, packed)
				}
				if rel == 0 {
					if face == EventFaceUnknown {
						t.Fatalf("own draw masked for observer %d", obs.Seat)
					}
					checkedOwnDraw = true
				}
			}
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	if !checkedOwnDraw {
		t.Fatalf("premise broken: no own-draw event ever observed")
	}
}

// Golden cross-check vs the paipu record: the event log and the recorder
// must tell the same story for the same seeded match.
func TestEventLogMatchesPaipuRecord(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		EventHistoryWindow: 512,
	}
	env := New(config)
	env.game = engine.NewGame("golden-events", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.Recorder = engine.NewPaipuRecorder("golden-events", "fenghua")
	env.game.SetWallSeed(engine.SeedFromUint64(99))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	env.lastScores = snapshotScores(env.game.State)
	step, err := env.advanceToDecision()
	if err != nil {
		t.Fatalf("advance: %v", err)
	}
	obs := step.Observation
	rng := rand.New(rand.NewSource(99))
	// Drive ONE round: stop at the first round boundary (log would clear).
	startEvents := len(env.game.PublicEvents())
	if startEvents == 0 {
		t.Fatalf("premise: initial deal produced no events (expected initial flowers or first draw)")
	}
	for i := 0; obs != nil && i < 3000; i++ {
		if env.game.State.Phase == pb.GamePhase_PHASE_ROUND_END || env.game.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			break
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil {
			t.Fatalf("step %d: %v", i, err)
		}
		if sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}

	paipu := env.game.Recorder.Finalize([4]int32{})
	// The round may still be current (unfinished) — pull actions from the
	// recorder's completed rounds or skip if none completed; either way the
	// event log covers the CURRENT round, so compare against the actions
	// recorded SINCE the last StartRound. Simplest robust form: replay the
	// recorder's last-known actions if a round completed, else compare
	// counts of each public action kind seen so far.
	var actions []engine.PaipuAction
	if len(paipu.Rounds) > 0 && env.game.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		actions = paipu.Rounds[len(paipu.Rounds)-1].Actions
	}
	if actions == nil {
		t.Skipf("no completed round at seed 99 within budget — pick a seed that finishes a round")
	}

	expected := make([]engine.PublicEvent, 0, len(actions))
	for _, a := range actions {
		switch a.Act {
		case "draw", "haitei":
			expected = append(expected, engine.PublicEvent{Type: engine.EventDraw, Seat: a.Seat})
		case "discard":
			expected = append(expected, engine.PublicEvent{Type: engine.EventDiscard, Seat: a.Seat})
		case "chii":
			expected = append(expected, engine.PublicEvent{Type: engine.EventChii, Seat: a.Seat})
		case "pon":
			expected = append(expected, engine.PublicEvent{Type: engine.EventPon, Seat: a.Seat})
		case "okan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanOpen, Seat: a.Seat})
		case "ckan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanClosed, Seat: a.Seat})
		case "ukan":
			expected = append(expected, engine.PublicEvent{Type: engine.EventKanUpgrade, Seat: a.Seat})
		case "flower":
			expected = append(expected, engine.PublicEvent{Type: engine.EventFlower, Seat: a.Seat})
		}
	}
	got := env.game.PublicEvents()
	// The log also holds initial-flower events the paipu stores outside
	// Actions; drop leading EventFlower entries not present in expected.
	for len(got) > 0 && got[0].Type == engine.EventFlower && (len(expected) == 0 || expected[0].Type != engine.EventFlower) {
		got = got[1:]
	}
	if len(got) != len(expected) {
		t.Fatalf("event count %d != paipu public-action count %d", len(got), len(expected))
	}
	for i := range got {
		if got[i].Type != expected[i].Type || got[i].Seat != expected[i].Seat {
			t.Fatalf("event %d: got {%d seat %d} want {%d seat %d}", i, got[i].Type, got[i].Seat, expected[i].Type, expected[i].Seat)
		}
	}
}

// Tsumogiri capture invariant over a full random match: every
// tsumogiri-flagged DISCARD's most recent preceding DRAW in the raw log is
// by the same seat (you can only cut the tile you just drew), and at least
// one flagged and one unflagged discard occur (both paths exercised).
func TestTsumogiriFlagCapture(t *testing.T) {
	env := newSeededHistoryEnv(t, 23, 512)
	rng := rand.New(rand.NewSource(23))
	obs := env.lastObservationForTest()
	for i := 0; obs != nil && i < 3000; i++ {
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	events := env.game.PublicEvents()
	flagged, unflagged := 0, 0
	for i, event := range events {
		if event.Type != engine.EventDiscard {
			continue
		}
		if event.Flags&engine.EventFlagTsumogiri == 0 {
			unflagged++
			continue
		}
		flagged++
		found := false
		for j := i - 1; j >= 0; j-- {
			if events[j].Type == engine.EventDraw {
				if events[j].Seat != event.Seat {
					t.Fatalf("event %d: tsumogiri discard by seat %d but last draw was by seat %d", i, event.Seat, events[j].Seat)
				}
				found = true
				break
			}
		}
		if !found {
			t.Fatalf("event %d: tsumogiri discard with no preceding draw", i)
		}
	}
	if flagged == 0 || unflagged == 0 {
		t.Fatalf("premise: need both flagged (%d) and unflagged (%d) discards — pick a different seed", flagged, unflagged)
	}
}

// Clone (search) consistency: clone inherits the record; clone appends
// don't leak back.
func TestSearchCloneEventConsistency(t *testing.T) {
	env := newSeededHistoryEnv(t, 11, 128)
	rng := rand.New(rand.NewSource(11))
	obs := env.lastObservationForTest()
	for i := 0; i < 40 && obs != nil; i++ {
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil || sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	parentLen := len(env.game.PublicEvents())
	if parentLen == 0 {
		t.Fatalf("premise: no events after 40 steps")
	}
	clone := env.game.CloneForBranch()
	if len(clone.PublicEvents()) != parentLen {
		t.Fatalf("clone log %d != parent %d", len(clone.PublicEvents()), parentLen)
	}
	if err := clone.ExecuteSystemDraw(clone.State.ActivePlayer); err == nil {
		if len(env.game.PublicEvents()) != parentLen {
			t.Fatalf("clone draw leaked into parent log")
		}
	}
}
```

Add `lastObservationForTest` if no equivalent accessor exists — a tiny in-package test helper in `eventcodec_test.go` is fine:

```go
// lastObservationForTest re-encodes the current decision observation.
func (e *Env) lastObservationForTest() *pb.SeatObservation {
	seat, ok := e.currentActionSeat()
	if !ok {
		seat = e.game.State.ActivePlayer
	}
	obs, err := encodeObservation(e.game.State, seat, e.decisionCount, e.config.OracleObservation, e.game.PublicEvents(), e.config.EventHistoryWindow)
	if err != nil {
		return nil
	}
	return obs
}
```

Imports needed in the test file: `bytes`, `math/rand`, `google.golang.org/protobuf/proto`, `github.com/plasma/fh-mahjong/internal/rules`.

- [ ] **Step 7: Run the rl suite**

Run: `go vet ./internal/rl/ && go test ./internal/rl/ -count=1`
Expected: all PASS, including every pre-existing test (signature updates compile everywhere; dormant parity holds). If `TestEventLogMatchesPaipuRecord` skips at seed 99, bump the seed until a round completes and pin it.

- [ ] **Step 8: Full Go suite + AGENTS.md**

Run: `go vet ./... && go test ./...` — PASS.
Update `internal/rl/AGENTS.md`: eventcodec.go owns the packed bit layout (mirrored in ai/.../events.py — change both or neither), rendering is observer-relative with draw-face masking, dormant at window 0.

- [ ] **Step 9: Commit**

```bash
git add internal/rl/eventcodec.go internal/rl/eventcodec_test.go internal/rl/observation.go internal/rl/env.go internal/rl/AGENTS.md
git commit -m "feat(rl): observer-relative packed event history in SeatObservation

Dormant at event_history_window=0 (byte-parity tested); information
legality enforced at encode time (opponent draw faces masked); golden
vector pins the bit layout; paipu cross-check, clone-consistency,
truncation and relative-seat tests.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(If searchpool.go changed in Step 5, stage it too.)

---

### Task 4: Python — events.py, config, bridge surfaces

**Files:**
- Create: `ai/src/fh_mahjong_ai/events.py`
- Create: `ai/tests/test_events.py`
- Modify: `ai/src/fh_mahjong_ai/config.py` (EnvConfig, ~line 9)
- Modify: `ai/src/fh_mahjong_ai/types.py` (Observation, ~line 13)
- Modify: `ai/src/fh_mahjong_ai/bridge.py` (`_config_message` ~293, `_decode_observation` ~339, mock `_observe` ~142)

**Interfaces:**
- Consumes: proto fields from Task 2; the bit layout (Global Constraints).
- Produces:
  - `events.py`: `EVENT_DRAW=0 ... EVENT_FLOWER=7`, `FACE_UNKNOWN=63`, `NUM_EVENT_TYPES=8`, `@dataclass(frozen=True) Event(type, rel_seat, face, rel_from, tsumogiri, haitei)`, `encode_event(Event) -> int`, `decode_event(int) -> Event` (raises `ValueError` on nonzero reserved bits), `decode_history(np.ndarray) -> list[Event]`, `event_to_token(Event) -> int` (B2 embedding index: `type*4*64 + rel_seat*64 + face`, vocab size `8*4*64 = 2048`; flags/from-seat are separate features, documented).
  - `EnvConfig.event_history_window: int = 0`.
  - `Observation.event_history: IntArray` (uint32, default empty).

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_events.py`:

```python
import numpy as np
import pytest

from fh_mahjong_ai.events import (
    EVENT_DISCARD,
    EVENT_DRAW,
    EVENT_FLOWER,
    EVENT_PON,
    FACE_UNKNOWN,
    Event,
    decode_event,
    decode_history,
    encode_event,
    event_to_token,
)

# The IDENTICAL golden vector as internal/rl/eventcodec_test.go — the two
# tests pin the cross-language bit layout. Change one, change both.
GOLDEN = [
    (0x00000140, Event(EVENT_DRAW, 0, 5, 0, False, False)),
    (0x00000FE0, Event(EVENT_DRAW, 2, FACE_UNKNOWN, 0, False, False)),
    (0x00004A51, Event(EVENT_DISCARD, 1, 41, 0, True, False)),
    (0x000032A3, Event(EVENT_PON, 2, 10, 3, False, False)),
    (0x00008000, Event(EVENT_DRAW, 0, 0, 0, False, True)),
    (0x000008B7, Event(EVENT_FLOWER, 3, 34, 0, False, False)),
]


def test_golden_vector_decode():
    for packed, expected in GOLDEN:
        assert decode_event(packed) == expected


def test_golden_vector_roundtrip():
    for packed, event in GOLDEN:
        assert encode_event(event) == packed
        assert decode_event(encode_event(event)) == event


def test_reserved_bits_rejected():
    with pytest.raises(ValueError, match="reserved"):
        decode_event(0x00010000)


def test_decode_history_order():
    packed = np.asarray([p for p, _ in GOLDEN], dtype=np.uint32)
    events = decode_history(packed)
    assert [e.type for e in events] == [e.type for _, e in GOLDEN]


def test_event_to_token_bounds():
    tokens = {event_to_token(e) for _, e in GOLDEN}
    assert all(0 <= t < 8 * 4 * 64 for t in tokens)
    # Distinct (type, seat, face) triples get distinct tokens.
    assert len(tokens) == len({(e.type, e.rel_seat, e.face) for _, e in GOLDEN})


def test_env_config_window_field():
    from fh_mahjong_ai.config import EnvConfig

    config = EnvConfig(bridge_kind="mock", event_history_window=128)
    assert config.event_history_window == 128
    assert EnvConfig(bridge_kind="mock").event_history_window == 0


def test_mock_bridge_emits_wellformed_history():
    from fh_mahjong_ai.bridge import build_bridge
    from fh_mahjong_ai.config import EnvConfig

    config = EnvConfig(bridge_kind="mock", event_history_window=16, seed=3)
    bridge = build_bridge(config)
    obs = bridge.reset(seed=3)
    assert obs.event_history.dtype == np.uint32
    assert 0 < obs.event_history.size <= 16
    for event in decode_history(obs.event_history):
        assert 0 <= event.type <= 7
        assert 0 <= event.rel_seat <= 3

    # Window 0: empty array, decode yields nothing.
    off = build_bridge(EnvConfig(bridge_kind="mock", seed=3))
    assert off.reset(seed=3).event_history.size == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_events.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.events'`.

- [ ] **Step 3: Implement events.py**

Create `ai/src/fh_mahjong_ai/events.py`:

```python
"""Packed public-event codec — the Python mirror of internal/rl/eventcodec.go.

Bit layout (wire-stable; change BOTH files or neither):
    bits  0-3  event type
    bits  4-5  actor seat relative to observer (0=self,1=right,2=across,3=left)
    bits  6-11 face index 0-41; 63 = unknown (masked opponent draw)
    bits 12-13 from-seat relative to observer (calls only; 0 otherwise)
    bit  14    tsumogiri flag
    bit  15    haitei flag
    bits 16-31 reserved, always zero
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

EVENT_DRAW = 0
EVENT_DISCARD = 1
EVENT_CHII = 2
EVENT_PON = 3
EVENT_KAN_OPEN = 4
EVENT_KAN_CLOSED = 5
EVENT_KAN_UPGRADE = 6
EVENT_FLOWER = 7
NUM_EVENT_TYPES = 8

FACE_UNKNOWN = 63

_SEAT_SHIFT = 4
_FACE_SHIFT = 6
_FROM_SHIFT = 12
_TSUMOGIRI_BIT = 1 << 14
_HAITEI_BIT = 1 << 15
_RESERVED_MASK = ~0xFFFF & 0xFFFFFFFF


@dataclass(frozen=True)
class Event:
    type: int
    rel_seat: int
    face: int
    rel_from: int
    tsumogiri: bool
    haitei: bool


def encode_event(event: Event) -> int:
    packed = event.type & 0xF
    packed |= (event.rel_seat & 0x3) << _SEAT_SHIFT
    packed |= (event.face & 0x3F) << _FACE_SHIFT
    packed |= (event.rel_from & 0x3) << _FROM_SHIFT
    if event.tsumogiri:
        packed |= _TSUMOGIRI_BIT
    if event.haitei:
        packed |= _HAITEI_BIT
    return packed


def decode_event(packed: int) -> Event:
    packed = int(packed)
    if packed & _RESERVED_MASK:
        raise ValueError(f"reserved bits set in packed event 0x{packed:08X}")
    return Event(
        type=packed & 0xF,
        rel_seat=(packed >> _SEAT_SHIFT) & 0x3,
        face=(packed >> _FACE_SHIFT) & 0x3F,
        rel_from=(packed >> _FROM_SHIFT) & 0x3,
        tsumogiri=bool(packed & _TSUMOGIRI_BIT),
        haitei=bool(packed & _HAITEI_BIT),
    )


def decode_history(packed: np.ndarray) -> List[Event]:
    return [decode_event(value) for value in np.asarray(packed, dtype=np.uint32).tolist()]


def event_to_token(event: Event) -> int:
    """Embedding index for B2's event encoder: (type, rel_seat, face) -> [0, 2048).

    Flags and rel_from ride as separate small features next to the token
    embedding — they carry too little mass to burn vocabulary on.
    """
    return (event.type * 4 + event.rel_seat) * 64 + event.face
```

- [ ] **Step 4: Wire config, types, bridges**

`ai/src/fh_mahjong_ai/config.py` — add to `EnvConfig` after `oracle_observation`:

```python
    event_history_window: int = 0
```

`ai/src/fh_mahjong_ai/types.py` — add to `Observation` (import `field` is already there):

```python
    event_history: IntArray = field(default_factory=lambda: np.zeros(0, dtype=np.uint32))
```

(Place AFTER `action_mask` but BEFORE `metadata` so positional construction sites break loudly at test time rather than silently misassign — then fix any positional constructors the type checker/tests surface, or use keyword args.)

`ai/src/fh_mahjong_ai/bridge.py`:

1. `_config_message` (~293), next to `oracle_observation`:

```python
        message.event_history_window = int(self.config.event_history_window)
```

2. `_decode_observation` (~339), add before the `return Observation(...)` and pass it:

```python
        event_history = np.asarray(observation.event_history, dtype=np.uint32)
```
```python
            event_history=event_history,
```

3. Mock `_observe` (~142): fabricate well-formed events when the window is on. Before `return Observation(...)`:

```python
        event_history = np.zeros(0, dtype=np.uint32)
        window = int(getattr(self.config, "event_history_window", 0))
        if window > 0:
            from .events import Event, encode_event

            count = int(self._rng.integers(low=1, high=window + 1))
            event_history = np.asarray(
                [
                    encode_event(
                        Event(
                            type=int(self._rng.integers(0, 8)),
                            rel_seat=int(self._rng.integers(0, 4)),
                            face=int(self._rng.integers(0, 42)),
                            rel_from=int(self._rng.integers(0, 4)),
                            tsumogiri=bool(self._rng.integers(0, 2)),
                            haitei=False,
                        )
                    )
                    for _ in range(count)
                ],
                dtype=np.uint32,
            )
```

and pass `event_history=event_history` in the mock's `Observation(...)`.

- [ ] **Step 5: Run the new tests, then the full suite**

Run: `uv run --project ai pytest ai/tests/test_events.py -v` — all PASS.
Run: `uv run --project ai pytest` — all PASS (the Observation field is default-valued; existing constructors unaffected unless positional — fix any that break with keywords).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/events.py ai/tests/test_events.py ai/src/fh_mahjong_ai/config.py ai/src/fh_mahjong_ai/types.py ai/src/fh_mahjong_ai/bridge.py
git commit -m "feat(ai): event-history codec mirror, config knob, bridge surfaces

events.py mirrors the Go bit layout (shared golden vector), Observation
gains event_history (uint32, empty by default), Go bridge decodes the
proto field, mock fabricates well-formed events, event_to_token ready
for B2's embedding.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Whole-branch verification + docs sweep

**Files:**
- Modify: `ai/AGENTS.md` (events.py entry: codec mirror, event_to_token contract, window knob)
- Verify: everything

- [ ] **Step 1: AGENTS.md sweep**

Confirm Task 1 updated `internal/engine/AGENTS.md` and Task 3 updated `internal/rl/AGENTS.md`; add the `ai/AGENTS.md` entry for events.py + `EnvConfig.event_history_window` (one bullet each, matching file style). `proto/AGENTS.md` needs a line only if it lists fields (check; likely it documents commands only).

- [ ] **Step 2: Full verification**

```bash
go vet ./... && go test ./...
uv run --project ai pytest
cd web && npx tsc --noEmit && cd ..
git diff origin/main --stat
```
Expected: all clean; diff touches only: `internal/engine/{events.go,events_test.go,game.go,clone.go,AGENTS.md}`, `proto/game.proto` + generated (Go/Py/TS), `internal/rl/{eventcodec.go,eventcodec_test.go,observation.go,env.go,searchpool.go?,AGENTS.md}`, `ai/src/fh_mahjong_ai/{events.py,config.py,types.py,bridge.py}`, `ai/tests/test_events.py`, `ai/AGENTS.md`, spec + this plan.

- [ ] **Step 3: Commit docs sweep**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document events.py codec + event_history_window

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Then: final whole-branch review → adversarial-review-loop → PR → GitHub Codex approval → `gh pr merge N --merge` (user workflow).
