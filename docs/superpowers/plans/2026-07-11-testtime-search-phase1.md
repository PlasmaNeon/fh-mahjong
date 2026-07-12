# Test-Time Search Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Honest determinized pMCPA search over the frozen champion, evaluable via `fh-mj-evaluate --duplicate-seats --search`, gated paired vs the raw greedy champion.

**Architecture:** Go provides determinized clone pools (engine `RedealUnseen` + `internal/rl` SearchPool following the FHEnvPool lockstep pattern, reusing the EnvPool proto messages); Python drives the search loop with the champion in-process on the GPU (`CheckpointPolicy.evaluate_batch`), wraps it as a `SearchPolicy` for the existing duplicate-seat eval harness.

**Tech Stack:** Go 1.25 (engine/rl/FFI), Protocol Buffers, Python 3.12 + PyTorch + ctypes.

## Global Constraints

- **THE invariant:** the acting seat's observation must be bit-identical across determinizations (no peeking).
- `internal/engine` must never import `internal/rules` or `internal/rl`; the new engine seam (`RedealUnseen`) takes only builtin/proto types.
- No heuristic completion anywhere in the search path — champion rollouts only.
- Fail-open: search must never crash or stall an eval; whole-search failure falls back to the greedy champion action, and fallbacks are counted.
- Default eval behavior byte-unchanged when search flags are absent (search metadata key appears in the report only when `--search` is active — the sampling-flags precedent).
- Follow FHEnvPool patterns for pool FFI + handle lifecycle (flat little-endian buffers, registry + Close, `FHFree`).
- After Go changes: `go test ./...` + `go vet ./...`. After Python changes: `uv run --project ai pytest`. Update AGENTS.md for touched dirs.
- Commit messages end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

## File Structure

- Create `internal/engine/redeal.go` + `internal/engine/redeal_test.go` — the determinization primitive (needs unexported wall fields).
- Create `internal/rl/searchpool.go` + `internal/rl/searchpool_test.go` — K determinized clones, apply/lockstep-step, round-end/cap semantics.
- Modify `proto/game.proto` — one new message (`SearchPoolNewRequest`); Apply/Step reuse `EnvPoolStepRequest`/`EnvPoolStepResponse`.
- Modify `cmd/rlbridge/main.go` — `FHSearchPoolNew/Step/Close` exports mirroring `FHEnvPool*`.
- Create `ai/src/fh_mahjong_ai/searchpool.py` — `GoSearchPool` ctypes wrapper (mirror `envpool.py`'s `GoEnvPool`).
- Create `ai/src/fh_mahjong_ai/search.py` + `ai/tests/test_search.py` — `SearchConfig`, `search_decision`, `SearchPolicy`.
- Modify `ai/src/fh_mahjong_ai/scripts/evaluate.py` + `ai/tests/test_search_eval.py` — `--search*` flags threading.
- Modify AGENTS.md in `internal/engine/`, `internal/rl/`, `cmd/rlbridge/` (covered by Task 8 in the repo's convention: each task updates its own).

---

### Task 1: `engine.Game.RedealUnseen` (the determinization primitive)

**Files:**
- Create: `internal/engine/redeal.go`
- Test: `internal/engine/redeal_test.go`

**Interfaces:**
- Consumes: unexported `Game` fields (`wall`, `wallIndex`, `wangpaiBoundary`, `wildIndicatorIndex`, `haiteiDrawIndex`, `deadWallIndex`, `interruptQueue`), `isTileConsumedByDeadWall(i)` (game.go), `pb.GameState`.
- Produces: `func (g *Game) RedealUnseen(actingSeat uint32, seed uint64) error` — used by Task 2's SearchPool on clones.

Semantics (from the spec, plus two pinned details found during design):
- Unseen pool = the 3 opponents' `ClosedHand` tiles + every undrawn wall tile. Undrawn wall index `i`: `wallIndex <= i < len(wall)`, `i != wildIndicatorIndex`, not `isTileConsumedByDeadWall(i)`, and `i != haiteiDrawIndex` when `haiteiDrawIndex >= 0`.
- Shuffle the pool with `math/rand.New(rand.NewSource(int64(seed)))` (search determinism needs a seeded stream, not MT19937 wall-replay compatibility).
- Deal back: opponents' hands first (seat ascending, same hand sizes, positional), then wall slots ascending. Only tile *identities* move; every index/count stays.
- **Pinned detail 1 — opponent `DrawnTileId`:** if an opponent's `DrawnTileId` is set, re-point it at the tile now occupying the same position in their `ClosedHand` (positional remap) so engine logic never references a tile id that moved elsewhere.
- **Pinned detail 2 — interrupt queue:** clear `g.interruptQueue`. Queued-but-unresolved opponent interrupt responses are themselves hidden information; clearing makes the rollout re-ask those seats via the policy, which is exactly the honest behavior.
- Error cases: `actingSeat > 3` → error; nil state → error.

- [ ] **Step 1: Write the failing tests**

Create `internal/engine/redeal_test.go`:

```go
package engine_test

import (
	"sort"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// startedGame deals a real seeded game so wall geometry (wangpai, wild
// indicator) is authentic, then returns it with seat 0 to act.
func startedGame(t *testing.T, seed uint64) *engine.Game {
	t.Helper()
	g := engine.NewGame("redeal-test", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.SetWallSeed(engine.SeedFromUint64(seed))
	g.SetNextDealer(0)
	if err := g.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	return g
}

func tileKeys(tiles []*pb.Tile) []uint32 {
	keys := make([]uint32, 0, len(tiles))
	for _, tile := range tiles {
		keys = append(keys, tile.Id)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	return keys
}

func handsEqual(a, b []*pb.Tile) bool {
	if len(a) != len(b) {
		return false
	}
	ka, kb := tileKeys(a), tileKeys(b)
	for i := range ka {
		if ka[i] != kb[i] {
			return false
		}
	}
	return true
}

func TestRedealUnseen_VisibleStateFixedAndPoolConserved(t *testing.T) {
	g := startedGame(t, 42)
	clone := g.CloneForBranch()

	before := clone.CloneForBranch() // snapshot
	if err := clone.RedealUnseen(0, 7); err != nil {
		t.Fatalf("redeal: %v", err)
	}

	// Acting seat's own hand identical (ids, order irrelevant but keep ids).
	if !handsEqual(before.State.Players[0].ClosedHand, clone.State.Players[0].ClosedHand) {
		t.Fatal("acting seat's hand changed")
	}
	// Opponents' hand SIZES unchanged.
	for s := 1; s < 4; s++ {
		if len(before.State.Players[s].ClosedHand) != len(clone.State.Players[s].ClosedHand) {
			t.Fatalf("seat %d hand size changed", s)
		}
	}
	// Global tile-id multiset conserved across hands+wall (nothing created/lost):
	collect := func(g2 *engine.Game) []uint32 {
		var all []*pb.Tile
		for _, p := range g2.State.Players {
			all = append(all, p.ClosedHand...)
		}
		return append(tileKeys(all), tileKeys(g2.WallTilesForTest())...)
	}
	a, b := collect(before), collect(clone)
	if len(a) != len(b) {
		t.Fatalf("tile count changed: %d vs %d", len(a), len(b))
	}
	sort.Slice(a, func(i, j int) bool { return a[i] < a[j] })
	sort.Slice(b, func(i, j int) bool { return b[i] < b[j] })
	for i := range a {
		if a[i] != b[i] {
			t.Fatal("tile multiset not conserved")
		}
	}
	// Wall geometry: wild indicator tile identity unchanged (it is visible).
	if before.WildIndicatorForTest().Id != clone.WildIndicatorForTest().Id {
		t.Fatal("wild indicator changed — it is visible and must not be redealt")
	}
	// WallCount (visible) unchanged.
	if before.State.WallCount != clone.State.WallCount {
		t.Fatal("visible wall count changed")
	}
}

func TestRedealUnseen_OpponentsDifferAcrossSeeds(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 1); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 2); err != nil {
		t.Fatal(err)
	}
	differ := false
	for s := 1; s < 4; s++ {
		if !handsEqual(a.State.Players[s].ClosedHand, b.State.Players[s].ClosedHand) {
			differ = true
		}
	}
	if !differ {
		t.Fatal("different seeds produced identical opponent hands")
	}
}

func TestRedealUnseen_SeedDeterminism(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	for s := 1; s < 4; s++ {
		ka := tileKeys(a.State.Players[s].ClosedHand)
		kb := tileKeys(b.State.Players[s].ClosedHand)
		for i := range ka {
			if ka[i] != kb[i] {
				t.Fatalf("seat %d differs under same seed", s)
			}
		}
	}
}

func TestRedealUnseen_RejectsBadSeat(t *testing.T) {
	g := startedGame(t, 42)
	if err := g.CloneForBranch().RedealUnseen(4, 1); err == nil {
		t.Fatal("expected error for seat 4")
	}
}
```

Note: the test needs two tiny exported test hooks on `Game` (wall access for conservation/indicator checks). Add to `redeal.go` (they are test-support accessors, deliberate and documented):

```go
// WallTilesForTest returns the undrawn wall tiles (test support: redeal
// conservation checks). Not for gameplay use.
func (g *Game) WallTilesForTest() []*pb.Tile { ... }

// WildIndicatorForTest returns the face-up wild indicator tile (test support).
func (g *Game) WildIndicatorForTest() *pb.Tile { return g.wall[g.wildIndicatorIndex] }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `go test ./internal/engine/ -run TestRedealUnseen -v`
Expected: FAIL — `undefined: ... RedealUnseen` (compile error).

- [ ] **Step 3: Implement `internal/engine/redeal.go`**

```go
package engine

import (
	"fmt"
	"math/rand"

	pb "github.com/plasma/fh-mahjong/proto"
)

// RedealUnseen re-deals everything the acting seat cannot see: the three
// opponents' concealed hands and every undrawn wall tile are collected into
// one pool, shuffled with the given seed, and dealt back into the same slots.
// Everything visible to the acting seat stays fixed: its own hand, all open
// melds, flower melds, discards, the wild indicator, scores, and the wall
// count/geometry (wangpai boundary, consumed dead-wall indices, haitei index
// are positions — only undrawn tile identities move).
//
// Two hidden-information details are part of the contract:
//   - An opponent's DrawnTileId (private) is positionally remapped to the tile
//     now occupying the same slot of their hand, so engine logic never points
//     at a tile id that moved elsewhere.
//   - The interrupt queue is CLEARED: queued-but-unresolved opponent responses
//     are themselves hidden information; a rollout re-asks those seats.
//
// Intended for use on CloneForBranch clones (search determinization), never on
// a live game.
func (g *Game) RedealUnseen(actingSeat uint32, seed uint64) error {
	if g == nil || g.State == nil {
		return fmt.Errorf("redeal: nil game state")
	}
	if int(actingSeat) >= len(g.State.Players) {
		return fmt.Errorf("redeal: invalid acting seat %d", actingSeat)
	}

	// 1. Collect the unseen pool.
	var pool []*pb.Tile
	for s, p := range g.State.Players {
		if uint32(s) == actingSeat {
			continue
		}
		pool = append(pool, p.ClosedHand...)
	}
	wallIdx := g.undrawnWallIndices()
	for _, i := range wallIdx {
		pool = append(pool, g.wall[i])
	}

	// 2. Seeded shuffle (plain math/rand: search determinism, not wall replay).
	rng := rand.New(rand.NewSource(int64(seed)))
	rng.Shuffle(len(pool), func(i, j int) { pool[i], pool[j] = pool[j], pool[i] })

	// 3. Deal back: opponents' hands first (seat ascending, positional), then
	// undrawn wall slots ascending.
	k := 0
	for s, p := range g.State.Players {
		if uint32(s) == actingSeat {
			continue
		}
		var drawnPos = -1
		if p.DrawnTileId != nil {
			for pos, tile := range p.ClosedHand {
				if int32(tile.Id) == *p.DrawnTileId {
					drawnPos = pos
					break
				}
			}
		}
		for pos := range p.ClosedHand {
			p.ClosedHand[pos] = pool[k]
			k++
		}
		if drawnPos >= 0 {
			remapped := int32(p.ClosedHand[drawnPos].Id)
			p.DrawnTileId = &remapped
		}
	}
	for _, i := range wallIdx {
		g.wall[i] = pool[k]
		k++
	}

	// 4. Queued interrupt responses are hidden information — drop them.
	g.interruptQueue = make(map[uint32]*pb.PlayerAction)
	return nil
}

// undrawnWallIndices lists wall positions whose tiles are still hidden: not
// yet front-drawn, not the face-up wild indicator, not consumed by a
// dead-wall draw, and not an already-drawn haitei tile.
func (g *Game) undrawnWallIndices() []int {
	var out []int
	for i := g.wallIndex; i < len(g.wall); i++ {
		if i == g.wildIndicatorIndex {
			continue
		}
		if g.isTileConsumedByDeadWall(i) {
			continue
		}
		if g.haiteiDrawIndex >= 0 && i == g.haiteiDrawIndex {
			continue
		}
		out = append(out, i)
	}
	return out
}

// WallTilesForTest returns the undrawn wall tiles (test support: redeal
// conservation checks). Not for gameplay use.
func (g *Game) WallTilesForTest() []*pb.Tile {
	idx := g.undrawnWallIndices()
	out := make([]*pb.Tile, 0, len(idx))
	for _, i := range idx {
		out = append(out, g.wall[i])
	}
	return out
}

// WildIndicatorForTest returns the face-up wild indicator tile (test support).
func (g *Game) WildIndicatorForTest() *pb.Tile { return g.wall[g.wildIndicatorIndex] }
```

Front-drawn tiles below `wallIndex` also include dead-wall-skipped positions handled by the wall-consumption invariant; `undrawnWallIndices` mirrors exactly the positions the engine itself would still dispense (front draws + dead-wall draws + haitei), so the redeal can never change an already-seen tile.

- [ ] **Step 4: Run tests to verify they pass**

Run: `go test ./internal/engine/ -run TestRedealUnseen -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Full engine suite + vet, update `internal/engine/AGENTS.md`**

Run: `go vet ./internal/engine/ && go test ./internal/engine/`
Expected: PASS, no regressions.
Add to `internal/engine/AGENTS.md` under game.go's bullet list:

```markdown
  - `RedealUnseen(actingSeat, seed)` — search determinization: re-deals the 3 opponents' concealed hands + undrawn wall from the acting seat's unseen pool (seeded); visible state and wall geometry fixed; remaps opponents' `DrawnTileId` positionally and clears the interrupt queue (queued responses are hidden info). Clone-only use (`CloneForBranch`).
```

- [ ] **Step 6: Commit**

```bash
git add internal/engine/redeal.go internal/engine/redeal_test.go internal/engine/AGENTS.md
git commit -m "feat(engine): RedealUnseen — honest search determinization primitive"
```

---

### Task 2: `internal/rl` SearchPool (K determinized clones, lockstep rollout)

**Files:**
- Create: `internal/rl/searchpool.go`
- Test: `internal/rl/searchpool_test.go`

**Interfaces:**
- Consumes: `Env` (env.go: `game`, `config`, `decisionCount`, `advanceToDecision()`), `engine.Game.CloneForBranch/RedealUnseen` (Task 1), `decodeActionID` (action.go), `EncodeObservation` (observation.go), proto `SlotCommand`/`EnvPoolStepRequest`/`EnvPoolStepResponse`/`SlotState` (existing), `appendFloat32LE` (envpool.go).
- Produces:
  - `func NewSearchPool(e *Env, clones int, seed uint64, maxRolloutDecisions uint64) (*SearchPool, error)`
  - `func (p *SearchPool) Step(request *pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error)` — SlotCommand `action_id` steps a clone, `skip` idles it; `reset_seed` is a per-slot error ("search pool has no reset").
  - `func (p *SearchPool) Close()`

Response contract (documented deviations from FHEnvPool, all within the same messages):
- `SlotState.round_outcome != nil` **and not terminated** ⇒ the clone's current ROUND ended; `has_observation=true` carries the FIRST decision observation of the NEXT hand (the value-bootstrap state). Python stops stepping that clone (sends `skip`).
- `terminated=true` ⇒ match ended; `has_observation=false`; the dense per-step rewards already telescoped the final outcome into the accumulated sum.
- `truncated=true` (decision cap hit) ⇒ **`has_observation=true`** (deviation: the cap-state observation IS returned, for value bootstrapping).
- Observation planes are the acting seat's 39ch (or 51ch if the env is oracle-configured — the search path always runs 39ch envs; assert `!config.OracleObservation` at pool creation: search must never see oracle channels).

Construction: for each clone `i`: `game := e.game.CloneForBranch()`; `game.RedealUnseen(actingSeat, seed*1_000_003 + uint64(i))`; wrap in a fresh `Env` (same pattern as `evaluateBranch`: `normalizeConfig(e.config)`, `learningSeats` = all four so every seat's decision surfaces, `decisionCount` copied); the acting seat is `e`'s current acting seat (from the live decision observation).

Honesty tests (THE invariant, verified at the rl level where observations exist):

```go
func TestSearchPool_ActingSeatObservationInvariant(t *testing.T) {
	// Build a live env at a decision point (mock-free: go bridge in-process).
	env := newStartedEnv(t, 4242) // helper: New(config)+Reset, config 39ch chongci
	seat, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 6, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()
	for i := 0; i < 6; i++ {
		cloneObs := pool.cloneObservationForTest(i, seat)
		if !bytesEqual(obs.Planes, cloneObs.Planes) || !bytesEqual(obs.Scalars, cloneObs.Scalars) {
			t.Fatalf("clone %d: acting seat observation differs — determinization leaked", i)
		}
	}
}

func TestSearchPool_OpponentHandsDifferAcrossClones(t *testing.T) { ... } // K=6, at least one pair differs
func TestSearchPool_SeedDeterminism(t *testing.T)                { ... } // two pools same seed => identical clone hands
func TestSearchPool_RejectsOracleEnv(t *testing.T)               { ... } // oracle_observation=true => error
func TestSearchPool_RoundEndEmitsNextHandObs(t *testing.T)       { ... } // step to round end => round_outcome set + has_observation
func TestSearchPool_DecisionCapTruncatesWithObs(t *testing.T)    { ... } // tiny cap => truncated=true, has_observation=true
func TestSearchPool_ResetCommandIsError(t *testing.T)            { ... } // reset_seed => SlotState.error non-empty
```

(The `...` test bodies follow the exact arrange/act/assert of the invariant test above and envpool_test.go's stepping patterns — the implementer writes them against the same helpers; each assertion is named in its test name. `cloneObservationForTest` is an unexported test hook returning `EncodeObservation` of a clone for a given seat.)

Implementation skeleton (complete logic, mirrors `applyOne`/`assemblePoolResponse` in envpool.go):

```go
type SearchPool struct {
	clones []*searchClone
	config *pb.EnvConfig
	maxDec uint64
}

type searchClone struct {
	env       *Env
	decisions uint64
	done      bool
}

func NewSearchPool(e *Env, clones int, seed uint64, maxRolloutDecisions uint64) (*SearchPool, error) {
	if e == nil || e.game == nil {
		return nil, fmt.Errorf("search pool: nil env")
	}
	cfg := normalizeConfig(e.config)
	if cfg.OracleObservation {
		return nil, fmt.Errorf("search pool: oracle observation is forbidden in search")
	}
	seat, ok := e.currentActionSeat()
	if !ok {
		return nil, fmt.Errorf("search pool: env is not at a decision point")
	}
	p := &SearchPool{config: cfg, maxDec: maxRolloutDecisions}
	for i := 0; i < clones; i++ {
		g := e.game.CloneForBranch()
		if g == nil {
			return nil, fmt.Errorf("search pool: clone failed")
		}
		if err := g.RedealUnseen(seat, seed*1000003+uint64(i)); err != nil {
			return nil, err
		}
		p.clones = append(p.clones, &searchClone{env: &Env{
			config:        cfg,
			game:          g,
			learningSeats: map[uint32]bool{0: true, 1: true, 2: true, 3: true},
			decisionCount: e.decisionCount,
			baseSeed:      e.baseSeed,
		}})
	}
	return p, nil
}
```

`Step` iterates commanded slots: decode `action_id` for the clone's current acting seat via `decodeActionID`, `ProcessPlayerAction`, then `advanceToDecision()`; detect round end by `HandNum` change or emitted `RoundOutcome`; enforce `p.maxDec` per clone (set `truncated`, keep the observation); assemble the response with the same flat-buffer code as `assemblePoolResponse` (share it — extract the buffer-assembly into a helper both pools call rather than duplicating).

- [ ] Steps: failing tests → RED → implement → GREEN → `go vet ./... && go test ./...` → update `internal/rl/AGENTS.md` (searchpool.go entry + the response-contract deviations) → commit `feat(rl): SearchPool — determinized clone pool for test-time search`.

---

### Task 3: Proto message + FFI exports + binding regen

**Files:**
- Modify: `proto/game.proto` (one new message, after the EnvPool block ~line 470)
- Modify: `cmd/rlbridge/main.go` (three exports + registry, mirror `FHEnvPool*` at lines 134-183)
- Regenerate: Go + Python + TS bindings (mirror commit ce5996d's file set exactly)

**Interfaces:**
- Produces: proto `SearchPoolNewRequest{uint32 clones; uint64 seed; uint32 max_rollout_decisions;}`; FFI `FHSearchPoolNew(envHandle uint64, req) -> handle`, `FHSearchPoolStep(handle, EnvPoolStepRequest) -> EnvPoolStepResponse bytes`, `FHSearchPoolClose(handle)`.

Proto addition:

```proto
// Test-time search: create K determinized clones of a live env's current
// decision point (opponents' hands + undrawn wall re-dealt per clone; the
// acting seat's observation is bit-identical across clones). Stepping reuses
// EnvPoolStepRequest/EnvPoolStepResponse with these deviations: reset_seed
// commands are per-slot errors; round_outcome set (non-terminal) means the
// round ended and the observation is the NEXT hand's first decision state;
// truncated=true (decision cap) still carries the cap-state observation.
message SearchPoolNewRequest {
  uint32 clones = 1;
  uint64 seed = 2;
  uint32 max_rollout_decisions = 3;
}
```

FFI exports (complete, mirroring the FHEnvPool trio + `lookupEnv`):

```go
//export FHSearchPoolNew
func FHSearchPoolNew(envHandle C.uint64_t, requestPtr *C.char, requestLen C.int) C.uint64_t {
	env, err := lookupEnv(uint64(envHandle))
	if err != nil {
		return 0
	}
	request := &pb.SearchPoolNewRequest{}
	if err := proto.Unmarshal(inputBytes(requestPtr, requestLen), request); err != nil {
		return 0
	}
	pool, err := rl.NewSearchPool(env, int(request.Clones), request.Seed, uint64(request.MaxRolloutDecisions))
	if err != nil {
		return 0
	}
	return storeSearchPool(pool) // same registry pattern as storePool/lookupPool
}

//export FHSearchPoolStep
func FHSearchPoolStep(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult { ... mirror FHEnvPoolStep ... }

//export FHSearchPoolClose
func FHSearchPoolClose(handle C.uint64_t) { ... mirror FHEnvPoolClose ... }
```

Regen commands (exact):

```bash
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
# Python (mirror ce5996d — check the command recorded there; conventionally:)
protoc --python_out=ai/generated proto/game.proto   # verify against ai/generated/proto/ layout first
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

(The implementer MUST check `git show ce5996d --stat` and reproduce the same generated-file set; the Python generation path in particular must match `ai/generated/proto/game_pb2.py`'s header conventions.)

Test: a Go-side smoke in `cmd/rlbridge` is impractical (cgo exports); the contract is covered by Task 2's Go tests + Task 4's Python round-trip. This task's gate: `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge` succeeds, `go vet ./...` clean, full suites green, bindings regenerated with no unrelated drift.

- [ ] Steps: proto edit → regen all bindings → FFI exports → build c-shared + vet + full suites → update `cmd/rlbridge`/proto AGENTS.md → commit `feat(proto+ffi): search-pool message and FHSearchPool exports`.

---

### Task 4: Python `GoSearchPool` wrapper

**Files:**
- Create: `ai/src/fh_mahjong_ai/searchpool.py`
- Test: `ai/tests/test_searchpool.py`

**Interfaces:**
- Consumes: `FHSearchPoolNew/Step/Close` (Task 3), `envpool.py`'s `PoolCommand`, `SlotMeta`, `PoolStepResult`, `_empty_result`, FFI plumbing conventions (`_configure_signatures`, `_call_bytes`, `FHBytesResult` from bridge.py).
- Produces: `class GoSearchPool: __init__(bridge: CtypesGoBridge, clones: int, seed: int, max_rollout_decisions: int)`, `.step(commands: Sequence[PoolCommand]) -> SearchStepResult`, `.close()`. `SearchStepResult` = `PoolStepResult` + `round_ended: dict[int, bool]` (slots whose SlotState carried a non-terminal `round_outcome`).

Implementation mirrors `GoEnvPool` line-for-line (same decode via `np.frombuffer`), plus: `round_ended[slot] = state.HasField("round_outcome") and not state.terminated`. The constructor takes the live `CtypesGoBridge` (which owns the env handle) and calls `FHSearchPoolNew(bridge.handle, request)`.

Tests: import/construct against the mock bridge is impossible (FFI-only feature) — so `test_searchpool.py` is gated:

```python
requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library"
)
```

Gated tests: create env → reset to a decision → `GoSearchPool(bridge, clones=4, seed=7, ...)` → step all clones with the greedy mask-argmax → assert 4 slot states, obs shapes `(rows, 39, 42, 1)`, and **same-seed pool twice → identical first-step observations** (FFI determinism, spec test #4). Ungated test: `PoolCommand`/decode helpers imported and re-used from envpool (no duplication).

- [ ] Steps: failing (gated) tests → implement → run with `FH_MAHJONG_BRIDGE_LIB` set locally (build the dylib first) → full pytest (gated tests skip in CI without the lib — matching existing repo convention for bridge-dependent tests; verify that convention in ai/tests before assuming) → AGENTS.md → commit `feat(ai): GoSearchPool ctypes wrapper`.

---

### Task 5: Search loop + `SearchPolicy` (`ai/src/fh_mahjong_ai/search.py`)

**Files:**
- Create: `ai/src/fh_mahjong_ai/search.py`
- Test: `ai/tests/test_search.py`

**Interfaces:**
- Consumes: `CheckpointPolicy` (`.evaluate_batch(planes, scalars, action_masks) -> (probs, values)`, `.choose(obs)`), `GoSearchPool`/`PoolCommand` (Task 4 — injected via a factory for testability), `ActionChoice` protocol (policies.py).
- Produces:

```python
@dataclass(frozen=True)
class SearchConfig:
    num_determinizations: int = 16
    max_candidates: int = 4
    prior_mass_cutoff: float = 0.95
    max_rollout_decisions: int = 512
    seed: int = 1

class SearchPolicy:
    """ActionChoice-protocol policy: determinized champion-rollout search.

    pool_factory(num_clones, seed, max_rollout_decisions) -> pool with
    .step(commands)->SearchStepResult and .close(). Production wires
    GoSearchPool over the live eval bridge; tests inject fakes.
    """
    def __init__(self, checkpoint_policy, pool_factory, config: SearchConfig): ...
    def choose(self, observation) -> ActionChoice: ...
    @property
    def fallback_count(self) -> int: ...
```

`choose()` (complete logic — the plan's core algorithm, transcribed from the spec):

```python
def choose(self, observation):
    greedy = self._policy.choose(observation)          # priors come from evaluate_batch below
    try:
        probs, _ = self._policy.evaluate_batch(
            observation.planes[None], observation.scalars[None], observation.action_mask[None])
        prior = probs[0]
        order = np.argsort(-prior)
        candidates, mass = [], 0.0
        for a in order:
            if prior[a] <= 0.0 or len(candidates) >= self._config.max_candidates:
                break
            candidates.append(int(a))
            mass += float(prior[a])
            if mass >= self._config.prior_mass_cutoff:
                break
        if len(candidates) <= 1:
            return self._as_choice(greedy, searched=False)

        K = self._config.num_determinizations
        pool = self._pool_factory(len(candidates) * K, self._config.seed,
                                  self._config.max_rollout_decisions)
        try:
            scores = self._rollout_scores(pool, candidates, K)   # np.ndarray [len(candidates)]
        finally:
            pool.close()
        best = candidates[int(np.argmax(scores))]
        return ActionChoice(action_id=best, value=greedy.value, info={
            "source": "search", "greedy_action_id": greedy.action_id,
            "candidates": candidates, "scores": [float(s) for s in scores],
        })
    except Exception:
        self._fallbacks += 1
        return self._as_choice(greedy, searched=False)
```

`_rollout_scores` (the lockstep loop): clone `c*K+k` gets candidate `c` applied on the first step; every subsequent stepping round gathers all live clones' observations, one `evaluate_batch` call, greedy argmax per clone (masked), one `pool.step`; per clone accumulate `step_rewards[acting_root_seat]`; on `round_ended` → score += value-head of the returned next-hand obs (one more `evaluate_batch` on those rows), mark done; on `terminated` → score is the accumulated sum; on `truncated` → score += value of the cap obs. Candidate score = mean over its K clones. Per-clone errors: drop that clone from the mean; if ALL clones of a candidate error, score it `-inf` unless it is the greedy action (then keep prior rank via score = value estimate) — and count a fallback.

Root-seat note: the acting seat at the root is `observation.seat`; `step_rewards` is per-seat len-4, indexed by that root seat throughout (the seat doesn't change identity across the rollout).

Tests (all with fakes, no FFI):
1. `test_degenerate_single_candidate_equals_greedy` — `max_candidates=1` (or prior mass 1.0 on one action) → returned action == `CheckpointPolicy.choose` action; `info["source"] != "search"`; pool factory NEVER called.
2. `test_search_prefers_higher_scoring_candidate` — FakePool scripted so candidate B's clones accumulate higher rewards → B chosen over the higher-prior A.
3. `test_fail_open_on_pool_error` — pool factory raises → greedy action returned, `fallback_count == 1`.
4. `test_round_end_uses_value_bootstrap` — FakePool emits `round_ended` with a distinguishable obs; FakePolicy's value head rewards it; assert bootstrapped candidate wins.
5. `test_truncation_scored_with_cap_value` — truncated slot contributes value-at-cap, not zero.
6. `test_chunk_invariance` — FakePolicy asserts it only ever receives batched calls; results identical for chunk sizes 8 vs 256 (delegated through evaluate_batch's own invariance, verified by identical chosen actions).

(Each fake is ~20 lines; the implementer builds `FakeCheckpointPolicy` (scripted probs/values) and `FakeSearchPool` (scripted per-step SlotMeta sequences) in the test file — full control, no bridge.)

- [ ] Steps: failing tests → implement → GREEN → full pytest → AGENTS.md → commit `feat(ai): determinized champion-rollout search (SearchConfig, SearchPolicy)`.

---

### Task 6: Eval integration (`fh-mj-evaluate --search`)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/evaluate.py` (mirror the sampling-flags threading at ~lines 236-260)
- Test: `ai/tests/test_search_eval.py`

**Interfaces:**
- Consumes: `SearchPolicy`/`SearchConfig` (Task 5), `GoSearchPool` (Task 4), `evaluate_duplicate_seats_policy(policy_factory=...)`, the CLI's existing checkpoint/model plumbing.
- Produces flags: `--search` (bool), `--search-determinizations` (default 16), `--search-max-candidates` (default 4), `--search-prior-mass` (default 0.95), `--search-max-rollout-decisions` (default 512), `--search-seed` (default 1). Validation: `--search` requires `--duplicate-seats`; the numeric flags require `--search` (mirror the sampling-flag validation style, loud `parser.error`).

Threading (the sampled_policy_factory precedent): when `--search` is set, build per-seat `SearchPolicy` instances whose `pool_factory` wraps the seat's live bridge (`GoSearchPool(bridge, ...)` — the duplicate-seat harness exposes the bridge per env; follow how the policy factory receives seat context today and pass the bridge the same way; if the current factory signature only passes `seat`, extend the eval path minimally in the same style the sampling work did). Report: a `"search"` key (config + total fallback count) present ONLY when `--search` is active; without the flag the report is byte-identical to today (regression-tested by asserting key absence).

Tests: flag validation (search without duplicate-seats errors; numeric flags without --search error); report contains `search` key with the config when active (mock bridge run, `max_candidates=1` so no pool is needed); report lacks the key when inactive.

- [ ] Steps: failing tests → implement threading → GREEN → full pytest → AGENTS.md → commit `feat(eval): --search flags run SearchPolicy through duplicate-seat eval`.

---

### Task 7: Gate runbook (operational — no code)

On the 4090 box (`ssh wsl`, repo `/root/fh-mahjong`):

```bash
cd /root/fh-mahjong && git pull origin main
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge
cd ai && export FH_MAHJONG_BRIDGE_LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so
# Search arm (detached, established chain/poll pattern):
uv run fh-mj-evaluate \
  --checkpoint /root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt \
  --model-residual-blocks 4 --duplicate-seats --online-episodes 120 --start-seed 870000 \
  --match-mode chongci --chongci-max-hands 50 --max-steps-per-episode 4000 \
  --large-loss-threshold -1.0 --device cuda \
  --search --search-determinizations 16 --search-max-candidates 4 --search-seed 7 \
  --report-output /root/fh-mahjong-runs/search-gate/eval-search-K16M4.json
# Raw-champion arm: reuse /root/fh-mahjong-runs/phaseB1/eval-275.json (same seeds).
```

Aggregation (paired, same as every campaign gate): per-episode placements diff vs `eval-275.json`, mean ± CI95, plus vs-anchor for ladder continuity, plus the report's `search.fallback_count`. **PASS:** paired diff − CI95 > 0 vs the raw champion AND `large_loss_rate` ≤ champion + 0.02 → proceed to the Phase-2 spec. **Parity/fail:** ONE escalation `--search-determinizations 32 --search-max-candidates 6`; still parity → stop, document in `docs/rl-papers/chongci-rl-experiment-progress.md` per the maintenance protocol. Expect 2–6 s/decision (K=16/M=4); budget 1–3 days of box time; use the detached `setsid` + background-poll pattern.

---

## Self-Review Notes

- Spec coverage: honesty invariants → Tasks 1–2 tests; pool/FFI → 2–4; search+fail-open → 5; gate/eval → 6–7; Phase-2 NPZ hook is deliberately OUT (spec says "opt-in flag" — deferred to the Phase-2 spec to keep this plan minimal; the `info["candidates"]/["scores"]` payload in ActionChoice already carries what logging needs).
- Type consistency: `PoolCommand`/`PoolStepResult` reused from envpool.py; `SearchStepResult.round_ended` introduced in Task 4 and consumed in Task 5; `pool_factory(num_clones, seed, max_rollout_decisions)` signature consistent across Tasks 5–6.
- Known judgment calls the reviewer may probe: test hooks on `Game` (`*ForTest` accessors) — deliberate, documented, mirrors the repo's exported-for-test precedents; sharing `assemblePoolResponse` between pools rather than duplicating.
