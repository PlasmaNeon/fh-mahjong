# Search-Teacher Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `fh-mj-search-diagnostic`, which measures whether belief-weighted determinized search scored by the
privileged critic beats the suit-averaged policy's choice at contested discard decisions, against true-state
ground truth.

**Architecture:** Three options on the existing Go `SearchPool` (oracle planes on re-dealt clones, true-state
clones, explicit world ids) plus a root-observation export; Python adds belief importance weights and a driver
that self-plays, clones each contested state into pools, rolls candidates out with batched forwards, and
summarizes 12 decision rules with game-clustered CIs.

**Tech Stack:** Go 1.25, protobuf (protoc-gen-go, protobufjs, standalone protoc 33.5 for Python), Python 3 +
PyTorch via `uv run --project ai`.

**Spec:** `worklog/specs/20261005-search-teacher-diagnostic.md`

## Global Constraints

- Default `SearchPool` behaviour is unchanged: every existing Go and Python search test passes as is.
- A re-dealt clone's root observation without oracle planes is byte-identical to the live env's.
- `true_state` together with `oracle_planes` is refused; an oracle-configured live env is still refused.
- Policy `f9662491`; baseline = its suit-averaged greedy choice; rollouts = its plain greedy policy in all seats.
- States: contested discard decisions (second-best suit-averaged discard probability ≥ 0.10), every 5th kept,
  4,000 states, self-play seeds 910,000+.
- Search: 32 worlds per candidate, top-3 candidates, samplers {uniform, belief-resampled from 256},
  horizons {next root decision + γ·V_privileged, end of hand}, margins z ∈ {0, 1, 2}; γ = 0.99.
- Primary rule: (belief, next, z = 1); go iff its game-clustered CI95 lower bound > 0; other rules at
  Bonferroni α = 0.05/11.
- Python protobuf gencode keeps the header `Protobuf Python Version: 6.33.5` (standalone protoc 33.5).
- CI gates: `gofmt -l .` empty, `go vet ./...`, `go test ./...`, `cd web && npx tsc && npx vitest run`,
  `uv run --project ai pytest -q ai/tests` with `FH_MAHJONG_BRIDGE_LIB` set.

## Review Focus

1. A clone erroring mid-rollout must stop the diagnostic with the error, not silently score 0 — pinned in Task 5.
2. The belief sampler's resampled world ids must be the same worlds the weighting pool scored (same pool seed,
   same ids) — pinned in Task 3.
3. A state whose hand ends before the root's next decision must still get a value at the next hand's root decision
   (next horizon) and stop at the hand end (hand horizon) — pinned in Task 5.
4. Δ must be exactly 0 for every rule that keeps candidate 0 — pinned in Task 5.
5. `GoSearchPool` with oracle planes must decode 51-channel rows without tripping the plane-count check — pinned
   in Task 3.

---

### Task 1: Proto fields and bindings

**Files:**
- Modify: `proto/game.proto` (message `SearchPoolNewRequest`, after field 5)
- Regenerate: `proto/game.pb.go`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`,
  `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`
- Modify: `proto/CLAUDE.md`

**Interfaces:**
- Produces: `SearchPoolNewRequest.oracle_planes` (bool, 6), `.true_state` (bool, 7),
  `.determinization_ids` (repeated uint64, 8).

- [ ] **Step 1: Write the failing check**

```bash
uv run --project ai python -c "from fh_mahjong_ai.generated.proto import game_pb2 as pb; pb.SearchPoolNewRequest(oracle_planes=True)"
```

Expected: `ValueError: Protocol message SearchPoolNewRequest has no "oracle_planes" field.`

- [ ] **Step 2: Add the fields**

```proto
  // Clones emit oracle observations (the opponents' re-dealt hands). Allowed
  // because a re-dealt clone's hidden state is a sample, not the true hands.
  bool oracle_planes = 6;
  // Clones keep the live wall and hands (no RedealUnseen): ground truth for
  // diagnostics only. Refused together with oracle_planes.
  bool true_state = 7;
  // When set, clone i re-deals world determinization_ids[i % len]; overrides
  // the k = i % determinizations assignment (seeds still derive from seed, id).
  repeated uint64 determinization_ids = 8;
```

- [ ] **Step 3: Regenerate**

```bash
protoc --plugin=protoc-gen-go=$(go env GOPATH)/bin/protoc-gen-go --go_out=. --go_opt=paths=source_relative proto/game.proto
P=/Users/plasma/fh-mahjong/web/node_modules/.bin
$P/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
$P/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
/private/tmp/claude-501/-Users-plasma-fh-mahjong/fc7fd8c5-80df-4702-8eb9-e6ecda1939a0/scratchpad/protoc335/bin/protoc \
  --python_out=ai/src/fh_mahjong_ai/generated --proto_path=. proto/game.proto
head -5 ai/src/fh_mahjong_ai/generated/proto/game_pb2.py | tail -1
```

Expected: `# Protobuf Python Version: 6.33.5`. (If the scratchpad protoc is gone, download
`protoc-33.5-osx-aarch_64.zip` from the protobuf v33.5 release and use its `bin/protoc`.)

- [ ] **Step 4: Verify**

Run Step 1's command again and `go build ./...`. Expected: no error.

- [ ] **Step 5: Document and commit**

Add to `proto/CLAUDE.md`'s `SearchPoolNewRequest` bullet: "`oracle_planes` (6), `true_state` (7, refused with
oracle_planes), `determinization_ids` (8) — diagnostic options; defaults keep the July behaviour."

```bash
git add proto/ web/src/proto/ ai/src/fh_mahjong_ai/generated/proto/game_pb2.py
git commit -m "feat(proto): search pool diagnostic options"
```

---

### Task 2: Go search pool options and root observations

**Files:**
- Modify: `internal/rl/searchpool.go`
- Modify: `cmd/rlbridge/main.go` (`FHSearchPoolNew`; new `FHSearchPoolRoot`)
- Test: `internal/rl/searchpool_options_test.go` (create)
- Modify: `internal/rl/CLAUDE.md`, `cmd/rlbridge/CLAUDE.md`

**Interfaces:**
- Consumes: Task 1 fields.
- Produces: `type SearchPoolOptions struct { OraclePlanes bool; TrueState bool; DeterminizationIDs []uint64 }`;
  `NewSearchPoolWithOptions(e *Env, clones int, seed uint64, maxRolloutDecisions uint64, determinizations uint32, opts SearchPoolOptions, rootSeat ...uint32) (*SearchPool, error)`;
  `(*SearchPool).RootObservations() (*pb.EnvPoolStepResponse, error)`; FFI
  `FHSearchPoolRoot(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult`.

- [ ] **Step 1: Write the failing tests**

Create `internal/rl/searchpool_options_test.go`:

```go
package rl

import (
	"bytes"
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func rootRowBytes(t *testing.T, obs *pb.SeatObservation) []byte {
	t.Helper()
	packed := &pb.EnvPoolStepResponse{}
	appendObservationRow(packed, obs)
	return packed.Planes
}

func TestSearchPoolRootObservationsMatchTheLivePublicView(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, live := currentDecision(t, env)
	pool, err := NewSearchPoolWithOptions(env, 4, 99, 512, 0, SearchPoolOptions{})
	if err != nil {
		t.Fatal(err)
	}
	resp, err := pool.RootObservations()
	if err != nil {
		t.Fatal(err)
	}
	want := bytes.Repeat(rootRowBytes(t, live), 4)
	if !bytes.Equal(resp.Planes, want) {
		t.Fatalf("re-dealt clones' public root view differs from the live view")
	}
	if len(resp.Slots) != 4 || resp.Slots[3].Seat != seat || !resp.Slots[3].HasObservation {
		t.Fatalf("root slots %+v", resp.Slots)
	}
}

func TestSearchPoolOraclePlanesShowTheRedealtHands(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, live := currentDecision(t, env)
	pool, err := NewSearchPoolWithOptions(env, 4, 99, 512, 0, SearchPoolOptions{OraclePlanes: true})
	if err != nil {
		t.Fatal(err)
	}
	resp, err := pool.RootObservations()
	if err != nil {
		t.Fatal(err)
	}
	if resp.PlaneChannels != 51 {
		t.Fatalf("plane channels %d, want 51", resp.PlaneChannels)
	}
	public := rootRowBytes(t, live)
	rowBytes := 51 * ObservationPlaneHeight * 4
	trueOracle, err := encodeObservation(env.game.State, seat, env.decisionCount, true, 0, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	differsFromTruth := false
	for i := 0; i < 4; i++ {
		row := resp.Planes[i*rowBytes : (i+1)*rowBytes]
		if !bytes.Equal(row[:len(public)], public) {
			t.Fatalf("clone %d public block differs from the live view", i)
		}
		want, err := encodeObservation(pool.clones[i].env.game.State, seat, env.decisionCount, true, 0, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(row, rootRowBytes(t, want)) {
			t.Fatalf("clone %d oracle block is not its own re-dealt hands", i)
		}
		differsFromTruth = differsFromTruth || !bytes.Equal(row, rootRowBytes(t, trueOracle))
	}
	if !differsFromTruth {
		t.Fatalf("every clone showed the true hands; re-deal did not happen")
	}
}

func TestSearchPoolTrueStateRefusesOraclePlanesAndKeepsTheRealHands(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)
	if _, err := NewSearchPoolWithOptions(env, 2, 1, 64, 0, SearchPoolOptions{TrueState: true, OraclePlanes: true}); err == nil {
		t.Fatalf("true_state with oracle_planes must be refused")
	}
	pool, err := NewSearchPoolWithOptions(env, 2, 1, 64, 0, SearchPoolOptions{TrueState: true})
	if err != nil {
		t.Fatal(err)
	}
	for _, opp := range opponentSeats(seat) {
		live := handTileIDs(env.game.State.Players[opp].ClosedHand)
		for i := 0; i < 2; i++ {
			if !idsEqual(handTileIDs(pool.clones[i].env.game.State.Players[opp].ClosedHand), live) {
				t.Fatalf("true-state clone %d changed seat %d's hand", i, opp)
			}
		}
	}
}

func TestSearchPoolTrueStateRolloutMatchesTheLiveEnv(t *testing.T) {
	env := newStartedEnv(t, 4242)
	pool, err := NewSearchPoolWithOptions(env, 1, 1, 4000, 0, SearchPoolOptions{TrueState: true})
	if err != nil {
		t.Fatal(err)
	}
	_, liveObs := currentDecision(t, env)
	action := firstLegal(liveObs.ActionMask)
	for step := 0; step < 25; step++ {
		resp, err := pool.Step(&pb.EnvPoolStepRequest{Commands: []*pb.SlotCommand{
			{Slot: 0, Cmd: &pb.SlotCommand_ActionId{ActionId: action}}}})
		if err != nil {
			t.Fatal(err)
		}
		live, err := env.Step(&pb.EnvStepRequest{ActionId: action})
		if err != nil {
			t.Fatal(err)
		}
		slot := resp.Slots[0]
		if slot.RoundOutcome != nil || slot.Terminated || live.Terminated {
			return // the hand ended; ground truth stops here
		}
		if !bytes.Equal(resp.Planes, rootRowBytes(t, live.Observation)) {
			t.Fatalf("step %d: true-state clone diverged from the live env", step)
		}
		action = firstLegal(live.Observation.ActionMask)
	}
}

func TestSearchPoolDeterminizationIDsReproduceWorlds(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)
	a, err := NewSearchPoolWithOptions(env, 3, 7, 64, 0, SearchPoolOptions{DeterminizationIDs: []uint64{5, 9, 5}})
	if err != nil {
		t.Fatal(err)
	}
	b, err := NewSearchPoolWithOptions(env, 2, 7, 64, 0, SearchPoolOptions{DeterminizationIDs: []uint64{9, 5}})
	if err != nil {
		t.Fatal(err)
	}
	plain, err := NewSearchPool(env, 10, 7, 64, 10)
	if err != nil {
		t.Fatal(err)
	}
	hands := func(p *SearchPool, i int) [][]uint32 {
		out := [][]uint32{}
		for _, opp := range opponentSeats(seat) {
			out = append(out, handTileIDs(p.clones[i].env.game.State.Players[opp].ClosedHand))
		}
		return out
	}
	same := func(x, y [][]uint32) bool {
		for i := range x {
			if !idsEqual(x[i], y[i]) {
				return false
			}
		}
		return true
	}
	if !same(hands(a, 0), hands(a, 2)) || !same(hands(a, 0), hands(b, 1)) || !same(hands(a, 1), hands(b, 0)) {
		t.Fatalf("the same world id gave different worlds")
	}
	if !same(hands(a, 0), hands(plain, 5)) || !same(hands(a, 1), hands(plain, 9)) {
		t.Fatalf("world id k must equal the default pool's world k")
	}
	if same(hands(a, 0), hands(a, 1)) {
		t.Fatalf("different world ids gave the same world")
	}
}
```

`firstLegal(mask []byte) uint32` already exists in `envpool_test.go` (same package); reuse it.

- [ ] **Step 2: Run them to verify they fail**

Run: `go test ./internal/rl -run 'SearchPool(Root|Oracle|TrueState|DeterminizationIDs)' -count=1`
Expected: FAIL to compile — `undefined: NewSearchPoolWithOptions`.

- [ ] **Step 3: Implement in `searchpool.go`**

Add the field `oracle bool` to `SearchPool`, and above `NewSearchPool`:

```go
// SearchPoolOptions extends NewSearchPool for the search-teacher diagnostic
// (worklog/specs/20261005-search-teacher-diagnostic.md). The zero value is the
// July behaviour.
type SearchPoolOptions struct {
	// OraclePlanes makes every clone row carry the opponents' hands, which in a
	// re-dealt clone are samples, never the true hands.
	OraclePlanes bool
	// TrueState keeps the live wall and hands (no RedealUnseen): ground truth
	// only, and refused together with OraclePlanes.
	TrueState bool
	// DeterminizationIDs, when set, gives clone i world DeterminizationIDs[i % len].
	DeterminizationIDs []uint64
}
```

Turn the body of `NewSearchPool` into `NewSearchPoolWithOptions` with the extra `opts SearchPoolOptions`
parameter before `rootSeat`, and make `NewSearchPool` a one-line delegate passing `SearchPoolOptions{}`. In the
new body, right after the oracle-env check:

```go
	if opts.TrueState && opts.OraclePlanes {
		return nil, fmt.Errorf("search pool: true_state clones cannot emit oracle planes")
	}
```

set `p := &SearchPool{config: cfg, maxDec: maxRolloutDecisions, rootSeat: seat, oracle: opts.OraclePlanes}`, and in
the clone loop:

```go
		k := uint64(uint32(i) % determinizations)
		if len(opts.DeterminizationIDs) > 0 {
			k = opts.DeterminizationIDs[i%len(opts.DeterminizationIDs)]
		}
		g := e.game.CloneForBranch()
		if g == nil {
			return nil, fmt.Errorf("search pool: clone %d failed", i)
		}
		if !opts.TrueState {
			if err := g.RedealUnseen(seat, seed*1000003+k); err != nil {
				return nil, err
			}
		}
```

Replace the `false` oracle argument with `p.oracle` in the three `encodeObservation` calls inside `advanceClone`
and in `cloneObservationForTest`. Add:

```go
// RootObservations encodes every clone's root-seat observation before any
// step: one row per clone, slot i = clone i.
func (p *SearchPool) RootObservations() (*pb.EnvPoolStepResponse, error) {
	response := &pb.EnvPoolStepResponse{}
	for i, clone := range p.clones {
		obs, err := encodeObservation(clone.env.game.State, p.rootSeat, clone.env.decisionCount, p.oracle,
			clone.env.config.LookaheadVersion, clone.env.game.PublicEvents(), clone.env.config.EventHistoryWindow)
		if err != nil {
			return nil, err
		}
		response.Slots = append(response.Slots, &pb.SlotState{Slot: uint32(i), Seat: p.rootSeat, HasObservation: true})
		appendObservationRow(response, obs)
	}
	return response, nil
}
```

- [ ] **Step 4: Wire the FFI (`cmd/rlbridge/main.go`)**

In `FHSearchPoolNew`, build options and call the new constructor in both branches:

```go
	opts := rl.SearchPoolOptions{
		OraclePlanes:       request.GetOraclePlanes(),
		TrueState:          request.GetTrueState(),
		DeterminizationIDs: request.GetDeterminizationIds(),
	}
	var pool *rl.SearchPool
	if request.RootSeat != nil {
		pool, err = rl.NewSearchPoolWithOptions(env, int(request.GetClones()), request.GetSeed(), uint64(request.GetMaxRolloutDecisions()), request.GetDeterminizations(), opts, request.GetRootSeat())
	} else {
		pool, err = rl.NewSearchPoolWithOptions(env, int(request.GetClones()), request.GetSeed(), uint64(request.GetMaxRolloutDecisions()), request.GetDeterminizations(), opts)
	}
```

Add after `FHSearchPoolStep`:

```go
//export FHSearchPoolRoot
func FHSearchPoolRoot(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	searchPoolMu.Lock()
	pool, ok := searchPools[uint64(handle)]
	searchPoolMu.Unlock()
	if !ok {
		return errorResult(errors.New("invalid search pool handle"))
	}
	response, err := pool.RootObservations()
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}
```

- [ ] **Step 5: Run the tests**

Run: `gofmt -l internal cmd && go vet ./internal/rl ./cmd/... && go test ./internal/rl -count=1`
Expected: gofmt prints nothing; all tests PASS, including every existing `TestSearchPool_*`.

- [ ] **Step 6: Document and commit**

`internal/rl/CLAUDE.md` searchpool bullet: "`NewSearchPoolWithOptions` / `SearchPoolOptions` (OraclePlanes,
TrueState, DeterminizationIDs) and `RootObservations()` serve the search-teacher diagnostic; TrueState is refused
with OraclePlanes." `cmd/rlbridge/CLAUDE.md`: add `FHSearchPoolRoot`.

```bash
git add internal/rl/ cmd/rlbridge/
git commit -m "feat(rl): search pool oracle planes, true state, world ids and root observations"
```

---

### Task 3: Python search pool options

**Files:**
- Modify: `ai/src/fh_mahjong_ai/searchpool.py`
- Test: `ai/tests/test_searchpool.py` (append)

**Interfaces:**
- Consumes: Task 2 FFI.
- Produces: `GoSearchPool(bridge, clones, seed, max_rollout_decisions, determinizations=0, root_seat=None, oracle_planes=False, true_state=False, determinization_ids=())`;
  `GoSearchPool.root_observations() -> PoolStepResult`.

- [ ] **Step 1: Write the failing test**

```python
@requires_go_lib
def test_go_search_pool_diagnostic_options():
    from fh_mahjong_ai.bridge import BridgeError, CtypesGoBridge
    from fh_mahjong_ai.searchpool import GoSearchPool

    config = _chongci_config()
    with CtypesGoBridge(config) as bridge:
        live = bridge.reset(seed=101)
        pool = GoSearchPool(bridge, clones=4, seed=7, max_rollout_decisions=64, oracle_planes=True,
                            root_seat=live.seat)
        roots = pool.root_observations()
        pool.close()
        assert roots.planes.shape == (4, 51, 42, 1)
        assert np.array_equal(roots.planes[:, :39], np.repeat(live.planes[None], 4, axis=0))
        with pytest.raises(BridgeError):
            GoSearchPool(bridge, clones=2, seed=7, max_rollout_decisions=64, oracle_planes=True, true_state=True)
        truth = GoSearchPool(bridge, clones=2, seed=7, max_rollout_decisions=64, true_state=True)
        assert truth.root_observations().planes.shape == (2, 39, 42, 1)
        truth.close()
        weigh = GoSearchPool(bridge, clones=8, seed=7, max_rollout_decisions=64, oracle_planes=True)
        worlds = weigh.root_observations().planes
        weigh.close()
        picked = GoSearchPool(bridge, clones=2, seed=7, max_rollout_decisions=64, oracle_planes=True,
                              determinization_ids=[6, 3])
        again = picked.root_observations().planes
        picked.close()
        assert np.array_equal(again[0], worlds[6]) and np.array_equal(again[1], worlds[3])
```

- [ ] **Step 2: Run it to verify it fails**

```bash
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_searchpool.py -k diagnostic_options
```

Expected: FAIL — `TypeError: GoSearchPool.__init__() got an unexpected keyword argument 'oracle_planes'`.

- [ ] **Step 3: Implement**

Signature and request:

```python
    def __init__(self, bridge: CtypesGoBridge, clones: int, seed: int, max_rollout_decisions: int,
                 determinizations: int = 0, root_seat: int | None = None, oracle_planes: bool = False,
                 true_state: bool = False, determinization_ids: Sequence[int] = ()) -> None:
        if clones < 1:
            raise ValueError("clones must be >= 1")
        # Rows carry 51 channels when clones emit oracle planes; the shared
        # decoder checks the channel count against env_config.
        self.env_config = (dataclasses.replace(bridge.config, oracle_observation=True)
                           if oracle_planes else bridge.config)
```

(add `import dataclasses`), then on the request:

```python
            oracle_planes=bool(oracle_planes),
            true_state=bool(true_state),
            determinization_ids=[int(i) for i in determinization_ids],
```

Signature setup in `_configure_signatures`:

```python
        self._library.FHSearchPoolRoot.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHSearchPoolRoot.restype = FHBytesResult
```

and the method:

```python
    def root_observations(self) -> PoolStepResult:
        """Every clone's root-seat observation before any step (slot i = clone i)."""
        raw = self._call_bytes(self._library.FHSearchPoolRoot, self._handle, b"")
        response = game_pb2.EnvPoolStepResponse()
        response.ParseFromString(raw)
        return GoEnvPool._decode_response(self, response)
```

- [ ] **Step 4: Run the search tests**

Run: `FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_searchpool.py ai/tests/test_search.py ai/tests/test_search_eval.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/searchpool.py ai/tests/test_searchpool.py
git commit -m "feat(ai): GoSearchPool diagnostic options and root observations"
```

---

### Task 4: Belief importance weights

**Files:**
- Create: `ai/src/fh_mahjong_ai/belief_weights.py`
- Test: `ai/tests/test_belief_weights.py` (create)

**Interfaces:**
- Produces: `world_log_likelihoods(belief_logits: torch.Tensor, oracle_planes: np.ndarray) -> np.ndarray`
  (logits `[12, 42]`, planes `[n, 12, 42, 1]`, result `[n]` float64);
  `normalized_weights(log_likelihoods: np.ndarray) -> np.ndarray`;
  `effective_sample_size(weights: np.ndarray) -> float`;
  `systematic_resample(weights: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray` (int64 indices).

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import torch
import torch.nn.functional as F

from fh_mahjong_ai.belief_weights import (effective_sample_size, normalized_weights, systematic_resample,
                                          world_log_likelihoods)


def test_log_likelihood_is_minus_the_heads_summed_training_bce():
    rng = np.random.default_rng(0)
    logits = torch.from_numpy(rng.normal(size=(12, 42)).astype(np.float32))
    planes = (rng.random((3, 12, 42, 1)) > 0.7).astype(np.float32)
    ll = world_log_likelihoods(logits, planes)
    for i in range(3):
        target = torch.from_numpy(planes[i, :, :, 0])
        bce = F.binary_cross_entropy_with_logits(logits, target, reduction="sum")
        assert abs(ll[i] + float(bce)) < 1e-3


def test_weights_ess_and_systematic_resampling():
    w = normalized_weights(np.array([0.0, 0.0, 0.0, 0.0]))
    assert np.allclose(w, 0.25) and abs(effective_sample_size(w) - 4.0) < 1e-9
    assert sorted(systematic_resample(w, 4, np.random.default_rng(1)).tolist()) == [0, 1, 2, 3]
    peaked = normalized_weights(np.array([-50.0, 0.0, -50.0]))
    assert systematic_resample(peaked, 5, np.random.default_rng(2)).tolist() == [1] * 5
    assert effective_sample_size(peaked) < 1.01
    a = systematic_resample(w, 4, np.random.default_rng(3))
    b = systematic_resample(w, 4, np.random.default_rng(3))
    assert np.array_equal(a, b)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest -q ai/tests/test_belief_weights.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'fh_mahjong_ai.belief_weights'`.

- [ ] **Step 3: Implement**

```python
"""Belief-head importance weights for re-dealt worlds (search-teacher diagnostic).

A world's weight is its likelihood under the belief head at the root: the Bernoulli likelihood of its opponent
threshold planes, the target the head trains on (ppo.py belief loss). Self-normalized, then resampled.
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F


def world_log_likelihoods(belief_logits: torch.Tensor, oracle_planes: np.ndarray) -> np.ndarray:
    """Log-likelihood of each world's opponent threshold planes [n, 12, 42, 1] under logits [12, 42]."""
    target = torch.from_numpy((np.asarray(oracle_planes)[..., 0] > 0).astype(np.float32)).to(belief_logits.device)
    logits = belief_logits.float().unsqueeze(0).expand_as(target)
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none").sum(dim=(1, 2))
    return (-bce).double().cpu().numpy()


def normalized_weights(log_likelihoods: np.ndarray) -> np.ndarray:
    ll = np.asarray(log_likelihoods, dtype=np.float64)
    w = np.exp(ll - ll.max())
    return w / w.sum()


def effective_sample_size(weights: np.ndarray) -> float:
    w = np.asarray(weights, dtype=np.float64)
    return float(1.0 / np.sum(w * w))


def systematic_resample(weights: np.ndarray, count: int, rng: np.random.Generator) -> np.ndarray:
    positions = (rng.random() + np.arange(count)) / count
    cumulative = np.cumsum(np.asarray(weights, dtype=np.float64))
    cumulative[-1] = 1.0
    return np.searchsorted(cumulative, positions, side="right").astype(np.int64)
```

- [ ] **Step 4: Run them**

Run: `uv run --project ai pytest -q ai/tests/test_belief_weights.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/belief_weights.py ai/tests/test_belief_weights.py
git commit -m "feat(ai): belief-head importance weights for re-dealt worlds"
```

---

### Task 5: Diagnostic core

**Files:**
- Create: `ai/src/fh_mahjong_ai/search_diagnostic.py`
- Test: `ai/tests/test_search_diagnostic.py` (create)

**Interfaces:**
- Consumes: Task 3 `GoSearchPool`, Task 4 functions, `suit_symmetry.suit_averaged_log_probs`,
  `evaluate._t_critical_975`.
- Produces: `DiagnosticConfig`; `Forward(model, device)`; `play_out(pool, forward, actions, root_seat, horizon, gamma) -> np.ndarray`;
  `rule_choice(scores: np.ndarray, z: float) -> int`; `clustered_mean_ci(deltas, clusters, critical) -> tuple[float, float]`;
  `run_diagnostic(bridge, forward, cfg, states, seed_base, sink) -> None`; `summarize(records) -> dict`;
  `RULES` (12 keys `(sampler, horizon, z)`), `PRIMARY = ("belief", "next", 1.0)`.

- [ ] **Step 1: Write the failing tests**

```python
import os

import numpy as np
import pytest
import torch

from conftest import SMALL_MODEL
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.search_diagnostic import (PRIMARY, RULES, DiagnosticConfig, Forward, clustered_mean_ci,
                                             rule_choice, run_diagnostic, summarize)

requires_go_lib = pytest.mark.skipif(
    not os.environ.get("FH_MAHJONG_BRIDGE_LIB"), reason="needs the Go bridge library")


def test_rule_keeps_greedy_unless_the_paired_gain_clears_the_margin():
    scores = np.array([[0.0, 0.0, 0.0, 0.0], [0.1, 0.1, 0.1, 0.1], [0.5, -0.5, 0.5, -0.5]])
    assert rule_choice(scores, 0.0) == 1          # best mean, constant gain
    assert rule_choice(scores, 2.0) == 1          # zero-variance gain clears any margin
    noisy = np.array([[0.0, 0.0, 0.0, 0.0], [0.4, -0.3, 0.2, -0.2]])
    assert rule_choice(noisy, 0.0) == 1 and rule_choice(noisy, 1.0) == 0
    assert rule_choice(np.array([[0.2, 0.2], [0.1, 0.1]]), 0.0) == 0


def test_clustered_ci_and_summary_count_deltas_and_overrides():
    mean, half = clustered_mean_ci(np.array([1.0, 1.0, -1.0, -1.0]), np.array([0, 0, 1, 1]), critical=2.0)
    assert mean == 0.0 and half > 0
    rec = {"game_seed": 1, "truth": [0.0, 1.0, -1.0], "ess": 10.0,
           "scores": {f"{s}/{h}": [[0.0] * 4, [1.0] * 4, [-1.0] * 4] for s in ("uniform", "belief")
                      for h in ("next", "hand")}}
    keep = {"game_seed": 2, "truth": [0.3, 0.9, 0.0], "ess": 10.0,
            "scores": {f"{s}/{h}": [[1.0] * 4, [0.0] * 4, [0.0] * 4] for s in ("uniform", "belief")
                       for h in ("next", "hand")}}
    out = summarize([rec, keep])
    primary = out["rules"]["belief/next/z1"]
    assert primary["override_rate"] == 0.5 and abs(primary["mean_delta"] - 0.5) < 1e-12
    assert out["rules"]["uniform/hand/z0"]["hindsight_best_rate"] == 0.5
    assert out["primary"] == "belief/next/z1" and len(out["rules"]) == len(RULES) == 12
    assert PRIMARY == ("belief", "next", 1.0)


@requires_go_lib
def test_diagnostic_runs_end_to_end_on_two_states():
    from fh_mahjong_ai.bridge import CtypesGoBridge
    torch.manual_seed(0)
    model = PolicyValueNet(EnvConfig(), ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True,
                                                    aux_heads=True)).eval()
    config = EnvConfig(bridge_kind="go", bridge_library_path=os.environ["FH_MAHJONG_BRIDGE_LIB"],
                       learning_seats=(0, 1, 2, 3), auto_play_heuristics=False, match_mode="chongci",
                       chongci_max_hands=2, max_steps_per_episode=4000, event_history_window=8)
    cfg = DiagnosticConfig(worlds=4, pool_worlds=8, contested_min=0.0, keep_every=1)
    records = []
    with CtypesGoBridge(config) as bridge:
        run_diagnostic(bridge, Forward(model, "cpu"), cfg, states=2, seed_base=910000, sink=records.append)
    assert len(records) == 2
    for record in records:
        m = len(record["candidates"])
        assert 2 <= m <= 3 and len(record["truth"]) == m
        for key, matrix in record["scores"].items():
            assert np.asarray(matrix).shape == (m, 4), key
        assert record["ess"] is not None and 1.0 <= record["ess"] <= 8.0
    summary = summarize(records)
    for name, rule in summary["rules"].items():
        if rule["override_rate"] == 0.0:
            assert rule["mean_delta"] == 0.0, name
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --project ai pytest -q ai/tests/test_search_diagnostic.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'fh_mahjong_ai.search_diagnostic'`.

- [ ] **Step 3: Implement `search_diagnostic.py`**

```python
"""Search-teacher diagnostic (worklog/specs/20261005-search-teacher-diagnostic.md).

At contested discard decisions of self-play, compares the suit-averaged policy's choice with 12 search rules
against true-state ground truth: each top-3 candidate played to the end of the hand on the real wall.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch

from .action_catalog import DISCARD_BASE, DISCARD_COUNT
from .belief_weights import effective_sample_size, normalized_weights, systematic_resample, world_log_likelihoods
from .envpool import PoolCommand
from .evaluate import _t_critical_975
from .searchpool import GoSearchPool
from .suit_symmetry import suit_averaged_log_probs

SAMPLERS = ("uniform", "belief")
HORIZONS = ("next", "hand")
MARGINS = (0.0, 1.0, 2.0)
RULES = tuple((s, h, z) for s in SAMPLERS for h in HORIZONS for z in MARGINS)
PRIMARY = ("belief", "next", 1.0)


def rule_name(rule) -> str:
    sampler, horizon, z = rule
    return f"{sampler}/{horizon}/z{int(z)}"


@dataclass(frozen=True)
class DiagnosticConfig:
    candidates: int = 3
    worlds: int = 32
    pool_worlds: int = 256
    contested_min: float = 0.10
    keep_every: int = 5
    gamma: float = 0.99
    max_rollout_decisions: int = 4000
    pool_seed: int = 1
    resample_seed: int = 1


class Forward:
    """Batched greedy actions, values, belief logits and suit-averaged probabilities for one model."""

    def __init__(self, model, device: str) -> None:
        self.model = model.to(device).eval()
        self.device = device
        self.window = int(model.model_config.event_window)
        self.policy_channels = int(model.policy_channels)

    def _events(self, grid, counts, n):
        if not self.model.wants_events:
            return None, None
        if grid is None:
            grid = np.zeros((n, self.window), dtype=np.uint32)
            counts = np.zeros(n, dtype=np.int64)
        ev = torch.from_numpy(np.ascontiguousarray(grid[:, : self.window]).astype(np.int64)).to(self.device)
        ln = torch.from_numpy(np.minimum(np.asarray(counts, dtype=np.int64), self.window)).to(self.device)
        return ev, ln

    def rows(self, planes, scalars, masks, grid, counts):
        to = lambda a: torch.from_numpy(np.ascontiguousarray(a)).to(self.device)  # noqa: E731
        ev, ln = self._events(grid, counts, len(planes))
        with torch.inference_mode():
            logits, values = self.model(to(planes), to(scalars), to(masks), events=ev, event_lengths=ln)
        return logits.argmax(dim=1).cpu().numpy(), values.double().cpu().numpy()

    def observation_arrays(self, obs):
        hist = np.asarray(obs.event_history, dtype=np.uint32)[-self.window:] if self.window else np.zeros(0)
        grid = np.zeros((1, max(self.window, 1)), dtype=np.uint32)
        grid[0, : hist.size] = hist
        return obs.planes[None], obs.scalars[None], obs.action_mask[None], grid, np.array([hist.size])

    def greedy(self, obs) -> int:
        actions, _ = self.rows(*self.observation_arrays(obs))
        return int(actions[0])

    def suit_averaged_probs(self, obs) -> np.ndarray:
        planes, scalars, masks, grid, counts = self.observation_arrays(obs)
        log_probs, _ = suit_averaged_log_probs(self.model, planes, scalars, masks, grid[:, : self.window],
                                               counts, device=self.device)
        return np.exp(log_probs[0])

    def belief_logits(self, obs) -> torch.Tensor:
        planes, scalars, _, grid, counts = self.observation_arrays(obs)
        ev, ln = self._events(grid, counts, 1)
        with torch.inference_mode():
            features = self.model.encode(torch.from_numpy(planes).to(self.device),
                                         torch.from_numpy(scalars).to(self.device), ev, ln)
            return self.model.aux_predictions(features)["belief"][0]


def play_out(pool, forward: Forward, actions: list[int], root_seat: int, horizon: str, gamma: float) -> np.ndarray:
    """Each clone plays its action, then every seat plays greedy; scores are the root seat's.

    horizon="hand": rewards summed to the end of the hand. horizon="next": rewards to the root seat's next
    decision, plus gamma * the value there (the privileged critic when the pool emits oracle planes)."""
    scores = np.zeros(len(actions), dtype=np.float64)
    live = set(range(len(actions)))
    result = pool.step([PoolCommand(slot=i, action_id=int(a)) for i, a in enumerate(actions)])
    while True:
        act, value, commands = [], [], []
        for meta in result.slots:
            i = int(meta.slot)
            if i not in live:
                continue
            if meta.error:
                raise RuntimeError(f"search clone {i} failed: {meta.error}")
            if len(meta.step_rewards):
                scores[i] += float(meta.step_rewards[root_seat])
            hand_over = meta.terminated or meta.round_outcome is not None
            if meta.terminated or meta.truncated or (horizon == "hand" and hand_over):
                live.discard(i)
            elif horizon == "next" and meta.has_observation and int(meta.seat) == root_seat:
                value.append(i)
                live.discard(i)
            elif meta.has_observation:
                act.append(i)
        for group, use in ((value, "value"), (act, "act")):
            if not group:
                continue
            rows = [result.row_of_slot[i] for i in group]
            grid = None if result.event_grid is None else result.event_grid[rows]
            counts = None if result.event_counts is None else result.event_counts[rows]
            actions_out, values = forward.rows(result.planes[rows], result.scalars[rows],
                                               result.action_masks[rows], grid, counts)
            if use == "value":
                for i, v in zip(group, values):
                    scores[i] += gamma * float(v)
            else:
                commands = [PoolCommand(slot=i, action_id=int(a)) for i, a in zip(group, actions_out)]
        if not live:
            return scores
        if not commands:
            raise RuntimeError("search rollout stalled: live clones without rows")
        result = pool.step(commands)


def rule_choice(scores: np.ndarray, z: float) -> int:
    """Index of the chosen candidate: the best mean score, if its paired gain over candidate 0 (the
    suit-averaged greedy choice) exceeds z standard errors over the worlds; otherwise 0."""
    scores = np.asarray(scores, dtype=np.float64)
    best = int(np.argmax(scores.mean(axis=1)))
    if best == 0:
        return 0
    d = scores[best] - scores[0]
    se = d.std(ddof=1) / np.sqrt(d.size) if d.size > 1 else np.inf
    return best if d.mean() > z * se else 0


def clustered_mean_ci(deltas: np.ndarray, clusters: np.ndarray, critical: float) -> tuple[float, float]:
    """Mean of deltas and its half-width clustered by `clusters` (ratio estimator over cluster sums)."""
    deltas = np.asarray(deltas, dtype=np.float64)
    n = deltas.size
    mean = float(deltas.mean())
    keys = np.unique(clusters)
    if keys.size < 2:
        return mean, float("inf")
    sums = np.array([np.sum(deltas[clusters == k] - mean) for k in keys])
    se = np.sqrt(keys.size / (keys.size - 1) * np.sum(sums ** 2)) / n
    return mean, float(critical * se)
```

Then the driver and summary in the same file:

```python
def _contested(obs, probs: np.ndarray, cfg: DiagnosticConfig) -> list[int]:
    discards = np.arange(DISCARD_BASE, DISCARD_BASE + DISCARD_COUNT)
    legal = discards[obs.action_mask[discards] > 0]
    if legal.size < 2:
        return []
    order = legal[np.argsort(-probs[legal], kind="stable")][: cfg.candidates]
    if probs[order[1]] < cfg.contested_min:
        return []
    return [int(a) for a in order if probs[a] > 0]


def _world_ids(bridge, forward, obs, cfg, rng) -> tuple[list[int], float]:
    weigh = GoSearchPool(bridge, clones=cfg.pool_worlds, seed=cfg.pool_seed, max_rollout_decisions=1,
                         oracle_planes=True, root_seat=int(obs.seat))
    try:
        roots = weigh.root_observations()
    finally:
        weigh.close()
    pc = forward.policy_channels
    weights = normalized_weights(world_log_likelihoods(forward.belief_logits(obs), roots.planes[:, pc:pc + 12]))
    return systematic_resample(weights, cfg.worlds, rng).tolist(), effective_sample_size(weights)


def analyse_state(bridge, forward: Forward, obs, candidates: list[int], cfg: DiagnosticConfig, rng) -> dict:
    seat = int(obs.seat)
    truth_pool = GoSearchPool(bridge, clones=len(candidates), seed=cfg.pool_seed,
                              max_rollout_decisions=cfg.max_rollout_decisions, true_state=True, root_seat=seat)
    try:
        truth = play_out(truth_pool, forward, candidates, seat, "hand", cfg.gamma)
    finally:
        truth_pool.close()
    belief_ids, ess = _world_ids(bridge, forward, obs, cfg, rng)
    ids = {"uniform": list(range(cfg.worlds)), "belief": belief_ids}
    scores = {}
    for sampler in SAMPLERS:
        for horizon in HORIZONS:
            pool = GoSearchPool(bridge, clones=len(candidates) * cfg.worlds, seed=cfg.pool_seed,
                                max_rollout_decisions=cfg.max_rollout_decisions, determinizations=cfg.worlds,
                                root_seat=seat, oracle_planes=(horizon == "next"),
                                determinization_ids=ids[sampler])
            try:
                actions = [c for c in candidates for _ in range(cfg.worlds)]
                flat = play_out(pool, forward, actions, seat, horizon, cfg.gamma)
            finally:
                pool.close()
            scores[f"{sampler}/{horizon}"] = flat.reshape(len(candidates), cfg.worlds).tolist()
    return {"root_seat": seat, "candidates": candidates, "truth": truth.tolist(), "scores": scores, "ess": ess}


def run_diagnostic(bridge, forward: Forward, cfg: DiagnosticConfig, states: int, seed_base: int,
                   sink: Callable[[dict], None]) -> None:
    rng = np.random.default_rng(cfg.resample_seed)
    seed, kept, seen = seed_base, 0, 0
    obs = bridge.reset(seed=seed)
    while kept < states:
        discards = obs.action_mask[DISCARD_BASE:DISCARD_BASE + DISCARD_COUNT]
        candidates = (_contested(obs, forward.suit_averaged_probs(obs), cfg)
                      if np.count_nonzero(discards) >= 2 else [])
        if candidates:
            seen += 1
            if seen % cfg.keep_every == 0:
                record = analyse_state(bridge, forward, obs, candidates, cfg, rng)
                record.update(state=kept, game_seed=seed)
                sink(record)
                kept += 1
        step = bridge.step(forward.greedy(obs))
        if step.terminated or step.truncated:
            seed += 1
            obs = bridge.reset(seed=seed)
        else:
            obs = step.observation


def summarize(records: list[dict]) -> dict:
    clusters = np.array([r["game_seed"] for r in records])
    games = np.unique(clusters).size
    primary_critical = _t_critical_975(games - 1)
    bonferroni = statistics.NormalDist().inv_cdf(1 - 0.05 / 11 / 2)
    truths = [np.asarray(r["truth"], dtype=np.float64) for r in records]
    greedy_best = float(np.mean([t[0] == t.max() for t in truths]))
    rules = {}
    for rule in RULES:
        sampler, horizon, z = rule
        choices = np.array([rule_choice(np.asarray(r["scores"][f"{sampler}/{horizon}"]), z) for r in records])
        deltas = np.array([t[c] - t[0] for t, c in zip(truths, choices)])
        critical = primary_critical if rule == PRIMARY else bonferroni
        mean, half = clustered_mean_ci(deltas, clusters, critical)
        overrides = choices != 0
        rules[rule_name(rule)] = {
            "mean_delta": mean, "ci_half_width": half, "ci_lower": mean - half,
            "override_rate": float(overrides.mean()),
            "mean_delta_when_overriding": float(deltas[overrides].mean()) if overrides.any() else 0.0,
            "hindsight_best_rate": float(np.mean([t[c] == t.max() for t, c in zip(truths, choices)])),
        }
    primary = rule_name(PRIMARY)
    others = [name for name in rules if name != primary and rules[name]["ci_lower"] > 0]
    ess = np.array([r["ess"] for r in records if r.get("ess") is not None])
    return {"states": len(records), "games": int(games), "greedy_hindsight_best_rate": greedy_best,
            "primary": primary, "go": bool(rules[primary]["ci_lower"] > 0), "other_qualifying": others,
            "ess_quantiles": (np.quantile(ess, [0.1, 0.5, 0.9]).tolist() if ess.size else None),
            "rules": rules}
```

- [ ] **Step 4: Run the tests**

```bash
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_search_diagnostic.py ai/tests/test_belief_weights.py
```

Expected: PASS (3 + 2 tests).

- [ ] **Step 5: Add the review-focus tests**

Append to `ai/tests/test_search_diagnostic.py`:

```python
class _FakeMeta:
    def __init__(self, slot, seat=0, rewards=(0.0, 0.0, 0.0, 0.0), terminated=False, truncated=False,
                 has_observation=True, error="", round_outcome=None):
        self.slot, self.seat, self.terminated, self.truncated = slot, seat, terminated, truncated
        self.step_rewards = np.asarray(rewards, dtype=np.float32)
        self.has_observation, self.error, self.round_outcome = has_observation, error, round_outcome


class _FakeResult:
    def __init__(self, metas):
        self.slots = metas
        self.row_of_slot = {m.slot: i for i, m in enumerate(metas)}
        n = len(metas)
        self.planes = np.zeros((n, 51, 42, 1), dtype=np.float32)
        self.scalars = np.zeros((n, 58), dtype=np.float32)
        self.action_masks = np.ones((n, 204), dtype=np.int8)
        self.event_grid = self.event_counts = None


class _FakePool:
    def __init__(self, script):
        self.script = list(script)

    def step(self, commands):
        return self.script.pop(0)


class _FakeForward:
    def rows(self, planes, scalars, masks, grid, counts):
        return np.zeros(len(planes), dtype=np.int64), np.full(len(planes), 2.0)


def test_play_out_raises_on_a_clone_error():
    pool = _FakePool([_FakeResult([_FakeMeta(0, error="boom")])])
    with pytest.raises(RuntimeError, match="boom"):
        from fh_mahjong_ai.search_diagnostic import play_out
        play_out(pool, _FakeForward(), [5], 0, "hand", 0.99)


def test_play_out_horizons_at_a_hand_boundary():
    from fh_mahjong_ai.search_diagnostic import play_out
    # The hand ends on the first step (score +1 for root seat 0) and the row is the root's next decision.
    boundary = lambda: _FakeResult([_FakeMeta(0, seat=0, rewards=(1.0, 0, 0, 0), round_outcome={"x": 1})])  # noqa: E731
    assert play_out(_FakePool([boundary()]), _FakeForward(), [5], 0, "hand", 0.99)[0] == 1.0
    assert abs(play_out(_FakePool([boundary()]), _FakeForward(), [5], 0, "next", 0.99)[0] - (1.0 + 0.99 * 2.0)) < 1e-12
```

Run: `uv run --project ai pytest -q ai/tests/test_search_diagnostic.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/search_diagnostic.py ai/tests/test_search_diagnostic.py
git commit -m "feat(ai): search-teacher diagnostic core"
```

---

### Task 6: CLI, docs and gates

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/search_diagnostic.py`
- Modify: `ai/pyproject.toml` (`[project.scripts]`), `ai/CLAUDE.md`, `ai/MODULES.md`
- Test: `ai/tests/test_search_diagnostic.py` (append)

**Interfaces:**
- Consumes: Task 5.
- Produces: `fh-mj-search-diagnostic --checkpoint PATH --bridge-lib PATH --out DIR [--states N] [--seed-base S]
  [--worlds W] [--pool-worlds P] [--candidates M] [--contested-min X] [--keep-every K] [--device D]`, writing
  `DIR/records.jsonl` and `DIR/summary.json`.

- [ ] **Step 1: Write the failing test**

```python
@requires_go_lib
def test_cli_writes_records_and_summary(tmp_path, monkeypatch):
    import json
    import fh_mahjong_ai.scripts.search_diagnostic as cli
    from fh_mahjong_ai.storage import model_config_metadata, save_checkpoint
    config = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    path = tmp_path / "m.pt"
    save_checkpoint(path, PolicyValueNet(EnvConfig(), config), metadata={"model_config": model_config_metadata(config)})
    monkeypatch.setattr("sys.argv", ["fh-mj-search-diagnostic", "--checkpoint", str(path),
                                     "--bridge-lib", os.environ["FH_MAHJONG_BRIDGE_LIB"], "--out", str(tmp_path / "out"),
                                     "--states", "1", "--worlds", "4", "--pool-worlds", "8",
                                     "--contested-min", "0", "--keep-every", "1", "--device", "cpu",
                                     "--chongci-max-hands", "2"])
    cli.main()
    records = (tmp_path / "out" / "records.jsonl").read_text().splitlines()
    summary = json.loads((tmp_path / "out" / "summary.json").read_text())
    assert len(records) == 1 and summary["states"] == 1 and summary["primary"] == "belief/next/z1"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_search_diagnostic.py -k cli`
Expected: FAIL — `ModuleNotFoundError: ... scripts.search_diagnostic`.

- [ ] **Step 3: Implement the CLI**

```python
"""fh-mj-search-diagnostic: does belief-weighted search beat the suit-averaged policy's choice?

worklog/specs/20261005-search-teacher-diagnostic.md. Writes records.jsonl (one contested state per line) and
summary.json (12 rules, primary go/no-go)."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

from fh_mahjong_ai.bridge import CtypesGoBridge
from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.search_diagnostic import DiagnosticConfig, Forward, run_diagnostic, summarize
from fh_mahjong_ai.serving import CheckpointPolicy


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--bridge-lib", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--states", type=int, default=4000)
    p.add_argument("--seed-base", type=int, default=910000)
    p.add_argument("--candidates", type=int, default=3)
    p.add_argument("--worlds", type=int, default=32)
    p.add_argument("--pool-worlds", type=int, default=256)
    p.add_argument("--contested-min", type=float, default=0.10)
    p.add_argument("--keep-every", type=int, default=5)
    p.add_argument("--chongci-max-hands", type=int, default=50)
    p.add_argument("--device", default="cuda")
    args = p.parse_args()
    model = CheckpointPolicy.from_checkpoint(args.checkpoint, device=args.device).model
    if not (model.model_config.privileged_critic and model.model_config.aux_heads):
        p.error("the diagnostic needs a checkpoint with a privileged critic and aux (belief) heads")
    cfg = replace(DiagnosticConfig(), candidates=args.candidates, worlds=args.worlds,
                  pool_worlds=args.pool_worlds, contested_min=args.contested_min, keep_every=args.keep_every)
    env = EnvConfig(bridge_kind="go", bridge_library_path=args.bridge_lib, learning_seats=(0, 1, 2, 3),
                    auto_play_heuristics=False, match_mode="chongci", chongci_max_hands=args.chongci_max_hands,
                    max_steps_per_episode=4000, event_history_window=int(model.model_config.event_window))
    args.out.mkdir(parents=True, exist_ok=True)
    records = []
    with (args.out / "records.jsonl").open("w") as fh, CtypesGoBridge(env) as bridge:
        def sink(record: dict) -> None:
            records.append(record)
            fh.write(json.dumps(record) + "\n")
            fh.flush()
            if len(records) % 100 == 0:
                print(f"[search-diagnostic] {len(records)}/{args.states} states", flush=True)
        run_diagnostic(bridge, Forward(model, args.device), cfg, args.states, args.seed_base, sink)
    summary = summarize(records)
    summary["config"] = {**vars(args), "checkpoint": str(args.checkpoint), "bridge_lib": str(args.bridge_lib),
                         "out": str(args.out)}
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: summary[k] for k in ("states", "games", "primary", "go", "other_qualifying")}))
    for name, rule in summary["rules"].items():
        print(f"{name:18s} mean {rule['mean_delta']:+.4f} ± {rule['ci_half_width']:.4f}  "
              f"override {rule['override_rate']:.3f}  hindsight-best {rule['hindsight_best_rate']:.3f}")


if __name__ == "__main__":
    main()
```

`ai/pyproject.toml` `[project.scripts]`: `fh-mj-search-diagnostic = "fh_mahjong_ai.scripts.search_diagnostic:main"`;
then `uv sync --project ai`.

- [ ] **Step 4: Run it**

Run: `FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests/test_search_diagnostic.py`
Expected: PASS.

- [ ] **Step 5: Docs and gates**

`ai/CLAUDE.md` CLI table: `| fh-mj-search-diagnostic | Search-teacher diagnostic: 12 belief/uniform × next/hand ×
margin rules vs the suit-averaged choice on true-state ground truth (descriptive, spends screening seeds) |`.
`ai/MODULES.md`: entries for `belief_weights.py` and `search_diagnostic.py` (one line each, the docstrings' first
sentence).

```bash
gofmt -l .
go vet ./...
go test ./...
ln -s /Users/plasma/fh-mahjong/web/node_modules web/node_modules && (cd web && npx tsc && npx vitest run); unlink web/node_modules
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge
FH_MAHJONG_BRIDGE_LIB=$PWD/build/libfh_mahjong_bridge.dylib uv run --project ai pytest -q ai/tests
```

Expected: gofmt prints nothing; every gate passes.

- [ ] **Step 6: Commit**

```bash
git add ai/ internal/rl/CLAUDE.md cmd/rlbridge/CLAUDE.md proto/CLAUDE.md
git commit -m "feat(ai): fh-mj-search-diagnostic CLI and docs"
```

---

## After merge (operational; not code)

1. Box worktree at the merge commit, one bridge build; message GPU peers before running.
2. `fh-mj-search-diagnostic --checkpoint /root/fh-mahjong-runs/lookahead-20261004/control/ckpt/iter_150.pt
   --bridge-lib <worktree>/build/libfh_mahjong_bridge.so --out /root/fh-mahjong-runs/search-diagnostic-<date>
   --device cuda` (defaults: 4,000 states, seeds 910,000+, 32 worlds, 256 pool worlds).
3. Record the summary in the spec's outcome section; a go leads to a separately registered gameplay probe.
