# Route Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `fh-mj-benchmark --route-study` records, for every seat at the strong table, route shanten at the deal, discard forks between Independence and the standard hand, and chii/pon offers, then prints human-readable charts.

**Architecture:** A read-only Go `Env.RouteProbe` (exported as `FHEnvRouteProbe`) reports a seat's shanten per route and after each legal discard, reusing `shanten.AnalyzeHand`. A Python `RouteStudyRecorder` calls it at every decision inside `evaluate_policy_online`, classifies forks and call offers, emits hand records at each round outcome, keeps summable aggregates, and streams raw records to a gzip JSONL shard. The benchmark adds a flag, one shard per chunk, merging, and charts.

**Tech Stack:** Go 1.25, protobuf (Go/TS/Python bindings), cgo c-shared bridge, Python 3.12 via uv, pytest.

**Spec:** `../specs/20261002-route-study-design.md`

## Global Constraints

- Work in worktree `/Users/plasma/fh-mahjong/.claude/worktrees/route-study`, branch `feat/route-study` (stacked on PR #266 / `feat/benchmark-opponent`). All paths below are relative to it.
- Routes are exactly `standard`, `seven_pairs`, `independence`; `99` = unavailable (seat has an open meld).
- Sides are the benchmark's existing `learner` / `opponents` (`hand_stats.WIN_PATTERN_SIDES`).
- With the flag off, `evaluate_policy_online` and the benchmark JSON are unchanged (no new keys).
- `RouteProbe` never mutates the game.
- Proto changes regenerate Go, TS **and** Python bindings. Python bindings must be generated with **protoc 33.5** (header `Protobuf Python Version: 6.33.5`) to match the 6.33 runtime; Go uses the local protoc.
- `internal/engine` must never import `internal/rules` (untouched here; `internal/rl` may import `internal/rules/shanten`, as it already does).
- Every changed directory updates its `CLAUDE.md` (never replace an `AGENTS.md` symlink); Python modules are documented in `ai/MODULES.md`.
- CI gates before the PR: `gofmt -l .` prints nothing, `go vet ./...`, `go test ./...`, `cd web && npx tsc && npx vitest run`, plus `uv run --project ai pytest ai/tests`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Seat 0 probe.** `RouteProbeRequest{seat: 0}` serializes to zero bytes, so the C call gets a null pointer and length 0; the probe must still answer for seat 0 (Task 2 fake-lib and real-lib tests).
2. **Flower wilds in the closed hand.** A wild flower is a legal discard with face index 34+; the probe must map it, not fail with "legal discard has no shanten option" (Task 1 test).
3. **A seat that never reaches a discard decision in a hand** (hand ends on an early ron, or the seat called first) must count in `hands_without_deal` or the `-` bucket, never crash or enter the deal chart (Task 3 tests).
4. **Truncated match mid-hand.** The open hand is dropped and counted in `truncated_hands`, never emitted as a hand record (Task 3 test).
5. **Stale outputs.** A bridge library built before this change must still load for everything else, failing only on `route_probe` with a rebuild hint (Task 2 test); a non-empty route-study directory from an earlier run must be refused rather than mixed (Task 6 test).

---

### Task 1: Proto messages and Go `Env.RouteProbe` through the bridge

**Files:**
- Modify: `proto/game.proto` (after `message BranchEvaluationResponse`)
- Regenerate: `proto/game.pb.go`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`
- Create: `internal/rl/route_probe.go`
- Create: `internal/rl/route_probe_test.go`
- Modify: `cmd/rlbridge/main.go` (new export after `FHEnvEvaluateBranches`)
- Docs: `proto/CLAUDE.md`, `internal/rl/CLAUDE.md`, `cmd/rlbridge/CLAUDE.md`

**Interfaces:**
- Produces: proto `RouteShanten{overall, standard, seven_pairs, independence: int32}`, `DiscardRoute{action_id: uint32, after: RouteShanten, is_wild: bool}`, `RouteProbeRequest{seat: uint32}`, `RouteProbe{seat: uint32, routes: RouteShanten, discards: repeated DiscardRoute, wild_count: uint32, open_meld_count: uint32}`; Go `func (e *Env) RouteProbe(request *pb.RouteProbeRequest) (*pb.RouteProbe, error)`; C export `FHEnvRouteProbe(handle uint64, requestPtr *char, requestLen int) FHBytesResult`.

- [ ] **Step 1: Add the proto messages**

Insert after `message BranchEvaluationResponse { ... }` in `proto/game.proto`:

```proto
// Route study (worklog/specs/20261002-route-study-design.md): a seat's shanten
// per hand route, read from the live env without changing it. 99 = route
// unavailable (the seat has an open meld).
message RouteShanten {
  int32 overall = 1;
  int32 standard = 2;
  int32 seven_pairs = 3;
  int32 independence = 4;
}

message DiscardRoute {
  uint32 action_id = 1;   // DISCARD_BASE + 42-face index
  RouteShanten after = 2; // route shanten of the 13 tiles left
  bool is_wild = 3;
}

message RouteProbeRequest {
  uint32 seat = 1;
}

message RouteProbe {
  uint32 seat = 1;
  RouteShanten routes = 2;
  repeated DiscardRoute discards = 3; // one per legal discard action; empty if none
  uint32 wild_count = 4;
  uint32 open_meld_count = 5;
}
```

- [ ] **Step 2: Regenerate all three bindings**

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto

P=/private/tmp/claude-501/-Users-plasma-fh-mahjong/e00b8634-49f3-47fd-baa0-551da589601e/scratchpad/protoc-33.5
[ -x $P/bin/protoc ] || { mkdir -p $P && curl -sSL -o $P.zip https://github.com/protocolbuffers/protobuf/releases/download/v33.5/protoc-33.5-osx-aarch_64.zip && unzip -q -o $P.zip -d $P; }
$P/bin/protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
head -3 ai/src/fh_mahjong_ai/generated/proto/game_pb2.py   # must say: Protobuf Python Version: 6.33.5

N=/Users/plasma/fh-mahjong/web/node_modules/.bin
$N/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
$N/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
git diff --stat   # only the four generated files + game.proto
```

Expected: `game_pb2.py` header says 6.33.5; `go build ./...` succeeds.

- [ ] **Step 3: Write the failing Go tests**

Create `internal/rl/route_probe_test.go`:

```go
package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

var routeTestSuits = map[byte]pb.Suit{
	'm': pb.Suit_SUIT_MAN, 'p': pb.Suit_SUIT_PIN, 's': pb.Suit_SUIT_SOU,
	'z': pb.Suit_SUIT_JIHAI, 'f': pb.Suit_SUIT_FLOWER,
}

// routeTestTiles parses "1m4m7m1z" into tiles with distinct ids.
func routeTestTiles(t *testing.T, faces string) []*pb.Tile {
	t.Helper()
	if len(faces)%2 != 0 {
		t.Fatalf("bad faces %q", faces)
	}
	out := make([]*pb.Tile, 0, len(faces)/2)
	for i := 0; i < len(faces); i += 2 {
		suit, ok := routeTestSuits[faces[i+1]]
		if !ok {
			t.Fatalf("bad suit in %q", faces)
		}
		out = append(out, &pb.Tile{Id: uint32(1000 + i), Suit: suit, Value: uint32(faces[i] - '0')})
	}
	return out
}

func routeTestDiscardID(t *testing.T, face string) uint32 {
	t.Helper()
	index, ok := tileFaceIndex42(routeTestTiles(t, face)[0])
	if !ok {
		t.Fatalf("no face index for %s", face)
	}
	return uint32(DiscardBase + index)
}

// discardTurnState is a minimal PLAYER_TURN state where seat 0 must discard.
func discardTurnState(hand []*pb.Tile, wilds []*pb.Tile, openMelds int) *pb.GameState {
	melds := make([]*pb.Meld, openMelds)
	for i := range melds {
		melds[i] = &pb.Meld{}
	}
	return &pb.GameState{
		Phase:        pb.GamePhase_PHASE_PLAYER_TURN,
		ActivePlayer: 0,
		WildTiles:    wilds,
		Players: []*pb.PlayerState{
			{ClosedHand: hand, OpenMelds: melds,
				ValidActions: []*pb.PlayerAction{{Type: pb.ActionType_ACTION_DISCARD}}},
			{}, {}, {},
		},
	}
}

func afterByAction(probe *pb.RouteProbe) map[uint32]*pb.RouteShanten {
	out := make(map[uint32]*pb.RouteShanten, len(probe.Discards))
	for _, d := range probe.Discards {
		out[d.ActionId] = d.After
	}
	return out
}

func TestRouteProbeIndependenceShape(t *testing.T) {
	// 13 independent tiles plus 2m, which conflicts with 1m and 4m.
	hand := routeTestTiles(t, "1m2m4m7m2p5p8p3s6s9s1z2z3z4z")
	probe, err := routeProbe(discardTurnState(hand, nil, 0), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	want := shanten.AnalyzeHand(hand, 0, nil).Routes
	if probe.Routes.Independence != 0 || probe.Routes.Standard != int32(want.Standard) ||
		probe.Routes.SevenPairs != int32(want.SevenPairs) || probe.Routes.Overall != int32(want.Overall) {
		t.Fatalf("routes %v, want independence 0 and %+v", probe.Routes, want)
	}
	if len(probe.Discards) != 14 {
		t.Fatalf("want 14 discard options (14 distinct faces), got %d", len(probe.Discards))
	}
	after := afterByAction(probe)
	for face, wantIndependence := range map[string]int32{"2m": 0, "1m": 1, "4m": 1, "7m": 1, "1z": 1} {
		if got := after[routeTestDiscardID(t, face)].Independence; got != wantIndependence {
			t.Errorf("after %s: independence %d, want %d", face, got, wantIndependence)
		}
	}
	if probe.WildCount != 0 || probe.OpenMeldCount != 0 || probe.Seat != 0 {
		t.Fatalf("wild/open/seat = %d/%d/%d", probe.WildCount, probe.OpenMeldCount, probe.Seat)
	}
}

func TestRouteProbeCountsWildsAndFlagsWildDiscards(t *testing.T) {
	// 7z is wild; a wild flower (1f with 2f as the indicator's group) sits in hand too.
	hand := routeTestTiles(t, "1m4m7m2p5p8p3s6s9s1z2z3z7z1f")
	wilds := routeTestTiles(t, "7z1f")
	probe, err := routeProbe(discardTurnState(hand, wilds, 0), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if probe.WildCount != 2 {
		t.Fatalf("wild count %d, want 2", probe.WildCount)
	}
	wildIDs := map[uint32]bool{routeTestDiscardID(t, "7z"): true, routeTestDiscardID(t, "1f"): true}
	for _, d := range probe.Discards {
		if d.IsWild != wildIDs[d.ActionId] {
			t.Errorf("action %d: is_wild %v", d.ActionId, d.IsWild)
		}
	}
	if _, ok := afterByAction(probe)[routeTestDiscardID(t, "1f")]; !ok {
		t.Fatalf("flower wild discard missing from probe")
	}
}

func TestRouteProbeOpenMeldMakesClosedRoutesUnavailable(t *testing.T) {
	hand := routeTestTiles(t, "1m4m7m2p5p8p3s6s9s1z2z")
	probe, err := routeProbe(discardTurnState(hand, nil, 1), 0)
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if probe.Routes.Independence != shanten.RouteUnavailable || probe.Routes.SevenPairs != shanten.RouteUnavailable {
		t.Fatalf("closed routes should be unavailable: %v", probe.Routes)
	}
	if probe.OpenMeldCount != 1 {
		t.Fatalf("open meld count %d", probe.OpenMeldCount)
	}
}

func TestEnvRouteProbeMatchesLegalDiscardsAndLeavesStateUnchanged(t *testing.T) {
	config := &pb.EnvConfig{LearningSeats: []uint32{0, 1, 2, 3}, MaxDecisions: 512}
	env := New(config)
	if _, err := env.RouteProbe(&pb.RouteProbeRequest{}); err == nil {
		t.Fatalf("probe before reset should fail")
	}
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 71, Config: config})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}
	seat := reset.Observation.Seat
	before := proto.Clone(env.game.State).(*pb.GameState)
	probe, err := env.RouteProbe(&pb.RouteProbeRequest{Seat: seat})
	if err != nil {
		t.Fatalf("probe: %v", err)
	}
	if !proto.Equal(before, env.game.State) {
		t.Fatalf("route probe mutated the game state")
	}
	legal, err := legalActionMap(env.game.State, seat)
	if err != nil {
		t.Fatalf("legal: %v", err)
	}
	var want []uint32
	for _, id := range SortedLegalIDs(legal) {
		if id >= DiscardBase && id < DiscardBase+DiscardCount {
			want = append(want, uint32(id))
		}
	}
	if len(want) == 0 {
		t.Fatalf("premise: first decision of seed 71 has no discard")
	}
	var got []uint32
	for _, d := range probe.Discards {
		got = append(got, d.ActionId)
	}
	if len(got) != len(want) {
		t.Fatalf("discard ids %v, want %v", got, want)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("discard ids %v, want %v", got, want)
		}
	}
	other, err := env.RouteProbe(&pb.RouteProbeRequest{Seat: (seat + 1) % 4})
	if err != nil {
		t.Fatalf("probe other seat: %v", err)
	}
	if len(other.Discards) != 0 {
		t.Fatalf("a seat without a discard action should have no discard routes")
	}
}
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `go test ./internal/rl -run 'RouteProbe' -count=1`
Expected: compile failure — `undefined: routeProbe` / `env.RouteProbe undefined`.

- [ ] **Step 5: Implement the probe**

Create `internal/rl/route_probe.go`:

```go
package rl

import (
	"fmt"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

// RouteProbe reports a seat's shanten on each hand route and, for every legal
// discard, the route shanten after it — the route study's view of a decision
// (worklog/specs/20261002-route-study-design.md). It only reads the live state.
func (e *Env) RouteProbe(request *pb.RouteProbeRequest) (*pb.RouteProbe, error) {
	if e.game == nil || e.game.State == nil {
		return nil, fmt.Errorf("environment must be reset before probing routes")
	}
	return routeProbe(e.game.State, request.GetSeat())
}

func routeProbe(state *pb.GameState, seat uint32) (*pb.RouteProbe, error) {
	if int(seat) >= len(state.Players) {
		return nil, fmt.Errorf("invalid seat %d", seat)
	}
	player := state.Players[seat]
	analysis := shanten.AnalyzeHand(player.ClosedHand, len(player.OpenMelds), state.WildTiles)
	legal, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}
	options := make(map[int]shanten.DiscardOption, len(analysis.DiscardOptions))
	for _, option := range analysis.DiscardOptions {
		if face, ok := tileFaceIndex42(&pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}); ok {
			options[face] = option
		}
	}
	probe := &pb.RouteProbe{
		Seat:          seat,
		Routes:        routeShanten(analysis.Routes),
		WildCount:     uint32(tiles.CountWilds(player.ClosedHand, tiles.WildSet(state.WildTiles))),
		OpenMeldCount: uint32(len(player.OpenMelds)),
	}
	for _, actionID := range SortedLegalIDs(legal) {
		if actionID < DiscardBase || actionID >= DiscardBase+DiscardCount {
			continue
		}
		option, ok := options[actionID-DiscardBase]
		if !ok {
			return nil, fmt.Errorf("legal discard %d has no shanten option", actionID)
		}
		probe.Discards = append(probe.Discards, &pb.DiscardRoute{
			ActionId: uint32(actionID),
			After:    routeShanten(option.After),
			IsWild:   option.IsWild,
		})
	}
	return probe, nil
}

func routeShanten(routes shanten.RouteBreakdown) *pb.RouteShanten {
	return &pb.RouteShanten{
		Overall:      int32(routes.Overall),
		Standard:     int32(routes.Standard),
		SevenPairs:   int32(routes.SevenPairs),
		Independence: int32(routes.Independence),
	}
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `go test ./internal/rl -run 'RouteProbe' -count=1 -v`
Expected: 4 PASS. If `TestRouteProbeCountsWildsAndFlagsWildDiscards` fails on the flower, inspect `shanten.analyzeDiscardOptions` for flower handling before changing the test — the probe must cover every legal discard (Review Focus 2).

- [ ] **Step 7: Add the bridge export**

In `cmd/rlbridge/main.go`, after `FHEnvEvaluateBranches`:

```go
//export FHEnvRouteProbe
func FHEnvRouteProbe(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	env, err := lookupEnv(uint64(handle))
	if err != nil {
		return errorResult(err)
	}

	request := &pb.RouteProbeRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := env.RouteProbe(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}
```

Run: `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge && nm -gU build/libfh_mahjong_bridge.dylib | grep FHEnvRouteProbe`
Expected: the symbol is listed.

- [ ] **Step 8: Docs**

- `proto/CLAUDE.md`, under "RL bridge messages", add: `` `RouteShanten`, `DiscardRoute`, `RouteProbeRequest`, `RouteProbe`: route-study probe — a seat's shanten per route (99 = unavailable) and after each legal discard, read-only (`FHEnvRouteProbe`) ``.
- `internal/rl/CLAUDE.md`, add an entry: `- **route_probe.go** — `Env.RouteProbe(request)`: the seat's `shanten.AnalyzeHand` routes, wild count, open-meld count, and one `DiscardRoute` per legal discard action (mapped from `DiscardOptions` by 42-face index; a legal discard without an option is an error). Read-only; used by the Python route study.`
- `cmd/rlbridge/CLAUDE.md`, add `FHEnvRouteProbe` to the export list with: "route-study probe for one seat (`RouteProbeRequest` → `RouteProbe`), read-only".

- [ ] **Step 9: Gates and commit**

```bash
gofmt -l . && go vet ./internal/rl ./cmd/rlbridge && go test ./internal/rl -count=1
git add proto/ internal/rl/route_probe.go internal/rl/route_probe_test.go internal/rl/CLAUDE.md cmd/rlbridge/ web/src/proto/ ai/src/fh_mahjong_ai/generated/proto/game_pb2.py
git commit -m "feat(rl): read-only route probe (shanten per route and per discard)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Python `CtypesGoBridge.route_probe`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/bridge.py` (`CtypesGoBridge.__init__`, new `route_probe`, module helper `_decode_route_shanten`)
- Test: `ai/tests/test_bridge.py`
- Docs: `ai/MODULES.md` (bridge.py entry)

**Interfaces:**
- Consumes: `FHEnvRouteProbe`, `game_pb2.RouteProbeRequest`, `game_pb2.RouteProbe` (Task 1).
- Produces: `CtypesGoBridge.route_probe(seat: int) -> dict` shaped
  `{"seat": int, "routes": {"overall","standard","seven_pairs","independence": int}, "wild_count": int, "open_meld_count": int, "discards": [{"action_id": int, "is_wild": bool, "after": {same four keys}}]}`.

- [ ] **Step 1: Write the failing tests**

In `ai/tests/test_bridge.py`:

1. Add to imports: `import os` and `import pytest`.
2. In `FakeGoLibrary.__init__` add `self.FHEnvRouteProbe = FakeFunction(callback=self._route_probe)` and `self.route_probe_seats = []`.
3. Add to `FakeGoLibrary`:

```python
    def _route_probe(self, handle, request_ptr, request_len):
        request = game_pb2.RouteProbeRequest()
        if request_len:
            request.ParseFromString(ctypes.string_at(request_ptr, request_len))
        self.route_probe_seats.append(int(request.seat))
        response = game_pb2.RouteProbe(
            seat=request.seat,
            routes=game_pb2.RouteShanten(overall=1, standard=3, seven_pairs=4, independence=1),
            wild_count=1,
            discards=[game_pb2.DiscardRoute(
                action_id=9, is_wild=True,
                after=game_pb2.RouteShanten(overall=1, standard=3, seven_pairs=5, independence=1))],
        )
        return self._bytes_result(response.SerializeToString())
```

4. Add tests to `CtypesGoBridgeTest`:

```python
    def _fake_bridge(self, fake_library):
        config = EnvConfig(plane_shape=(1, 1, 1), scalar_features=1, action_space_size=2,
                           bridge_library_path=Path("/tmp/libfh_mahjong_bridge_fake.so"))
        with mock.patch.object(bridge_module.ctypes, "CDLL", return_value=fake_library):
            return CtypesGoBridge(config)

    def test_route_probe_decodes_and_forwards_seat_including_zero(self) -> None:
        fake_library = FakeGoLibrary()
        bridge = self._fake_bridge(fake_library)
        probe = bridge.route_probe(2)
        zero = bridge.route_probe(0)
        bridge.close()

        self.assertEqual(fake_library.route_probe_seats, [2, 0])
        self.assertEqual(probe["seat"], 2)
        self.assertEqual(zero["seat"], 0)
        self.assertEqual(probe["routes"], {"overall": 1, "standard": 3, "seven_pairs": 4, "independence": 1})
        self.assertEqual(probe["wild_count"], 1)
        self.assertEqual(probe["open_meld_count"], 0)
        self.assertEqual(probe["discards"], [{
            "action_id": 9, "is_wild": True,
            "after": {"overall": 1, "standard": 3, "seven_pairs": 5, "independence": 1}}])

    def test_stale_library_loads_and_fails_only_on_route_probe(self) -> None:
        fake_library = FakeGoLibrary()
        del fake_library.FHEnvRouteProbe
        bridge = self._fake_bridge(fake_library)
        bridge.reset(seed=1)
        with self.assertRaisesRegex(BridgeError, "FHEnvRouteProbe"):
            bridge.route_probe(0)
        bridge.close()
```

5. Add a module-level real-library test at the end of the file:

```python
requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)


@requires_go_lib
def test_route_probe_reads_the_live_decision_without_changing_it():
    config = EnvConfig(learning_seats=(0, 1, 2, 3), auto_play_heuristics=False)
    with CtypesGoBridge(config) as bridge:
        observation = bridge.reset(seed=71)
        probe = bridge.route_probe(observation.seat)
        discard_ids = [a for a in observation.legal_actions if 5 <= a < 47]
        assert discard_ids, "premise: first decision has discards"
        assert [d["action_id"] for d in probe["discards"]] == discard_ids
        assert probe["seat"] == observation.seat
        assert bridge.route_probe(observation.seat) == probe
        assert bridge.route_probe(0)["seat"] == 0
        assert bridge.route_probe((observation.seat + 1) % 4)["discards"] == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_bridge.py -k route_probe -q`
Expected: FAIL — `AttributeError: 'CtypesGoBridge' object has no attribute 'route_probe'`.

- [ ] **Step 3: Implement**

In `ai/src/fh_mahjong_ai/bridge.py`:

- In `CtypesGoBridge.__init__`, first line after `super().__init__(config)`: `self._route_probe_fn = None`.
- Add the method after `evaluate_branches`:

```python
    def route_probe(self, seat: int) -> dict[str, object]:
        """Route shanten of `seat` now and after each legal discard (FHEnvRouteProbe,
        read-only). Bound on first use so a library built before the export still
        loads for everything else."""
        if self._route_probe_fn is None:
            fn = getattr(self._library, "FHEnvRouteProbe", None)
            if fn is None:
                raise BridgeError("bridge library has no FHEnvRouteProbe; rebuild it from cmd/rlbridge")
            fn.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
            fn.restype = FHBytesResult
            self._route_probe_fn = fn
        request = game_pb2.RouteProbeRequest(seat=int(seat))
        response = game_pb2.RouteProbe()
        response.ParseFromString(self._call_bytes(self._route_probe_fn, self._handle, self._serialize(request)))
        return {
            "seat": int(response.seat),
            "routes": _decode_route_shanten(response.routes),
            "wild_count": int(response.wild_count),
            "open_meld_count": int(response.open_meld_count),
            "discards": [
                {"action_id": int(d.action_id), "is_wild": bool(d.is_wild),
                 "after": _decode_route_shanten(d.after)}
                for d in response.discards
            ],
        }
```

- Add the module-level helper just above `class CtypesGoBridge`:

```python
def _decode_route_shanten(routes: game_pb2.RouteShanten) -> dict[str, int]:
    return {
        "overall": int(routes.overall),
        "standard": int(routes.standard),
        "seven_pairs": int(routes.seven_pairs),
        "independence": int(routes.independence),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run --project ai pytest ai/tests/test_bridge.py -q
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest ai/tests/test_bridge.py -k live_decision -q
```
Expected: all pass; the second run executes (not skips) the real-library test.

- [ ] **Step 5: Docs and commit**

`ai/MODULES.md` bridge.py entry: append "`CtypesGoBridge.route_probe(seat)` decodes `FHEnvRouteProbe` (route shanten now and per legal discard; bound lazily so an older library still loads)."

```bash
git add ai/src/fh_mahjong_ai/bridge.py ai/tests/test_bridge.py ai/MODULES.md
git commit -m "feat(ai): CtypesGoBridge.route_probe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `route_study.py` — classification, recorder, aggregates

**Files:**
- Create: `ai/src/fh_mahjong_ai/route_study.py`
- Create: `ai/tests/test_route_study.py`
- Docs: `ai/MODULES.md` (new entry after hand_stats.py), `ai/CLAUDE.md` line listing "Evaluation and diagnostics" modules (add `route_study.py`)

**Interfaces:**
- Consumes: probe dicts from `CtypesGoBridge.route_probe` (Task 2); `hand_stats.hand_record`, `hand_stats.WIN_PATTERN_SIDES`; `action_catalog.action_family`, `action_catalog.ACTION_RON`.
- Produces:
  - `ROUTES`, `SHANTEN_BUCKETS`, `GAP_BUCKETS`, `TURN_BUCKETS`, `WILD_BUCKETS`
  - `shanten_bucket(int) -> str`, `gap_bucket(int, int) -> str`, `turn_bucket(int) -> str`, `wild_bucket(int) -> str`
  - `win_route(outcome: dict, seat: int) -> str`, `end_route(routes: dict, open_meld_count: int) -> str`
  - `classify_fork(probe: dict, action_id: int) -> Optional[dict]` (keys `choice`, `keeps_seven_pairs`, `best_after`)
  - `is_call_offer(legal_actions: Sequence[int]) -> bool`
  - `new_route_study_summary() -> dict`, `merge_route_study(summaries) -> dict`
  - `class RouteStudyRecorder(learning_seat, probe, recorded_seats, shard_path=None)` with `start_match(seed)`, `on_decision(observation, action_id)`, `on_hand_end(outcome)`, `on_match_end(truncated)`, `summary() -> dict`, `close()`.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_route_study.py`:

```python
import gzip
import json
from types import SimpleNamespace

import pytest

from fh_mahjong_ai.action_catalog import ACTION_PASS, ACTION_RON, CHII_BASE, DISCARD_BASE, PON_BASE
from fh_mahjong_ai.route_study import (
    RouteStudyRecorder,
    classify_fork,
    end_route,
    gap_bucket,
    is_call_offer,
    merge_route_study,
    new_route_study_summary,
    shanten_bucket,
    turn_bucket,
    win_route,
)


def _routes(std, sp, ind):
    return {"overall": min(std, sp, ind), "standard": std, "seven_pairs": sp, "independence": ind}


def _probe(routes, discards=(), wilds=0, open_melds=0, seat=0):
    return {"seat": seat, "routes": routes, "wild_count": wilds, "open_meld_count": open_melds,
            "discards": [{"action_id": a, "is_wild": False, "after": after} for a, after in discards]}


def _obs(seat, legal):
    return SimpleNamespace(seat=seat, legal_actions=tuple(legal))


def _outcome(winner, patterns=(), draw=False, discarder=-1, payouts=None):
    return {"is_draw": draw, "winner_seat": winner, "discarder_seat": discarder,
            "win_type_name": "ACTION_RON" if discarder >= 0 else "ACTION_TSUMO",
            "payouts": payouts or [], "breakdown": [{"pattern_id": p} for p in patterns]}


D1, D2, D3 = DISCARD_BASE, DISCARD_BASE + 1, DISCARD_BASE + 2


def test_buckets_clip_and_mark_unavailable():
    assert [shanten_bucket(v) for v in (-1, 0, 6, 9, 99)] == ["0", "0", "6", "6", "-"]
    assert [gap_bucket(i, s) for i, s in ((0, 5), (2, 2), (8, 1))] == ["-3", "0", "3"]
    assert [turn_bucket(t) for t in (1, 3, 4, 9, 10, 15)] == ["1-3", "1-3", "4-6", "7-9", "10+", "10+"]


def test_win_route_maps_pattern_families():
    assert win_route(_outcome(1, ["independence", "closed_seven_stars"]), 1) == "independence"
    assert win_route(_outcome(1, ["wild_seven_pairs", "open_bomb"]), 1) == "seven_pairs"
    assert win_route(_outcome(1, ["completed_all_honors"]), 1) == "special"
    assert win_route(_outcome(1, ["base_point", "common_win"]), 1) == "standard"
    assert win_route(_outcome(1, ["independence"]), 2) == "none"
    assert win_route(_outcome(0, draw=True), 0) == "none"


def test_end_route_unique_lowest_tie_and_open_meld():
    assert end_route(_routes(3, 4, 1), 0) == "independence"
    assert end_route(_routes(2, 4, 2), 0) == "tie"
    assert end_route(_routes(99, 99, 99) | {"standard": 2}, 1) == "standard"


def test_classify_fork_disjoint_vs_shared_best():
    # D1 best for independence only, D2 best for standard only -> fork.
    probe = _probe(_routes(3, 5, 2), [(D1, _routes(4, 5, 1)), (D2, _routes(2, 5, 3)), (D3, _routes(4, 6, 3))])
    assert classify_fork(probe, D1)["choice"] == "independence"
    assert classify_fork(probe, D2)["choice"] == "standard"
    assert classify_fork(probe, D3)["choice"] == "neither"
    assert classify_fork(probe, D1)["best_after"] == {"standard": 2, "seven_pairs": 5, "independence": 1}
    assert classify_fork(probe, D1)["keeps_seven_pairs"] is True
    # D1 is best for both -> no fork.
    shared = _probe(_routes(3, 5, 2), [(D1, _routes(2, 5, 1)), (D2, _routes(2, 6, 3))])
    assert classify_fork(shared, D2) is None
    # Open meld -> never a fork.
    assert classify_fork(_probe(_routes(3, 99, 99), [(D1, _routes(2, 99, 99))], open_melds=1), D1) is None


def test_is_call_offer_needs_chii_or_pon_and_no_ron():
    assert is_call_offer([ACTION_PASS, PON_BASE])
    assert is_call_offer([ACTION_PASS, CHII_BASE])
    assert not is_call_offer([ACTION_PASS, PON_BASE, ACTION_RON])
    assert not is_call_offer([D1, D2])


class _ScriptedProbe:
    def __init__(self):
        self.next = {}

    def __call__(self, seat):
        return self.next[seat]


def _recorder(tmp_path, recorded=(0, 1, 2, 3), learning_seat=0):
    probe = _ScriptedProbe()
    rec = RouteStudyRecorder(learning_seat, probe=probe, recorded_seats=recorded,
                             shard_path=tmp_path / "rs.jsonl.gz")
    rec.start_match(500)
    return rec, probe


def _records(tmp_path):
    with gzip.open(tmp_path / "rs.jsonl.gz", "rt") as fh:
        return [json.loads(line) for line in fh]


def test_hand_record_deal_chart_fork_and_turns(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    fork_probe = _probe(_routes(3, 5, 2), [(D1, _routes(4, 5, 1)), (D2, _routes(2, 5, 3))], wilds=1)
    probe.next[0] = fork_probe
    rec.on_decision(_obs(0, [D1, D2]), D1)          # deal + fork at turn 1, independence side
    rec.on_decision(_obs(0, [D1, D2]), D2)          # fork at turn 2, standard side
    probe.next[1] = _probe(_routes(2, 4, 4), [(D1, _routes(1, 4, 4))], seat=1)
    rec.on_decision(_obs(1, [D1]), D1)              # seat 1 deal, no fork (single option is best for both)
    rec.on_hand_end(_outcome(0, ["independence"], payouts=[{"seat": 0, "amount": 150}, {"seat": 1, "amount": -50}]))
    rec.on_match_end(truncated=False)
    rec.close()

    learner = rec.summary()["learner"]
    assert learner["hands_recorded"] == 1
    cell = learner["deal"]["3"]["2"]
    assert cell == {"hands": 1, "end_independence": 1, "win_independence": 1, "deal_ins": 0, "payout_sum": 150}
    assert learner["deal_by_wilds"]["1"]["3"]["2"]["hands"] == 1
    assert learner["fork"]["-1"]["1-3"] == {"forks": 2, "independence": 1, "standard": 1}
    opponents = rec.summary()["opponents"]
    assert opponents["deal"]["2"]["4"]["end_standard"] == 1
    assert opponents["deal"]["2"]["4"]["payout_sum"] == -50

    records = _records(tmp_path)
    forks = [r for r in records if r["kind"] == "fork"]
    assert [(f["turn"], f["choice"]) for f in forks] == [(1, "independence"), (2, "standard")]
    hands = [r for r in records if r["kind"] == "hand"]
    assert {(h["seat"], h["side"], h["win_route"]) for h in hands} == {(0, "learner", "independence"), (1, "opponents", "none")}
    assert all(h["seed"] == 500 and h["hand"] == 0 for h in hands)


def test_seat_without_a_discard_decision_counts_without_deal(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    probe.next[0] = _probe(_routes(3, 5, 2), [(D1, _routes(3, 5, 2))])
    rec.on_decision(_obs(0, [D1]), D1)
    rec.on_hand_end(_outcome(1, ["base_point"], discarder=0))   # seat 1 never decided
    summary = rec.summary()
    assert summary["opponents"]["hands_without_deal"] == 1
    assert summary["opponents"]["deal"] == {}
    assert summary["learner"]["deal"]["3"]["2"]["deal_ins"] == 1


def test_call_offers_with_closed_hand_only(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(2,), learning_seat=2)
    probe.next[2] = _probe(_routes(3, 4, 1), seat=2)
    rec.on_decision(_obs(2, [ACTION_PASS, PON_BASE]), ACTION_PASS)
    rec.on_decision(_obs(2, [ACTION_PASS, CHII_BASE]), CHII_BASE)
    probe.next[2] = _probe(_routes(2, 99, 99), seat=2, open_melds=1)
    rec.on_decision(_obs(2, [ACTION_PASS, PON_BASE]), PON_BASE)    # already open: not an offer
    assert rec.summary()["learner"]["call"] == {"1": {"offers": 2, "called": 1}}


def test_truncated_match_drops_open_hand(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0, 1))
    probe.next[0] = _probe(_routes(3, 5, 2), [(D1, _routes(3, 5, 2))])
    rec.on_decision(_obs(0, [D1]), D1)
    rec.on_match_end(truncated=True)
    rec.close()
    summary = rec.summary()
    assert summary["learner"]["hands_recorded"] == 0
    assert summary["learner"]["truncated_hands"] == 1
    assert summary["opponents"]["truncated_hands"] == 1
    assert [r for r in _records(tmp_path) if r["kind"] == "hand"] == []


def test_unrecorded_seats_are_ignored(tmp_path):
    rec, probe = _recorder(tmp_path, recorded=(0,))
    rec.on_decision(_obs(3, [D1]), D1)     # probe has no entry for seat 3: must not be called
    rec.on_hand_end(_outcome(3, ["base_point"]))
    assert rec.summary()["learner"]["hands_without_deal"] == 1
    assert rec.summary()["opponents"]["hands_recorded"] == 0


def test_merge_sums_nested_counts():
    a, b = new_route_study_summary(), new_route_study_summary()
    a["learner"]["deal"] = {"3": {"2": {"hands": 1, "payout_sum": 10}}}
    a["learner"]["hands_recorded"] = 1
    b["learner"]["deal"] = {"3": {"2": {"hands": 2, "payout_sum": -4}, "1": {"hands": 1}}}
    b["learner"]["hands_recorded"] = 3
    merged = merge_route_study([a, b])
    assert merged["learner"]["deal"] == {"3": {"2": {"hands": 3, "payout_sum": 6}, "1": {"hands": 1}}}
    assert merged["learner"]["hands_recorded"] == 4
    assert merged["opponents"]["hands_recorded"] == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_route_study.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'fh_mahjong_ai.route_study'`.

- [ ] **Step 3: Implement**

Create `ai/src/fh_mahjong_ai/route_study.py`:

```python
"""Route study: when a policy pursues Independence vs the standard hand.

For every recorded seat's decision the recorder reads the seat's route shanten
from the Go bridge (`CtypesGoBridge.route_probe`), classifies discard forks and
chii/pon offers, and at each hand's end emits one hand record. Aggregates merge
by summing, so chunked benchmark runs combine exactly.
Spec: worklog/specs/20261002-route-study-design.md.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from .action_catalog import ACTION_RON, action_family
from .hand_stats import WIN_PATTERN_SIDES, hand_record

ROUTES = ("standard", "seven_pairs", "independence")
UNAVAILABLE = 99
SHANTEN_BUCKETS = ("0", "1", "2", "3", "4", "5", "6", "-")
GAP_BUCKETS = ("-3", "-2", "-1", "0", "1", "2", "3")
TURN_BUCKETS = ("1-3", "4-6", "7-9", "10+")
WILD_BUCKETS = ("0", "1", "2+")

_INDEPENDENCE_PATTERNS = frozenset({"independence"})
_SEVEN_PAIRS_PATTERNS = frozenset({"straight_seven_pairs", "wild_seven_pairs"})
_SPECIAL_PATTERNS = frozenset({
    "uncompleted_all_honors", "completed_all_honors",
    "uncompleted_eight_flowers", "completed_eight_flowers",
})
_CALL_FAMILIES = frozenset({"chii", "pon", "kan"})


def shanten_bucket(value: int) -> str:
    if value >= UNAVAILABLE:
        return "-"
    return str(max(0, min(6, int(value))))


def gap_bucket(independence: int, standard: int) -> str:
    return str(max(-3, min(3, int(independence) - int(standard))))


def turn_bucket(turn: int) -> str:
    if turn <= 3:
        return "1-3"
    if turn <= 6:
        return "4-6"
    if turn <= 9:
        return "7-9"
    return "10+"


def wild_bucket(wilds: int) -> str:
    return "2+" if wilds >= 2 else str(int(wilds))


def win_route(outcome: dict[str, Any], seat: int) -> str:
    """The route a hand was won on, from `seat`'s view: `none` unless it won."""
    if outcome.get("is_draw") or int(outcome.get("winner_seat", -1)) != int(seat):
        return "none"
    ids = {entry.get("pattern_id") for entry in outcome.get("breakdown") or []}
    if ids & _INDEPENDENCE_PATTERNS:
        return "independence"
    if ids & _SEVEN_PAIRS_PATTERNS:
        return "seven_pairs"
    if ids & _SPECIAL_PATTERNS:
        return "special"
    return "standard"


def end_route(routes: dict[str, int], open_meld_count: int) -> str:
    """The route closest to completion: the unique lowest shanten, else `tie`."""
    if open_meld_count > 0:
        return "standard"
    lowest = min(routes[r] for r in ROUTES)
    leaders = [r for r in ROUTES if routes[r] == lowest]
    return leaders[0] if len(leaders) == 1 else "tie"


def classify_fork(probe: dict[str, Any], action_id: int) -> Optional[dict[str, Any]]:
    """The fork facts for a chosen discard, or None when the decision is no fork.

    A fork: no open melds, and no discard minimizes both the after-Independence
    and the after-standard shanten.
    """
    discards = probe["discards"]
    if probe["open_meld_count"] > 0 or not discards:
        return None
    chosen = next((d for d in discards if d["action_id"] == int(action_id)), None)
    if chosen is None:
        return None
    best = {r: min(d["after"][r] for d in discards) for r in ROUTES}
    keeps = {r: {d["action_id"] for d in discards if d["after"][r] == best[r]} for r in ROUTES}
    if keeps["independence"] & keeps["standard"]:
        return None
    if chosen["action_id"] in keeps["independence"]:
        choice = "independence"
    elif chosen["action_id"] in keeps["standard"]:
        choice = "standard"
    else:
        choice = "neither"
    return {"choice": choice, "keeps_seven_pairs": chosen["action_id"] in keeps["seven_pairs"],
            "best_after": best}


def is_call_offer(legal_actions: Sequence[int]) -> bool:
    families = {action_family(a) for a in legal_actions}
    return bool(families & {"chii", "pon"}) and ACTION_RON not in legal_actions


def new_route_study_summary() -> dict[str, Any]:
    return {side: {"deal": {}, "deal_by_wilds": {}, "fork": {}, "call": {},
                   "hands_recorded": 0, "hands_without_deal": 0, "truncated_hands": 0}
            for side in WIN_PATTERN_SIDES}


def _add_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict):
            _add_into(target.setdefault(key, {}), value)
        else:
            target[key] = target.get(key, 0) + value


def merge_route_study(summaries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    merged = new_route_study_summary()
    for summary in summaries:
        _add_into(merged, summary)
    return merged


def _cell(table: dict[str, Any], *keys: str) -> dict[str, int]:
    for key in keys:
        table = table.setdefault(key, {})
    return table


def _bump(cell: dict[str, int], key: str, amount: int = 1) -> None:
    cell[key] = cell.get(key, 0) + amount


class _SeatHand:
    __slots__ = ("deal", "last_routes", "last_open_melds", "discards")

    def __init__(self) -> None:
        self.deal: Optional[dict[str, int]] = None
        self.last_routes: Optional[dict[str, int]] = None
        self.last_open_melds = 0
        self.discards = 0


class RouteStudyRecorder:
    """Route-study accounting for one evaluation run (one learning seat).

    Call `start_match(seed)` after each reset, `on_decision` for every decision
    BEFORE stepping the env, `on_hand_end` with each delivered round outcome, and
    `on_match_end` when the match stops. Seats outside `recorded_seats` are ignored.
    """

    def __init__(self, learning_seat: int, probe: Callable[[int], dict[str, Any]],
                 recorded_seats: Sequence[int], shard_path: Optional[Path] = None) -> None:
        self.learning_seat = int(learning_seat)
        self._probe = probe
        self._recorded = tuple(int(s) for s in recorded_seats)
        self._shard = gzip.open(shard_path, "wt", encoding="utf-8") if shard_path is not None else None
        self._summary = new_route_study_summary()
        self._seed = -1
        self._hand_index = 0
        self._hands: dict[int, _SeatHand] = {}

    def _side(self, seat: int) -> str:
        return "learner" if seat == self.learning_seat else "opponents"

    def _write(self, record: dict[str, Any]) -> None:
        if self._shard is not None:
            self._shard.write(json.dumps(record, sort_keys=True) + "\n")

    def start_match(self, seed: int) -> None:
        self._seed = int(seed)
        self._hand_index = 0
        self._hands = {}

    def on_decision(self, observation: Any, action_id: int) -> None:
        seat = int(observation.seat)
        if seat not in self._recorded:
            return
        probe = self._probe(seat)
        routes = {r: int(probe["routes"][r]) for r in ROUTES}
        hand = self._hands.setdefault(seat, _SeatHand())
        hand.last_routes = routes
        hand.last_open_melds = int(probe["open_meld_count"])
        side = self._side(seat)
        base = {"seed": self._seed, "seat": seat, "side": side, "hand": self._hand_index,
                "routes": routes, "action_id": int(action_id)}
        if probe["discards"]:
            if hand.deal is None:
                hand.deal = {**routes, "wild_count": int(probe["wild_count"]),
                             "open_meld_count": hand.last_open_melds}
            if action_family(action_id) != "discard":
                return
            hand.discards += 1
            fork = classify_fork(probe, action_id)
            if fork is None:
                return
            cell = _cell(self._summary[side]["fork"],
                         gap_bucket(routes["independence"], routes["standard"]),
                         turn_bucket(hand.discards))
            _bump(cell, "forks")
            _bump(cell, fork["choice"])
            self._write({**base, "kind": "fork", "turn": hand.discards,
                         "wild_count": int(probe["wild_count"]), **fork})
        elif hand.last_open_melds == 0 and is_call_offer(observation.legal_actions):
            called = action_family(action_id) in _CALL_FAMILIES
            cell = _cell(self._summary[side]["call"], shanten_bucket(routes["independence"]))
            _bump(cell, "offers")
            _bump(cell, "called", int(called))
            self._write({**base, "kind": "call", "turn": hand.discards + 1, "called": called})

    def on_hand_end(self, outcome: dict[str, Any]) -> None:
        for seat in self._recorded:
            hand = self._hands.get(seat, _SeatHand())
            side = self._side(seat)
            stats = self._summary[side]
            result = hand_record(outcome, seat)
            route = win_route(outcome, seat)
            ended = (end_route(hand.last_routes, hand.last_open_melds)
                     if hand.last_routes is not None else None)
            stats["hands_recorded"] += 1
            self._write({"kind": "hand", "seed": self._seed, "seat": seat, "side": side,
                         "hand": self._hand_index, "deal": hand.deal, "end_route": ended,
                         "win_route": route, "payout": result["payout"],
                         "win": result["win"], "deal_in": result["deal_in"]})
            if hand.deal is None:
                stats["hands_without_deal"] += 1
                continue
            std = shanten_bucket(hand.deal["standard"])
            ind = shanten_bucket(hand.deal["independence"])
            for cell in (_cell(stats["deal"], std, ind),
                         _cell(stats["deal_by_wilds"], wild_bucket(hand.deal["wild_count"]), std, ind)):
                _bump(cell, "hands")
                _bump(cell, f"end_{ended}")
                if route != "none":
                    _bump(cell, f"win_{route}")
                _bump(cell, "deal_ins", int(result["deal_in"]))
                _bump(cell, "payout_sum", int(result["payout"]))
        self._hand_index += 1
        self._hands = {}

    def on_match_end(self, truncated: bool) -> None:
        if truncated and self._hands:
            for seat in self._recorded:
                self._summary[self._side(seat)]["truncated_hands"] += 1
        self._hands = {}

    def summary(self) -> dict[str, Any]:
        return self._summary

    def close(self) -> None:
        if self._shard is not None:
            self._shard.close()
            self._shard = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_route_study.py -q`
Expected: all pass. Note `test_hand_record_deal_chart_fork_and_turns` pins the exact deal cell (no `end_tie`, no `win_*` beyond the actual route), so a stray `_bump` shows up as a dict mismatch.

- [ ] **Step 5: Docs and commit**

- `ai/MODULES.md`, new entry after hand_stats.py: `- **route_study.py** — Route study (spec `worklog/specs/20261002-route-study-design.md`): `RouteStudyRecorder` probes every recorded seat's decision through `CtypesGoBridge.route_probe`, records the deal-time route shanten per hand with `win_route` (from the outcome `breakdown`) and `end_route`, discard forks (no discard best for both Independence and standard), and closed-hand chii/pon offers. Aggregates are nested count dicts merged by summing (`merge_route_study`); raw `hand`/`fork`/`call` records stream to a gzip JSONL shard. Consumed by `evaluate.py` (`route_study_shard`) and `scripts/benchmark.py` (`--route-study`).`
- `ai/CLAUDE.md`: in the "Evaluation and diagnostics" row add `route_study.py`.

```bash
git add ai/src/fh_mahjong_ai/route_study.py ai/tests/test_route_study.py ai/MODULES.md ai/CLAUDE.md
git commit -m "feat(ai): route-study recorder (deal chart, forks, call offers)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Route-study charts

**Files:**
- Modify: `ai/src/fh_mahjong_ai/route_study.py` (append `format_route_study` and helpers)
- Test: `ai/tests/test_route_study.py`

**Interfaces:**
- Consumes: summary dicts from Task 3.
- Produces: `format_route_study(summary: dict, labels: dict[str, str]) -> str`.

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_route_study.py`:

```python
from fh_mahjong_ai.route_study import format_route_study


def test_format_route_study_renders_each_chart():
    summary = new_route_study_summary()
    learner = summary["learner"]
    learner["hands_recorded"] = 4
    learner["deal"] = {"3": {"1": {"hands": 4, "end_independence": 3, "win_independence": 2,
                                   "payout_sum": 120}}}
    learner["fork"] = {"-2": {"4-6": {"forks": 5, "independence": 4, "standard": 1}}}
    learner["call"] = {"1": {"offers": 10, "called": 1}}
    text = format_route_study(summary, {"learner": "ckpt/a.pt", "opponents": "ckpt/b.pt"})

    assert "learner (ckpt/a.pt): 4 hands" in text
    assert "opponents" not in text            # a side with no hands is skipped
    assert "50.0% (4)" in text                # won by Independence: 2 of 4
    assert "75.0% (4)" in text                # ended on Independence: 3 of 4
    assert "+30.0" in text                    # mean payout 120 / 4
    assert "80.0% (5)" in text                # fork: 4 of 5 on the Independence side
    assert "10.0% (10)" in text               # call: 1 of 10 called
    assert "6+" in text and "<=-3" in text and ">=+3" in text
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_route_study.py -k format -q`
Expected: FAIL — `ImportError: cannot import name 'format_route_study'`.

- [ ] **Step 3: Implement**

Append to `ai/src/fh_mahjong_ai/route_study.py`:

```python
_LABELS = {"6": "6+", "-3": "<=-3", "3": ">=+3"}
_CELL_WIDTH = 14


def _rate_cell(numerator: int, denominator: int) -> str:
    return f"{100.0 * numerator / denominator:.1f}% ({denominator})" if denominator else "."


def _grid(title: str, corner: str, rows: Sequence[str], cols: Sequence[str],
          cell: Callable[[str, str], str]) -> list[str]:
    lines = [title, f"{corner:>8}" + "".join(f"{_LABELS.get(c, c):>{_CELL_WIDTH}}" for c in cols)]
    for row in rows:
        lines.append(f"{_LABELS.get(row, row):>8}"
                     + "".join(f"{cell(row, col):>{_CELL_WIDTH}}" for col in cols))
    return lines


def format_route_study(summary: dict[str, Any], labels: dict[str, str]) -> str:
    """Per-side charts: deal pivots, fork pivot, call row."""
    lines: list[str] = []
    for side in WIN_PATTERN_SIDES:
        stats = summary[side]
        if not stats["hands_recorded"]:
            continue
        deal = stats["deal"]

        def deal_counts(row: str, col: str) -> dict[str, int]:
            return deal.get(row, {}).get(col, {})

        def deal_rate(key: str) -> Callable[[str, str], str]:
            return lambda r, c: _rate_cell(deal_counts(r, c).get(key, 0), deal_counts(r, c).get("hands", 0))

        def mean_payout(r: str, c: str) -> str:
            counts = deal_counts(r, c)
            return f"{counts['payout_sum'] / counts['hands']:+.1f}" if counts.get("hands") else "."

        def fork_rate(r: str, c: str) -> str:
            counts = stats["fork"].get(r, {}).get(c, {})
            return _rate_cell(counts.get("independence", 0), counts.get("forks", 0))

        def call_rate(_: str, c: str) -> str:
            counts = stats["call"].get(c, {})
            return _rate_cell(counts.get("called", 0), counts.get("offers", 0))

        rows, cols = SHANTEN_BUCKETS[:-1], SHANTEN_BUCKETS
        lines += [f"Route study — {side} ({labels.get(side, side)}): {stats['hands_recorded']} hands, "
                  f"{stats['hands_without_deal']} without a deal, {stats['truncated_hands']} truncated",
                  "Deal charts: rows = standard shanten at the deal, columns = Independence shanten "
                  "('-' = called before the first discard)", ""]
        lines += _grid("Won by Independence, % of hands (hands)", "std\\ind", rows, cols,
                       deal_rate("win_independence")) + [""]
        lines += _grid("Ended on the Independence route, % of hands (hands)", "std\\ind", rows, cols,
                       deal_rate("end_independence")) + [""]
        lines += _grid("Mean hand payout", "std\\ind", rows, cols, mean_payout) + [""]
        lines += _grid("Forks: % choosing the Independence side (forks); rows = Independence minus "
                       "standard shanten, columns = discard number", "gap", GAP_BUCKETS, TURN_BUCKETS,
                       fork_rate) + [""]
        lines += _grid("Closed-hand chii/pon offers: % called (offers); columns = Independence shanten",
                       "", ("called",), SHANTEN_BUCKETS[:-1], call_rate) + [""]
    return "\n".join(lines).rstrip() + "\n"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_route_study.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/route_study.py ai/tests/test_route_study.py
git commit -m "feat(ai): route-study charts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Hook the recorder into `evaluate_policy_online`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (imports; `evaluate_policy_online` signature, setup, loop, return)
- Test: `ai/tests/test_strong_table_eval.py` (real-library test), `ai/tests/test_evaluate.py` (mock-bridge guard)
- Docs: `ai/MODULES.md` (evaluate.py entry)

**Interfaces:**
- Consumes: `RouteStudyRecorder` (Task 3), `bridge.route_probe` (Task 2).
- Produces: `evaluate_policy_online(..., route_study_shard: Optional[Path] = None)`; when set, the report gains `report["route_study"]` (a `new_route_study_summary()`-shaped dict); when unset the report is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_strong_table_eval.py` (it already defines `requires_go_lib`, `_model`, `TorchGreedyPolicy`, `evaluate_policy_online`):

```python
import gzip
import json
from collections import Counter


@requires_go_lib
def test_route_study_records_every_seat_at_a_strong_table(tmp_path):
    shard = tmp_path / "rs.jsonl.gz"
    report = evaluate_policy_online(
        policy=TorchGreedyPolicy(_model(1)), episodes=2, seeds=[11, 12], learning_seat=1,
        match_mode="chongci", chongci_max_hands=4, max_steps_per_episode=4000,
        opponent_policy=TorchGreedyPolicy(_model(2)), route_study_shard=shard,
    )
    study = report["route_study"]
    hands = report["hand_stats"]["hands_played"]
    assert hands > 0
    assert study["learner"]["hands_recorded"] == hands
    assert study["opponents"]["hands_recorded"] == 3 * hands
    with gzip.open(shard, "rt") as fh:
        records = [json.loads(line) for line in fh]
    kinds = Counter(r["kind"] for r in records)
    assert kinds["hand"] == 4 * hands
    assert {r["seat"] for r in records if r["kind"] == "hand"} == {0, 1, 2, 3}
    dealt = sum(cell["hands"] for row in study["learner"]["deal"].values() for cell in row.values())
    assert dealt == hands - study["learner"]["hands_without_deal"]


@requires_go_lib
def test_route_study_off_leaves_report_without_the_key():
    report = evaluate_policy_online(
        policy=TorchGreedyPolicy(_model(1)), episodes=1, seeds=[11], learning_seat=0,
        match_mode="classic",
    )
    assert "route_study" not in report
```

Append to `ai/tests/test_evaluate.py`:

```python
def test_route_study_requires_the_go_bridge(tmp_path):
    import pytest
    from fh_mahjong_ai.evaluate import evaluate_policy_online
    with pytest.raises(ValueError, match="Go bridge"):
        evaluate_policy_online(policy=object(), episodes=1, seeds=[1], bridge_kind="mock",
                               route_study_shard=tmp_path / "rs.jsonl.gz")
```

- [ ] **Step 2: Run them to verify they fail**

```bash
uv run --project ai pytest ai/tests/test_evaluate.py -k route_study -q
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest ai/tests/test_strong_table_eval.py -k route_study -q
```
Expected: FAIL — `TypeError: evaluate_policy_online() got an unexpected keyword argument 'route_study_shard'`.

- [ ] **Step 3: Implement**

In `ai/src/fh_mahjong_ai/evaluate.py`:

1. Import: `from .route_study import RouteStudyRecorder` (next to the `hand_stats` import).
2. Signature: add `route_study_shard: Optional[Path] = None,` after `opponent_policy: Optional[Any] = None,`. Add to the docstring: "With ``route_study_shard`` set (Go bridge only) every decision of every seat this loop plays is probed for the route study; the report gains ``route_study`` and raw records go to that gzip JSONL path."
3. First statement of the body:

```python
    if route_study_shard is not None and bridge_kind != "go":
        raise ValueError("route study needs the Go bridge (bridge_kind='go')")
```

4. After `record_episode = acc.record_episode`:

```python
    route_recorder = None
    if route_study_shard is not None:
        route_recorder = RouteStudyRecorder(
            learning_seat,
            probe=bridge.route_probe,
            recorded_seats=(0, 1, 2, 3) if opponent_policy is not None else (learning_seat,),
            shard_path=Path(route_study_shard),
        )
```

5. In the episode loop, right after `observation = env.reset(seed=seed)`:

```python
            if route_recorder is not None:
                route_recorder.start_match(seed)
```

6. Immediately before `step_result = env.step(action_id)`:

```python
                if route_recorder is not None:
                    route_recorder.on_decision(observation, action_id)
```

7. Immediately after `step_result = env.step(action_id)`:

```python
                if route_recorder is not None:
                    hand_outcome = step_result.info.get("round_outcome")
                    if hand_outcome is not None:
                        route_recorder.on_hand_end(hand_outcome)
                    if step_result.terminated or step_result.truncated:
                        route_recorder.on_match_end(bool(step_result.truncated))
```

8. Replace the inner `if not observation.legal_actions: break` (the one after `observation = step_result.observation`) with:

```python
                if not observation.legal_actions:
                    if route_recorder is not None:
                        route_recorder.on_match_end(True)
                    break
```

9. Replace the tail

```python
    finally:
        env.close()

    return acc.report()
```

with

```python
    finally:
        env.close()
        if route_recorder is not None:
            route_recorder.close()

    report = acc.report()
    if route_recorder is not None:
        report["route_study"] = route_recorder.summary()
    return report
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
uv run --project ai pytest ai/tests/test_evaluate.py ai/tests/test_route_study.py -q
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest ai/tests/test_strong_table_eval.py -q
```
Expected: all pass, the real-library tests run (not skipped).

- [ ] **Step 5: Docs and commit**

`ai/MODULES.md` evaluate.py entry: append "`evaluate_policy_online(route_study_shard=...)` (Go bridge only) runs a `route_study.RouteStudyRecorder` over every decision the loop plays (all four seats at a strong table, the learner otherwise) and adds `route_study` to the report; unset, the report is unchanged."

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py ai/tests/test_strong_table_eval.py ai/MODULES.md
git commit -m "feat(ai): route study in evaluate_policy_online

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: `fh-mj-benchmark --route-study`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/benchmark.py`
- Test: `ai/tests/test_benchmark.py`
- Docs: `ai/MODULES.md` (scripts/benchmark.py entry)

**Interfaces:**
- Consumes: `evaluate_policy_online(route_study_shard=...)` (Task 5), `merge_route_study`, `format_route_study` (Tasks 3–4).
- Produces: `route_study_shard_path(route_study_dir: Optional[Path], seat: int, seeds: Sequence[int]) -> Optional[Path]`; `_run_chunk(seat, seeds, route_study_dir=None)`; JSON keys `overall.route_study` and `route_study_records` only when the flag is set.

- [ ] **Step 1: Write the failing tests**

Append to `ai/tests/test_benchmark.py`:

```python
class RouteStudyMainTest(unittest.TestCase):
    def _run_main(self, tmp, extra_args, fake_eval):
        fake_model = mock.Mock()
        fake_model.model_config.event_window = 0
        ckpt = Path(tmp) / "champion.pt"
        ckpt.write_bytes(b"fake")
        with mock.patch.object(
            benchmark_cli.CheckpointPolicy, "from_checkpoint", return_value=mock.Mock(model=fake_model),
        ), mock.patch.object(
            benchmark_cli, "evaluate_policy_online", side_effect=fake_eval,
        ), mock.patch.object(
            benchmark_cli, "TorchGreedyPolicy", return_value=mock.Mock(),
        ):
            benchmark_cli.main(["--checkpoint", str(ckpt), "--episodes-per-seat", "2",
                                "--bootstrap-iters", "10", *extra_args])
        return ckpt

    def test_flag_gives_each_seat_a_shard_and_merges_summaries(self) -> None:
        from fh_mahjong_ai.route_study import new_route_study_summary
        calls = []

        def fake_eval(**kwargs):
            calls.append(kwargs)
            report = _seat_report(kwargs["learning_seat"], [[_win(kwargs["learning_seat"])]])
            study = new_route_study_summary()
            study["learner"]["hands_recorded"] = 1
            report["route_study"] = study
            return report

        with TemporaryDirectory() as tmp:
            ckpt = self._run_main(tmp, ["--route-study"], fake_eval)
            shard_dir = Path(tmp) / "champion.pt.benchmark.route-study"
            shards = [c["route_study_shard"] for c in calls]
            self.assertEqual(len(set(shards)), 4)
            self.assertTrue(all(s.parent == shard_dir for s in shards))
            self.assertEqual(shards[0].name, "seat0-seeds1000-1001.jsonl.gz")
            payload = json.loads(Path(str(ckpt) + ".benchmark.json").read_text())
            self.assertEqual(payload["overall"]["route_study"]["learner"]["hands_recorded"], 4)
            self.assertEqual(payload["route_study_records"], str(shard_dir))

    def test_flag_off_adds_nothing(self) -> None:
        calls = []

        def fake_eval(**kwargs):
            calls.append(kwargs)
            return _seat_report(kwargs["learning_seat"], [[_win(kwargs["learning_seat"])]])

        with TemporaryDirectory() as tmp:
            ckpt = self._run_main(tmp, [], fake_eval)
            payload = json.loads(Path(str(ckpt) + ".benchmark.json").read_text())
            self.assertNotIn("route_study", payload["overall"])
            self.assertNotIn("route_study_records", payload)
            self.assertTrue(all(c["route_study_shard"] is None for c in calls))
            self.assertFalse((Path(tmp) / "champion.pt.benchmark.route-study").exists())

    def test_refuses_a_non_empty_route_study_dir(self) -> None:
        with TemporaryDirectory() as tmp:
            shard_dir = Path(tmp) / "champion.pt.benchmark.route-study"
            shard_dir.mkdir()
            (shard_dir / "old.jsonl.gz").write_bytes(b"x")
            with self.assertRaises(SystemExit):
                self._run_main(tmp, ["--route-study"], lambda **kwargs: None)

    def test_combine_chunk_reports_merges_route_study(self) -> None:
        from fh_mahjong_ai.route_study import new_route_study_summary
        chunks = []
        for n in (1, 2):
            study = new_route_study_summary()
            study["opponents"]["hands_recorded"] = n
            chunks.append({**_seat_report(0, [[_win(0)]]), "route_study": study})
        combined = benchmark_cli.combine_chunk_reports(chunks)
        self.assertEqual(combined["route_study"]["opponents"]["hands_recorded"], 3)
        self.assertNotIn("route_study", benchmark_cli.combine_chunk_reports([_seat_report(0, [[_win(0)]])]))

    def test_shard_path_is_none_without_a_dir(self) -> None:
        self.assertIsNone(benchmark_cli.route_study_shard_path(None, 0, [1, 2]))
        self.assertEqual(benchmark_cli.route_study_shard_path(Path("d"), 3, [7, 8, 9]),
                         Path("d") / "seat3-seeds7-9.jsonl.gz")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_benchmark.py -k "RouteStudy or route_study or shard_path" -q`
Expected: FAIL — `unrecognized arguments: --route-study` / `AttributeError: ... route_study_shard_path`.

- [ ] **Step 3: Implement**

In `ai/src/fh_mahjong_ai/scripts/benchmark.py`:

1. Docstring: add "`--route-study` records route shanten at every decision of every seat the loop plays (`route_study.py`) and prints Independence-vs-standard charts."
2. Import: `from fh_mahjong_ai.route_study import format_route_study, merge_route_study`.
3. In `merge_seat_reports`, before `return`, build the result dict into a variable `merged = {...}` and add:

```python
    route_studies = [r["route_study"] for _, r in sorted(seat_reports.items()) if "route_study" in r]
    if route_studies:
        merged["overall"]["route_study"] = merge_route_study(route_studies)
    return merged
```

4. In `combine_chunk_reports`, likewise assign the dict to `combined`, then:

```python
    route_studies = [c["route_study"] for c in chunks if "route_study" in c]
    if route_studies:
        combined["route_study"] = merge_route_study(route_studies)
    return combined
```

5. Add after `plan_chunks`:

```python
def route_study_shard_path(route_study_dir: Optional[Path], seat: int,
                           seeds: Sequence[int]) -> Optional[Path]:
    """One gzip JSONL shard per (seat, seed range); None when the study is off."""
    if route_study_dir is None:
        return None
    return route_study_dir / f"seat{seat}-seeds{seeds[0]}-{seeds[-1]}.jsonl.gz"
```

6. `_run_chunk`:

```python
def _run_chunk(seat: int, seeds: list[int], route_study_dir: Optional[Path] = None) -> dict[str, Any]:
    return evaluate_policy_online(
        policy=_WORKER["policy"],
        episodes=len(seeds),
        seeds=seeds,
        learning_seat=seat,
        event_history_window=_WORKER["event_window"],
        opponent_policy=_WORKER["opponent_policy"],
        route_study_shard=route_study_shard_path(route_study_dir, seat, seeds),
        **_WORKER["eval_kwargs"],
    )
```

7. Parser: `parser.add_argument("--route-study", action="store_true", help="record route shanten at every decision (Independence vs standard) and print route charts; raw records go to <out stem>.route-study/")`.
8. Move `out_path = args.out if args.out is not None else Path(str(args.checkpoint) + ".benchmark.json")` up to just after argument validation, and add:

```python
    route_study_dir = out_path.parent / (out_path.stem + ".route-study") if args.route_study else None
    if route_study_dir is not None:
        if route_study_dir.exists() and any(route_study_dir.iterdir()):
            parser.error(f"{route_study_dir} is not empty; remove it or choose another --out")
        route_study_dir.mkdir(parents=True, exist_ok=True)
```

9. Sequential path: add `route_study_shard=route_study_shard_path(route_study_dir, seat, seeds),` to the `evaluate_policy_online(...)` call.
10. Pool path: `pool.submit(_run_chunk, seat, seeds, route_study_dir)`.
11. Payload: after building `payload`, before writing:

```python
    if route_study_dir is not None:
        payload["route_study_records"] = str(route_study_dir)
```

12. After printing the win-pattern table:

```python
    if "route_study" in merged["overall"]:
        print()
        print(format_route_study(merged["overall"]["route_study"],
                                 {"learner": str(args.checkpoint), "opponents": opponent_label}))
        print(f"route-study records in {route_study_dir}")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_benchmark.py -q`
Expected: all pass, including the pre-existing tests (flag-off behavior unchanged).

- [ ] **Step 5: Docs and commit**

`ai/MODULES.md` scripts/benchmark.py entry: append "`--route-study` passes each (seat, seed-range) chunk its own shard (`route_study_shard_path`, under `<out stem>.route-study/`, refused if non-empty), merges `route_study` summaries into `overall.route_study`, records the shard dir as `route_study_records`, and prints `format_route_study` charts. Off, the JSON has neither key."

```bash
git add ai/src/fh_mahjong_ai/scripts/benchmark.py ai/tests/test_benchmark.py ai/MODULES.md
git commit -m "feat(benchmark): --route-study flag with per-chunk shards and charts

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Gates, smoke run, PR

**Files:** none new (fixes only if a gate fails).

- [ ] **Step 1: Full CI gates**

```bash
gofmt -l .            # must print nothing
go vet ./...
go test ./...
[ -e web/node_modules ] || ln -s /Users/plasma/fh-mahjong/web/node_modules web/node_modules
(cd web && npx tsc && npx vitest run)
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest ai/tests -q
```
Expected: all green. Paste failures in full if any; fix in the owning task's files and re-run.

- [ ] **Step 2: Smoke run on the real checkpoints (4 matches)**

```bash
cd /Users/plasma/fh-mahjong-models/vs-prod
W=/Users/plasma/fh-mahjong/.claude/worktrees/route-study
FH_MAHJONG_BRIDGE_LIB=$W/build/libfh_mahjong_bridge.dylib uv run --project $W/ai fh-mj-benchmark \
  --checkpoint ckpt/saug-ext-iter150.pt --symmetry-average suits \
  --opponent-checkpoint ckpt/anchor075.pt --episodes-per-seat 1 --seed-base 1000 \
  --route-study --out /private/tmp/claude-501/-Users-plasma-fh-mahjong/e00b8634-49f3-47fd-baa0-551da589601e/scratchpad/smoke.benchmark.json
```
Expected: charts print for `learner` and `opponents`; `learner.hands_recorded` equals `overall.hand_stats.hands_played`; four shards exist in `smoke.benchmark.route-study/`; zero truncated hands.

- [ ] **Step 3: Push and open the PR (base `feat/benchmark-opponent` until #266 merges, then retarget to `main`)**

```bash
git push -u origin feat/route-study
gh pr create --base feat/benchmark-opponent --title "feat(benchmark): route study — when the AI goes Independence" --body "$(cat <<'EOF'
Adds `fh-mj-benchmark --route-study`: a read-only Go route probe (`FHEnvRouteProbe`) and a Python recorder that log, for every seat at the strong table, route shanten at the deal, discard forks between Independence and the standard hand, and chii/pon offers — with printed charts and raw gzip JSONL records.

Spec: worklog/specs/20261002-route-study-design.md. Stacked on #266 (needs `RoundOutcome.breakdown`).

Flag off, the benchmark report is unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

### Task 8: The 1,600-match run and the worklog entry

- [ ] **Step 1: Run**

```bash
cd /Users/plasma/fh-mahjong-models/vs-prod
W=/Users/plasma/fh-mahjong/.claude/worktrees/route-study
FH_MAHJONG_BRIDGE_LIB=$W/build/libfh_mahjong_bridge.dylib uv run --project $W/ai fh-mj-benchmark \
  --checkpoint ckpt/saug-ext-iter150.pt --symmetry-average suits \
  --opponent-checkpoint ckpt/anchor075.pt --episodes-per-seat 400 --seed-base 1000 --workers 10 \
  --route-study --out ../benchmarks/saug-ext-iter150-suits-vs-anchor075-1600m-routes.benchmark.json \
  2>&1 | tee ../benchmarks/saug-ext-iter150-suits-vs-anchor075-1600m-routes.log
```
Run in the background (~50 min).

- [ ] **Step 2: Verify the probe changed nothing**

```bash
cd /Users/plasma/fh-mahjong-models/benchmarks
python3 -c "
import json
a=json.load(open('saug-ext-iter150-suits-vs-anchor075-1600m.benchmark.json'))['overall']
b=json.load(open('saug-ext-iter150-suits-vs-anchor075-1600m-routes.benchmark.json'))['overall']
assert a['hand_stats']==b['hand_stats'] and a['win_patterns']==b['win_patterns'], 'outcomes differ'
print('identical outcomes')"
```
Expected: `identical outcomes` (same seeds, deterministic greedy play, read-only probe).

- [ ] **Step 3: Worklog entry**

Append a `### <run date, yyyy-mm-dd> — route study: when the AI goes Independence` entry to `worklog/rl-experiment/chongci-rl-experiment-progress.md` (before `## Maintenance Protocol`) in the notebook's `Setup:` / table / `Interpretation:` format: the run setup and report path, the deal chart (won-by-Independence and ended-on-Independence pivots, learner and anchor075), the fork pivot, the call row, and a plain-language reading of the thresholds. State it is descriptive (choices, not EV; bot table). Commit and push to the PR branch.

- [ ] **Step 4: Delete this plan once the PR merges** (per `worklog/CLAUDE.md`; the spec stays).
