# Discard and Call Look-ahead Planes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `EnvConfig.lookahead_version = 1`: 13 per-face plane channels carrying shanten and useful-tile
look-ahead for every legal discard and call, wired end to end (Go encoder → bridge → B2b training → batched
evaluation), dormant and byte-identical at version 0.

**Architecture:** Go computes the channels from `shanten.AnalyzeHand` and the engine's own legal actions
(`internal/rl/lookahead.go`) and inserts them between the 39 public channels and the 12 oracle channels.
Python resolves the plane count from the version, the model's stem widens to 39 + 13 with zero-initialised
new columns, and every 39/51 literal becomes `policy_channels`-relative.

**Tech Stack:** Go 1.25, protobuf (protoc-gen-go, protobufjs, grpcio-tools on a protobuf 6.x runtime),
Python 3 + PyTorch via `uv run --project ai`.

**Spec:** `worklog/specs/20261004-discard-call-lookahead-planes.md`

## Global Constraints

- Version 0 is byte-identical: the three process-collector golden digests
  (`ai/tests/test_b2b_collector_parity.py`) and every existing Go/Python test pass unchanged.
- Versions above 1 are rejected in Go (`Env.Reset`, `NewSearchPool`, `FHEnvPoolNew`, the encoder) and Python
  (`EnvConfig`, `ModelConfig`).
- Plane layout: public `[0, 39)`, look-ahead `[39, 52)`, oracle `[52, 64)` when oracle is on.
- Channel order inside the block (offset from 39): 0 discard overall shanten, 1 standard, 2 seven pairs,
  3 Independence, 4 raw useful tiles, 5 live useful tiles, 6 danger, 7 pon shanten, 8 pon live, 9 chii shanten,
  10 chii live, 11 kan shanten, 12 kan live.
- Shanten uses `normalizeShanten`; useful-tile counts use `normalizeUsefulTileCount` (÷64, clamped).
- Chii features sit in the sequence's middle face; pon and kan in the called face; discards in the discarded face.
- No second rules implementation: call look-ahead removes the engine's `meld_tiles` from the closed hand.
- Python protobuf bindings target a protobuf **6.x** runtime (header `Protobuf Python Version: 6.33.x`).
- Run CI gates before the PR: `gofmt -l .` (prints nothing), `go vet ./...`, `go test ./...`,
  `cd web && npx tsc && npx vitest run`, and `uv run --project ai pytest -q ai/tests`.
- Update each touched directory's `CLAUDE.md` (never replace an `AGENTS.md` symlink).

## Review Focus

1. A call whose `meld_tiles` are not all in the closed hand (stale or malformed action) must make the encoder
   return an error, never silently analyse the wrong hand — pinned in Task 2.
2. A Python `EnvConfig` toggled with `dataclasses.replace(..., oracle_observation=True)` from a version-1
   non-oracle config must resolve to 64 channels, not raise or keep 52 — pinned in Task 4.
3. Loading a version-1 checkpoint through any path that builds `EnvConfig()` without the version must fail
   closed with a version-mismatch error, not run a 39-channel env into a 52-channel stem — pinned in Task 5.
4. `fh-mj-compare` on a version-1 report vs a version-0 report must refuse without
   `--allow-lookahead-mismatch` and label the result with it — pinned in Task 7.
5. A stale Go bridge that ignores `lookahead_version` must raise a "rebuild the bridge" error on the first
   decoded observation, not a reshape error deep in a worker — pinned in Task 4.

---

### Task 1: Proto field and regenerated bindings

**Files:**
- Modify: `proto/game.proto` (message `EnvConfig`, after field 7)
- Regenerate: `proto/game.pb.go`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`,
  `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`
- Modify: `proto/CLAUDE.md`

**Interfaces:**
- Produces: `pb.EnvConfig.LookaheadVersion uint32` (Go), `EnvConfig.lookahead_version` (Python/TS).

- [ ] **Step 1: Add the field**

In `proto/game.proto`, inside `message EnvConfig`, after `uint32 event_history_window = 7;`:

```proto
  // Per-action look-ahead planes inserted after the 39 public channels
  // (internal/rl/lookahead.go). 0 (default) adds none — byte-identical
  // observations. 1 adds 13 discard/call channels (39 -> 52, oracle 51 -> 64).
  uint32 lookahead_version = 8;
```

- [ ] **Step 2: Regenerate Go and TypeScript**

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

- [ ] **Step 3: Regenerate Python on a protobuf 6.x toolchain**

```bash
uv run --no-project --with "grpcio-tools>=1.70,<1.77" --with "protobuf>=6.33,<7" \
  python -m grpc_tools.protoc --python_out=ai/src/fh_mahjong_ai/generated --proto_path=. proto/game.proto
head -5 ai/src/fh_mahjong_ai/generated/proto/game_pb2.py
```

Expected: the header reads `# Protobuf Python Version: 6.33.x`. If it reads `7.`, pick an older
`grpcio-tools` pin and rerun; never commit 7.x gencode.

- [ ] **Step 4: Verify the field round-trips**

```bash
go build ./... && uv run --project ai python -c "
from fh_mahjong_ai.generated.proto import game_pb2 as pb
m = pb.EnvConfig(lookahead_version=1); assert pb.EnvConfig.FromString(m.SerializeToString()).lookahead_version == 1; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Document and commit**

Add one line to `proto/CLAUDE.md`'s EnvConfig notes: "`lookahead_version` (8): 0 dormant; 1 = 13 look-ahead
channels after the 39 public ones (`internal/rl/lookahead.go`)."

```bash
git add proto/ web/src/proto/ ai/src/fh_mahjong_ai/generated/proto/game_pb2.py
git commit -m "feat(proto): EnvConfig.lookahead_version (dormant)"
```

---

### Task 2: Go look-ahead block in the encoder

**Files:**
- Create: `internal/rl/lookahead.go`
- Create: `internal/rl/lookahead_test.go`
- Modify: `internal/rl/observation.go` (`encodeObservation`, `emptyObservation`, the two exported wrappers)
- Modify: `internal/rl/action.go` (`actionMask` → shared `maskFromLegal`)
- Modify: every `encodeObservation(`/`emptyObservation(` caller: `internal/rl/env.go` (lines ~112, 173–212,
  356–392), `internal/rl/searchpool.go` (lines ~341–387), `internal/rl/observation_symmetry_test.go`
  and any other `_test.go` the compiler flags

**Interfaces:**
- Consumes: `pb.EnvConfig.LookaheadVersion` (Task 1).
- Produces: `const MaxLookaheadVersion = 1`; `func LookaheadPlaneCount(version uint32) int`;
  `func validateLookaheadVersion(version uint32) error`; `func observationChannels(oracle bool, lookahead uint32) int`;
  `encodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64, oracle bool, lookahead uint32, events []engine.PublicEvent, window uint32)`;
  `emptyObservation(state *pb.GameState, decisionIndex uint64, oracle bool, lookahead uint32, window uint32)`.

- [ ] **Step 1: Write the failing tests**

Create `internal/rl/lookahead_test.go`:

```go
package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
)

func lookaheadCell(obs *pb.SeatObservation, channel, face int) float32 {
	return obs.Planes[channelOffset(ObservationPlaneChannels+channel)+face]
}

func testFace(t *testing.T, face string) int {
	t.Helper()
	index, ok := tileFaceIndex42(routeTestTiles(t, face)[0])
	if !ok {
		t.Fatalf("no face index for %s", face)
	}
	return index
}

func faceOfType(t *testing.T, tile shanten.TileType) int {
	t.Helper()
	index, ok := tileFaceIndex42(&pb.Tile{Suit: tile.Suit, Value: tile.Value})
	if !ok {
		t.Fatalf("no face index for %+v", tile)
	}
	return index
}

// claimState is a WAIT_DISCARDS state where seat 0 may answer seat 3's discard.
func claimState(hand []*pb.Tile, discard *pb.Tile, actions []*pb.PlayerAction) *pb.GameState {
	return &pb.GameState{
		Phase:         pb.GamePhase_PHASE_WAIT_DISCARDS,
		ActivePlayer:  3,
		ActiveDiscard: discard,
		Players: []*pb.PlayerState{
			{ClosedHand: hand, ValidActions: actions},
			{}, {}, {Discards: []*pb.Tile{discard}},
		},
	}
}

// bestStandardAfterDiscard is the reference for the pon/chii channels: the
// best (lowest standard shanten, then most live useful tiles) discard after
// the call, computed from an explicitly written post-call hand.
func bestStandardAfterDiscard(rest []*pb.Tile, melds int, wilds []*pb.Tile, visible [42]int) (int, int) {
	best, bestLive := shanten.RouteUnavailable, 0
	for _, option := range shanten.AnalyzeHand(rest, melds, wilds).DiscardOptions {
		live := liveUsefulCount(option.UsefulTiles, visible)
		if option.After.Standard < best || (option.After.Standard == best && live > bestLive) {
			best, bestLive = option.After.Standard, live
		}
	}
	return best, bestLive
}

func TestLookaheadVersionZeroUnchangedAndVersionOneShiftsOracle(t *testing.T) {
	hand := routeTestTiles(t, "1m2m4m7m2p5p8p3s6s9s1z2z3z4z")
	state := discardTurnState(hand, nil, 0)
	state.Players[1].ClosedHand = routeTestTiles(t, "1p1p1p")
	for _, oracle := range []bool{false, true} {
		v0, err := encodeObservation(state, 0, 0, oracle, 0, nil, 0)
		if err != nil {
			t.Fatalf("v0: %v", err)
		}
		v1, err := encodeObservation(state, 0, 0, oracle, 1, nil, 0)
		if err != nil {
			t.Fatalf("v1: %v", err)
		}
		if int(v0.PlaneChannels) != observationChannels(oracle, 0) || int(v1.PlaneChannels) != int(v0.PlaneChannels)+13 {
			t.Fatalf("oracle=%v channels v0=%d v1=%d", oracle, v0.PlaneChannels, v1.PlaneChannels)
		}
		for i := 0; i < channelOffset(ObservationPlaneChannels); i++ {
			if v0.Planes[i] != v1.Planes[i] {
				t.Fatalf("oracle=%v public plane cell %d differs", oracle, i)
			}
		}
		if oracle {
			for i := 0; i < channelOffset(12); i++ {
				if v0.Planes[channelOffset(39)+i] != v1.Planes[channelOffset(52)+i] {
					t.Fatalf("oracle cell %d not shifted to channel 52+", i)
				}
			}
		}
		for i := range v0.Scalars {
			if v0.Scalars[i] != v1.Scalars[i] {
				t.Fatalf("scalar %d differs", i)
			}
		}
		if string(v0.ActionMask) != string(v1.ActionMask) {
			t.Fatalf("mask differs")
		}
	}
	if _, err := encodeObservation(state, 0, 0, false, 2, nil, 0); err == nil {
		t.Fatalf("version 2 must be rejected")
	}
}

func TestLiveUsefulCountSubtractsVisibleCopiesAndIndicator(t *testing.T) {
	state := &pb.GameState{
		WildTiles: routeTestTiles(t, "5m"),
		Players:   []*pb.PlayerState{{}, {Discards: routeTestTiles(t, "3s3s")}, {}, {}},
	}
	useful := []shanten.UsefulTile{
		{Suit: pb.Suit_SUIT_SOU, Value: 3, Remaining: 3}, // 2 discarded -> 1 live
		{Suit: pb.Suit_SUIT_MAN, Value: 5, Remaining: 4}, // indicator face-up -> 3 live
		{Suit: pb.Suit_SUIT_PIN, Value: 1, Remaining: 2}, // unseen -> 2 live
	}
	if got := liveUsefulCount(useful, visibleFaceCounts(state)); got != 6 {
		t.Fatalf("live useful %d, want 6", got)
	}
	state.WildTiles = []*pb.Tile{{Suit: pb.Suit_SUIT_FLOWER, Value: 2}}
	if got := liveUsefulCount(useful, visibleFaceCounts(state)); got != 7 {
		t.Fatalf("flower indicator hides no suited copy: live %d, want 7", got)
	}
}

func TestLookaheadDiscardChannelsMatchAnalysis(t *testing.T) {
	hand := routeTestTiles(t, "1m2m3m4m4m5p6p7p3s4s1z1z5z6z")
	wilds := routeTestTiles(t, "9p")
	state := discardTurnState(hand, wilds, 0)
	state.Players[1].Discards = routeTestTiles(t, "2s5s")
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	visible := visibleFaceCounts(state)
	liveBelowRaw := false
	for _, option := range shanten.AnalyzeHand(hand, 0, wilds).DiscardOptions {
		face := faceOfType(t, option.Discard)
		live := liveUsefulCount(option.UsefulTiles, visible)
		liveBelowRaw = liveBelowRaw || live < option.TotalUseful
		want := map[int]float32{
			0: normalizeShanten(option.After.Overall),
			1: normalizeShanten(option.After.Standard),
			2: normalizeShanten(option.After.SevenPairs),
			3: normalizeShanten(option.After.Independence),
			4: normalizeUsefulTileCount(option.TotalUseful),
			5: normalizeUsefulTileCount(live),
			6: publicDangerScore(state, 0, &pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}),
		}
		for channel, value := range want {
			if got := lookaheadCell(obs, channel, face); got != value {
				t.Fatalf("discard %+v channel %d: got %v, want %v", option.Discard, channel, got, value)
			}
		}
	}
	if !liveBelowRaw {
		t.Fatalf("the visible 2s/5s should lower some discard's live count below its raw count")
	}
	for channel := 0; channel < 13; channel++ {
		if got := lookaheadCell(obs, channel, testFace(t, "9m")); got != 0 {
			t.Fatalf("face 9m is not in hand but channel %d = %v", channel, got)
		}
	}
}

func TestLookaheadPonAndChiiChannels(t *testing.T) {
	hand := routeTestTiles(t, "2m4m5m6m6m7p8p9p1s1s3z3z5z")
	discard := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 6}
	sixes := []*pb.Tile{hand[3], hand[4]} // 6m 6m
	actions := []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_PON, Tile: discard, MeldTiles: sixes, TargetPlayer: 3},
		// 4m5m + 6m is the only chii (no 7m or 8m in hand); its middle face is 5m.
		{Type: pb.ActionType_ACTION_CHII, Tile: discard, MeldTiles: []*pb.Tile{hand[1], hand[2]}, TargetPlayer: 3},
	}
	state := claimState(hand, discard, actions)
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}
	visible := visibleFaceCounts(state)

	ponRest := routeTestTiles(t, "2m4m5m7p8p9p1s1s3z3z5z")
	ponShanten, ponLive := bestStandardAfterDiscard(ponRest, 1, nil, visible)
	if got := lookaheadCell(obs, 7, testFace(t, "6m")); got != normalizeShanten(ponShanten) {
		t.Fatalf("pon shanten %v, want %v", got, normalizeShanten(ponShanten))
	}
	if got := lookaheadCell(obs, 8, testFace(t, "6m")); got != normalizeUsefulTileCount(ponLive) {
		t.Fatalf("pon live %v, want %v", got, normalizeUsefulTileCount(ponLive))
	}

	chiiRest := routeTestTiles(t, "2m6m6m7p8p9p1s1s3z3z5z")
	chiiShanten, chiiLive := bestStandardAfterDiscard(chiiRest, 1, nil, visible)
	middle := testFace(t, "5m") // 4m5m6m
	if got := lookaheadCell(obs, 9, middle); got != normalizeShanten(chiiShanten) {
		t.Fatalf("chii shanten %v, want %v", got, normalizeShanten(chiiShanten))
	}
	if got := lookaheadCell(obs, 10, middle); got != normalizeUsefulTileCount(chiiLive) {
		t.Fatalf("chii live %v, want %v", got, normalizeUsefulTileCount(chiiLive))
	}
	if got := lookaheadCell(obs, 9, testFace(t, "4m")); got != 0 {
		t.Fatalf("chii must sit in the middle face, not the start face")
	}
}

func TestLookaheadKanMeldCounts(t *testing.T) {
	// Closed kan on own turn: 4 tiles leave, one more meld.
	hand := routeTestTiles(t, "1m1m1m1m3p4p5p7s8s2z2z6z7z9s")
	state := discardTurnState(hand, nil, 0)
	state.Players[0].ValidActions = append(state.Players[0].ValidActions,
		&pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: hand[:4]})
	obs, err := encodeObservation(state, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode closed kan: %v", err)
	}
	rest := routeTestTiles(t, "3p4p5p7s8s2z2z6z7z9s")
	want := shanten.AnalyzeHand(rest, 1, nil)
	if got := lookaheadCell(obs, 11, testFace(t, "1m")); got != normalizeShanten(want.Routes.Standard) {
		t.Fatalf("closed kan shanten %v, want %v", got, normalizeShanten(want.Routes.Standard))
	}
	if got := lookaheadCell(obs, 12, testFace(t, "1m")); got != normalizeUsefulTileCount(liveUsefulCount(want.UsefulTiles, visibleFaceCounts(state))) {
		t.Fatalf("closed kan live %v", got)
	}

	// Upgraded kan: one tile leaves, the pon becomes a kan, the meld count is unchanged.
	pon := &pb.Meld{Type: pb.ActionType_ACTION_PON, Tiles: routeTestTiles(t, "7z7z7z")}
	upHand := routeTestTiles(t, "7z2m3m4m5p6p7p1s2s3s9s")
	upState := discardTurnState(upHand, nil, 0)
	upState.Players[0].OpenMelds = []*pb.Meld{pon}
	upState.Players[0].ValidActions = append(upState.Players[0].ValidActions,
		&pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: upHand[:1]})
	upObs, err := encodeObservation(upState, 0, 0, false, 1, nil, 0)
	if err != nil {
		t.Fatalf("encode upgraded kan: %v", err)
	}
	upWant := shanten.AnalyzeHand(upHand[1:], 1, nil)
	if got := lookaheadCell(upObs, 11, testFace(t, "7z")); got != normalizeShanten(upWant.Routes.Standard) {
		t.Fatalf("upgraded kan shanten %v, want %v (meld count must stay 1)", got, normalizeShanten(upWant.Routes.Standard))
	}
}

func TestLookaheadRejectsCallTilesMissingFromHand(t *testing.T) {
	hand := routeTestTiles(t, "2m4m5m6m6m7p8p9p1s1s3z3z5z")
	discard := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 6}
	ghost := []*pb.Tile{{Id: 4242, Suit: pb.Suit_SUIT_MAN, Value: 6}, hand[4]}
	state := claimState(hand, discard, []*pb.PlayerAction{
		{Type: pb.ActionType_ACTION_PON, Tile: discard, MeldTiles: ghost, TargetPlayer: 3},
	})
	if _, err := encodeObservation(state, 0, 0, false, 1, nil, 0); err == nil {
		t.Fatalf("a call revealing a tile not in the closed hand must be an encoder error")
	}
	if _, err := encodeObservation(state, 0, 0, false, 0, nil, 0); err != nil {
		t.Fatalf("version 0 never inspects meld tiles: %v", err)
	}
}
```

- [ ] **Step 2: Run them to verify they fail to compile**

Run: `go test ./internal/rl -run 'Lookahead|LiveUseful' -count=1`
Expected: FAIL — `undefined: observationChannels`, `liveUsefulCount`, `visibleFaceCounts`, and
`too many arguments in call to encodeObservation`.

- [ ] **Step 3: Create `internal/rl/lookahead.go`**

```go
package rl

import (
	"fmt"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
)

// MaxLookaheadVersion is the highest EnvConfig.lookahead_version the encoder
// knows. Version 1 adds the 13 discard/call look-ahead channels of
// worklog/specs/20261004-discard-call-lookahead-planes.md; 0 adds none.
const MaxLookaheadVersion = 1

// Channel offsets inside the version-1 block, which starts at channel 39.
const (
	lookaheadDiscardOverall = iota
	lookaheadDiscardStandard
	lookaheadDiscardSevenPairs
	lookaheadDiscardIndependence
	lookaheadDiscardUseful
	lookaheadDiscardLive
	lookaheadDiscardDanger
	lookaheadPonShanten
	lookaheadPonLive
	lookaheadChiiShanten
	lookaheadChiiLive
	lookaheadKanShanten
	lookaheadKanLive
	lookaheadV1Channels
)

// LookaheadPlaneCount is the number of plane channels a look-ahead version adds.
func LookaheadPlaneCount(version uint32) int {
	if version == 1 {
		return lookaheadV1Channels
	}
	return 0
}

func validateLookaheadVersion(version uint32) error {
	if version > MaxLookaheadVersion {
		return fmt.Errorf("lookahead_version %d exceeds maximum %d", version, MaxLookaheadVersion)
	}
	return nil
}

// observationChannels is the plane channel count of an encoder configuration:
// the 39 public channels, the look-ahead block, then the 12 oracle channels.
func observationChannels(oracle bool, lookahead uint32) int {
	channels := ObservationPlaneChannels + LookaheadPlaneCount(lookahead)
	if oracle {
		channels += 12
	}
	return channels
}

// visibleFaceCounts is publicSeenCounts plus the face-up wild indicator: a
// standard-tile indicator (GameState.WildTiles[0]) shows one copy of its face.
func visibleFaceCounts(state *pb.GameState) [42]int {
	counts := publicSeenCounts(state)
	if len(state.WildTiles) > 0 && state.WildTiles[0].Suit != pb.Suit_SUIT_FLOWER {
		if face, ok := tileFaceIndex42(state.WildTiles[0]); ok {
			counts[face]++
		}
	}
	return counts
}

// liveUsefulCount is the useful-tile count net of copies the seat can see.
func liveUsefulCount(useful []shanten.UsefulTile, visible [42]int) int {
	total := 0
	for _, tile := range useful {
		face, ok := tileFaceIndex42(&pb.Tile{Suit: tile.Suit, Value: tile.Value})
		if !ok {
			continue
		}
		if live := tile.Remaining - visible[face]; live > 0 {
			total += live
		}
	}
	return total
}

// handWithout is the closed hand minus the tiles (by id) a call reveals.
func handWithout(hand []*pb.Tile, revealed []*pb.Tile) ([]*pb.Tile, error) {
	drop := make(map[uint32]bool, len(revealed))
	for _, tile := range revealed {
		drop[tile.GetId()] = true
	}
	rest := make([]*pb.Tile, 0, len(hand))
	for _, tile := range hand {
		if drop[tile.GetId()] {
			delete(drop, tile.GetId())
			continue
		}
		rest = append(rest, tile)
	}
	if len(drop) > 0 {
		return nil, fmt.Errorf("call reveals %d tile(s) not in the closed hand", len(drop))
	}
	return rest, nil
}

// bestAfterCall analyses the hand after a pon or chii and the discard that must
// follow: the lowest standard shanten, then the most live useful tiles.
func bestAfterCall(player *pb.PlayerState, action *pb.PlayerAction, wilds []*pb.Tile, visible [42]int) (int, int, error) {
	rest, err := handWithout(player.ClosedHand, action.MeldTiles)
	if err != nil {
		return 0, 0, err
	}
	best, bestLive := shanten.RouteUnavailable, 0
	for _, option := range shanten.AnalyzeHand(rest, len(player.OpenMelds)+1, wilds).DiscardOptions {
		live := liveUsefulCount(option.UsefulTiles, visible)
		if option.After.Standard < best || (option.After.Standard == best && live > bestLive) {
			best, bestLive = option.After.Standard, live
		}
	}
	return best, bestLive, nil
}

// afterKan analyses the hand after a kan, before the replacement draw.
func afterKan(player *pb.PlayerState, action *pb.PlayerAction, melds int, wilds []*pb.Tile, visible [42]int) (int, int, error) {
	rest, err := handWithout(player.ClosedHand, action.MeldTiles)
	if err != nil {
		return 0, 0, err
	}
	analysis := shanten.AnalyzeHand(rest, melds, wilds)
	return analysis.Routes.Standard, liveUsefulCount(analysis.UsefulTiles, visible), nil
}

// setLookaheadPlanes writes the version-1 block starting at channel `base`.
func setLookaheadPlanes(planes []float32, base int, state *pb.GameState, seat uint32,
	legal map[int]*pb.PlayerAction, analysis shanten.HandAnalysis) error {
	player := state.Players[seat]
	visible := visibleFaceCounts(state)
	options := make(map[int]shanten.DiscardOption, len(analysis.DiscardOptions))
	for _, option := range analysis.DiscardOptions {
		if face, ok := tileFaceIndex42(&pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}); ok {
			options[face] = option
		}
	}
	set := func(channel, face int, value float32) {
		planes[channelOffset(base+channel)+face] = value
	}
	setCall := func(shantenChannel, face, standard, live int) {
		set(shantenChannel, face, normalizeShanten(standard))
		set(shantenChannel+1, face, normalizeUsefulTileCount(live))
	}
	for _, actionID := range SortedLegalIDs(legal) {
		action := legal[actionID]
		switch {
		case actionID >= DiscardBase && actionID < DiscardBase+DiscardCount:
			face := actionID - DiscardBase
			option, ok := options[face]
			if !ok {
				return fmt.Errorf("legal discard %d has no shanten option", actionID)
			}
			set(lookaheadDiscardOverall, face, normalizeShanten(option.After.Overall))
			set(lookaheadDiscardStandard, face, normalizeShanten(option.After.Standard))
			set(lookaheadDiscardSevenPairs, face, normalizeShanten(option.After.SevenPairs))
			set(lookaheadDiscardIndependence, face, normalizeShanten(option.After.Independence))
			set(lookaheadDiscardUseful, face, normalizeUsefulTileCount(option.TotalUseful))
			set(lookaheadDiscardLive, face, normalizeUsefulTileCount(liveUsefulCount(option.UsefulTiles, visible)))
			set(lookaheadDiscardDanger, face, publicDangerScore(state, seat, action.Tile))
		case actionID >= PonBase && actionID < PonBase+PonCount:
			standard, live, err := bestAfterCall(player, action, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadPonShanten, actionID-PonBase, standard, live)
		case actionID >= KanDirectBase && actionID < ChiiBase:
			melds := len(player.OpenMelds) + 1
			if actionID >= KanUpgradedBase {
				melds = len(player.OpenMelds) // the pon becomes the kan
			}
			standard, live, err := afterKan(player, action, melds, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadKanShanten, (actionID-KanDirectBase)%KanModeCount, standard, live)
		case actionID >= ChiiBase && actionID < ChiiBase+ChiiCount:
			index := actionID - ChiiBase
			middle := (index/7)*9 + index%7 + 1
			standard, live, err := bestAfterCall(player, action, state.WildTiles, visible)
			if err != nil {
				return err
			}
			setCall(lookaheadChiiShanten, middle, standard, live)
		}
	}
	return nil
}
```

- [ ] **Step 4: Wire the encoder**

In `internal/rl/action.go`, split the mask out of `actionMask` so the encoder builds the legal map once:

```go
func actionMask(state *pb.GameState, seat uint32) ([]byte, error) {
	actions, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}
	return maskFromLegal(actions), nil
}

func maskFromLegal(actions map[int]*pb.PlayerAction) []byte {
	mask := make([]byte, ActionSpaceSize)
	for actionID := range actions {
		mask[actionID] = 1
	}
	return mask
}
```

In `internal/rl/observation.go`, change the head of `encodeObservation`:

```go
func encodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64, oracle bool, lookahead uint32, events []engine.PublicEvent, window uint32) (*pb.SeatObservation, error) {
	if err := validateLookaheadVersion(lookahead); err != nil {
		return nil, err
	}
	legal, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}
	mask := maskFromLegal(legal)

	channels := observationChannels(oracle, lookahead)
	planes := make([]float32, channels*ObservationPlaneHeight*ObservationPlaneWidth)
```

After `scalars[41] = legalDiscardDangerRange(state, seat, mask)` and `setMatchContextScalars(...)`, before the
oracle block:

```go
	if lookahead > 0 {
		if err := setLookaheadPlanes(planes, ObservationPlaneChannels, state, seat, legal, selfAnalysis); err != nil {
			return nil, err
		}
	}
```

Replace the oracle block and the trailing channel count:

```go
	if oracle {
		// The three opponents' concealed hands, relative to `seat`, after the
		// public and look-ahead channels. right=+1, across=+2, left=+3.
		base := ObservationPlaneChannels + LookaheadPlaneCount(lookahead)
		setThresholdPlanes(planes, base, faceCountsFromTiles(right.ClosedHand))
		setThresholdPlanes(planes, base+4, faceCountsFromTiles(across.ClosedHand))
		setThresholdPlanes(planes, base+8, faceCountsFromTiles(left.ClosedHand))
	}

	planeChannels := uint32(channels)
```

Update the wrappers to pass `0` for `lookahead` (`EncodeObservation`, `EncodeObservationWithEvents` — serving
stays at version 0). Change `emptyObservation` to take `lookahead uint32` after `oracle` and size its planes with
`observationChannels(oracle, lookahead)`.

- [ ] **Step 5: Update callers until it compiles**

`internal/rl/env.go`: pass `e.config.LookaheadVersion` after `e.config.OracleObservation` in both
`encodeObservation` calls and every `emptyObservation` call. `internal/rl/searchpool.go`: pass
`env.config.LookaheadVersion` / `clone.env.config.LookaheadVersion` after the `false` oracle argument.
`internal/rl/observation_symmetry_test.go` and other tests: pass `0`.

Run: `go build ./... && go vet ./internal/rl`
Expected: clean.

- [ ] **Step 6: Run the new and existing tests**

Run: `go test ./internal/rl -count=1`
Expected: PASS, including every pre-existing test (version 0 untouched).

- [ ] **Step 7: Commit**

```bash
gofmt -l internal/rl
git add internal/rl/
git commit -m "feat(rl): discard/call look-ahead planes behind lookahead_version"
```

---

### Task 3: Go config plumbing and equivariance proof

**Files:**
- Modify: `internal/rl/env.go` (`normalizeConfig`, `Reset`, `GenerateHeuristicTrajectory` config copy at ~258)
- Modify: `internal/rl/searchpool.go` (`NewSearchPool` validation at ~147)
- Modify: `cmd/rlbridge/main.go` (`FHEnvPoolNew` at ~173)
- Modify: `internal/rl/observation_symmetry_test.go` (`assertEquivariant`, `TestObservationIsFaceSymmetryEquivariant`)
- Test: `internal/rl/lookahead_test.go`

**Interfaces:**
- Consumes: `validateLookaheadVersion`, `encodeObservation(..., lookahead, ...)` (Task 2).
- Produces: version-1 observations from `rl.New(config).Reset`, `NewEnvPool`, and the c-shared pool.

- [ ] **Step 1: Write the failing tests**

Append to `internal/rl/lookahead_test.go`:

```go
func TestEnvCarriesLookaheadVersion(t *testing.T) {
	config := &pb.EnvConfig{LearningSeats: []uint32{0, 1, 2, 3}, LookaheadVersion: 1}
	env := New(config)
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 7, Config: config})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}
	if reset.Observation.PlaneChannels != 52 {
		t.Fatalf("channels %d, want 52", reset.Observation.PlaneChannels)
	}
	bad := &pb.EnvConfig{LearningSeats: []uint32{0}, LookaheadVersion: 2}
	if _, err := New(bad).Reset(&pb.EnvResetRequest{Seed: 7, Config: bad}); err == nil {
		t.Fatalf("version 2 must be rejected at reset")
	}
}
```

In `observation_symmetry_test.go`, give `assertEquivariant` a `lookahead uint32` parameter, pass it to both
`encodeObservation` calls, and loop `for channel := 0; channel < int(original.PlaneChannels); channel++`. In
`TestObservationIsFaceSymmetryEquivariant`, call it for both versions inside the symmetry loop:

```go
			for _, sym := range symmetries {
				for _, lookahead := range []uint32{0, 1} {
					if assertEquivariant(t, env.game.State, seat, env.game.PublicEvents(), sym, lookahead) {
						tieBreaks++
					}
				}
			}
```

and update the coverage log's denominator to `checked*len(symmetries)*2`.

- [ ] **Step 2: Run them to verify they fail**

Run: `go test ./internal/rl -run 'EnvCarriesLookahead|FaceSymmetryEquivariant' -count=1`
Expected: `TestEnvCarriesLookaheadVersion` FAILS (channels 39: `normalizeConfig` drops the field).

- [ ] **Step 3: Implement**

`normalizeConfig` (env.go ~606): add `LookaheadVersion: config.LookaheadVersion,`. `Reset`, after the window
check:

```go
	if err := validateLookaheadVersion(e.config.LookaheadVersion); err != nil {
		return nil, err
	}
```

`GenerateHeuristicTrajectory` (env.go ~264): add `LookaheadVersion: config.LookaheadVersion,`.
`NewSearchPool` (searchpool.go, after the window check):

```go
	if err := validateLookaheadVersion(cfg.LookaheadVersion); err != nil {
		return nil, fmt.Errorf("search pool: %w", err)
	}
```

`FHEnvPoolNew` (cmd/rlbridge/main.go, after the window bound):

```go
	if request.GetConfig().GetLookaheadVersion() > rl.MaxLookaheadVersion {
		return 0
	}
```

- [ ] **Step 4: Run the Go suite**

Run: `go test ./internal/rl ./cmd/... -count=1`
Expected: PASS. The equivariance test now proves all 13 channels transform by the plain face map under every
tested symmetry (suit permutations, dragon permutations, rank reversal).

- [ ] **Step 5: Commit**

```bash
gofmt -l internal cmd
git add internal/rl/ cmd/rlbridge/
git commit -m "feat(rl): thread lookahead_version through env, pools and bridge; prove equivariance"
```

---

### Task 4: Python config, bridge and pool plumbing

**Files:**
- Modify: `ai/src/fh_mahjong_ai/config.py` (`EnvConfig`, `ModelConfig`)
- Modify: `ai/src/fh_mahjong_ai/bridge.py` (proto conversion ~359, `_decode_observation` ~400)
- Modify: `ai/src/fh_mahjong_ai/envpool.py` (proto conversion ~299, decode ~233, `make_selfplay_pool` ~338)
- Modify: `ai/src/fh_mahjong_ai/batched_b2b.py` (`_POOL_PASSTHROUGH_FIELDS`)
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (process-collector `EnvConfig` at ~990)
- Modify: `ai/src/fh_mahjong_ai/train_state.py` (`_LEGACY_ECHO_ADDITIONS`, `_LEGACY_ECHO_PINNED_VALUES`)
- Test: `ai/tests/test_lookahead_config.py` (create)

**Interfaces:**
- Produces: `EnvConfig.lookahead_version: int = 0`; `EnvConfig.policy_channels -> int` (property);
  `config.lookahead_plane_count(version: int) -> int`;
  `config.observation_plane_channels(oracle: bool, lookahead_version: int) -> int`;
  `ModelConfig.lookahead_version: int = 0`.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_lookahead_config.py`:

```python
import dataclasses
import os

import numpy as np
import pytest

from fh_mahjong_ai.config import EnvConfig, ModelConfig, observation_plane_channels

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")


def test_plane_shape_resolves_from_version():
    assert EnvConfig().plane_shape == (39, 42, 1)
    assert EnvConfig(oracle_observation=True).plane_shape == (51, 42, 1)
    assert EnvConfig(lookahead_version=1).plane_shape == (52, 42, 1)
    assert EnvConfig(lookahead_version=1, oracle_observation=True).plane_shape == (64, 42, 1)
    assert EnvConfig(lookahead_version=1).policy_channels == 52
    assert EnvConfig(oracle_observation=True).policy_channels == 39
    assert observation_plane_channels(True, 1) == 64


def test_replace_toggling_oracle_reresolves_version_one():
    base = EnvConfig(lookahead_version=1)
    assert dataclasses.replace(base, oracle_observation=True).plane_shape == (64, 42, 1)
    oracle = EnvConfig(lookahead_version=1, oracle_observation=True)
    assert dataclasses.replace(oracle, oracle_observation=False).plane_shape == (52, 42, 1)


def test_version_zero_keeps_explicit_shapes():
    assert EnvConfig(plane_shape=(51, 42, 1)).plane_shape == (51, 42, 1)
    assert EnvConfig(plane_shape=(2, 3, 1)).plane_shape == (2, 3, 1)


def test_bad_versions_and_shapes_raise():
    with pytest.raises(ValueError, match="lookahead_version"):
        EnvConfig(lookahead_version=2)
    with pytest.raises(ValueError, match="plane_shape"):
        EnvConfig(lookahead_version=1, plane_shape=(40, 42, 1))
    with pytest.raises(ValueError, match="lookahead_version"):
        ModelConfig(lookahead_version=3)


def test_legacy_resume_echo_reads_version_zero():
    from fh_mahjong_ai.ppo import PPOConfig
    from fh_mahjong_ai.train_state import _train_b2b_config_echo, _validate_resume_config_echo
    current = _train_b2b_config_echo(PPOConfig(), ModelConfig(), EnvConfig())
    legacy = {section: dict(values) for section, values in current.items()}
    del legacy["env_config"]["lookahead_version"]
    del legacy["model_config"]["lookahead_version"]
    _validate_resume_config_echo(current, legacy)  # admitted: legacy runs had no look-ahead
    changed = _train_b2b_config_echo(PPOConfig(), ModelConfig(lookahead_version=1),
                                     EnvConfig(lookahead_version=1))
    with pytest.raises(Exception, match="lookahead_version"):
        _validate_resume_config_echo(changed, current)


@requires_go_lib
def test_go_bridge_emits_version_one_planes():
    from fh_mahjong_ai.bridge import build_bridge
    from fh_mahjong_ai.env import MahjongEnv
    config = EnvConfig(bridge_kind="go", bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False, lookahead_version=1)
    observation = MahjongEnv(config, build_bridge(config)).reset(seed=5)
    assert observation.planes.shape == (52, 42, 1)
    assert np.any(observation.planes[39:52] != 0)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest -q ai/tests/test_lookahead_config.py`
Expected: FAIL — `ImportError: cannot import name 'observation_plane_channels'`.

- [ ] **Step 3: Implement `config.py`**

Module level, above `EnvConfig`:

```python
POLICY_BASE_CHANNELS = 39
ORACLE_CHANNELS = 12
MAX_LOOKAHEAD_VERSION = 1
_LOOKAHEAD_PLANE_COUNTS = {0: 0, 1: 13}  # mirrors internal/rl LookaheadPlaneCount


def _validate_lookahead_version(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= MAX_LOOKAHEAD_VERSION:
        raise ValueError(f"lookahead_version must be an int in [0, {MAX_LOOKAHEAD_VERSION}], got {value!r}")
    return value


def lookahead_plane_count(version: int) -> int:
    return _LOOKAHEAD_PLANE_COUNTS[_validate_lookahead_version(version)]


def observation_plane_channels(oracle: bool, lookahead_version: int) -> int:
    """39 public channels, the look-ahead block, then 12 oracle channels."""
    return POLICY_BASE_CHANNELS + lookahead_plane_count(lookahead_version) + (ORACLE_CHANNELS if oracle else 0)
```

In `EnvConfig`, add the field `lookahead_version: int = 0` after `event_history_window`, replace the oracle
resolution in `__post_init__` with:

```python
        _validate_lookahead_version(self.lookahead_version)
        expected = observation_plane_channels(self.oracle_observation, self.lookahead_version)
        shape = tuple(self.plane_shape)
        if self.lookahead_version == 0:
            # Version 0 keeps the historical rule: only the default resolves;
            # an explicit non-default plane_shape (e.g. a 51ch shape-inferred
            # oracle net) is respected.
            if shape == (POLICY_BASE_CHANNELS, 42, 1):
                self.plane_shape = (expected, 42, 1)
        else:
            # Any of this version's encoder shapes (or the 39ch default)
            # re-resolves, so dataclasses.replace() can toggle oracle mode.
            resolvable = {(POLICY_BASE_CHANNELS, 42, 1)} | {
                (observation_plane_channels(oracle, self.lookahead_version), 42, 1)
                for oracle in (False, True)}
            if shape not in resolvable:
                raise ValueError(f"plane_shape {shape} does not match lookahead_version "
                                 f"{self.lookahead_version} (expected {(expected, 42, 1)})")
            self.plane_shape = (expected, 42, 1)
```

and the property:

```python
    @property
    def policy_channels(self) -> int:
        """Channels the policy stem reads: public plus look-ahead, never oracle."""
        return POLICY_BASE_CHANNELS + lookahead_plane_count(self.lookahead_version)
```

In `ModelConfig`, add `lookahead_version: int = 0` (last field) and in `__post_init__`
`_validate_lookahead_version(self.lookahead_version)`.

- [ ] **Step 4: Implement the wire, pool and resume plumbing**

`bridge.py` and `envpool.py` proto conversions (beside `message.event_history_window = ...`):

```python
        message.lookahead_version = int(config.lookahead_version)
```

(`bridge.py` uses `self.config`.) In `bridge.py` `_decode_observation`, before the reshape:

```python
        if int(observation.plane_channels) != channels:
            raise BridgeError(
                f"bridge returned {int(observation.plane_channels)} plane channels but the client expects "
                f"{channels} (lookahead_version={int(self.config.lookahead_version)}) — the Go bridge "
                "library predates look-ahead planes; rebuild it (go build -buildmode=c-shared ./cmd/rlbridge)")
```

In `envpool.py` at the response decode (~233), after reading `channels`, the same check against
`self.env_config.plane_shape[0]` when rows > 0, raising `BridgeError` (import it from `.bridge` if not already).
In `make_selfplay_pool` add `lookahead_version=env_config.lookahead_version,`. In `batched_b2b.py` append
`"lookahead_version"` to `_POOL_PASSTHROUGH_FIELDS`. In `train_b2b.py`'s process-collector `EnvConfig(...)`
(~990–1003) add `lookahead_version=env_config.lookahead_version,`.

`train_state.py`: add `"lookahead_version",` to `_LEGACY_ECHO_ADDITIONS["model_config"]`, add a new
`"env_config": {"lookahead_version"}` section, and pin both to 0:

```python
_LEGACY_ECHO_PINNED_VALUES = {
    "ppo_config": { ...existing... },
    "model_config": {"lookahead_version": 0},  # no run before the field existed used look-ahead planes
    "env_config": {"lookahead_version": 0},
}
```

`_fill_legacy_echo_defaults` already reads both tables with `.get(section, ...)`, so the new `env_config`
section needs no other change.

- [ ] **Step 5: Run the tests**

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_lookahead_config.py ai/tests/test_b2b_collector_parity.py ai/tests/test_b2b_resume.py
```

Expected: PASS; the collector golden digests are unchanged.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/{config,bridge,envpool,batched_b2b,train_b2b,train_state}.py ai/tests/test_lookahead_config.py
git commit -m "feat(ai): lookahead_version in EnvConfig/ModelConfig, bridge, pools and resume echo"
```

---

### Task 5: Model, warm start and checkpoint loading

**Files:**
- Modify: `ai/src/fh_mahjong_ai/model.py` (`PolicyValueNet.__init__`, `_value_features`, `_reconstruct_env_config`,
  `_verify_metadata_matches_shapes`)
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (belief targets at ~461–468 and ~569)
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py` (`_b2b_model_env_config`, `build_b2b_model`)
- Modify: `ai/src/fh_mahjong_ai/serving.py` (`CheckpointPolicy.from_checkpoint_bytes`)
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (fail closed for version > 0)
- Test: `ai/tests/test_lookahead_model.py` (create)

**Interfaces:**
- Consumes: `EnvConfig.lookahead_version`, `EnvConfig.policy_channels`, `ModelConfig.lookahead_version` (Task 4).
- Produces: `PolicyValueNet.policy_channels == 39 + K`; `build_b2b_model(env_config, model_config, champion)`
  widening a version-0 init to version 1 with identical step-zero outputs.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_lookahead_model.py`:

```python
import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet, infer_model_config
from fh_mahjong_ai.storage import load_checkpoint, model_config_metadata, save_checkpoint
from fh_mahjong_ai.train_b2b import _b2b_model_env_config, build_b2b_model

B2B = dict(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)


def _init_checkpoint(tmp_path):
    env = EnvConfig(bridge_kind="mock")
    config = ModelConfig(**B2B)
    model = PolicyValueNet(env, config)
    path = tmp_path / "init.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(config)})
    return env, config, path


def _inputs(seed=0, batch=4):
    rng = np.random.default_rng(seed)
    public = torch.from_numpy(rng.random((batch, 39, 42, 1), dtype=np.float32))
    lookahead = torch.from_numpy(rng.random((batch, 13, 42, 1), dtype=np.float32))
    oracle = torch.from_numpy(rng.random((batch, 12, 42, 1), dtype=np.float32))
    scalars = torch.from_numpy(rng.random((batch, 58), dtype=np.float32))
    mask = torch.ones((batch, 204), dtype=torch.int8)
    events = torch.from_numpy(rng.integers(0, 0x10000, size=(batch, 8)).astype(np.int64))
    lengths = torch.full((batch,), 8, dtype=torch.int64)
    return public, lookahead, oracle, scalars, mask, events, lengths


def test_widened_warm_start_matches_init_at_step_zero(tmp_path):
    env0, config0, path = _init_checkpoint(tmp_path)
    init = PolicyValueNet(env0, config0)
    load_checkpoint(path, init)
    init.eval()
    env1 = _b2b_model_env_config(EnvConfig(bridge_kind="mock", oracle_observation=True, lookahead_version=1))
    assert env1.plane_shape == (52, 42, 1)
    model = build_b2b_model(env1, ModelConfig(**B2B, lookahead_version=1), path)
    assert model.policy_channels == 52
    public, lookahead, oracle, scalars, mask, events, lengths = _inputs()
    with torch.no_grad():
        ref_logits, ref_value = init(torch.cat([public, oracle], 1), scalars, mask, events, lengths)
        logits, value = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        ref_aux = init.aux_predictions(init.encode(torch.cat([public, oracle], 1), scalars, events, lengths))
        aux = model.aux_predictions(model.encode(torch.cat([public, lookahead, oracle], 1), scalars, events, lengths))
    assert torch.allclose(logits, ref_logits, atol=1e-5)
    assert torch.allclose(value, ref_value, atol=1e-5)
    for key in ref_aux:
        assert torch.allclose(aux[key], ref_aux[key], atol=1e-5), key
    assert torch.equal(logits.argmax(1), ref_logits.argmax(1))


def test_privileged_slice_follows_policy_channels():
    env1 = EnvConfig(bridge_kind="mock", lookahead_version=1)
    model = PolicyValueNet(env1, ModelConfig(**B2B, lookahead_version=1))
    model.eval()
    public, lookahead, oracle, scalars, mask, events, lengths = _inputs(seed=1)
    with torch.no_grad():
        _, va = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        _, vb = model(torch.cat([public, lookahead, torch.rand_like(oracle)], 1), scalars, mask, events, lengths)
        la, _ = model(torch.cat([public, lookahead, oracle], 1), scalars, mask, events, lengths)
        lb, _ = model(torch.cat([public, torch.rand_like(lookahead), oracle], 1), scalars, mask, events, lengths)
    assert not torch.allclose(va, vb)  # value reads channels 52-63
    assert not torch.allclose(la, lb)  # the policy reads the look-ahead block


def test_env_and_model_versions_must_agree(tmp_path):
    with pytest.raises(ValueError, match="lookahead_version"):
        PolicyValueNet(EnvConfig(), ModelConfig(**B2B, lookahead_version=1))
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    payload = torch.load(path, map_location="cpu")
    assert infer_model_config(payload["model"], payload["metadata"]).lookahead_version == 1
    stripped = dict(payload["metadata"]["model_config"], lookahead_version=0)
    with pytest.raises(Exception):
        PolicyValueNet(EnvConfig(), infer_model_config(payload["model"], {"model_config": stripped}))\
            .load_state_dict(payload["model"])


def test_serving_loader_builds_version_one_models(tmp_path):
    from fh_mahjong_ai.serving import CheckpointPolicy
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    loaded = CheckpointPolicy.from_checkpoint(path)
    assert loaded.model.policy_channels == 52
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest -q ai/tests/test_lookahead_model.py`
Expected: FAIL — `build_b2b_model` raises "architecturally incompatible" (`plane_stem.0.weight` skipped) and the
version-agreement test does not raise.

- [ ] **Step 3: Implement the model changes**

`PolicyValueNet.__init__`, right after `channels, height, width = env_config.plane_shape`:

```python
        env_version = int(getattr(env_config, "lookahead_version", 0))
        if env_version != model_config.lookahead_version:
            raise ValueError(
                f"env lookahead_version {env_version} != model lookahead_version "
                f"{model_config.lookahead_version}: build the EnvConfig with the checkpoint's version")
```

Change the comment on `self.policy_channels = channels` to `# public + look-ahead channels; oracle planes follow`.
`_value_features`:

```python
        start = self.policy_channels
        if planes.shape[1] >= start + 12:
            priv = self.privileged_encoder(planes[:, start : start + 12])
```

`_reconstruct_env_config`: add `lookahead_version=model_config.lookahead_version,` to the returned `EnvConfig`.
`_verify_metadata_matches_shapes`: add

```python
    if config.lookahead_version > 0:
        expected = observation_plane_channels(False, config.lookahead_version)
        got = int(state_dict["plane_stem.0.weight"].shape[1])
        if got != expected:
            raise RuntimeError(f"metadata lookahead_version {config.lookahead_version} needs a "
                               f"{expected}-channel stem, checkpoint has {got}")
```

(import `observation_plane_channels` from `.config`).

`ppo.py`: in both belief-target sites use the model's offset:

```python
    pc = int(getattr(model, "policy_channels", 39))
    ...
        if plane_channels < pc + 12:
            raise ValueError(
                f"model has aux_heads enabled but planes have only {plane_channels} channels "
                f"(need {pc + 12} for the belief-target oracle-threshold planes {pc}:{pc + 12}); "
                "this would silently compute wrong belief targets.")
        if not host_transfer:
            belief_target = (planes[:, pc : pc + 12] > 0).float().squeeze(-1)
```

and `(mb["planes"][:, pc : pc + 12] > 0)` in the minibatch path.

`serving.py` `from_checkpoint_bytes`:

```python
        config = infer_model_config(saved_state, metadata)
        model = PolicyValueNet(EnvConfig(lookahead_version=config.lookahead_version), config)
```

`oracle.py`: at the top of `build_oracle_model` and `extract_deployable_student` (and the feature-dropout helper
that uses `oracle_lo, oracle_hi = 39, 51`), raise
`ValueError("the oracle feature-dropout pipeline supports lookahead_version 0 only")` when the passed
config's `lookahead_version` is non-zero.

- [ ] **Step 4: Implement the warm start**

`_b2b_model_env_config`: add `lookahead_version=env_config.lookahead_version,`. In `build_b2b_model`, widen the
surgical set and repair the stem:

```python
    payload = torch.load(Path(champion_checkpoint), map_location="cpu")
    old_stem_w = payload["model"]["plane_stem.0.weight"]    # [C, 39(+K0), 3, kw]
    widen_stem = old_stem_w.shape[1] != model.plane_stem[0].weight.shape[1]
    if widen_stem and old_stem_w.shape[1] > model.plane_stem[0].weight.shape[1]:
        raise RuntimeError("init checkpoint has more stem channels than the model; "
                           "narrowing a look-ahead net is not supported")
    surgical = {"trunk.0.weight", "value_head.0.weight"} | ({"plane_stem.0.weight"} if widen_stem else set())
```

and inside the existing `with torch.no_grad():` block:

```python
        if widen_stem:
            sw = model.plane_stem[0].weight                 # [C, 39+K, 3, kw]
            sw.zero_()
            sw[:, : old_stem_w.shape[1]].copy_(old_stem_w.to(sw.device))
```

Update the docstring: "The plane stem keeps the init's input columns; a look-ahead model's extra columns start at
zero, so step-zero outputs equal the init's."

- [ ] **Step 5: Run the tests**

```bash
uv run --project ai pytest -q ai/tests/test_lookahead_model.py ai/tests/test_b2b_model.py ai/tests/test_b2b_training.py ai/tests/test_model.py ai/tests/test_serving.py ai/tests/test_ppo*.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/{model,ppo,train_b2b,serving,oracle}.py ai/tests/test_lookahead_model.py
git commit -m "feat(ai): look-ahead stem widening with exact step-zero parity; policy_channels-relative slices"
```

---

### Task 6: Training CLI

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/train_b2b.py`
- Test: `ai/tests/test_lookahead_config.py` (append)

**Interfaces:**
- Consumes: Tasks 4–5.
- Produces: `fh-mj-train-b2b --lookahead-version {0,1}`.

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_lookahead_config.py`:

```python
def test_train_cli_threads_lookahead_version(monkeypatch, tmp_path):
    import fh_mahjong_ai.scripts.train_b2b as cli
    seen = {}
    monkeypatch.setattr(cli, "train_b2b", lambda **kwargs: seen.update(kwargs))
    monkeypatch.setattr("sys.argv", [
        "fh-mj-train-b2b", "--champion", str(tmp_path / "init.pt"),
        "--checkpoint-dir", str(tmp_path / "ckpt"), "--event-window", "8",
        "--lookahead-version", "1", "--bridge-kind", "mock"])
    cli.main()
    assert seen["env_config"].lookahead_version == 1
    assert seen["env_config"].plane_shape == (64, 42, 1)
    assert seen["model_config"].lookahead_version == 1
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --project ai pytest -q ai/tests/test_lookahead_config.py -k train_cli`
Expected: FAIL — `unrecognized arguments: --lookahead-version 1`.

- [ ] **Step 3: Implement**

Beside `--suit-augment`:

```python
    p.add_argument("--lookahead-version", type=int, choices=(0, 1), default=0,
                   help="per-action look-ahead planes (0 = none; 1 = 13 discard/call channels, "
                        "worklog/specs/20261004-discard-call-lookahead-planes.md); "
                        "rejected-on-change at resume")
```

Add `lookahead_version=args.lookahead_version` to the `EnvConfig(...)` call and to the `replace(base_model_config, ...)`
call.

- [ ] **Step 4: Run it**

Run: `uv run --project ai pytest -q ai/tests/test_lookahead_config.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/train_b2b.py ai/tests/test_lookahead_config.py
git commit -m "feat(ai): fh-mj-train-b2b --lookahead-version"
```

---

### Task 7: Evaluation, reports, compare and benchmark

**Files:**
- Modify: `ai/src/fh_mahjong_ai/storage.py` (new `checkpoint_lookahead_version`)
- Modify: `ai/src/fh_mahjong_ai/scripts/evaluate.py`
- Modify: `ai/src/fh_mahjong_ai/batched_eval.py` (`evaluate_duplicate_seats_batched`)
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (`aggregate_duplicate_seat_reports` ~1408, report dict ~1289)
- Modify: `ai/src/fh_mahjong_ai/scripts/compare_reports.py`
- Modify: `ai/src/fh_mahjong_ai/scripts/benchmark.py` (~170, ~196, ~379)
- Test: `ai/tests/test_compare_reports.py` (append), `ai/tests/test_lookahead_eval.py` (create)

**Interfaces:**
- Consumes: Tasks 4–6.
- Produces: `storage.checkpoint_lookahead_version(path: Path) -> int`;
  `evaluate_duplicate_seats_batched(..., lookahead_version: int = 0)`;
  `aggregate_duplicate_seat_reports(..., lookahead_version: int = 0)`; report key `"lookahead_version"`;
  `paired_comparison(..., allow_lookahead_mismatch: bool = False)` and `--allow-lookahead-mismatch`;
  result key `"lookahead_check"`.

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_compare_reports.py` (it already defines `make_report(seeds, per_seed_means, ...)` and
imports `paired_comparison`):

```python
def test_lookahead_mismatch_refused_unless_allowed():
    a = make_report([1, 2, 3], [0.2, 0.4, 0.1])
    b = make_report([1, 2, 3], [0.1, 0.3, 0.0])
    a["lookahead_version"], b["lookahead_version"] = 1, 0
    with pytest.raises(ValueError, match="lookahead_version"):
        paired_comparison(a, b)
    result = paired_comparison(a, b, allow_lookahead_mismatch=True)
    assert result["lookahead_check"] == "mismatch-allowed"
    b["lookahead_version"] = 1
    assert paired_comparison(a, b)["lookahead_check"] == "match"
```

Create `ai/tests/test_lookahead_eval.py`:

```python
import os

import pytest

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import checkpoint_lookahead_version, model_config_metadata, save_checkpoint

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")
B2B = dict(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)


def _v1_checkpoint(tmp_path):
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**B2B, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    return model, path


def test_checkpoint_lookahead_version_reads_metadata(tmp_path):
    _, path = _v1_checkpoint(tmp_path)
    assert checkpoint_lookahead_version(path) == 1
    legacy = tmp_path / "legacy.pt"
    save_checkpoint(legacy, PolicyValueNet(EnvConfig(), ModelConfig(**SMALL_MODEL)))
    assert checkpoint_lookahead_version(legacy) == 0


@requires_go_lib
def test_batched_eval_runs_and_records_version(tmp_path):
    from fh_mahjong_ai.batched_eval import evaluate_duplicate_seats_batched
    model, _ = _v1_checkpoint(tmp_path)
    report = evaluate_duplicate_seats_batched(
        model, seeds=[1, 2], bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
        match_mode="chongci", chongci_max_hands=2, max_steps_per_episode=4000,
        event_history_window=8, lookahead_version=1, slots=2)
    assert report["lookahead_version"] == 1
    with pytest.raises(ValueError, match="lookahead"):
        evaluate_duplicate_seats_batched(
            model, seeds=[1], bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
            event_history_window=8, lookahead_version=0, slots=1)
```

- [ ] **Step 2: Run them to verify they fail**

```bash
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_lookahead_eval.py ai/tests/test_compare_reports.py -k "lookahead"
```

Expected: FAIL — `ImportError: checkpoint_lookahead_version`; `paired_comparison() got an unexpected keyword`.

- [ ] **Step 3: Implement reports and compare**

`storage.py`:

```python
def checkpoint_lookahead_version(path: Path) -> int:
    """The look-ahead version a checkpoint was trained with (0 when its metadata predates the field)."""
    payload = torch.load(Path(path), map_location="cpu")
    model_config = (payload.get("metadata") or {}).get("model_config") or {}
    return int(model_config.get("lookahead_version", 0))
```

`evaluate.py`: add `lookahead_version: int = 0` as a keyword parameter of `aggregate_duplicate_seat_reports` and of
the function owning the report dict at ~1289 (thread `0` from its callers), and write
`"lookahead_version": lookahead_version,` after `"event_history_window"` in both dicts.

`batched_eval.py` `evaluate_duplicate_seats_batched`: add `lookahead_version: int = 0`; after the window check:

```python
    model_version = int(getattr(getattr(model, "model_config", None), "lookahead_version", 0) or 0)
    if model_version != int(lookahead_version):
        raise ValueError(f"model lookahead_version {model_version} != lookahead_version {lookahead_version}")
```

pass `lookahead_version=int(lookahead_version)` into the per-seat `EnvConfig(...)` and into
`aggregate_duplicate_seat_reports(...)`.

`compare_reports.py`: append `"lookahead_version",` to `_COMPAT_KEYS` with the comment
`# Look-ahead planes on vs off is a different observation protocol.`; add `allow_lookahead_mismatch: bool = False`
to `_check_comparable` and `paired_comparison` beside `allow_window_mismatch`; in the mismatch loop:

```python
            if key == "lookahead_version" and allow_lookahead_mismatch:
                continue  # the look-ahead lap's primary comparison; labeled, not silent
```

with hint `" — pass --allow-lookahead-mismatch when the look-ahead planes are the intervention under test"`;
the result key

```python
        "lookahead_check": (
            "mismatch-allowed"
            if report_a.get("lookahead_version", 0) != report_b.get("lookahead_version", 0)
            else "match"
        ),
```

the CLI flag mirroring `--allow-window-mismatch`, and a printed line `lookahead check: <value>` wherever the
text output prints the window check.

- [ ] **Step 4: Implement the evaluate CLI and benchmark**

`scripts/evaluate.py`: add `--lookahead-version` (`type=int`, `default=None`, help "defaults to the checkpoint's;
an explicit value that disagrees is an error"). After `model_config = replace(model_config_from_args(args), ...)`:

```python
    from fh_mahjong_ai.storage import checkpoint_lookahead_version
    lookahead_version = checkpoint_lookahead_version(args.checkpoint)
    if args.lookahead_version is not None and args.lookahead_version != lookahead_version:
        parser.error(f"--lookahead-version {args.lookahead_version} disagrees with the checkpoint's "
                     f"lookahead_version {lookahead_version}")
    if lookahead_version > 0 and not (args.duplicate_seats and args.batched_eval_slots > 0
                                      and args.opponent_checkpoint is None and not args.ensemble_checkpoint
                                      and not args.from_oracle and not args.search):
        parser.error("look-ahead checkpoints are supported only by the batched duplicate-seat evaluator")
    model_config = replace(model_config, lookahead_version=lookahead_version)
```

Build the model with `EnvConfig(oracle_observation=args.oracle, lookahead_version=lookahead_version)` and pass
`lookahead_version=lookahead_version` to the `evaluate_duplicate_seats_batched(...)` call (~557).

`scripts/benchmark.py`: after loading the candidate model (~170), read
`version = int(model.model_config.lookahead_version)`; load the opponent's the same way and `raise SystemExit`
if the two differ ("candidate and opponents must share lookahead_version: the env encodes one observation for
all seats"); pass `lookahead_version=version` to both `EnvConfig(...)` constructions (~196, ~379; carry it through
`_WORKER` like `event_window`).

- [ ] **Step 5: Run the tests**

```bash
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_lookahead_eval.py ai/tests/test_compare_reports.py ai/tests/test_batched_eval*.py ai/tests/test_evaluate*.py ai/tests/test_benchmark*.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/{storage,evaluate,batched_eval}.py ai/src/fh_mahjong_ai/scripts/{evaluate,compare_reports,benchmark}.py ai/tests/
git commit -m "feat(ai): batched eval, reports, compare and benchmark carry lookahead_version"
```

---

### Task 8: Serving refuses look-ahead checkpoints

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/serve_policy.py` (startup ~1072, `reload` ~394)
- Test: `ai/tests/test_serve_policy.py` (append)

**Interfaces:**
- Produces: `serve_policy._require_servable(policy) -> None` raising `RuntimeError` for version > 0.

- [ ] **Step 1: Write the failing test**

```python
def test_serving_refuses_lookahead_checkpoints(tmp_path):
    from conftest import SMALL_MODEL
    from fh_mahjong_ai.config import EnvConfig, ModelConfig
    from fh_mahjong_ai.model import PolicyValueNet
    from fh_mahjong_ai.scripts.serve_policy import _require_servable
    from fh_mahjong_ai.serving import CheckpointPolicy
    from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
    model = PolicyValueNet(EnvConfig(lookahead_version=1), ModelConfig(**SMALL_MODEL, lookahead_version=1))
    path = tmp_path / "v1.pt"
    save_checkpoint(path, model, metadata={"model_config": model_config_metadata(model.model_config)})
    with pytest.raises(RuntimeError, match="look-ahead"):
        _require_servable(CheckpointPolicy.from_checkpoint(path))
```

Also extend the file's existing reload test pattern (find the test that reloads a second checkpoint): a reload to
a version-1 checkpoint must raise and leave the serving policy unchanged.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --project ai pytest -q ai/tests/test_serve_policy.py -k lookahead`
Expected: FAIL — `ImportError: cannot import name '_require_servable'`.

- [ ] **Step 3: Implement**

```python
def _require_servable(policy) -> None:
    """The backend sends 39 public planes; a look-ahead checkpoint needs planes it never requests."""
    version = int(getattr(policy.model.model_config, "lookahead_version", 0) or 0)
    if version > 0:
        raise RuntimeError(
            f"checkpoint uses look-ahead planes (lookahead_version={version}); serving supports 0 only "
            "until the backend requests them (worklog/specs/20261004-discard-call-lookahead-planes.md)")
```

Call it on the startup policy right after `load_policy_from_manifest_with_hash(...)` and on `new_policy` in
`reload` before the swap (beside the event-window validation, so a refused reload keeps the old policy).

- [ ] **Step 4: Run the serving tests**

Run: `uv run --project ai pytest -q ai/tests/test_serve_policy.py ai/tests/test_serve_policy_evaluate.py ai/tests/test_serving*.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/serve_policy.py ai/tests/test_serve_policy.py
git commit -m "feat(ai): serving refuses look-ahead checkpoints"
```

---

### Task 9: Docs, CI gates and PR

**Files:**
- Modify: `internal/rl/CLAUDE.md`, `ai/CLAUDE.md` (or `ai/src/fh_mahjong_ai/CLAUDE.md`, whichever lists modules
  and flags), `ai/MODULES.md` if it lists `fh-mj-train-b2b`/`fh-mj-compare` flags, `cmd/rlbridge/CLAUDE.md`

- [ ] **Step 1: Document**

`internal/rl/CLAUDE.md`: add `lookahead.go` — "version-1 look-ahead block (13 channels after the 39 public ones;
oracle planes follow); chii features in the sequence's middle face; `MaxLookaheadVersion`". AI docs: the
`--lookahead-version` training flag, `EnvConfig.lookahead_version`/`policy_channels`, the batched-only evaluator
support, `fh-mj-compare --allow-lookahead-mismatch`, and serving's refusal.

- [ ] **Step 2: Run every CI gate**

```bash
gofmt -l .
go vet ./...
go test ./...
(cd web && npx tsc && npx vitest run)
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests
```

Expected: `gofmt` prints nothing; everything else passes.

- [ ] **Step 3: Commit, push, open the PR**

```bash
git add -A internal/rl/CLAUDE.md ai/ cmd/rlbridge/CLAUDE.md
git commit -m "docs: look-ahead planes"
git push -u origin feat/lookahead-planes
gh pr create --title "feat: discard/call look-ahead planes (lookahead_version 1)" --body-file <(printf '%s\n' \
  "Implements worklog/specs/20261004-discard-call-lookahead-planes.md: 13 per-face look-ahead channels behind EnvConfig.lookahead_version, dormant and byte-identical at 0." \
  "" "Gates: gofmt, go vet, go test, tsc, vitest, full ai pytest (with the bridge)." "" \
  "🤖 Generated with [Claude Code](https://claude.com/claude-code)")
```

---

## After merge (operational; not code)

Recorded in the spec's pre-launch section before launch; nothing here changes the protocol.

1. On the box, a fresh checkout `/root/fh-mahjong-lookahead` at the merge commit; verify it descends from
   `6c354655` and `785b3b85`; build `build/libfh_mahjong_bridge.so`; `uv sync --project ai`.
2. Init: control `iter_150` (`ea6d4d41`, `/root/fh-mahjong-runs/suit-distill-20261002/control/ckpt/iter_150.pt`); verify its sha256 before launch.
3. Step-zero parity on the real init: build the version-1 model with `build_b2b_model` and compare logits, values,
   aux outputs and greedy actions against the init on one real 320-match collection's rows (all within 1e-5;
   greedy actions identical).
4. Pace: three iterations of each arm, one at a time. If features-arm collection exceeds 1.5× the control's, stop
   and report.
5. Message GPU peers (perf-improve) before each arm. Launch the features arm, then the control arm, never side by
   side: the `distill_lap.sh` shape with `--lookahead-version 1` / `0`, `--base-seed 3210000`, 150 iterations,
   the recipe row of the spec, then the three evaluations on 3,260,000–3,269,999 (10,000 × 4) and
   `fh-mj-compare --allow-lookahead-mismatch` for features-vs-control and features-vs-init.
