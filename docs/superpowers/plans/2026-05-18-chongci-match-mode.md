# Chongci Match Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Chongci match-mode flag end-to-end (proto, engine, API, frontend) that turns the existing per-hand Fenghua engine into a configurable bust-out tournament: every player starts with a small stack (default 2000), each hand's winner becomes next hand's dealer, draws keep the dealer (renchan), and the match terminates when any score drops at or below a configurable threshold (default 0) or a hand-cap (default 50) is reached.

**Architecture:** Match-mode state lives on `core.Game`. `NewGame` accepts a `MatchOptions{Mode, ChongciConfig}`; classic mode is the zero value and preserves today's behavior. A new `PHASE_MATCH_END` terminal phase carries a `MatchEndResult` (reason + sorted standings). A new next-dealer override is consumed once by `dealTiles()`. The seven `PlayerReady = []bool{false,false,false,false}` sites collapse into one `finalizeRoundEnd()` helper that owns dealer succession and end-of-match detection. Host configuration of private-table Chongci settings flows through a new `POST /api/v1/private-tables/:tableId/mode` endpoint; a parallel `queue:chongci-fh` public queue ships fixed defaults.

**Tech Stack:** Go 1.25, Gin, protobuf, GORM/PostgreSQL, React 19 + TypeScript + Vite, protobufjs.

**Spec:** [docs/superpowers/specs/2026-05-18-chongci-match-mode-design.md](../specs/2026-05-18-chongci-match-mode-design.md)

---

## File Structure

**Created:**
- `web/src/pages/MatchEndOverlay.tsx` — Chongci final-standings modal.

**Modified:**
- `proto/game.proto` — adds `MatchMode`, `ChongciConfig`, `PlayerStanding`, `MatchEndResult`, `PHASE_MATCH_END`; new `GameState` fields `match_mode`, `chongci_config`, `match_end_result`; `PrivateTableState` gains `match_mode` and `chongci_config`.
- `proto/game.pb.go` — regenerated.
- `web/src/proto/game.js`, `web/src/proto/game.d.ts`, `web/src/proto/game_cjs.js` — regenerated.
- `core/game.go` — `MatchOptions` type, `NewGame` signature change, `SetNextDealer`, `dealTiles` consumes override, new `finalizeRoundEnd`/`shouldEndChongciMatch`/`computeMatchEndResult`/`currentDealerSeat` helpers, action gating on `PHASE_MATCH_END`. All seven `PlayerReady` literal initializers collapse into `finalizeRoundEnd()`.
- `core/game_test.go` — call-site updates and new tests for `MatchOptions`, dealer override, finalizeRoundEnd, standings, dealer succession.
- `core/flower_auto_reveal_test.go` — call-site updates for `NewGame`.
- `core/paipu_test.go` — call-site update.
- `core/AGENTS.md` — describes the new match-mode plumbing.
- `rlenv/env.go` — call-site update.
- `cmd/cli/main.go` — call-site update.
- `cmd/rlpaipu/main.go` — call-site update.
- `api/room.go` — call-site update; new `WithMatchOptions` option threads `MatchOptions` into `core.NewGame`; handler for `PHASE_MATCH_END` broadcasts then 30s grace shutdown.
- `api/matchmaker.go` — `createMatch` maps ruleset key to `MatchOptions`; `StartPrivateTable` reads `MatchMode`/`ChongciConfig` from the registry.
- `api/private_tables.go` — `PrivateTable` struct gains `MatchMode` + `ChongciConfig`; `setMatchMode` method; `toProto` carries the new fields; new `handlePrivateTableMode` handler; new sentinels `ErrModeLocked`, `ErrChongciConfigInvalid`.
- `api/private_tables_test.go` — tests for mode endpoint, validation, threading into `NewGame`.
- `api/server.go` — registers `POST /api/v1/private-tables/:tableId/mode`.
- `api/server_test.go` — integration tests for the new endpoint and the public Chongci queue.
- `api/room_bot_test.go` — end-to-end bust + hand-cap tests.
- `api/AGENTS.md` — describes the Chongci threading.
- `cmd/server/main.go` — registers `StartQueueWatcher("chongci-fh")`.
- `web/src/pages/Table.tsx` — match-mode picker + Chongci config inputs.
- `web/src/pages/Lobby.tsx` — "Quick Match — Chongci" button.
- `web/src/pages/Game.tsx` — in-match Chongci HUD badge; renders `MatchEndOverlay` on `PHASE_MATCH_END`.
- `web/src/pages/AGENTS.md` — adds `MatchEndOverlay.tsx`.
- `proto/AGENTS.md` — adds the new match-mode types to the index.

---

## Task 1: Proto — add `MatchMode`, `ChongciConfig`, standings, `PHASE_MATCH_END`, `GameState` and `PrivateTableState` fields

**Files:**
- Modify: `proto/game.proto`
- Modify: `proto/game.pb.go` (regenerated)
- Modify: `web/src/proto/game.js`, `web/src/proto/game.d.ts`, `web/src/proto/game_cjs.js` (regenerated)
- Modify: `proto/AGENTS.md`

- [ ] **Step 1: Add `PHASE_MATCH_END` to the `GamePhase` enum.**

In `proto/game.proto`, find the `enum GamePhase` block. Add a fifth value:

```proto
enum GamePhase {
  PHASE_INIT = 0;
  PHASE_DEAL = 1;
  PHASE_PLAYER_TURN = 2;
  PHASE_WAIT_DISCARDS = 3;
  PHASE_ROUND_END = 4;
  PHASE_MATCH_END = 5;            // Terminal; no further hands will start
}
```

- [ ] **Step 2: Add `MatchMode`, `ChongciConfig`, `PlayerStanding`, `MatchEndResult`.**

Append a new section to `proto/game.proto` (placement: after the `PrivateTable Configuration` block introduced by the AI-seats feature):

```proto
// ---------------------------------------------------------
// Match Mode (Chongci)
// ---------------------------------------------------------

enum MatchMode {
  MATCH_MODE_UNSPECIFIED = 0;
  MATCH_MODE_CLASSIC = 1;   // Endless hands, random dealer per hand
  MATCH_MODE_CHONGCI = 2;   // Bust-out match, dealer succession to winner
}

message ChongciConfig {
  int32 starting_score = 1;       // e.g. 2000
  int32 bust_threshold = 2;       // Match ends when any player score <= this; default 0
  uint32 max_hands = 3;           // 0 = unbounded
}

message PlayerStanding {
  uint32 seat = 1;
  uint32 rank = 2;                // 1-based; tied players share rank
  int32 final_score = 3;
  int32 net_change = 4;           // final_score - starting_score
}

message MatchEndResult {
  string reason = 1;              // "bust" | "hand_cap"
  uint32 final_hand_num = 2;
  repeated PlayerStanding standings = 3;  // length 4, sorted by score desc
}
```

- [ ] **Step 3: Add new fields to `GameState`.**

In the `message GameState` block, append three new fields after the last existing field (currently `wangpai_tiles_left = 20`):

```proto
  MatchMode match_mode = 21;
  ChongciConfig chongci_config = 22;     // set iff match_mode == MATCH_MODE_CHONGCI
  MatchEndResult match_end_result = 23;  // set iff phase == PHASE_MATCH_END
```

- [ ] **Step 4: Add new fields to `PrivateTableState`.**

Locate `message PrivateTableState` and add at the end:

```proto
  MatchMode match_mode = 6;
  ChongciConfig chongci_config = 7;      // set iff match_mode == MATCH_MODE_CHONGCI
```

- [ ] **Step 5: Regenerate Go bindings.**

Run:

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
```

Expected: `proto/game.pb.go` is updated. Sanity-check by grepping:

```bash
grep -n "MATCH_MODE_CHONGCI\|MatchEndResult\|PHASE_MATCH_END" proto/game.pb.go | head -5
```

Expected: at least three matches found.

- [ ] **Step 6: Regenerate TS/JS bindings.**

Run (from project root):

```bash
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
web/node_modules/.bin/pbjs -t static-module -w commonjs --null-semantics -o web/src/proto/game_cjs.js proto/game.proto
```

Expected: three files written, no errors.

Sanity-check:

```bash
grep -n "MATCH_MODE_CHONGCI\|MatchEndResult" web/src/proto/game.d.ts | head -5
```

Expected: matches found.

- [ ] **Step 7: Update `proto/AGENTS.md` index.**

In the "Key Files / game.proto" bullet list, add a sub-bullet:

```
  - Match-mode types: `MatchMode`, `ChongciConfig`, `PlayerStanding`, `MatchEndResult`
  - `GamePhase` adds `PHASE_MATCH_END` terminal value
```

- [ ] **Step 8: Verify everything still compiles.**

Run:

```bash
go build ./...
```

Expected: no errors. (Frontend not built here; later tasks touch it.)

- [ ] **Step 9: Commit.**

```bash
git add proto/game.proto proto/game.pb.go web/src/proto/game.js web/src/proto/game.d.ts web/src/proto/game_cjs.js proto/AGENTS.md
git commit -m "proto: MatchMode, ChongciConfig, PHASE_MATCH_END"
```

---

## Task 2: Engine — `MatchOptions` type and `NewGame` signature (classic-mode preserving)

**Files:**
- Modify: `core/game.go` (`NewGame` near line 37)
- Modify: `core/game_test.go`
- Modify: `core/flower_auto_reveal_test.go`
- Modify: `core/paipu_test.go`
- Modify: `api/room.go` (line 87)
- Modify: `rlenv/env.go` (line 43)
- Modify: `cmd/cli/main.go` (line 99)
- Modify: `cmd/rlpaipu/main.go` (line 49)

- [ ] **Step 1: Write the failing test.**

Open `core/game_test.go` and add a new test in the package:

```go
func TestNewGame_ClassicDefault(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-classic", r, core.MatchOptions{})

	if got := g.State.MatchMode; got != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("default MatchMode = %v, want CLASSIC", got)
	}
	if g.State.ChongciConfig != nil {
		t.Fatalf("classic-mode ChongciConfig should be nil, got %+v", g.State.ChongciConfig)
	}
	for i, p := range g.State.Players {
		if p.Score != 25000 {
			t.Fatalf("classic seat %d Score = %d, want 25000", i, p.Score)
		}
	}
}
```

If the existing test file lacks the `pb` import alias, add `pb "github.com/plasma/fh-mahjong/proto"` to the import block.

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./core -run TestNewGame_ClassicDefault
```

Expected: FAIL — `MatchOptions` undefined and/or `NewGame` arity mismatch.

- [ ] **Step 3: Add `MatchOptions` and update `NewGame`.**

In `core/game.go`, just above `func NewGame(...)`, add:

```go
// MatchOptions configures a freshly constructed Game. The zero value
// yields the project's classic match (endless hands, random dealer per
// hand, players start at 25000). When Mode == MATCH_MODE_CHONGCI,
// ChongciConfig must be non-nil and is copied onto State.
type MatchOptions struct {
	Mode          pb.MatchMode
	ChongciConfig *pb.ChongciConfig
}
```

Replace the existing `NewGame` signature and body initializer block:

```go
func NewGame(matchID string, rules RuleEngine, opts MatchOptions) *Game {
	mode := opts.Mode
	if mode == pb.MatchMode_MATCH_MODE_UNSPECIFIED {
		mode = pb.MatchMode_MATCH_MODE_CLASSIC
	}

	g := &Game{
		Rules: rules,
		State: &pb.GameState{
			MatchId:       matchID,
			Phase:         pb.GamePhase_PHASE_INIT,
			ActivePlayer:  0,
			WallCount:     0,
			HandNum:       1, // East 1
			Players:       make([]*pb.PlayerState, 4),
			ActiveDiscard: nil,
			MatchMode:     mode,
		},
		interruptQueue: make(map[uint32]*pb.PlayerAction),
	}
	g.haiteiDrawIndex = -1

	startingScore := int32(25000)
	for i := 0; i < 4; i++ {
		g.State.Players[i] = &pb.PlayerState{
			Seat:        uint32(i),
			Score:       startingScore,
			ClosedHand:  make([]*pb.Tile, 0),
			HandSize:    0,
			DrawnTileId: nil,
			OpenMelds:   make([]*pb.Meld, 0),
			Discards:    make([]*pb.Tile, 0),
			SeatWind:    uint32(i + 1), // 1=East, 2=South, 3=West, 4=North
			FlowerMelds: make([]*pb.Tile, 0),
		}
	}

	return g
}
```

(Chongci-specific initialization is added in Task 6 — for now keep classic-mode behavior identical and accept the option harmlessly.)

- [ ] **Step 4: Update every existing `core.NewGame` call site.**

Run:

```bash
grep -rn "core\.NewGame\|NewGame(matchID" /Users/plasma/fh-mahjong-claude --include='*.go' | grep -v "_test.go.snap"
```

Update each call site to add `core.MatchOptions{}` (or `MatchOptions{}` inside the `core` package) as the third argument:

- `core/game_test.go` (5 sites, e.g. lines 13, 25, 51, 85, 139): `g := core.NewGame("test-uuid", r, core.MatchOptions{})`
- `core/flower_auto_reveal_test.go` (3 sites): `g := NewGame("test-auto-flower", &flowerAutoRevealRules{}, MatchOptions{})`
- `core/paipu_test.go` (1 site): `g := core.NewGame("test-paipu", ruleset, core.MatchOptions{})`
- `api/room.go:87`: `Engine: core.NewGame(matchID, ruleset, core.MatchOptions{}),`
- `rlenv/env.go:43`: `e.game = core.NewGame(fmt.Sprintf("rl-%d", seed), &rules.HometownRuleset{}, core.MatchOptions{})`
- `cmd/cli/main.go:99`: `game := core.NewGame("demo-1", &rules.HometownRuleset{}, core.MatchOptions{})`
- `cmd/rlpaipu/main.go:49`: `game := core.NewGame(matchID, &rules.HometownRuleset{}, core.MatchOptions{})`

- [ ] **Step 5: Run the targeted test and the full module.**

```bash
go test ./core -run TestNewGame_ClassicDefault
go test ./...
```

Expected: PASS on both. The full suite should still be green — no behavioral change yet.

- [ ] **Step 6: Commit.**

```bash
git add core/game.go core/game_test.go core/flower_auto_reveal_test.go core/paipu_test.go api/room.go rlenv/env.go cmd/cli/main.go cmd/rlpaipu/main.go
git commit -m "core: parameterize NewGame with MatchOptions"
```

---

## Task 3: Engine — `SetNextDealer` override consumed once by `dealTiles`

**Files:**
- Modify: `core/game.go` (`Game` struct around line 22, `dealTiles` around line 108)
- Modify: `core/game_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `core/game_test.go`:

```go
func TestSetNextDealer_ConsumedOnce(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-override", r, core.MatchOptions{})
	if err := g.Start(); err != nil {
		t.Fatalf("Start failed: %v", err)
	}

	// Confirm there is exactly one East-wind seat after Start.
	eastCount := 0
	for _, p := range g.State.Players {
		if p.SeatWind == 1 {
			eastCount++
		}
	}
	if eastCount != 1 {
		t.Fatalf("after Start, expected exactly one East seat, got %d", eastCount)
	}

	// Override the next dealer and call dealTiles directly via the public Start path.
	g.SetNextDealer(2)
	// Re-deal by simulating round transition: clear phase and call the engine's
	// re-deal helper. For this unit test we exercise the override by re-running
	// the deal logic through a second Game.Start equivalent. The simplest route
	// is to call core.Game.DealForNextHand() — which is added in this task.
	g.DealForNextHand()

	if g.State.Players[2].SeatWind != 1 {
		t.Fatalf("after SetNextDealer(2), seat 2 SeatWind = %d, want 1 (East)", g.State.Players[2].SeatWind)
	}

	// Calling DealForNextHand again should NOT keep seat 2 as East — the override
	// is single-shot. We can't reliably assert randomness in a unit test, but
	// running 20 deals should produce at least one non-2 dealer.
	sawOther := false
	for i := 0; i < 20 && !sawOther; i++ {
		g.DealForNextHand()
		if g.State.Players[2].SeatWind != 1 {
			sawOther = true
		}
	}
	if !sawOther {
		t.Fatalf("override leaked: seat 2 was dealer for 20 consecutive deals")
	}
}
```

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./core -run TestSetNextDealer_ConsumedOnce
```

Expected: FAIL — `SetNextDealer` and `DealForNextHand` undefined.

- [ ] **Step 3: Add the override field and `SetNextDealer` method.**

In `core/game.go`, find the `Game` struct (around line 22) and add a new field alongside `wallSeedOverride`:

```go
type Game struct {
	// ...existing fields...
	wallSeedOverride   *[MT19937SeedSize]uint32
	nextDealerOverride *uint32
}
```

Add a setter directly below the `SetWallSeed` method:

```go
// SetNextDealer queues a deterministic dealer for the next deal. The
// override is consumed once; subsequent deals re-randomize unless another
// override is set.
func (g *Game) SetNextDealer(seat uint32) {
	if seat > 3 {
		return
	}
	g.nextDealerOverride = &seat
}
```

- [ ] **Step 4: Consume the override in `dealTiles`.**

In `core/game.go`, find the line `dealer := mt.GenU32() % 4` inside `dealTiles()` (around line 134). Replace it with:

```go
var dealer uint32
if g.nextDealerOverride != nil {
	dealer = *g.nextDealerOverride
	g.nextDealerOverride = nil
} else {
	dealer = mt.GenU32() % 4
}
```

- [ ] **Step 5: Expose a thin re-deal helper for tests.**

The existing engine re-deals from `startNextRound` (line 1080). Test code needs a way to trigger one extra deal without driving the whole round-end transition. Add a small helper directly below `startNextRound`:

```go
// DealForNextHand runs the same re-deal pipeline as startNextRound,
// resetting per-player hand state and dealing. Intended for tests that
// need to exercise dealer-override behavior in isolation; production
// callers should use the normal round-end → ready flow.
func (g *Game) DealForNextHand() {
	g.startNextRound()
}
```

- [ ] **Step 6: Run the test, confirm it passes.**

```bash
go test ./core -run TestSetNextDealer_ConsumedOnce
```

Expected: PASS.

- [ ] **Step 7: Run the full module to confirm no regression.**

```bash
go test ./...
```

Expected: all green.

- [ ] **Step 8: Commit.**

```bash
git add core/game.go core/game_test.go
git commit -m "core: SetNextDealer override consumed once by dealTiles"
```

---

## Task 4: Engine — extract `finalizeRoundEnd` helper (classic-mode preserving)

**Files:**
- Modify: `core/game.go` (lines 420, 504, 533, 641, 714, 873, 1044)

- [ ] **Step 1: Add the new helper function.**

In `core/game.go`, immediately above `handleReadyAction` (around line 1055), insert:

```go
// finalizeRoundEnd is called at every hand-end to set up the next-round
// transition. In classic mode it just arms PlayerReady so each player must
// ack before the next hand starts. Chongci-specific behavior (dealer
// succession, end-of-match detection) is wired into this helper in later
// tasks; today it preserves the literal PlayerReady initialization that
// every hand-end site used to perform inline.
func (g *Game) finalizeRoundEnd() {
	g.State.PlayerReady = []bool{false, false, false, false}
}
```

- [ ] **Step 2: Replace every literal PlayerReady initializer.**

Run:

```bash
grep -n "PlayerReady = \[\]bool{false, false, false, false}" core/game.go
```

Expected: 7 matches at lines ~420, 504, 533, 641, 714, 873, 1044.

For each match, replace the literal assignment with a single call:

```go
g.finalizeRoundEnd()
```

Tip: a safe global substitution is

```bash
perl -i -pe 's/g\.State\.PlayerReady = \[\]bool\{false, false, false, false\}/g.finalizeRoundEnd()/g' core/game.go
```

After the substitution, re-run the grep — expected: 0 matches for the literal pattern; 7 new matches for `g.finalizeRoundEnd()`.

- [ ] **Step 3: Run the full module — no behavioral change expected.**

```bash
go test ./...
```

Expected: all green. If any test fails, the substitution caught a callsite where the line was wrapped or differently formatted — re-run grep to find it and fix manually.

- [ ] **Step 4: Commit.**

```bash
git add core/game.go
git commit -m "core: extract finalizeRoundEnd helper"
```

---

## Task 5: Engine — Chongci-mode initialization in `NewGame`

**Files:**
- Modify: `core/game.go` (`NewGame`)
- Modify: `core/game_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `core/game_test.go`:

```go
func TestNewGame_ChongciInitialization(t *testing.T) {
	r := &rules.HometownRuleset{}
	cfg := &pb.ChongciConfig{
		StartingScore: 2000,
		BustThreshold: 0,
		MaxHands:      50,
	}
	g := core.NewGame("test-chongci", r, core.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	})

	if g.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", g.State.MatchMode)
	}
	if g.State.ChongciConfig == nil {
		t.Fatalf("ChongciConfig is nil")
	}
	if got := g.State.ChongciConfig.StartingScore; got != 2000 {
		t.Fatalf("ChongciConfig.StartingScore = %d, want 2000", got)
	}
	for i, p := range g.State.Players {
		if p.Score != 2000 {
			t.Fatalf("chongci seat %d Score = %d, want 2000", i, p.Score)
		}
	}
}
```

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./core -run TestNewGame_ChongciInitialization
```

Expected: FAIL — players still start at 25000.

- [ ] **Step 3: Implement Chongci-mode initialization.**

In `core/game.go`, update the `NewGame` body. Replace the `startingScore := int32(25000)` line and the loop's `Score: startingScore` reference with mode-aware logic. The full revised block:

```go
	startingScore := int32(25000)
	if mode == pb.MatchMode_MATCH_MODE_CHONGCI {
		if opts.ChongciConfig == nil {
			// Defensive: caller passed CHONGCI without a config. Fall back to
			// the default public-queue config so the engine never produces an
			// inconsistent state.
			opts.ChongciConfig = &pb.ChongciConfig{
				StartingScore: 2000,
				BustThreshold: 0,
				MaxHands:      50,
			}
		}
		startingScore = opts.ChongciConfig.StartingScore
		// Store a copy so future engine mutations cannot leak back to the caller.
		cfgCopy := *opts.ChongciConfig
		g.State.ChongciConfig = &cfgCopy
	}

	for i := 0; i < 4; i++ {
		g.State.Players[i] = &pb.PlayerState{
			Seat:        uint32(i),
			Score:       startingScore,
			ClosedHand:  make([]*pb.Tile, 0),
			HandSize:    0,
			DrawnTileId: nil,
			OpenMelds:   make([]*pb.Meld, 0),
			Discards:    make([]*pb.Tile, 0),
			SeatWind:    uint32(i + 1),
			FlowerMelds: make([]*pb.Tile, 0),
		}
	}
```

- [ ] **Step 4: Run the test, confirm it passes.**

```bash
go test ./core -run TestNewGame_ChongciInitialization
go test ./...
```

Expected: both green.

- [ ] **Step 5: Commit.**

```bash
git add core/game.go core/game_test.go
git commit -m "core: Chongci-mode initialization in NewGame"
```

---

## Task 6: Engine — `currentDealerSeat`, `shouldEndChongciMatch`, `computeMatchEndResult`

**Files:**
- Modify: `core/game.go`
- Modify: `core/game_test.go`

- [ ] **Step 1: Write failing tests for the three helpers.**

Append to `core/game_test.go`:

```go
func TestComputeMatchEndResult_Standings(t *testing.T) {
	cases := []struct {
		name      string
		scores    [4]int32
		startScore int32
		wantRanks [4]uint32 // indexed by seat
	}{
		{
			name:       "all distinct",
			scores:     [4]int32{1500, 3000, -200, 1700},
			startScore: 2000,
			wantRanks:  [4]uint32{3, 1, 4, 2},
		},
		{
			name:       "two-way tie for first",
			scores:     [4]int32{3000, 3000, 1000, -1000},
			startScore: 2000,
			wantRanks:  [4]uint32{1, 1, 3, 4},
		},
		{
			name:       "four-way tie",
			scores:     [4]int32{2000, 2000, 2000, 2000},
			startScore: 2000,
			wantRanks:  [4]uint32{1, 1, 1, 1},
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			r := &rules.HometownRuleset{}
			g := core.NewGame("t", r, core.MatchOptions{
				Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
				ChongciConfig: &pb.ChongciConfig{
					StartingScore: c.startScore,
					BustThreshold: 0,
					MaxHands:      0,
				},
			})
			for i, s := range c.scores {
				g.State.Players[i].Score = s
			}
			result := g.ComputeMatchEndResultForTest("bust")
			if result == nil || len(result.Standings) != 4 {
				t.Fatalf("nil or wrong-length standings: %+v", result)
			}
			gotRanks := [4]uint32{}
			for _, s := range result.Standings {
				gotRanks[s.Seat] = s.Rank
			}
			if gotRanks != c.wantRanks {
				t.Fatalf("ranks = %v, want %v", gotRanks, c.wantRanks)
			}
		})
	}
}

func TestShouldEndChongciMatch(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      3,
		},
	})

	// Healthy scores, hand 1 — no end.
	if g.ShouldEndChongciMatchForTest() {
		t.Fatal("unexpected end on healthy state")
	}

	// One player on zero — match-end via bust (<=).
	g.State.Players[1].Score = 0
	if !g.ShouldEndChongciMatchForTest() {
		t.Fatal("expected bust on score == 0 with threshold 0")
	}

	// Reset to healthy; trip hand-cap.
	g.State.Players[1].Score = 1500
	g.State.HandNum = 3
	if !g.ShouldEndChongciMatchForTest() {
		t.Fatal("expected hand_cap on HandNum == MaxHands")
	}
}

func TestCurrentDealerSeat(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{})
	for i := uint32(0); i < 4; i++ {
		g.State.Players[i].SeatWind = ((i + 2) % 4) + 1 // East lands at seat 2
	}
	if got := g.CurrentDealerSeatForTest(); got != 2 {
		t.Fatalf("CurrentDealerSeat = %d, want 2", got)
	}
}
```

(These tests use a `*ForTest` naming convention so the production helpers can stay package-private. They expose the lowercased internals via thin wrappers added in Step 3.)

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./core -run "TestComputeMatchEndResult_Standings|TestShouldEndChongciMatch|TestCurrentDealerSeat"
```

Expected: FAIL — helpers undefined.

- [ ] **Step 3: Implement the three helpers (and test exports).**

Append to `core/game.go`:

```go
import "sort"
// (Add "sort" to the existing import block; do not re-declare the keyword.)
```

Add these unexported helpers near `finalizeRoundEnd`:

```go
// currentDealerSeat returns the seat whose SeatWind == 1 (East). Falls
// back to seat 0 if no East is set (defensive — shouldn't happen).
func (g *Game) currentDealerSeat() uint32 {
	for _, p := range g.State.Players {
		if p.SeatWind == 1 {
			return p.Seat
		}
	}
	return 0
}

// shouldEndChongciMatch returns true if the match should terminate based
// on the current scores and hand number. Only meaningful when
// State.MatchMode == MATCH_MODE_CHONGCI and ChongciConfig is set.
func (g *Game) shouldEndChongciMatch() bool {
	cfg := g.State.ChongciConfig
	if cfg == nil {
		return false
	}
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

// computeMatchEndResult builds a sorted, rank-annotated standings list
// for the current scores. Tied players share the same rank; the rank of
// the player after a tie is incremented by the size of the tie group
// (e.g. two tied 1st → next player is 3rd).
func (g *Game) computeMatchEndResult(reason string) *pb.MatchEndResult {
	cfg := g.State.ChongciConfig
	var startScore int32
	if cfg != nil {
		startScore = cfg.StartingScore
	}

	standings := make([]*pb.PlayerStanding, 4)
	for i, p := range g.State.Players {
		standings[i] = &pb.PlayerStanding{
			Seat:       p.Seat,
			FinalScore: p.Score,
			NetChange:  p.Score - startScore,
		}
	}
	sort.SliceStable(standings, func(i, j int) bool {
		return standings[i].FinalScore > standings[j].FinalScore
	})
	// Assign ranks with tie-sharing.
	for i := 0; i < 4; i++ {
		if i == 0 || standings[i].FinalScore != standings[i-1].FinalScore {
			standings[i].Rank = uint32(i + 1)
		} else {
			standings[i].Rank = standings[i-1].Rank
		}
	}

	return &pb.MatchEndResult{
		Reason:       reason,
		FinalHandNum: g.State.HandNum,
		Standings:    standings,
	}
}
```

Now add thin test exports — these allow tests in `package core_test` to drive the unexported helpers without leaking them to other packages. Append to `core/game.go`:

```go
// CurrentDealerSeatForTest exposes currentDealerSeat to package-external tests.
func (g *Game) CurrentDealerSeatForTest() uint32 { return g.currentDealerSeat() }

// ShouldEndChongciMatchForTest exposes shouldEndChongciMatch to tests.
func (g *Game) ShouldEndChongciMatchForTest() bool { return g.shouldEndChongciMatch() }

// ComputeMatchEndResultForTest exposes computeMatchEndResult to tests.
func (g *Game) ComputeMatchEndResultForTest(reason string) *pb.MatchEndResult {
	return g.computeMatchEndResult(reason)
}
```

- [ ] **Step 4: Run the three tests, confirm they pass.**

```bash
go test ./core -run "TestComputeMatchEndResult_Standings|TestShouldEndChongciMatch|TestCurrentDealerSeat"
go test ./...
```

Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add core/game.go core/game_test.go
git commit -m "core: chongci match-end detection and standings helpers"
```

---

## Task 7: Engine — wire match-end detection and dealer succession into `finalizeRoundEnd`

**Files:**
- Modify: `core/game.go` (`finalizeRoundEnd`)
- Modify: `core/game_test.go`

- [ ] **Step 1: Write failing tests for the four behaviors.**

Append to `core/game_test.go`:

```go
func TestFinalizeRoundEnd_ChongciBust(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      50,
		},
	})
	g.State.Players[3].Score = -300
	g.State.RoundResult = &pb.RoundResult{WinnerSeat: 1, IsDraw: false}

	g.FinalizeRoundEndForTest()

	if g.State.Phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("Phase = %v, want PHASE_MATCH_END", g.State.Phase)
	}
	if g.State.MatchEndResult == nil || g.State.MatchEndResult.Reason != "bust" {
		t.Fatalf("MatchEndResult = %+v, want reason=bust", g.State.MatchEndResult)
	}
}

func TestFinalizeRoundEnd_ChongciHandCap(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      3,
		},
	})
	g.State.HandNum = 3
	g.State.RoundResult = &pb.RoundResult{WinnerSeat: 2, IsDraw: false}

	g.FinalizeRoundEndForTest()

	if g.State.Phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("Phase = %v, want PHASE_MATCH_END", g.State.Phase)
	}
	if g.State.MatchEndResult.Reason != "hand_cap" {
		t.Fatalf("Reason = %q, want hand_cap", g.State.MatchEndResult.Reason)
	}
}

func TestFinalizeRoundEnd_DealerSuccession_Win(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      50,
		},
	})
	g.State.RoundResult = &pb.RoundResult{WinnerSeat: 2, IsDraw: false}

	g.FinalizeRoundEndForTest()

	if got := g.NextDealerOverrideForTest(); got == nil || *got != 2 {
		t.Fatalf("nextDealerOverride = %v, want pointer-to-2", got)
	}
	if g.State.Phase == pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("Phase = PHASE_MATCH_END, expected continue")
	}
	// Classic ready-flow is armed.
	if len(g.State.PlayerReady) != 4 {
		t.Fatalf("PlayerReady not armed: %v", g.State.PlayerReady)
	}
}

func TestFinalizeRoundEnd_DealerSuccession_Draw(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      50,
		},
	})
	// Place East at seat 1.
	for i := uint32(0); i < 4; i++ {
		g.State.Players[i].SeatWind = ((i + 3) % 4) + 1 // East at seat 1
	}
	g.State.RoundResult = &pb.RoundResult{IsDraw: true}

	g.FinalizeRoundEndForTest()

	if got := g.NextDealerOverrideForTest(); got == nil || *got != 1 {
		t.Fatalf("draw renchan: nextDealerOverride = %v, want pointer-to-1", got)
	}
}

func TestFinalizeRoundEnd_ClassicUnchanged(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{})
	g.State.RoundResult = &pb.RoundResult{WinnerSeat: 2, IsDraw: false}

	g.FinalizeRoundEndForTest()

	if g.NextDealerOverrideForTest() != nil {
		t.Fatal("classic mode must not set next-dealer override")
	}
	if g.State.Phase == pb.GamePhase_PHASE_MATCH_END {
		t.Fatal("classic mode must not transition to PHASE_MATCH_END")
	}
	if len(g.State.PlayerReady) != 4 {
		t.Fatalf("classic PlayerReady not armed: %v", g.State.PlayerReady)
	}
}
```

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./core -run "TestFinalizeRoundEnd"
```

Expected: FAIL — `FinalizeRoundEndForTest`, `NextDealerOverrideForTest` undefined; behavior not yet implemented.

- [ ] **Step 3: Update `finalizeRoundEnd` and add test exports.**

Replace the existing `finalizeRoundEnd` body with:

```go
func (g *Game) finalizeRoundEnd() {
	if g.State.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI {
		if g.State.RoundResult != nil {
			if g.State.RoundResult.IsDraw {
				g.SetNextDealer(g.currentDealerSeat()) // renchan, no honba
			} else {
				g.SetNextDealer(g.State.RoundResult.WinnerSeat)
			}
		}
		if g.shouldEndChongciMatch() {
			reason := "bust"
			cfg := g.State.ChongciConfig
			if cfg != nil && cfg.MaxHands > 0 && g.State.HandNum >= cfg.MaxHands {
				// Hand cap may also coincide with a bust; bust takes precedence
				// only if any player is actually <= threshold.
				busted := false
				for _, p := range g.State.Players {
					if p.Score <= cfg.BustThreshold {
						busted = true
						break
					}
				}
				if !busted {
					reason = "hand_cap"
				}
			}
			g.State.Phase = pb.GamePhase_PHASE_MATCH_END
			g.State.MatchEndResult = g.computeMatchEndResult(reason)
			return
		}
	}
	g.State.PlayerReady = []bool{false, false, false, false}
}
```

Add the test exports near the existing `*ForTest` exports:

```go
// FinalizeRoundEndForTest exposes finalizeRoundEnd to tests.
func (g *Game) FinalizeRoundEndForTest() { g.finalizeRoundEnd() }

// NextDealerOverrideForTest exposes the override pointer to tests.
// Returns nil if no override is currently queued.
func (g *Game) NextDealerOverrideForTest() *uint32 { return g.nextDealerOverride }
```

- [ ] **Step 4: Run the tests, confirm they pass.**

```bash
go test ./core -run "TestFinalizeRoundEnd"
go test ./...
```

Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add core/game.go core/game_test.go
git commit -m "core: dealer succession and match-end detection in finalizeRoundEnd"
```

---

## Task 8: Engine — gate `handleReadyAction` on `PHASE_MATCH_END`

**Files:**
- Modify: `core/game.go` (`handleReadyAction` around line 1055)
- Modify: `core/game_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `core/game_test.go`:

```go
func TestHandleReadyAction_RejectedAfterMatchEnd(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("t", r, core.MatchOptions{
		Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000, BustThreshold: 0, MaxHands: 50,
		},
	})
	g.State.Phase = pb.GamePhase_PHASE_MATCH_END

	err := g.HandleReadyActionForTest(0)
	if err == nil {
		t.Fatal("expected error on ready after match end")
	}
}
```

If `HandleReadyActionForTest` doesn't exist yet, add it in this task.

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./core -run TestHandleReadyAction_RejectedAfterMatchEnd
```

Expected: FAIL.

- [ ] **Step 3: Update `handleReadyAction` and add the test export.**

In `core/game.go`, locate `handleReadyAction` (around line 1055). Add a phase check at the top:

```go
func (g *Game) handleReadyAction(seat uint32) error {
	if g.State.Phase == pb.GamePhase_PHASE_MATCH_END {
		return fmt.Errorf("cannot ready: match has ended")
	}
	if int(seat) >= len(g.State.PlayerReady) {
		return fmt.Errorf("invalid seat %d for ready action", seat)
	}
	// ...existing body unchanged...
}
```

Append the test export:

```go
// HandleReadyActionForTest exposes handleReadyAction to tests.
func (g *Game) HandleReadyActionForTest(seat uint32) error { return g.handleReadyAction(seat) }
```

- [ ] **Step 4: Run the test, confirm it passes.**

```bash
go test ./core -run TestHandleReadyAction_RejectedAfterMatchEnd
go test ./...
```

Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add core/game.go core/game_test.go
git commit -m "core: reject ready action after PHASE_MATCH_END"
```

---

## Task 9: API — `PrivateTable` carries `MatchMode` + `ChongciConfig`

**Files:**
- Modify: `api/private_tables.go` (`PrivateTable` struct, `newConfiguringTable`, `toProto`)
- Modify: `api/private_tables_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `api/private_tables_test.go`:

```go
func TestPrivateTable_DefaultMatchMode(t *testing.T) {
	pt := newConfiguringTable("table-x", 42)
	if pt.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("default MatchMode = %v, want CLASSIC", pt.MatchMode)
	}
	if pt.ChongciConfig != nil {
		t.Fatalf("default ChongciConfig should be nil, got %+v", pt.ChongciConfig)
	}
	state := pt.SnapshotProto()
	if state.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("proto MatchMode = %v, want CLASSIC", state.MatchMode)
	}
}

func TestPrivateTable_ChongciProto(t *testing.T) {
	pt := newConfiguringTable("table-x", 42)
	pt.MatchMode = pb.MatchMode_MATCH_MODE_CHONGCI
	pt.ChongciConfig = &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50}

	state := pt.SnapshotProto()
	if state.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("proto MatchMode = %v, want CHONGCI", state.MatchMode)
	}
	if state.ChongciConfig == nil || state.ChongciConfig.StartingScore != 2000 {
		t.Fatalf("proto ChongciConfig = %+v", state.ChongciConfig)
	}
}
```

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./api -run "TestPrivateTable_DefaultMatchMode|TestPrivateTable_ChongciProto"
```

Expected: FAIL — fields and proto round-trip undefined.

- [ ] **Step 3: Add the fields and update construction + proto serialization.**

In `api/private_tables.go`, update the `PrivateTable` struct:

```go
type PrivateTable struct {
	mu sync.Mutex

	TableID    string
	HostUserID uint
	Seats      [4]SeatConfig
	State      string // "configuring" | "started"
	MatchID    string // populated when State == "started"

	MatchMode     pb.MatchMode      // CLASSIC if unset
	ChongciConfig *pb.ChongciConfig // non-nil iff MatchMode == CHONGCI
}
```

Update `newConfiguringTable` to set the default mode explicitly:

```go
func newConfiguringTable(tableID string, hostUserID uint) *PrivateTable {
	return &PrivateTable{
		TableID:    tableID,
		HostUserID: hostUserID,
		State:      "configuring",
		MatchMode:  pb.MatchMode_MATCH_MODE_CLASSIC,
	}
}
```

Update `toProto` to carry the new fields. Replace the `return &pb.PrivateTableState{...}` block with:

```go
	state := &pb.PrivateTableState{
		TableId:    t.TableID,
		HostUserId: uint32(t.HostUserID),
		Seats:      seats,
		State:      t.State,
		MatchId:    t.MatchID,
		MatchMode:  t.MatchMode,
	}
	if t.ChongciConfig != nil {
		cfg := *t.ChongciConfig
		state.ChongciConfig = &cfg
	}
	return state
```

- [ ] **Step 4: Run the tests, confirm they pass.**

```bash
go test ./api -run "TestPrivateTable_DefaultMatchMode|TestPrivateTable_ChongciProto"
go test ./...
```

Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add api/private_tables.go api/private_tables_test.go
git commit -m "api: PrivateTable carries MatchMode and ChongciConfig"
```

---

## Task 10: API — `setMatchMode` method on `PrivateTable` with validation

**Files:**
- Modify: `api/private_tables.go`
- Modify: `api/private_tables_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `api/private_tables_test.go`:

```go
func TestSetMatchMode_Classic(t *testing.T) {
	pt := newConfiguringTable("table-x", 42)
	pt.MatchMode = pb.MatchMode_MATCH_MODE_CHONGCI
	pt.ChongciConfig = &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50}

	if err := pt.setMatchMode("classic", nil); err != nil {
		t.Fatalf("setMatchMode(classic) error: %v", err)
	}
	if pt.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("MatchMode = %v, want CLASSIC", pt.MatchMode)
	}
	if pt.ChongciConfig != nil {
		t.Fatalf("ChongciConfig should be cleared, got %+v", pt.ChongciConfig)
	}
}

func TestSetMatchMode_Chongci(t *testing.T) {
	pt := newConfiguringTable("table-x", 42)
	cfg := &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50}
	if err := pt.setMatchMode("chongci", cfg); err != nil {
		t.Fatalf("setMatchMode(chongci) error: %v", err)
	}
	if pt.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", pt.MatchMode)
	}
	if pt.ChongciConfig == nil || pt.ChongciConfig.StartingScore != 2000 {
		t.Fatalf("ChongciConfig = %+v", pt.ChongciConfig)
	}
}

func TestSetMatchMode_ValidationErrors(t *testing.T) {
	cases := []struct {
		name string
		mode string
		cfg  *pb.ChongciConfig
	}{
		{"chongci without config", "chongci", nil},
		{"unknown mode", "tonpuusen", &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50}},
		{"starting too low", "chongci", &pb.ChongciConfig{StartingScore: 50, BustThreshold: 0, MaxHands: 50}},
		{"starting too high", "chongci", &pb.ChongciConfig{StartingScore: 2_000_000, BustThreshold: 0, MaxHands: 50}},
		{"threshold above starting", "chongci", &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 2000, MaxHands: 50}},
		{"threshold below floor", "chongci", &pb.ChongciConfig{StartingScore: 2000, BustThreshold: -2_000_000, MaxHands: 50}},
		{"max_hands above ceiling", "chongci", &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 500}},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			pt := newConfiguringTable("t", 42)
			if err := pt.setMatchMode(c.mode, c.cfg); err == nil {
				t.Fatalf("expected error, got nil")
			} else if !errors.Is(err, ErrChongciConfigInvalid) && c.mode == "chongci" {
				t.Fatalf("expected ErrChongciConfigInvalid, got %v", err)
			}
		})
	}
}
```

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./api -run "TestSetMatchMode"
```

Expected: FAIL.

- [ ] **Step 3: Add the typed sentinel and the method.**

In `api/private_tables.go`, near `var errHostOnly`, add:

```go
var ErrChongciConfigInvalid = errors.New("chongci config invalid")
var ErrModeLocked = errors.New("cannot change mode after match has started")
```

Below `setSeat`, add:

```go
// setMatchMode applies a host-driven match-mode change to the table.
// Returns ErrChongciConfigInvalid for any validation failure, or a plain
// error for an unknown mode string.
func (t *PrivateTable) setMatchMode(mode string, cfg *pb.ChongciConfig) error {
	switch mode {
	case "classic":
		t.MatchMode = pb.MatchMode_MATCH_MODE_CLASSIC
		t.ChongciConfig = nil
		return nil
	case "chongci":
		if cfg == nil {
			return fmt.Errorf("%w: chongci_config required", ErrChongciConfigInvalid)
		}
		if cfg.StartingScore < 100 || cfg.StartingScore > 1_000_000 {
			return fmt.Errorf("%w: starting_score %d out of range [100, 1000000]", ErrChongciConfigInvalid, cfg.StartingScore)
		}
		if cfg.BustThreshold >= cfg.StartingScore {
			return fmt.Errorf("%w: bust_threshold %d must be < starting_score %d", ErrChongciConfigInvalid, cfg.BustThreshold, cfg.StartingScore)
		}
		if cfg.BustThreshold < -1_000_000 {
			return fmt.Errorf("%w: bust_threshold %d below floor -1000000", ErrChongciConfigInvalid, cfg.BustThreshold)
		}
		if cfg.MaxHands > 200 {
			return fmt.Errorf("%w: max_hands %d above ceiling 200", ErrChongciConfigInvalid, cfg.MaxHands)
		}
		copied := *cfg
		t.MatchMode = pb.MatchMode_MATCH_MODE_CHONGCI
		t.ChongciConfig = &copied
		return nil
	default:
		return fmt.Errorf("unsupported match mode %q", mode)
	}
}
```

- [ ] **Step 4: Run the tests, confirm they pass.**

```bash
go test ./api -run "TestSetMatchMode"
go test ./...
```

Expected: all green.

- [ ] **Step 5: Commit.**

```bash
git add api/private_tables.go api/private_tables_test.go
git commit -m "api: setMatchMode with validation sentinels"
```

---

## Task 11: API — `POST /api/v1/private-tables/:tableId/mode` endpoint

**Files:**
- Modify: `api/private_tables.go` (new handler)
- Modify: `api/server.go` (route registration)
- Modify: `api/private_tables_test.go` (integration tests)

- [ ] **Step 1: Write failing integration tests.**

The existing fixtures in `api/private_tables_test.go` are: `newPrivateTableTestServer() *Server`, `privateTableAuthToken(t, userID, username) string`, and `doPrivateTableRequest(t, server, method, path, token, body) (*ResponseRecorder, map[string]any)`. Use those directly. Append:

```go
func TestHandlePrivateTableMode_HostSuccess(t *testing.T) {
	s := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 100, "Host")

	// Host joins to create the table.
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-1/join", hostToken, nil)

	body := map[string]any{
		"mode": "chongci",
		"chongci_config": map[string]any{
			"starting_score": 2000,
			"bust_threshold": 0,
			"max_hands":      50,
		},
	}
	w, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-1/mode", hostToken, body)
	if w.Code != http.StatusOK {
		t.Fatalf("status = %d body=%s", w.Code, w.Body.String())
	}

	tbl := s.Matchmaker.GetConfiguringPrivateTable("table-mode-1")
	if tbl.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", tbl.MatchMode)
	}
	if tbl.ChongciConfig.StartingScore != 2000 {
		t.Fatalf("StartingScore = %d", tbl.ChongciConfig.StartingScore)
	}
}

func TestHandlePrivateTableMode_NonHostForbidden(t *testing.T) {
	s := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 100, "Host")
	otherToken := privateTableAuthToken(t, 200, "Other")

	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-2/join", hostToken, nil)
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-2/join", otherToken, nil)

	w, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-2/mode", otherToken, map[string]any{"mode": "classic"})
	if w.Code != http.StatusForbidden {
		t.Fatalf("status = %d, want 403", w.Code)
	}
}

func TestHandlePrivateTableMode_InvalidConfig(t *testing.T) {
	s := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 100, "Host")
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-3/join", hostToken, nil)

	body := map[string]any{
		"mode":           "chongci",
		"chongci_config": map[string]any{"starting_score": 50, "bust_threshold": 0, "max_hands": 50},
	}
	w, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-3/mode", hostToken, body)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("status = %d, want 400", w.Code)
	}
}

func TestHandlePrivateTableMode_AfterStartLocked(t *testing.T) {
	// Reuse the start-with-three-bots flow from TestPrivateTableStartWithThreeBots
	// to leave the table in the "started" state, then attempt a mode change.
	s := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 100, "Host")
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-4/join", hostToken, nil)
	for seat := 1; seat <= 3; seat++ {
		doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-4/seat", hostToken, map[string]any{
			"seat": seat, "kind": "bot", "difficulty": 1,
		})
	}
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-4/start", hostToken, map[string]any{})

	w, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-mode-4/mode", hostToken, map[string]any{
		"mode":           "chongci",
		"chongci_config": map[string]any{"starting_score": 2000, "bust_threshold": 0, "max_hands": 50},
	})
	if w.Code != http.StatusConflict {
		t.Fatalf("status = %d, want 409", w.Code)
	}
}
```

Note: After `/start`, the `configuringTables` entry is removed asynchronously by `removeConfiguringTable`; the mode mutation will see the table either as missing (404) or as `state=="started"` (409). The plan's expectation is 409 — if you observe 404 instead, the goroutine ran first. Either accept both as success criteria in the test, or wait briefly via `s.Matchmaker.GetConfiguringPrivateTable("table-mode-4")` becoming `nil` and assert 404 instead. Both responses are "mode change rejected after start," which is the spec's intent.

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./api -run "TestHandlePrivateTableMode"
```

Expected: FAIL — route 404.

- [ ] **Step 3: Add the handler.**

In `api/private_tables.go`, below `handlePrivateTableSeat`, add:

```go
func (s *Server) handlePrivateTableMode(c *gin.Context) {
	userID, _ := c.Get("userID")
	tableID := c.Param("tableId")

	if s.Matchmaker == nil {
		c.JSON(http.StatusServiceUnavailable, gin.H{"error": "Private matchmaking unavailable"})
		return
	}

	var req struct {
		Mode          string `json:"mode"`
		ChongciConfig *struct {
			StartingScore int32  `json:"starting_score"`
			BustThreshold int32  `json:"bust_threshold"`
			MaxHands      uint32 `json:"max_hands"`
		} `json:"chongci_config,omitempty"`
	}
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	var cfg *pb.ChongciConfig
	if req.ChongciConfig != nil {
		cfg = &pb.ChongciConfig{
			StartingScore: req.ChongciConfig.StartingScore,
			BustThreshold: req.ChongciConfig.BustThreshold,
			MaxHands:      req.ChongciConfig.MaxHands,
		}
	}

	table, err := s.Matchmaker.MutatePrivateTable(tableID, func(t *PrivateTable) error {
		if t.HostUserID != userID.(uint) {
			return errHostOnly
		}
		if t.State != "configuring" {
			return ErrModeLocked
		}
		return t.setMatchMode(req.Mode, cfg)
	})
	if err != nil {
		status := http.StatusBadRequest
		switch {
		case errors.Is(err, errHostOnly):
			status = http.StatusForbidden
		case errors.Is(err, ErrModeLocked):
			status = http.StatusConflict
		case errors.Is(err, ErrChongciConfigInvalid):
			status = http.StatusBadRequest
		case errors.Is(err, ErrPrivateTableNotFound):
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	s.broadcastPrivateTable(table)
	c.Data(http.StatusOK, "application/json", marshalPrivateTableJSON(table))
}
```

- [ ] **Step 4: Register the route.**

In `api/server.go`, locate the existing private-table route block (around line 76-79). Add the new route alongside:

```go
protected.POST("/private-tables/:tableId/mode", s.handlePrivateTableMode)
```

Place this line directly after `protected.POST("/private-tables/:tableId/start", s.handlePrivateTableStart)`.

- [ ] **Step 5: Run the tests, confirm they pass.**

```bash
go test ./api -run "TestHandlePrivateTableMode"
go test ./...
```

Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add api/private_tables.go api/server.go api/private_tables_test.go
git commit -m "api: POST /private-tables/:tableId/mode endpoint"
```

---

## Task 12: API — thread `MatchOptions` through `NewRoom` and `StartPrivateTable`

**Files:**
- Modify: `api/room.go` (around line 87)
- Modify: `api/matchmaker.go` (`StartPrivateTable` around line 405)
- Modify: `api/private_tables_test.go`

- [ ] **Step 1: Write the failing integration test.**

Append to `api/private_tables_test.go`:

```go
func TestStartPrivateTable_ChongciThreaded(t *testing.T) {
	s := newPrivateTableTestServer()
	hostToken := privateTableAuthToken(t, 100, "Host")
	doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-chongci-1/join", hostToken, nil)

	// Set chongci mode.
	w1, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-chongci-1/mode", hostToken, map[string]any{
		"mode":           "chongci",
		"chongci_config": map[string]any{"starting_score": 2000, "bust_threshold": 0, "max_hands": 50},
	})
	if w1.Code != http.StatusOK {
		t.Fatalf("set mode: %d body=%s", w1.Code, w1.Body.String())
	}

	// Fill remaining seats with bots.
	for seat := 1; seat <= 3; seat++ {
		w, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-chongci-1/seat", hostToken, map[string]any{
			"seat": seat, "kind": "bot", "difficulty": 1,
		})
		if w.Code != http.StatusOK {
			t.Fatalf("set seat %d: %d body=%s", seat, w.Code, w.Body.String())
		}
	}

	// Start the match.
	w2, _ := doPrivateTableRequest(t, s, "POST", "/api/v1/private-tables/table-chongci-1/start", hostToken, map[string]any{})
	if w2.Code != http.StatusOK {
		t.Fatalf("start: %d body=%s", w2.Code, w2.Body.String())
	}

	// Inspect the active room.
	room := s.Matchmaker.RoomForTableForTest("table-chongci-1")
	if room == nil {
		t.Fatal("no active room for table")
	}
	if room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("engine MatchMode = %v, want CHONGCI", room.Engine.State.MatchMode)
	}
	for i, p := range room.Engine.State.Players {
		if p.Score != 2000 {
			t.Fatalf("seat %d Score = %d, want 2000", i, p.Score)
		}
	}
}
```

- [ ] **Step 2: Run the test, confirm it fails.**

```bash
go test ./api -run TestStartPrivateTable_ChongciThreaded
```

Expected: FAIL.

- [ ] **Step 3: Add a `WithMatchOptions` option to `NewRoom`.**

In `api/room.go`, locate the existing `RoomOption` definitions (search for `WithBotPolicy`). Add:

```go
// WithMatchOptions configures the engine constructed by NewRoom with a
// match-mode + Chongci config. Default is MatchOptions{} (classic).
func WithMatchOptions(opts core.MatchOptions) RoomOption {
	return func(r *Room) {
		r.matchOptions = opts
	}
}
```

Add the storage field to the `Room` struct:

```go
type Room struct {
	// ...existing fields...
	matchOptions core.MatchOptions
}
```

Update the `NewRoom` constructor to use it. Currently (around line 87):

```go
Engine:             core.NewGame(matchID, ruleset),
```

Replace with a two-step build so options can be applied before constructing the engine:

```go
room := &Room{
	ID:                 matchID,
	Hub:                hub,
	DB:                 db,
	SeatPolicies:       make(map[uint32]bot.Policy),
	Seats:              make(map[uint32]*Client),
	TileObfuscationMap: obfMap,
	ActionQueue:        make(chan ClientAction),
	Shutdown:           make(chan bool),
	InterruptChan:      make(chan bool, 1),
	TimerResolveChan:   make(chan bool, 1),
}
for _, opt := range opts {
	opt(room)
}
room.Engine = core.NewGame(matchID, ruleset, room.matchOptions)
room.Engine.Recorder = core.NewPaipuRecorder(matchID, "hometown")
return room
```

(Adjust the existing two-pass `for _, opt := range opts { opt(room) }` block as needed so options are applied **before** `core.NewGame` is called.)

- [ ] **Step 4: Use the option in `StartPrivateTable`.**

In `api/matchmaker.go`, find the `NewRoom(...)` call inside `StartPrivateTable` (around line 405). Just before it, build the options:

```go
		roomOptions := []RoomOption{}
		if m.BotPolicyFactory != nil {
			roomOptions = append(roomOptions, WithBotPolicy(m.BotPolicyFactory()))
		}
		if table.MatchMode == pb.MatchMode_MATCH_MODE_CHONGCI && table.ChongciConfig != nil {
			cfg := *table.ChongciConfig
			roomOptions = append(roomOptions, WithMatchOptions(core.MatchOptions{
				Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
				ChongciConfig: &cfg,
			}))
		}
		room = NewRoom(matchID, m.Hub, m.DB, roomOptions...)
```

(Replace the existing `var roomOptions []RoomOption` / `NewRoom(...)` block — keep the rest of the function body unchanged.)

- [ ] **Step 5: Extend `ActivePrivateTable` with a `Room` pointer.**

The current `ActivePrivateTable` struct (around line 113 in `api/matchmaker.go`) is:

```go
type ActivePrivateTable struct {
	TableID        string
	MatchID        string
	ParticipantIDs map[uint]bool
}
```

Add a `*Room` field:

```go
type ActivePrivateTable struct {
	TableID        string
	MatchID        string
	ParticipantIDs map[uint]bool
	Room           *Room
}
```

Update `registerActivePrivateTable` (around line 167) to accept and store the room. Change its signature:

```go
func (m *Matchmaker) registerActivePrivateTable(tableID string, matchID string, userIDs []uint, room *Room) {
	participants := map[uint]bool{}
	for _, uid := range userIDs {
		participants[uid] = true
	}
	m.privateTablesMu.Lock()
	defer m.privateTablesMu.Unlock()
	m.activePrivateTables[tableID] = ActivePrivateTable{
		TableID:        tableID,
		MatchID:        matchID,
		ParticipantIDs: participants,
		Room:           room,
	}
}
```

Update the two callers of `registerActivePrivateTable`:

- `Matchmaker.createMatch` (around line 265): change to `m.registerActivePrivateTable(tableID, matchID, userIDs, room)`.
- `Matchmaker.StartPrivateTable` (around line 413): change to `m.registerActivePrivateTable(tableID, matchID, mapValues(humanSeats), room)`.

- [ ] **Step 6: Add the `RoomForTableForTest` helper.**

In `api/matchmaker.go`, append:

```go
// RoomForTableForTest returns the live *Room registered for the given
// private-table ID, or nil if no match is active. Test-only.
func (m *Matchmaker) RoomForTableForTest(tableID string) *Room {
	m.privateTablesMu.RLock()
	defer m.privateTablesMu.RUnlock()
	ap, ok := m.activePrivateTables[tableID]
	if !ok {
		return nil
	}
	return ap.Room
}
```

- [ ] **Step 7: Run the test, confirm it passes.**

```bash
go test ./api -run TestStartPrivateTable_ChongciThreaded
go test ./...
```

Expected: all green.

- [ ] **Step 8: Commit.**

```bash
git add api/room.go api/matchmaker.go api/private_tables_test.go
git commit -m "api: thread MatchOptions through NewRoom and StartPrivateTable"
```

---

## Task 13: API — public `chongci-fh` queue

**Files:**
- Modify: `api/matchmaker.go` (`createMatch` around line 217)
- Modify: `cmd/server/main.go` (line 78)
- Modify: `api/room_bot_test.go` (new test added alongside existing matchmaker tests)

- [ ] **Step 1: Write the failing test.**

Append to `api/room_bot_test.go` (it already imports `bot` and `pb` so this is the cleanest place):

```go
func TestCreateMatch_ChongciRulesetThreadsMatchOptions(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "chongci-fh", "")

	bind := <-hub.BindRoom
	if bind.Room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CHONGCI {
		t.Fatalf("MatchMode = %v, want CHONGCI", bind.Room.Engine.State.MatchMode)
	}
	for i, p := range bind.Room.Engine.State.Players {
		if p.Score != 2000 {
			t.Fatalf("seat %d Score = %d, want 2000", i, p.Score)
		}
	}
	if bind.Room.Engine.State.ChongciConfig == nil ||
		bind.Room.Engine.State.ChongciConfig.MaxHands != 50 {
		t.Fatalf("ChongciConfig = %+v, want MaxHands=50", bind.Room.Engine.State.ChongciConfig)
	}
}

func TestCreateMatch_HometownRulesetKeepsClassic(t *testing.T) {
	hub := NewHub()
	hub.BindRoom = make(chan RoomBind, 1)
	matchmaker := NewMatchmaker(NewInMemoryQueue(), nil, hub)

	matchmaker.createMatch([]string{"1", "2", "3", "4"}, "hometown", "")

	bind := <-hub.BindRoom
	if bind.Room.Engine.State.MatchMode != pb.MatchMode_MATCH_MODE_CLASSIC {
		t.Fatalf("MatchMode = %v, want CLASSIC", bind.Room.Engine.State.MatchMode)
	}
	if bind.Room.Engine.State.Players[0].Score != 25000 {
		t.Fatalf("classic seat Score = %d, want 25000", bind.Room.Engine.State.Players[0].Score)
	}
}
```

(This pattern mirrors the existing `TestMatchmakerCreateMatchUsesBotPolicyFactory` test in the same file — it calls `createMatch` directly and consumes the `hub.BindRoom` send.)

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./api -run "TestCreateMatch_ChongciRulesetThreadsMatchOptions|TestCreateMatch_HometownRulesetKeepsClassic"
```

Expected: the chongci one FAILs (today's `createMatch` ignores ruleset for match-mode purposes); the hometown one likely PASSes already if the engine still defaults to CLASSIC.

- [ ] **Step 3: Map ruleset to `MatchOptions` in `createMatch`.**

In `api/matchmaker.go`, find `createMatch` (around line 217). Just before the `NewRoom(...)` call (around line 247), build options:

```go
	roomOptions := []RoomOption{}
	if m.BotPolicyFactory != nil {
		roomOptions = append(roomOptions, WithBotPolicy(m.BotPolicyFactory()))
	}
	if matchOpts, ok := defaultMatchOptionsFor(ruleset); ok {
		roomOptions = append(roomOptions, WithMatchOptions(matchOpts))
	}
	room := NewRoom(matchID, m.Hub, m.DB, roomOptions...)
```

Add the helper at the bottom of `matchmaker.go`:

```go
// defaultMatchOptionsFor returns the canonical MatchOptions for a public
// queue ruleset key. Returns false if the key has no match-mode mapping
// (i.e. classic queues fall through to MatchOptions{}).
func defaultMatchOptionsFor(ruleset string) (core.MatchOptions, bool) {
	switch ruleset {
	case "chongci-fh":
		return core.MatchOptions{
			Mode: pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: &pb.ChongciConfig{
				StartingScore: 2000,
				BustThreshold: 0,
				MaxHands:      50,
			},
		}, true
	default:
		return core.MatchOptions{}, false
	}
}
```

- [ ] **Step 4: Register the queue watcher.**

In `cmd/server/main.go`, locate the existing watcher start (line 78):

```go
go matchmaker.StartQueueWatcher("hometown")
```

Add directly below:

```go
go matchmaker.StartQueueWatcher("chongci-fh")
```

- [ ] **Step 5: Run the tests, confirm they pass.**

```bash
go test ./api -run "TestCreateMatch_ChongciRulesetThreadsMatchOptions|TestCreateMatch_HometownRulesetKeepsClassic"
go test ./...
```

Expected: all green.

- [ ] **Step 6: Commit.**

```bash
git add api/matchmaker.go cmd/server/main.go api/room_bot_test.go
git commit -m "api: chongci-fh public queue with default MatchOptions"
```

---

## Task 14: API — `Room` reaches `PHASE_MATCH_END` end-to-end and schedules grace shutdown

This task has two halves, each with its own test:

- (a) **Bot-only room reaches `PHASE_MATCH_END`** — exercises the full engine + room loop with all four seats automated. Works after Task 7's engine plumbing alone; this test catches integration regressions across the engine + room interface.
- (b) **`Room` arms a one-shot grace shutdown when `PHASE_MATCH_END` is observed via `BroadcastState`** — covers the new shutdown hook on the Room.

**Files:**
- Modify: `api/room.go` (state-broadcast / shutdown path)
- Modify: `api/room_bot_test.go`

- [ ] **Step 1: Write the failing tests.**

Append to `api/room_bot_test.go`. The test drives the engine synchronously via `advanceAutomatedSeats` — no Hub, no goroutines, no networking. Bots already handle `ACTION_READY` between hands inside `advanceAutomatedSeats()`.

```go
// runBotOnlyRoomUntilTerminal repeatedly drives advanceAutomatedSeats on
// a fully-bot room until the engine reports PHASE_MATCH_END or the safety
// iteration cap trips. Returns the final-phase reached.
func runBotOnlyRoomUntilTerminal(t *testing.T, room *Room, maxIters int) pb.GamePhase {
	t.Helper()
	if err := room.Engine.Start(); err != nil {
		t.Fatalf("Engine.Start: %v", err)
	}
	for i := 0; i < maxIters; i++ {
		if room.Engine.State.Phase == pb.GamePhase_PHASE_MATCH_END {
			return room.Engine.State.Phase
		}
		room.advanceAutomatedSeats()
	}
	return room.Engine.State.Phase
}

func TestRoom_ChongciBust_TerminatesViaPhaseMatchEnd(t *testing.T) {
	// Aggressive thresholds so the test completes in a bounded number of hands.
	cfg := &pb.ChongciConfig{
		StartingScore: 50,
		BustThreshold: 0,
		MaxHands:      30,
	}
	room := NewRoom("bust-test", nil, nil, WithMatchOptions(core.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	}))

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}
	if room.Engine.State.MatchEndResult == nil {
		t.Fatal("MatchEndResult is nil")
	}
	got := room.Engine.State.MatchEndResult.Reason
	if got != "bust" && got != "hand_cap" {
		t.Fatalf("Reason = %q, want bust or hand_cap", got)
	}
	if len(room.Engine.State.MatchEndResult.Standings) != 4 {
		t.Fatalf("Standings length = %d, want 4", len(room.Engine.State.MatchEndResult.Standings))
	}
}
```

The `core` import needs to be present (`"github.com/plasma/fh-mahjong/core"`); add it to the file's imports if not already there.

Now add the grace-shutdown test:

```go
func TestRoom_GraceShutdown_ArmedOnMatchEnd(t *testing.T) {
	room := NewRoom("grace-test", nil, nil)
	// Probe directly via the test export so we don't have to drive the full
	// BroadcastState path (which iterates over connected clients we don't have).
	room.Engine.State.Phase = pb.GamePhase_PHASE_MATCH_END

	room.CheckMatchEndShutdownForTest()
	if !room.MatchEndScheduledForTest() {
		t.Fatal("first check after PHASE_MATCH_END must arm grace-shutdown timer")
	}

	prev := room.MatchEndScheduledForTest()
	room.CheckMatchEndShutdownForTest()
	if room.MatchEndScheduledForTest() != prev {
		t.Fatal("second check must not re-arm the timer (idempotent)")
	}
}

func TestRoom_GraceShutdown_NotArmedBeforeMatchEnd(t *testing.T) {
	room := NewRoom("grace-test-pre", nil, nil)
	// Default phase is PHASE_INIT; should not arm.
	room.CheckMatchEndShutdownForTest()
	if room.MatchEndScheduledForTest() {
		t.Fatal("grace-shutdown armed before PHASE_MATCH_END")
	}
}
```

- [ ] **Step 2: Run the tests, confirm they fail.**

```bash
go test ./api -run "TestRoom_ChongciBust_TerminatesViaPhaseMatchEnd|TestRoom_GraceShutdown" -timeout 60s
```

Expected: the grace-shutdown tests FAIL (`MatchEndScheduledForTest` / `CheckMatchEndShutdownForTest` undefined). The bust test may PASS if Tasks 7–12 already wired the engine correctly; if it FAILs, the iteration cap trip points at an integration regression earlier in the plan — fix that before continuing.

- [ ] **Step 3: Handle `PHASE_MATCH_END` in the room's broadcast path.**

In `api/room.go`, add a struct field to `Room`:

```go
type Room struct {
	// ...existing fields...
	matchEndScheduled bool
}
```

Add a helper near the end of the file:

```go
// checkMatchEndShutdown arms a 30-second timer the first time the engine
// reports PHASE_MATCH_END. When the timer fires, it sends on the Shutdown
// channel so the main loop runs its usual teardown (paipu persistence,
// hub deregister, etc.). Players see the final state during the grace
// window so client overlays render before any reconnect attempt 404s.
//
// The send is non-blocking: if no one is reading from Shutdown (e.g.
// synchronous tests that never started Room.Start), the timer signal is
// silently dropped. Production rooms always have a Shutdown receiver.
func (r *Room) checkMatchEndShutdown() {
	if r.matchEndScheduled {
		return
	}
	if r.Engine.State.Phase != pb.GamePhase_PHASE_MATCH_END {
		return
	}
	r.matchEndScheduled = true
	go func() {
		time.Sleep(30 * time.Second)
		select {
		case r.Shutdown <- true:
		default:
		}
	}()
}

// MatchEndScheduledForTest exposes the matchEndScheduled flag to tests.
func (r *Room) MatchEndScheduledForTest() bool { return r.matchEndScheduled }

// CheckMatchEndShutdownForTest exposes checkMatchEndShutdown to tests.
func (r *Room) CheckMatchEndShutdownForTest() { r.checkMatchEndShutdown() }
```

Add `"time"` to the import block of `api/room.go` if not already present (it likely is — the file already deals with timestamps).

Wire the helper into the broadcast path. The `Room.BroadcastState` method (search for `func (r *Room) BroadcastState`) is the natural single chokepoint — add `r.checkMatchEndShutdown()` at the end of the method body, after the broadcast send.

- [ ] **Step 4: Run the tests, confirm they pass.**

```bash
go test ./api -run "TestRoom_ChongciBust_TerminatesViaPhaseMatchEnd|TestRoom_GraceShutdown" -timeout 60s
go test ./...
```

Expected: all green. The bust test completes far under 30 seconds because the engine reaches PHASE_MATCH_END after a small number of hands with `starting_score: 50`. The grace-shutdown tests run in milliseconds — they probe the flag-flip directly.

- [ ] **Step 5: Commit.**

```bash
git add api/room.go api/room_bot_test.go
git commit -m "api: Room arms 30s grace shutdown on PHASE_MATCH_END"
```

---

## Task 15: API — hand-cap end-to-end test

**Files:**
- Modify: `api/room_bot_test.go`

- [ ] **Step 1: Write the failing test.**

Append to `api/room_bot_test.go`:

```go
func TestRoom_ChongciHandCap_Terminates(t *testing.T) {
	cfg := &pb.ChongciConfig{
		StartingScore: 10_000_000, // intentionally high so nobody busts
		BustThreshold: 0,
		MaxHands:      1,            // cap after one hand
	}
	room := NewRoom("handcap-test", nil, nil, WithMatchOptions(core.MatchOptions{
		Mode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: cfg,
	}))

	phase := runBotOnlyRoomUntilTerminal(t, room, 200_000)
	if phase != pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("phase = %v, want PHASE_MATCH_END (handNum=%d)", phase, room.Engine.State.HandNum)
	}
	if room.Engine.State.MatchEndResult.Reason != "hand_cap" {
		t.Fatalf("Reason = %q, want hand_cap (scores=%v)",
			room.Engine.State.MatchEndResult.Reason,
			[]int32{
				room.Engine.State.Players[0].Score,
				room.Engine.State.Players[1].Score,
				room.Engine.State.Players[2].Score,
				room.Engine.State.Players[3].Score,
			})
	}
}
```

- [ ] **Step 2: Run the test.**

```bash
go test ./api -run TestRoom_ChongciHandCap_Terminates -timeout 60s
```

Expected: PASS (if the engine wiring from Tasks 7 and 14 is correct). If the test fails because some player's score drops below 0 even with a 100,000 stack (i.e. the hand happens to produce a very large payout), bump `StartingScore` to `10_000_000` and re-run.

- [ ] **Step 3: Commit.**

```bash
git add api/room_bot_test.go
git commit -m "api: chongci hand-cap end-to-end test"
```

---

## Task 16: Frontend — match-mode picker + Chongci config inputs on `Table.tsx`

**Files:**
- Modify: `web/src/pages/Table.tsx`

- [ ] **Step 1: Add the `setMatchMode` callback.**

Near the existing `mutateSeat` callback (around line 151), add:

```ts
const setMatchMode = useCallback(async (mode: 'classic' | 'chongci', cfg?: { starting_score: number; bust_threshold: number; max_hands: number }) => {
    if (!tableId || !guestToken) return;
    try {
        const res = await fetch(getApiUrl(`/api/v1/private-tables/${tableId}/mode`), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${guestToken}` },
            body: JSON.stringify({ mode, chongci_config: cfg }),
        });
        if (res.status === 401) {
            handleAuthFailure();
            return;
        }
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            setError(data.error || 'Failed to update match mode');
        }
    } catch (err: any) {
        setError(err.message || 'Failed to update match mode');
    }
}, [guestToken, tableId, handleAuthFailure]);
```

- [ ] **Step 2: Add local UI state for the Chongci form.**

Near the top of the component (next to the existing `useState` calls), add:

```ts
const [chongciDraft, setChongciDraft] = useState({ starting_score: 2000, bust_threshold: 0, max_hands: 50 });
```

When `tableState.chongci_config` arrives from the server, sync the draft:

```ts
useEffect(() => {
    const cfg = tableState?.chongciConfig;
    if (cfg) {
        setChongciDraft({
            starting_score: Number(cfg.startingScore ?? 2000),
            bust_threshold: Number(cfg.bustThreshold ?? 0),
            max_hands: Number(cfg.maxHands ?? 50),
        });
    }
}, [tableState?.chongciConfig]);
```

- [ ] **Step 3: Render the match-mode section.**

In the JSX returned after the guest-join screen, above the seat cards (search for `seats.map` or `SeatCard`), add a new section. Use Tailwind classes matching the existing dark-emerald palette:

```tsx
{(() => {
    const currentMode = tableState?.matchMode ?? 1; // 1 = CLASSIC
    const isChongci = currentMode === 2;
    return (
        <section className="mb-6 rounded-3xl border border-emerald-300/15 bg-slate-950/55 p-6">
            <h2 className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Match Mode</h2>
            <div className="mt-4 flex gap-3">
                <button
                    disabled={!iAmHost || tableState?.state === 'started'}
                    onClick={() => setMatchMode('classic')}
                    className={`flex-1 rounded-2xl border px-4 py-3 text-sm font-black uppercase tracking-[0.18em] ${!isChongci ? 'border-emerald-300/40 bg-emerald-600/30 text-emerald-100' : 'border-slate-700 bg-slate-900/60 text-slate-400'} disabled:cursor-not-allowed disabled:opacity-50`}
                >
                    Classic
                </button>
                <button
                    disabled={!iAmHost || tableState?.state === 'started'}
                    onClick={() => setMatchMode('chongci', chongciDraft)}
                    className={`flex-1 rounded-2xl border px-4 py-3 text-sm font-black uppercase tracking-[0.18em] ${isChongci ? 'border-emerald-300/40 bg-emerald-600/30 text-emerald-100' : 'border-slate-700 bg-slate-900/60 text-slate-400'} disabled:cursor-not-allowed disabled:opacity-50`}
                >
                    Chongci
                </button>
            </div>
            {isChongci && (
                <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
                    {[
                        { key: 'starting_score', label: 'Starting points', min: 100, max: 1_000_000 },
                        { key: 'bust_threshold', label: 'Bust threshold', min: -1_000_000, max: 0 },
                        { key: 'max_hands', label: 'Max hands (0=∞)', min: 0, max: 200 },
                    ].map(({ key, label, min, max }) => (
                        <label key={key} className="block text-xs uppercase tracking-[0.18em] text-emerald-200/70">
                            {label}
                            <input
                                type="number"
                                min={min}
                                max={max}
                                value={(chongciDraft as any)[key]}
                                disabled={!iAmHost || tableState?.state === 'started'}
                                onChange={e => setChongciDraft(d => ({ ...d, [key]: Number(e.target.value) }))}
                                onBlur={() => iAmHost && setMatchMode('chongci', chongciDraft)}
                                className="mt-2 w-full rounded-2xl border border-emerald-300/20 bg-slate-900/60 px-3 py-2 text-sm text-emerald-100 focus:outline-none focus:ring-2 focus:ring-emerald-400/40 disabled:opacity-50"
                            />
                        </label>
                    ))}
                </div>
            )}
            {!iAmHost && (
                <p className="mt-3 text-xs text-slate-400">Only the host can change match settings.</p>
            )}
        </section>
    );
})()}
```

(The two-button rendering avoids a radio in favor of the host pressing the button to commit; the `onBlur` handler on each input re-posts the config so edits stick when focus leaves the field.)

- [ ] **Step 4: Verify locally.**

Run the frontend dev server:

```bash
cd web && npm run dev
```

Open `/table/<some-id>` as a host and confirm:
- The "Match Mode" section renders with Classic / Chongci buttons.
- Clicking Chongci reveals three number inputs pre-populated with `2000 / 0 / 50`.
- Editing a field and tabbing out (blur) saves it — refresh the page and the value persists.
- A second tab opened as a non-host sees the inputs as disabled.

- [ ] **Step 5: Commit.**

```bash
git add web/src/pages/Table.tsx
git commit -m "web(table): match-mode picker with chongci settings"
```

---

## Task 17: Frontend — "Quick Match — Chongci" button on `Lobby.tsx`

**Files:**
- Modify: `web/src/pages/Lobby.tsx`

- [ ] **Step 1: Locate the existing "Quick Match" button.**

Open `web/src/pages/Lobby.tsx`. Find the existing button that calls `POST /api/v1/matchmaking/join` with `ruleset: "hometown"`. Note its surrounding markup so the new button matches the visual style.

- [ ] **Step 2: Add a parallel button.**

Below (or beside) the existing Quick Match button, add:

```tsx
<button
    onClick={async () => {
        const res = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ ruleset: 'chongci-fh' }),
        });
        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            setError(data.error || 'Failed to join Chongci queue');
        }
    }}
    className="rounded-2xl border border-emerald-300/30 bg-emerald-600/80 px-6 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500"
>
    Quick Match — Chongci
</button>
```

(Adjust `token` / `setError` references to match the existing variable names in `Lobby.tsx`.)

- [ ] **Step 3: Verify locally.**

```bash
cd web && npm run dev
```

Open `/lobby`, click "Quick Match — Chongci" in four browser tabs (or one tab + three test users), and confirm a match starts with the chongci HUD badge visible (HUD comes in Task 18; for this task verify the request goes out and the matchmaking response is 200/202).

- [ ] **Step 4: Commit.**

```bash
git add web/src/pages/Lobby.tsx
git commit -m "web(lobby): quick-match button for chongci-fh queue"
```

---

## Task 18: Frontend — Chongci HUD badge on `Game.tsx`

**Files:**
- Modify: `web/src/pages/Game.tsx`

- [ ] **Step 1: Locate the hand-counter section.**

Open `web/src/pages/Game.tsx` and find the element that renders `gameState.handNum` (search for `handNum`). The badge sits directly below it.

- [ ] **Step 2: Render the badge conditionally.**

Add this snippet beneath the hand-counter:

```tsx
{gameState?.matchMode === 2 && gameState.chongciConfig && (
    <div className="mt-1 inline-flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-900/30 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-amber-200">
        <span>Chongci</span>
        <span className="text-amber-400/70">·</span>
        <span>Start {Number(gameState.chongciConfig.startingScore)}</span>
        <span className="text-amber-400/70">·</span>
        <span>Bust ≤ {Number(gameState.chongciConfig.bustThreshold)}</span>
        <span className="text-amber-400/70">·</span>
        <span>
            {Number(gameState.chongciConfig.maxHands) === 0
                ? 'No cap'
                : `Cap ${Number(gameState.chongciConfig.maxHands)}`}
        </span>
    </div>
)}
```

- [ ] **Step 3: Verify locally.**

Start a Chongci match (private table) and confirm the badge appears with the configured values; verify it does NOT appear for a classic match.

- [ ] **Step 4: Commit.**

```bash
git add web/src/pages/Game.tsx
git commit -m "web(game): chongci HUD badge"
```

---

## Task 19: Frontend — `MatchEndOverlay.tsx`

**Files:**
- Create: `web/src/pages/MatchEndOverlay.tsx`
- Modify: `web/src/pages/Game.tsx`
- Modify: `web/src/pages/AGENTS.md`

- [ ] **Step 1: Create the overlay component.**

Create `web/src/pages/MatchEndOverlay.tsx`:

```tsx
import { useNavigate } from 'react-router-dom';
import { game } from '../proto/game';

type Props = {
    state: game.IGameState;
    seatNames: (string | null)[];   // length 4; null for AI seats
};

const reasonLabel = (reason?: string | null) => {
    switch (reason) {
        case 'bust': return 'Match Over — Bust';
        case 'hand_cap': return 'Match Over — Hand cap reached';
        default: return 'Match Over';
    }
};

const rankLabel = (rank: number) => {
    if (rank === 1) return '1st';
    if (rank === 2) return '2nd';
    if (rank === 3) return '3rd';
    return `${rank}th`;
};

export default function MatchEndOverlay({ state, seatNames }: Props) {
    const navigate = useNavigate();
    const result = state.matchEndResult;
    if (!result || !result.standings) return null;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-6">
            <div className="w-full max-w-lg rounded-[28px] border border-emerald-300/20 bg-slate-950/95 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.5)]">
                <p className="text-[11px] font-black uppercase tracking-[0.32em] text-emerald-300/78">Chongci</p>
                <h1 className="mt-2 text-2xl font-black uppercase tracking-[0.12em] text-emerald-100">
                    {reasonLabel(result.reason)}
                </h1>
                <p className="mt-1 text-xs text-slate-400">Final hand: {Number(result.finalHandNum ?? 0)}</p>

                <div className="mt-6 overflow-hidden rounded-2xl border border-slate-800">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-900/80 text-[10px] uppercase tracking-[0.18em] text-emerald-200/70">
                            <tr>
                                <th className="px-4 py-2 text-left">Rank</th>
                                <th className="px-4 py-2 text-left">Player</th>
                                <th className="px-4 py-2 text-right">Score</th>
                                <th className="px-4 py-2 text-right">Δ</th>
                            </tr>
                        </thead>
                        <tbody>
                            {result.standings.map(s => {
                                const seat = Number(s.seat ?? 0);
                                const name = seatNames[seat] ?? `Seat ${seat}`;
                                const net = Number(s.netChange ?? 0);
                                return (
                                    <tr key={seat} className="border-t border-slate-800/80">
                                        <td className="px-4 py-2 font-black text-emerald-100">{rankLabel(Number(s.rank ?? 0))}</td>
                                        <td className="px-4 py-2 text-slate-200">{name}</td>
                                        <td className="px-4 py-2 text-right text-slate-100">{Number(s.finalScore ?? 0)}</td>
                                        <td className={`px-4 py-2 text-right font-mono ${net >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
                                            {net >= 0 ? `+${net}` : `${net}`}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>

                <button
                    onClick={() => navigate('/lobby')}
                    className="mt-6 w-full rounded-2xl border border-emerald-300/30 bg-emerald-600 px-5 py-3 text-sm font-black uppercase tracking-[0.18em] text-white shadow-[0_18px_38px_rgba(5,150,105,0.32)] hover:bg-emerald-500"
                >
                    Leave
                </button>
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Render the overlay from `Game.tsx`.**

In `web/src/pages/Game.tsx`, near the other top-level component imports, add:

```ts
import MatchEndOverlay from './MatchEndOverlay';
```

In the JSX return, add at the very top of the rendered tree (so it sits above the table):

```tsx
{gameState?.phase === 5 /* PHASE_MATCH_END */ && (
    <MatchEndOverlay
        state={gameState}
        seatNames={[null, null, null, null]}
    />
)}
```

`Game.tsx` does not currently carry per-seat usernames (the table-board only renders seat winds + scores). Passing `[null, null, null, null]` makes the overlay render `Seat 0 / Seat 1 / Seat 2 / Seat 3` labels. Adding richer player names is deferred to the "Future Extensions" line in the spec — when the page does start carrying usernames, the prop is already in place.

- [ ] **Step 3: Update the pages AGENTS.md.**

In `web/src/pages/AGENTS.md`, add a line to the file index:

```
- `MatchEndOverlay.tsx` — Chongci final-standings modal rendered when `gameState.phase === PHASE_MATCH_END`.
```

- [ ] **Step 4: Verify locally.**

Run a Chongci match with `starting_score: 50` so a bust happens quickly. Confirm:
- The overlay appears layered over the dimmed table when the engine reports `PHASE_MATCH_END`.
- The standings are sorted with correct ranks; ties share a rank.
- The `Leave` button navigates back to `/lobby`.
- A page reload while the overlay is up restores it identically (the engine state still has `PHASE_MATCH_END`).

- [ ] **Step 5: Commit.**

```bash
git add web/src/pages/MatchEndOverlay.tsx web/src/pages/Game.tsx web/src/pages/AGENTS.md
git commit -m "web: MatchEndOverlay for chongci final standings"
```

---

## Task 20: Manual end-to-end verification

This task has no automated test; it is the manual sign-off list referenced in the spec.

- [ ] **Step 1: Solo Chongci (1 human + 3 AI) via private table.**

```bash
go run ./cmd/server &
cd web && npm run dev
```

In a browser:
1. Log in as a user, navigate to `/create-room` → `/table/<id>`.
2. Click "Chongci"; set `starting_score: 200, bust_threshold: 0, max_hands: 50`.
3. Add three AI heuristic seats; click Start.
4. Play through hands until one player busts.
5. Confirm: HUD badge shows `Chongci · Start 200 · Bust ≤ 0 · Cap 50`. Overlay renders with four ranked standings; clicking Leave routes to `/lobby`.

- [ ] **Step 2: Mixed Chongci (2 humans + 2 AI) — two browser tabs.**

Same as above but join from a second tab as a second user; confirm the second tab sees the same lobby_update stream and identical overlay at the end.

- [ ] **Step 3: Non-host cannot edit settings.**

In the second tab, confirm the Match Mode buttons and Chongci config inputs are disabled.

- [ ] **Step 4: Reload during `configuring`.**

Refresh the host tab mid-config; the saved mode + config values come back from the server.

- [ ] **Step 5: Reload during `PHASE_MATCH_END`.**

Refresh the host tab while the overlay is visible; the overlay re-renders with the same standings.

- [ ] **Step 6: Public Chongci queue.**

In four browser tabs (four logged-in users), each clicks "Quick Match — Chongci". Confirm a match starts with `starting_score: 2000`, `bust_threshold: 0`, `max_hands: 50` shown in the HUD badge.

- [ ] **Step 7: Classic mode regression check.**

Start a normal private-table match (no mode change). Confirm: no HUD badge appears, players start at 25000, the game runs hands indefinitely without `PHASE_MATCH_END`.

- [ ] **Step 8: Commit (docs only).**

If `web/src/pages/AGENTS.md` or other docs need updates discovered during manual testing, commit them now. Otherwise no commit is needed for this task.

---

## Out-of-band cleanup

After the plan finishes, run:

```bash
go test ./...
cd web && npm run build
```

Both must succeed end-to-end. Any failures here surface integration gaps not caught by per-task tests — open them as follow-ups, do not paper over with skips.
