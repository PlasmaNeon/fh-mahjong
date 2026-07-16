# Spec B2a: Search-Honest Events + Flat Pool Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make event history honest under search determinization and available through the flat pool layout, then replace all four B1 fail-fast guards with positive tests.

**Architecture:** `RedealUnseen` rewrites non-root DRAW faces to -1 in the clone's log (root-invariance proven by test). `EnvPoolStepResponse` gains fixed-width uint32 event rows plus explicit per-row counts (packed `0x0` is a valid event, so padding alone is ambiguous); one shared `appendObservationRow` keeps EnvPool and SearchPool identical. Python pools decode to per-row true-length uint32 arrays on `PoolStepResult`. Dormant at window 0: all new fields empty, existing consumers byte-unaffected.

**Tech Stack:** Go 1.25 (`internal/engine`, `internal/rl`, `cmd/rlbridge`), Protocol Buffers (Go+Python+TS), Python 3.12 + numpy (`ai/`).

**Spec:** `docs/superpowers/specs/2026-07-16-spec-b2a-events-infra-design.md` (approved). Branch: `claude/spec-b2a-events-infra` (exists, off main @ feb1485).

## Global Constraints

- `event_history_window = 0` stays byte-identical everywhere — dormancy tests required for the new response fields.
- Proto changes append-only: `EnvPoolStepResponse` fields 10/11/12. Regen Go AND Python (`grpc_tools.protoc`, NEVER bare protoc) AND TS (`--null-semantics`), commands in Task 2.
- `internal/engine` must never import `internal/rules`.
- NO model / RolloutBatch / collector / training changes — that is B2b.
- All four B1 guards must be REMOVED in this branch, each replaced by a positive test (never delete a guard without its replacement landing in the same task).
- After Go changes: `go vet ./... && go test ./...`. After Python: `uv run --project ai pytest`. After proto: TS regen + `cd web && npx tsc --noEmit`.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: RedealUnseen event-face rewrite (search honesty)

**Files:**
- Modify: `internal/engine/redeal.go` (end of `RedealUnseen`, before the final `return nil` at ~line 145)
- Test: `internal/rl/eventcodec_test.go` (append)

**Interfaces:**
- Consumes: `engine.PublicEvent`, `engine.EventDraw`, `g.PublicEvents()`, `CloneForBranch`, `RedealUnseen(actingSeat uint32, seed uint64) error`, `renderEventHistory(events, observer, window)`, `EventFaceUnknown` — all existing.
- Produces: behavior only — after `RedealUnseen(actingSeat, seed)`, every `EventDraw` log entry with `Seat != actingSeat` has `Face == -1`.

- [ ] **Step 1: Write the failing tests**

Append to `internal/rl/eventcodec_test.go`:

```go
// buildRedealTestEnv drives a seeded random match ~40 decisions so the log
// holds draws by several seats, then returns the env plus a seat that is
// NOT the current acting seat and has drawn at least once.
func buildRedealTestEnv(t *testing.T, seed uint64) (*Env, uint32, uint32) {
	t.Helper()
	env := newSeededHistoryEnv(t, seed, 128)
	rng := rand.New(rand.NewSource(int64(seed)))
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
	rootSeat, ok := env.currentActionSeat()
	if !ok {
		rootSeat = env.game.State.ActivePlayer
	}
	var nonRoot uint32
	found := false
	for _, event := range env.game.PublicEvents() {
		if event.Type == engine.EventDraw && event.Seat != rootSeat && event.Face >= 0 {
			nonRoot = event.Seat
			found = true
			break
		}
	}
	if !found {
		t.Fatalf("premise: no non-root draw with a real face at seed %d — pick another seed", seed)
	}
	return env, rootSeat, nonRoot
}

// Root invariance: the ROOT observer's rendered history must be
// byte-identical before vs after the redeal rewrite — masking already hid
// non-root draw faces from the root, so the rewrite removes EXACTLY the
// information the root could never see, and nothing else.
func TestRedealRewriteRootInvariance(t *testing.T) {
	env, rootSeat, _ := buildRedealTestEnv(t, 17)
	clone := env.game.CloneForBranch()
	before := renderEventHistory(clone.PublicEvents(), rootSeat, 128)
	if err := clone.RedealUnseen(rootSeat, 771); err != nil {
		t.Fatalf("redeal: %v", err)
	}
	after := renderEventHistory(clone.PublicEvents(), rootSeat, 128)
	if len(before) != len(after) {
		t.Fatalf("root history length changed: %d -> %d", len(before), len(after))
	}
	for i := range before {
		if before[i] != after[i] {
			t.Fatalf("root history changed at %d: 0x%08X -> 0x%08X", i, before[i], after[i])
		}
	}
}

// Non-root honesty: after the rewrite a non-root seat's OWN view shows
// UNKNOWN for its pre-redeal draws (its hand was redealt; the old faces are
// inconsistent and correlated with the live hidden world).
func TestRedealRewriteNonRootHonesty(t *testing.T) {
	env, rootSeat, nonRoot := buildRedealTestEnv(t, 17)
	clone := env.game.CloneForBranch()
	if err := clone.RedealUnseen(rootSeat, 772); err != nil {
		t.Fatalf("redeal: %v", err)
	}
	for i, event := range clone.PublicEvents() {
		if event.Type != engine.EventDraw {
			continue
		}
		if event.Seat == rootSeat {
			continue // root faces stay truthful — its hand is fixed across clones
		}
		if event.Face != -1 {
			t.Fatalf("event %d: non-root draw (seat %d) kept face %d after redeal", i, event.Seat, event.Face)
		}
	}
	// And the rendered self-view: every DRAW by nonRoot shows UNKNOWN.
	rendered := renderEventHistory(clone.PublicEvents(), nonRoot, 128)
	for i, packed := range rendered {
		if packed&0xF == uint32(engine.EventDraw) && (packed>>4)&0x3 == 0 {
			if face := (packed >> 6) & 0x3F; face != EventFaceUnknown {
				t.Fatalf("rendered %d: nonRoot's own pre-redeal draw shows face %d", i, face)
			}
		}
	}
	// Clone isolation: the LIVE game's log is untouched.
	liveHasFace := false
	for _, event := range env.game.PublicEvents() {
		if event.Type == engine.EventDraw && event.Seat != rootSeat && event.Face >= 0 {
			liveHasFace = true
			break
		}
	}
	if !liveHasFace {
		t.Fatalf("live log lost its faces — rewrite leaked into the parent")
	}
}

// Post-redeal appends render normally: a fresh draw logged in the clone
// after the rewrite keeps its face for the drawing seat.
func TestRedealRewriteDoesNotAffectNewEvents(t *testing.T) {
	env, rootSeat, _ := buildRedealTestEnv(t, 17)
	clone := env.game.CloneForBranch()
	if err := clone.RedealUnseen(rootSeat, 773); err != nil {
		t.Fatalf("redeal: %v", err)
	}
	preLen := len(clone.PublicEvents())
	if err := clone.ExecuteSystemDraw(clone.State.ActivePlayer); err != nil {
		t.Skipf("no draw available at this state: %v", err)
	}
	events := clone.PublicEvents()
	if len(events) <= preLen {
		t.Fatalf("draw appended no event")
	}
	last := events[len(events)-1]
	if last.Type != engine.EventDraw || last.Face < 0 {
		t.Fatalf("post-redeal draw event malformed: %+v", last)
	}
}
```

- [ ] **Step 2: Run to verify the honesty test fails**

Run: `go test ./internal/rl/ -run 'TestRedealRewrite' -count=1 -v`
Expected: `TestRedealRewriteRootInvariance` PASSES already (masking makes it invariant either way — it guards the rewrite's blast radius); `TestRedealRewriteNonRootHonesty` FAILS ("kept face ... after redeal"); `TestRedealRewriteDoesNotAffectNewEvents` may pass or skip. If the seed-17 premise fails, bump the seed and pin it.

- [ ] **Step 3: Implement the rewrite**

In `internal/engine/redeal.go`, immediately before the final `return nil` of `RedealUnseen`:

```go
	// Search honesty: this clone's non-acting seats just got NEW hands, but
	// the inherited event log still stores their true pre-redeal draw faces.
	// packPublicEvent unmasks a draw's face for the DRAWING seat itself, so a
	// rollout row encoded for a redealt seat would show faces inconsistent
	// with its new hand and correlated with the live hidden world. Erase
	// them; every other observer already saw these draws as unknown, so the
	// acting (root) seat's rendered history is unchanged (tested).
	for i := range g.publicEvents {
		if g.publicEvents[i].Type == EventDraw && g.publicEvents[i].Seat != actingSeat {
			g.publicEvents[i].Face = -1
		}
	}
	return nil
```

(Replacing the existing bare `return nil`.)

- [ ] **Step 4: Run the tests, then the affected suites**

Run: `go test ./internal/rl/ -run 'TestRedealRewrite' -count=1 -v` — all PASS (no skips left: if Step 2 skipped the append test, adjust its seed now).
Run: `go vet ./internal/engine/ ./internal/rl/ && go test ./internal/engine/ ./internal/rl/ -count=1` — PASS (searchpool suites must be untouched: search still rejects window>0 until Task 3).

- [ ] **Step 5: Commit**

```bash
git add internal/engine/redeal.go internal/rl/eventcodec_test.go
git commit -m "feat(engine): RedealUnseen erases non-root draw faces from the clone event log

A redealt seat's own pre-redeal draw faces are unmasked for that seat at
encode time — inconsistent with its new hand and correlated with the live
hidden world. Root-invariance test proves the rewrite removes exactly the
information the root could never see.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Proto — pool event buffers + trilingual regen

**Files:**
- Modify: `proto/game.proto` (`EnvPoolStepResponse`, after `action_space_size = 9`)
- Regenerate: `proto/game.pb.go`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`

**Interfaces:**
- Produces: `pb.EnvPoolStepResponse.EventHistories []byte`, `.EventCounts []byte`, `.EventHistoryWindow uint32` (Go); `event_histories`/`event_counts`/`event_history_window` (Python/TS).

- [ ] **Step 1: Edit proto/game.proto**

In `message EnvPoolStepResponse`, after `uint32 action_space_size = 9;`:

```proto
  // Flat event-history buffers for rows with has_observation, matching the
  // planes/scalars row order. event_histories: uint32 LE
  // [rows, event_history_window], tail-padded with zeros; event_counts:
  // uint32 LE [rows] true lengths (an explicit count is required — packed
  // value 0x0 is a VALID event, so padding alone is ambiguous). All three
  // empty when event_history_window == 0 (dormant, zero cost).
  bytes event_histories = 10;
  bytes event_counts = 11;
  uint32 event_history_window = 12;
```

- [ ] **Step 2: Regenerate all three languages**

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
uv run --project ai python -m grpc_tools.protoc --python_out=ai/src/fh_mahjong_ai/generated --proto_path=. proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

- [ ] **Step 3: Verify builds and suites**

```bash
go build ./... && go vet ./...
uv run --project ai python -c "from fh_mahjong_ai.generated.proto import game_pb2; r = game_pb2.EnvPoolStepResponse(event_history_window=128, event_counts=b'\x01\x00\x00\x00'); print(r.event_history_window, len(r.event_counts))"
cd web && npx tsc --noEmit && cd ..
go test ./... && uv run --project ai pytest
```
Expected: builds clean; Python prints `128 4`; both suites PASS (fields dormant).

- [ ] **Step 4: Commit**

```bash
git add proto/game.proto proto/game.pb.go ai/src/fh_mahjong_ai/generated web/src/proto/game.js web/src/proto/game.d.ts
git commit -m "feat(proto): flat event-history buffers on EnvPoolStepResponse (dormant)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Go — pool rows carry events; Go guards removed; positive tests

**Files:**
- Modify: `internal/rl/envpool.go` (`appendObservationRow` ~line 122, add `appendUint32LE` beside `appendFloat32LE`)
- Modify: `internal/rl/searchpool.go` (DELETE the `cfg.EventHistoryWindow > 0` guard block added in B1)
- Modify: `cmd/rlbridge/main.go` (DELETE the `request.GetConfig().GetEventHistoryWindow() > 0` guard in `FHEnvPoolNew`)
- Test: `internal/rl/eventcodec_test.go` (REPLACE `TestPoolsRejectEventHistoryWindow`; add positive tests)

**Interfaces:**
- Consumes: proto fields from Task 2; `EnvPool.ApplyCommands(*pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error)`; `NewSearchPool(...)`.
- Produces: pool responses whose `EventHistories`/`EventCounts`/`EventHistoryWindow` follow the fixed-width layout. Later tasks (Python decode) rely on exactly: rows in ascending-slot has_observation order, per-row stride `window` uint32s, count = true prefix length.

- [ ] **Step 1: Write the failing tests**

In `internal/rl/eventcodec_test.go`, DELETE `TestPoolsRejectEventHistoryWindow` entirely and add:

```go
// decodeEventRow pulls row i's true-length events from the flat buffers.
func decodeEventRow(t *testing.T, response *pb.EnvPoolStepResponse, row int) []uint32 {
	t.Helper()
	window := int(response.EventHistoryWindow)
	if window == 0 {
		t.Fatalf("response has no event window")
	}
	if len(response.EventCounts) < 4*(row+1) {
		t.Fatalf("event_counts too short for row %d", row)
	}
	count := int(binary.LittleEndian.Uint32(response.EventCounts[4*row:]))
	if count > window {
		t.Fatalf("row %d count %d exceeds window %d", row, count, window)
	}
	out := make([]uint32, count)
	base := 4 * row * window
	for i := 0; i < count; i++ {
		out[i] = binary.LittleEndian.Uint32(response.EventHistories[base+4*i:])
	}
	// Padding beyond count must be zeros.
	for i := count; i < window; i++ {
		if v := binary.LittleEndian.Uint32(response.EventHistories[base+4*i:]); v != 0 {
			t.Fatalf("row %d: nonzero padding 0x%08X at %d", row, v, i)
		}
	}
	return out
}

// Pool/single-env parity: same seed, same config, same actions — the pool's
// flat event row equals the single env's SeatObservation.EventHistory.
func TestEnvPoolEventRowsMatchSingleEnv(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
		EventHistoryWindow: 32,
	}
	single := New(config)
	sr, err := single.Reset(&pb.EnvResetRequest{Seed: 61, Config: config})
	if err != nil {
		t.Fatalf("single reset: %v", err)
	}
	pool := NewEnvPool(config, 1)
	resetResp, err := pool.ApplyCommands(&pb.EnvPoolStepRequest{Commands: []*pb.SlotCommand{
		{Slot: 0, Command: &pb.SlotCommand_ResetSeed{ResetSeed: 61}},
	}})
	if err != nil {
		t.Fatalf("pool reset: %v", err)
	}
	singleObs := sr.Observation
	poolResp := resetResp
	rng := rand.New(rand.NewSource(61))
	compared := 0
	for step := 0; step < 120 && singleObs != nil; step++ {
		if !poolResp.Slots[0].HasObservation {
			break
		}
		if poolResp.EventHistoryWindow != 32 {
			t.Fatalf("step %d: pool window %d", step, poolResp.EventHistoryWindow)
		}
		poolEvents := decodeEventRow(t, poolResp, 0)
		if len(poolEvents) != len(singleObs.EventHistory) {
			t.Fatalf("step %d: pool %d events, single %d", step, len(poolEvents), len(singleObs.EventHistory))
		}
		for i := range poolEvents {
			if poolEvents[i] != singleObs.EventHistory[i] {
				t.Fatalf("step %d event %d: pool 0x%08X single 0x%08X", step, i, poolEvents[i], singleObs.EventHistory[i])
			}
		}
		if len(poolEvents) > 0 {
			compared++
		}
		aid, ok := randomLegalActionID(singleObs.ActionMask, rng)
		if !ok {
			break
		}
		ssr, err := single.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil {
			t.Fatalf("single step: %v", err)
		}
		poolResp, err = pool.ApplyCommands(&pb.EnvPoolStepRequest{Commands: []*pb.SlotCommand{
			{Slot: 0, Command: &pb.SlotCommand_ActionId{ActionId: uint32(aid)}},
		}})
		if err != nil {
			t.Fatalf("pool step: %v", err)
		}
		if ssr.Terminated || ssr.Truncated {
			break
		}
		singleObs = ssr.Observation
	}
	if compared < 10 {
		t.Fatalf("premise: only %d nonempty comparisons — extend steps or change seed", compared)
	}
}

// Dormancy: window 0 leaves all three new response fields empty.
func TestEnvPoolEventBuffersDormantAtWindowZero(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       200,
	}
	pool := NewEnvPool(config, 1)
	resp, err := pool.ApplyCommands(&pb.EnvPoolStepRequest{Commands: []*pb.SlotCommand{
		{Slot: 0, Command: &pb.SlotCommand_ResetSeed{ResetSeed: 9}},
	}})
	if err != nil {
		t.Fatalf("pool reset: %v", err)
	}
	if len(resp.EventHistories) != 0 || len(resp.EventCounts) != 0 || resp.EventHistoryWindow != 0 {
		t.Fatalf("dormancy broken: hist=%d counts=%d window=%d",
			len(resp.EventHistories), len(resp.EventCounts), resp.EventHistoryWindow)
	}
}

// SearchPool accepts window>0 now (guard removed) and its clones share the
// same flat layout via appendObservationRow.
func TestSearchPoolAcceptsEventHistoryWindow(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
		EventHistoryWindow: 32,
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 5, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	if _, err := NewSearchPool(env, 2, 5, 64, 4); err != nil {
		t.Fatalf("NewSearchPool rejected window>0 after guard removal: %v", err)
	}
}
```

Check the actual `SlotCommand` oneof accessor names against `proto/game.pb.go` (`SlotCommand_ResetSeed`/`SlotCommand_ActionId` — if the generated names differ, e.g. plain fields not a oneof, use the same construction `envpool_test.go`'s `TestEnvPoolMatchesSingleEnv` uses; mirror that test's request-building style exactly). Add `"encoding/binary"` to the test imports.

- [ ] **Step 2: Run to verify failure**

Run: `go test ./internal/rl/ -run 'TestEnvPoolEvent|TestSearchPoolAccepts' -count=1 -v`
Expected: parity test FAILS (pool events empty — layout not implemented); dormancy PASSES; search-pool test FAILS (guard still present).

- [ ] **Step 3: Implement the layout + remove Go guards**

In `internal/rl/envpool.go`, extend `appendObservationRow` and add the helper:

```go
// appendObservationRow appends one observation's planes/scalars/mask — and,
// when event history is enabled, its count + tail-padded event row — to the
// flat little-endian response buffers, seeding the shared header dims on the
// first row. Shared by EnvPool and SearchPool so the flat-buffer layout stays
// identical across both pools.
func appendObservationRow(response *pb.EnvPoolStepResponse, obs *pb.SeatObservation) {
	if response.PlaneChannels == 0 {
		response.PlaneChannels = obs.PlaneChannels
		response.PlaneHeight = obs.PlaneHeight
		response.PlaneWidth = obs.PlaneWidth
		response.ScalarCount = uint32(len(obs.Scalars))
		response.ActionSpaceSize = obs.ActionSpaceSize
		response.EventHistoryWindow = obs.EventHistoryWindow
	}
	response.Planes = appendFloat32LE(response.Planes, obs.Planes)
	response.Scalars = appendFloat32LE(response.Scalars, obs.Scalars)
	response.ActionMasks = append(response.ActionMasks, obs.ActionMask...)
	if window := response.EventHistoryWindow; window > 0 {
		response.EventCounts = appendUint32LE(response.EventCounts, []uint32{uint32(len(obs.EventHistory))})
		response.EventHistories = appendUint32LE(response.EventHistories, obs.EventHistory)
		// Tail-pad the row to exactly `window` uint32 slots. Padding is
		// zeros and is never decoded: event_counts carries the true length
		// (packed 0x0 is a VALID event, so padding alone would be ambiguous).
		if pad := int(window) - len(obs.EventHistory); pad > 0 {
			response.EventHistories = append(response.EventHistories, make([]byte, 4*pad)...)
		}
	}
}

func appendUint32LE(dst []byte, values []uint32) []byte {
	off := len(dst)
	dst = append(dst, make([]byte, 4*len(values))...)
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], v)
	}
	return dst
}
```

(`encoding/binary` is already imported by envpool.go for `appendFloat32LE`.)
Note: `len(obs.EventHistory)` can never exceed `window` — `renderEventHistory` truncates — so no clamp is needed; the decoder still validates.

In `internal/rl/searchpool.go`, DELETE the whole B1 guard block:

```go
	if cfg.EventHistoryWindow > 0 {
		// ... (Spec B2) ...
		return nil, fmt.Errorf("search pool: event history is not supported (Spec B2)")
	}
```

In `cmd/rlbridge/main.go` (`FHEnvPoolNew`), DELETE:

```go
	// The pool's flat observation layout (appendObservationRow) carries only
	// planes/scalars/masks — it would silently DROP event history. Fail fast
	// until Spec B2 extends the layout.
	if request.GetConfig().GetEventHistoryWindow() > 0 {
		return 0
	}
```

- [ ] **Step 4: Run the tests, then the full Go suite**

Run: `go test ./internal/rl/ -run 'TestEnvPoolEvent|TestSearchPoolAccepts' -count=1 -v` — all PASS.
Run: `go vet ./... && go test ./...` — PASS.

- [ ] **Step 5: Commit**

```bash
git add internal/rl/envpool.go internal/rl/searchpool.go cmd/rlbridge/main.go internal/rl/eventcodec_test.go
git commit -m "feat(rl): flat pool rows carry event history; Go fail-fast guards removed

Fixed-width uint32 rows + explicit per-row counts (0x0 is a valid packed
event) via the shared appendObservationRow, so EnvPool and SearchPool stay
layout-identical by construction. Pool/single-env parity and dormancy
tests replace the B1 rejection test.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Python — pool decode, guard removal, positive tests

**Files:**
- Modify: `ai/src/fh_mahjong_ai/envpool.py` (PoolStepResult, `_empty_result`, both pool constructors, both `step` methods)
- Test: `ai/tests/test_events.py` (replace the two B1 rejection tests; add positive + synthetic-decode + gated tests)

**Interfaces:**
- Consumes: Task 2 proto fields; Task 3 layout semantics (ascending-slot row order, stride = window uint32s per row, count = true prefix).
- Produces: `PoolStepResult.event_histories: list[np.ndarray]` — one uint32 array of TRUE length per observation row (empty list when the window is 0). Both pools produce identical shapes. B2b's collectors consume this field.

- [ ] **Step 1: Write the failing tests**

In `ai/tests/test_events.py`: DELETE `test_env_pools_reject_event_history_window` entirely. In `test_go_pool_config_message_carries_window`, DELETE the rejection half (the `with pytest.raises(ValueError...)` on the GoEnvPool constructor) and KEEP the serializer half (the `_Stub` + `_config_message` assertion). Then add:

```python
def test_inprocess_pool_carries_event_histories():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import InProcessEnvPool, PoolCommand

    config = EnvConfig(bridge_kind="mock", event_history_window=16, seed=3)
    pool = InProcessEnvPool(config, slots=2)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=3), PoolCommand(slot=1, reset_seed=4)])
        rows = sum(1 for m in result.slots if m.has_observation)
        assert len(result.event_histories) == rows
        for row in result.event_histories:
            assert row.dtype == np.uint32
            assert 0 < row.size <= 16
            for event in decode_history(row):
                assert 0 <= event.type <= 7
    finally:
        pool.close()


def test_inprocess_pool_window_zero_has_empty_event_rows():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import InProcessEnvPool, PoolCommand

    pool = InProcessEnvPool(EnvConfig(bridge_kind="mock", seed=3), slots=1)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=3)])
        rows = sum(1 for m in result.slots if m.has_observation)
        assert len(result.event_histories) == rows
        assert all(row.size == 0 for row in result.event_histories)
    finally:
        pool.close()


def _synthetic_pool_response(window, rows_events, game_pb2, config):
    """Build an EnvPoolStepResponse with valid planes/scalars/masks for
    len(rows_events) rows plus the flat event buffers under test."""
    import struct

    channels, height, width = config.plane_shape
    rows = len(rows_events)
    response = game_pb2.EnvPoolStepResponse(
        plane_channels=channels,
        plane_height=height,
        plane_width=width,
        scalar_count=config.scalar_features,
        action_space_size=config.action_space_size,
        event_history_window=window,
        planes=b"\x00" * (4 * rows * channels * height * width),
        scalars=b"\x00" * (4 * rows * config.scalar_features),
        action_masks=b"\x00" * (rows * config.action_space_size),
    )
    counts = b""
    hist = b""
    for events in rows_events:
        counts += struct.pack("<I", len(events))
        hist += b"".join(struct.pack("<I", e) for e in events)
        hist += b"\x00" * (4 * (window - len(events)))
    response.event_counts = counts
    response.event_histories = hist
    for i in range(rows):
        slot = response.slots.add()
        slot.slot = i
        slot.has_observation = True
    return response


def test_go_pool_decode_synthetic_buffers():
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=4)

    class _Stub:
        env_config = config

    # Row 0's first event packs to 0x0 (a VALID event: self draw of face 0)
    # — the ambiguity case that forces explicit counts.
    response = _synthetic_pool_response(4, [[0x0, 0x140], [0x8B7, 0x32A3, 0xFE0]], game_pb2, config)
    result = GoEnvPool._decode_response(_Stub(), response)
    assert [row.tolist() for row in result.event_histories] == [[0x0, 0x140], [0x8B7, 0x32A3, 0xFE0]]

    # count > window must raise loudly.
    bad = _synthetic_pool_response(4, [[1, 2]], game_pb2, config)
    bad.event_counts = (5).to_bytes(4, "little")
    with pytest.raises(Exception, match="count|window"):
        GoEnvPool._decode_response(_Stub(), bad)

    # buffer-size mismatch must raise loudly.
    short = _synthetic_pool_response(4, [[1, 2]], game_pb2, config)
    short.event_histories = short.event_histories[:-4]
    with pytest.raises(Exception, match="event"):
        GoEnvPool._decode_response(_Stub(), short)


def test_go_pool_stale_bridge_window_mismatch_raises():
    from fh_mahjong_ai.bridge import BridgeError
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool
    from fh_mahjong_ai.generated.proto import game_pb2

    config = EnvConfig(bridge_kind="go", event_history_window=8)

    class _Stub:
        env_config = config

    stale = _synthetic_pool_response(0, [], game_pb2, config)
    stale.event_history_window = 0
    slot = stale.slots.add()
    slot.slot = 0
    slot.has_observation = True
    stale.planes = b"\x00" * (4 * 39 * 42 * 1)
    stale.scalars = b"\x00" * (4 * config.scalar_features)
    stale.action_masks = b"\x00" * config.action_space_size
    with pytest.raises(BridgeError, match="predates"):
        GoEnvPool._decode_response(_Stub(), stale)
```

And the FFI-gated end-to-end test (runs only when the built library exists):

```python
def test_go_pool_ffi_event_rows_match_single_env():
    from fh_mahjong_ai.bridge import build_bridge, resolve_bridge_library
    from fh_mahjong_ai.config import EnvConfig
    from fh_mahjong_ai.envpool import GoEnvPool, PoolCommand

    config = EnvConfig(bridge_kind="go", event_history_window=16, seed=21,
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False,
                       max_steps_per_episode=200)
    if not resolve_bridge_library(config).exists():
        pytest.skip("Go bridge library not built")

    single = build_bridge(config)
    pool = GoEnvPool(config, slots=1)
    try:
        obs = single.reset(seed=21)
        result = pool.step([PoolCommand(slot=0, reset_seed=21)])
        compared = 0
        for _ in range(60):
            if not result.slots[0].has_observation:
                break
            row = result.event_histories[result.row_of_slot[0]]
            assert row.tolist() == obs.event_history.tolist()
            if row.size > 0:
                compared += 1
            action = obs.legal_actions[0]
            step = single.step(action)
            result = pool.step([PoolCommand(slot=0, action_id=action)])
            if step.terminated or step.truncated:
                break
            obs = step.observation
        assert compared >= 5, "premise: too few nonempty comparisons"
    finally:
        pool.close()
        single.close()
```

This requires factoring `GoEnvPool.step`'s decode into a `_decode_response(self, response) -> PoolStepResult` method (Step 3) so the synthetic tests can drive it without FFI. NOTE for the FFI test: the local library must be rebuilt first (`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.$(uname | grep -qi darwin && echo dylib || echo so) ./cmd/rlbridge`) or the stale-bridge handshake will (correctly) raise — rebuild it as part of this task and note the artifact is gitignored.

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai pytest ai/tests/test_events.py -v`
Expected: new tests FAIL (`AttributeError: ... no attribute 'event_histories'` / `_decode_response`); the InProcess positive test fails on the still-present constructor guard.

- [ ] **Step 3: Implement**

In `ai/src/fh_mahjong_ai/envpool.py`:

1. DELETE the B1 guard block (the `raise ValueError("env pools do not carry event history yet...` lines) from BOTH `InProcessEnvPool.__init__` and `GoEnvPool.__init__`.

2. `PoolStepResult` gains the field (after `action_masks`):

```python
    event_histories: list[np.ndarray] = field(default_factory=list)  # per-row uint32, TRUE length
```

with `row_of_slot` keeping its existing position. Update `_empty_result` to pass `event_histories=[]`.

3. `InProcessEnvPool.step`: extend each `obs_rows.append((...))` tuple with `np.asarray(observation.event_history, dtype=np.uint32)` as a 6th element, and the final constructor with:

```python
            event_histories=[r[5] for r in obs_rows],
```

4. `GoEnvPool.step`: after `response.ParseFromString(raw)`, replace the inline decode with `return self._decode_response(response)`, moving the existing body into:

```python
    def _decode_response(self, response) -> PoolStepResult:
        metas: list[SlotMeta] = []
        live_slots: list[int] = []
        for state in response.slots:
            metas.append(SlotMeta(
                slot=int(state.slot),
                seat=int(state.seat),
                terminated=bool(state.terminated),
                truncated=bool(state.truncated),
                step_rewards=np.asarray(state.step_rewards, dtype=np.float32),
                has_observation=bool(state.has_observation),
                error=str(state.error),
            ))
            if state.has_observation:
                live_slots.append(int(state.slot))
        rows = len(live_slots)
        requested_window = int(self.env_config.event_history_window)
        if rows > 0 and requested_window > 0 and int(response.event_history_window) != requested_window:
            raise BridgeError(
                f"pool returned event_history_window={int(response.event_history_window)} "
                f"but the client requested {requested_window} — the Go bridge library predates "
                "pool event history; rebuild it (go build -buildmode=c-shared ./cmd/rlbridge)"
            )
        if rows == 0:
            return _empty_result(self.env_config, metas)
        channels, height, width = (int(response.plane_channels), int(response.plane_height),
                                   int(response.plane_width))
        planes = np.frombuffer(response.planes, dtype="<f4").reshape(rows, channels, height, width)
        scalars = np.frombuffer(response.scalars, dtype="<f4").reshape(rows, int(response.scalar_count))
        masks = np.frombuffer(response.action_masks, dtype=np.uint8).astype(np.int8, copy=False)
        masks = masks.reshape(rows, int(response.action_space_size))

        event_histories: list[np.ndarray] = []
        window = int(response.event_history_window)
        if window > 0:
            counts = np.frombuffer(response.event_counts, dtype="<u4")
            if counts.size != rows:
                raise BridgeError(f"event_counts has {counts.size} rows, expected {rows}")
            flat = np.frombuffer(response.event_histories, dtype="<u4")
            if flat.size != rows * window:
                raise BridgeError(
                    f"event_histories has {flat.size} uint32s, expected rows*window={rows * window}"
                )
            grid = flat.reshape(rows, window)
            for i in range(rows):
                count = int(counts[i])
                if count > window:
                    raise BridgeError(f"row {i} event count {count} exceeds window {window}")
                event_histories.append(grid[i, :count].copy())
        else:
            event_histories = [np.zeros(0, dtype=np.uint32) for _ in range(rows)]

        return PoolStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            event_histories=event_histories,
            row_of_slot={slot: i for i, slot in enumerate(live_slots)},
        )
```

`BridgeError` is already imported in envpool.py (check the imports; add `from .bridge import BridgeError` if not).

- [ ] **Step 4: Run tests, then the full suite**

Run: `uv run --project ai pytest ai/tests/test_events.py ai/tests/test_envpool.py -v` — all PASS.
Run: `uv run --project ai pytest` — all PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/envpool.py ai/tests/test_events.py
git commit -m "feat(ai): pool results carry per-row event histories; Python guards removed

GoEnvPool decodes the fixed-width buffers into true-length uint32 rows
(count/size validation raises loudly; stale-bridge window handshake, pool
edition); InProcessEnvPool passes bridge histories through — identical
per-row shapes. B1 rejection tests replaced by positive + synthetic-decode
tests, including the 0x0-first-event ambiguity case.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Docs sweep + whole-branch verification

**Files:**
- Modify: `internal/rl/AGENTS.md` (envpool: event-row layout note; searchpool: guard gone, redeal rewrite note)
- Modify: `ai/AGENTS.md` (envpool.py: event_histories field, handshake)
- Modify: `cmd/rlbridge/AGENTS.md` (only if it mentions the removed guard — check)
- Modify: `internal/engine/AGENTS.md` (events.go bullet: add the RedealUnseen rewrite sentence)

- [ ] **Step 1: Update the four AGENTS.md files**

- `internal/engine/AGENTS.md` events.go bullet: append — "`RedealUnseen` erases non-root DRAW faces from the clone's log (search honesty; root-invariance tested in internal/rl)."
- `internal/rl/AGENTS.md`: envpool bullet gains the flat event-row layout (fixed-width uint32 rows + explicit counts because 0x0 is a valid event; shared appendObservationRow keeps EnvPool/SearchPool identical; dormant at window 0); searchpool/eventcodec notes drop any mention of the removed fail-fast guard.
- `ai/AGENTS.md`: envpool.py entry gains `PoolStepResult.event_histories` (per-row true-length uint32) + the pool stale-bridge handshake.
- `cmd/rlbridge/AGENTS.md`: grep for the guard mention; update or leave untouched accordingly.

- [ ] **Step 2: Full verification**

```bash
go vet ./... && go test ./...
uv run --project ai pytest
cd web && npx tsc --noEmit && cd ..
grep -rn "event history is not supported\|do not carry event history\|would silently DROP" internal/ cmd/ ai/src/ && echo "GUARD REMNANT FOUND" || echo "guards fully removed"
git diff origin/main --stat
```
Expected: suites clean; "guards fully removed"; diff touches only the files this plan names (plus spec/plan docs).

- [ ] **Step 3: Commit**

```bash
git add internal/engine/AGENTS.md internal/rl/AGENTS.md ai/AGENTS.md cmd/rlbridge/AGENTS.md
git commit -m "docs: B2a AGENTS.md sweep — event rows at scale, guards retired

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(Stage only the AGENTS.md files actually modified.)

Then: final whole-branch review → adversarial-review-loop → PR → GitHub Codex approval → `gh pr merge N --merge`.
