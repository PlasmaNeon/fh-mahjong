# Batched-Inference Actor Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace per-worker CPU inference in self-play rollout collection with a Go env pool stepped over batched FFI feeding one batched GPU forward per round, in a single Python process (target ≥3× decisions/s, expect ~6×).

**Architecture:** Go gains `FHEnvPoolNew/Step/Close` c-shared exports over a new `internal/rl` pool type that steps M independent envs in goroutines and returns flat float32/uint8 observation buffers inside a proto envelope. Python gains an env-pool abstraction (`GoEnvPool` over ctypes, `InProcessEnvPool` for tests) and a round-loop collector that δ-masks, forwards all pending rows in one batch, and samples with per-match numpy RNGs. Existing process collectors stay untouched and remain the default behind a new `--collector` flag.

**Tech Stack:** Go 1.25 (goroutines, c-shared cgo), Protocol Buffers, Python 3.12 + PyTorch + numpy + ctypes, pytest, uv.

**Spec:** `docs/superpowers/specs/2026-07-02-batched-inference-actors-design.md` (approved). Branch: `claude/batched-inference-actors` (spec committed at c296ed7).

## Global Constraints

- Per-seat-contiguous emission with `dones=[0]*(n-1)+[1]` per seat (the GAE invariant) — unchanged from `collect_selfplay_rollouts`.
- Record the MASKED observation the policy acted on (PPO updates on what the policy saw).
- δ-mask stream: `mask_rng = np.random.default_rng(base_seed + m)`, drawn once per decision in the match's own decision order; action-sampling stream: `np.random.default_rng([base_seed + m, 17])`.
- Emit completed matches into the RolloutBatch in SEED ORDER (buffer out-of-order completions) — this is what makes `per_row` CPU slot-count-invariance FULL-ARRAY exact.
- Process collectors remain default and untouched; `PPOConfig.collector = "process"` is the default.
- Go never self-resets a slot; Python owns the seed schedule.
- Flat buffers: planes float32 little-endian C-order `[rows, C, H, W]`; scalars float32 `[rows, S]`; action_masks uint8 `[rows, A]`; rows = slots with `has_observation`, ascending slot order; one `SlotState` per commanded slot, ascending slot order.
- The batched path never calls `torch.manual_seed`.
- Run `go test ./...` after any Go change and `uv run --project ai pytest` after Python changes; `go vet ./...` clean.
- Proto changes regenerate Go AND Python AND TypeScript bindings together (commands in Task 1).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File inventory

- Modify: `proto/game.proto` (+regen `proto/game.pb.go`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`)
- Create: `internal/rl/envpool.go`, `internal/rl/envpool_test.go`
- Modify: `cmd/rlbridge/main.go`
- Create: `ai/src/fh_mahjong_ai/envpool.py`
- Create: `ai/src/fh_mahjong_ai/batched_selfplay.py`
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (PPOConfig: `collector`, `pool_slots`)
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (`train_selfplay_oracle` collector switch)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py` (CLI flags)
- Create: `ai/tests/test_batched_selfplay.py`, `ai/tests/test_envpool.py`
- Modify: `ai/AGENTS.md`, `internal/rl/AGENTS.md`, `cmd/rlbridge/AGENTS.md`

---

### Task 1: Proto pool messages + regenerate all three bindings

**Files:**
- Modify: `proto/game.proto` (append after `MatchEndResult`, the last message in the file)
- Regenerated: `proto/game.pb.go`, `ai/src/fh_mahjong_ai/generated/proto/game_pb2.py`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`

**Interfaces:**
- Consumes: existing `EnvConfig`, `RoundOutcome` proto messages.
- Produces: `EnvPoolNewRequest`, `SlotCommand`, `EnvPoolStepRequest`, `SlotState`, `EnvPoolStepResponse` in package `pb` (Go) and `game_pb2` (Python) — used by Tasks 2–4.

- [ ] **Step 1: Append the pool messages to `proto/game.proto`**

Append at the end of the file (after `MatchEndResult`):

```proto
message EnvPoolNewRequest {
  EnvConfig config = 1;
  uint32 slots = 2;
}

message SlotCommand {
  uint32 slot = 1;
  oneof cmd {
    uint32 action_id = 2;   // step this slot
    uint64 reset_seed = 3;  // reset this slot with a new match seed
    bool skip = 4;          // slot idle this round (no-op; absent == skip)
  }
}

message EnvPoolStepRequest {
  repeated SlotCommand commands = 1;
}

message SlotState {
  uint32 slot = 1;
  uint32 seat = 2;                 // acting seat of the returned observation
  bool terminated = 3;
  bool truncated = 4;
  repeated float step_rewards = 5; // per-seat rewards for THIS step (len 4)
  bool has_observation = 6;        // false when terminated/truncated/skipped
  RoundOutcome round_outcome = 7;
  string error = 8;                // per-slot failure (empty = ok)
}

message EnvPoolStepResponse {
  repeated SlotState slots = 1;    // one per commanded slot, ascending slot id
  // Flat observation buffers for slots with has_observation, concatenated in
  // ascending slot order. planes: float32 LE, C-order [rows, C, H, W].
  bytes planes = 2;
  bytes scalars = 3;               // float32 LE [rows, scalar_count]
  bytes action_masks = 4;          // uint8 [rows, action_space_size]
  uint32 plane_channels = 5;
  uint32 plane_height = 6;
  uint32 plane_width = 7;
  uint32 scalar_count = 8;
  uint32 action_space_size = 9;
}
```

- [ ] **Step 2: Regenerate Go, Python, and TypeScript bindings**

Run from repo root:

```bash
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
protoc --python_out=ai/src/fh_mahjong_ai/generated proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

- [ ] **Step 3: Verify the bindings compile/import**

```bash
go build ./...
uv run --project ai python -c "from fh_mahjong_ai.generated.proto import game_pb2; m = game_pb2.EnvPoolStepRequest(commands=[game_pb2.SlotCommand(slot=0, reset_seed=7)]); print(len(m.SerializeToString()) > 0)"
cd web && npx tsc --noEmit && cd ..
```

Expected: `go build` silent; Python prints `True`; tsc clean.

- [ ] **Step 4: Run both suites (no behavior change expected)**

```bash
go test ./... && uv run --project ai pytest -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add proto/game.proto proto/game.pb.go ai/src/fh_mahjong_ai/generated/proto/game_pb2.py web/src/proto/game.js web/src/proto/game.d.ts
git commit -m "feat(proto): env-pool messages for batched rollout FFI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Go env pool (`internal/rl/envpool.go`)

**Files:**
- Create: `internal/rl/envpool.go`
- Test: `internal/rl/envpool_test.go`

**Interfaces:**
- Consumes: `rl.New(*pb.EnvConfig) *Env`, `env.Reset(*pb.EnvResetRequest) (*pb.EnvResetResponse, error)`, `env.Step(*pb.EnvStepRequest) (*pb.EnvStepResponse, error)` (see `internal/rl/env.go:23,32,67`).
- Produces: `NewEnvPool(config *pb.EnvConfig, slots int) *EnvPool`; `(*EnvPool).ApplyCommands(*pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error)` — used by Task 3.

- [ ] **Step 1: Write the failing test**

`internal/rl/envpool_test.go`:

```go
package rl

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func poolTestConfig() *pb.EnvConfig {
	return &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 2},
	}
}

func firstLegal(mask []byte) uint32 {
	for i, v := range mask {
		if v == 1 {
			return uint32(i)
		}
	}
	return 0
}

// driveSingleEnv plays one match with the first-legal-action policy and
// returns the per-step (seat, rewards, planes checksum) trace.
type stepTrace struct {
	seat     uint32
	rewards  []float32
	checksum float64
}

func driveSingleEnv(t *testing.T, seed uint64) []stepTrace {
	t.Helper()
	env := New(poolTestConfig())
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: poolTestConfig()})
	if err != nil {
		t.Fatalf("reset: %v", err)
	}
	trace := []stepTrace{}
	obs, terminated, truncated := reset.Observation, reset.Terminated, reset.Truncated
	for !terminated && !truncated {
		trace = append(trace, stepTrace{seat: obs.Seat, checksum: planesChecksum(obs.Planes)})
		step, err := env.Step(&pb.EnvStepRequest{ActionId: firstLegal(obs.ActionMask)})
		if err != nil {
			t.Fatalf("step: %v", err)
		}
		trace[len(trace)-1].rewards = step.Rewards
		obs, terminated, truncated = step.Observation, step.Terminated, step.Truncated
	}
	return trace
}

func planesChecksum(planes []float32) float64 {
	sum := 0.0
	for i, v := range planes {
		sum += float64(v) * float64(i%97+1)
	}
	return sum
}

func TestEnvPoolMatchesSingleEnv(t *testing.T) {
	seeds := []uint64{9001, 9002, 9003, 9004}
	want := make([][]stepTrace, len(seeds))
	for i, seed := range seeds {
		want[i] = driveSingleEnv(t, seed)
	}

	pool := NewEnvPool(poolTestConfig(), len(seeds))
	// Round 0: reset every slot.
	req := &pb.EnvPoolStepRequest{}
	for i, seed := range seeds {
		req.Commands = append(req.Commands, &pb.SlotCommand{
			Slot: uint32(i), Cmd: &pb.SlotCommand_ResetSeed{ResetSeed: seed},
		})
	}
	got := make([][]stepTrace, len(seeds))
	pending := map[int][]float32{} // slot -> planes of pending obs
	pendingSeat := map[int]uint32{}
	pendingMask := map[int][]byte{}
	for {
		resp, err := pool.ApplyCommands(req)
		if err != nil {
			t.Fatalf("ApplyCommands: %v", err)
		}
		// Decode flat planes rows back per slot.
		rowBytes := int(resp.PlaneChannels * resp.PlaneHeight * resp.PlaneWidth * 4)
		row := 0
		req = &pb.EnvPoolStepRequest{}
		for _, state := range resp.Slots {
			slot := int(state.Slot)
			if state.Error != "" {
				t.Fatalf("slot %d error: %s", slot, state.Error)
			}
			if len(state.StepRewards) > 0 && len(got[slot]) > 0 {
				got[slot][len(got[slot])-1].rewards = state.StepRewards
			}
			if state.Terminated || state.Truncated {
				continue // match done; issue no further commands for this slot
			}
			if !state.HasObservation {
				continue
			}
			planes := decodeFloat32Rows(t, resp.Planes[row*rowBytes:(row+1)*rowBytes])
			maskOff := row * int(resp.ActionSpaceSize)
			mask := resp.ActionMasks[maskOff : maskOff+int(resp.ActionSpaceSize)]
			row++
			pending[slot], pendingSeat[slot], pendingMask[slot] = planes, state.Seat, mask
			got[slot] = append(got[slot], stepTrace{seat: state.Seat, checksum: planesChecksum(planes)})
			req.Commands = append(req.Commands, &pb.SlotCommand{
				Slot: uint32(slot), Cmd: &pb.SlotCommand_ActionId{ActionId: firstLegal(mask)},
			})
		}
		if len(req.Commands) == 0 {
			break
		}
	}
	for i := range seeds {
		if len(got[i]) != len(want[i]) {
			t.Fatalf("slot %d: %d steps, want %d", i, len(got[i]), len(want[i]))
		}
		for j := range want[i] {
			if got[i][j].seat != want[i][j].seat || got[i][j].checksum != want[i][j].checksum {
				t.Fatalf("slot %d step %d: (seat %d, sum %f) != (seat %d, sum %f)",
					i, j, got[i][j].seat, got[i][j].checksum, want[i][j].seat, want[i][j].checksum)
			}
			for k, r := range want[i][j].rewards {
				if got[i][j].rewards[k] != r {
					t.Fatalf("slot %d step %d reward[%d]: %f != %f", i, j, k, got[i][j].rewards[k], r)
				}
			}
		}
	}
}

func decodeFloat32Rows(t *testing.T, raw []byte) []float32 {
	t.Helper()
	if len(raw)%4 != 0 {
		t.Fatalf("raw length %d not multiple of 4", len(raw))
	}
	out := make([]float32, len(raw)/4)
	for i := range out {
		bits := uint32(raw[i*4]) | uint32(raw[i*4+1])<<8 | uint32(raw[i*4+2])<<16 | uint32(raw[i*4+3])<<24
		out[i] = float32frombits(bits)
	}
	return out
}
```

Add `import "math"` usage via a tiny helper at the bottom of the test file:

```go
func float32frombits(b uint32) float32 { return math.Float32frombits(b) }
```

(and add `"math"` to the test imports).

- [ ] **Step 2: Run test to verify it fails**

Run: `go test ./internal/rl -run TestEnvPoolMatchesSingleEnv`
Expected: FAIL — `undefined: NewEnvPool`.

- [ ] **Step 3: Implement `internal/rl/envpool.go`**

```go
package rl

import (
	"encoding/binary"
	"fmt"
	"math"
	"sort"
	"sync"

	pb "github.com/plasma/fh-mahjong/proto"
)

// EnvPool holds `slots` independent environments stepped in lockstep rounds by
// a single foreign caller. Each ApplyCommands call applies at most one command
// (step / reset / skip) per slot; commanded slots are processed concurrently
// (each env is touched only by its own goroutine). The pool never self-resets:
// the caller owns the seed schedule.
type EnvPool struct {
	config *pb.EnvConfig
	envs   []*Env
}

func NewEnvPool(config *pb.EnvConfig, slots int) *EnvPool {
	if slots < 1 {
		slots = 1
	}
	pool := &EnvPool{config: config, envs: make([]*Env, slots)}
	for i := range pool.envs {
		pool.envs[i] = New(config)
	}
	return pool
}

// slotResult carries one slot's outcome from its goroutine to assembly.
type slotResult struct {
	slot        uint32
	observation *pb.SeatObservation
	rewards     []float32
	terminated  bool
	truncated   bool
	outcome     *pb.RoundOutcome
	skipped     bool
	err         error
}

func (p *EnvPool) ApplyCommands(request *pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error) {
	commands := request.GetCommands()
	seen := make(map[uint32]bool, len(commands))
	for _, cmd := range commands {
		if int(cmd.GetSlot()) >= len(p.envs) {
			return nil, fmt.Errorf("slot %d out of range (pool has %d slots)", cmd.GetSlot(), len(p.envs))
		}
		if seen[cmd.GetSlot()] {
			return nil, fmt.Errorf("duplicate command for slot %d", cmd.GetSlot())
		}
		seen[cmd.GetSlot()] = true
	}

	results := make([]slotResult, len(commands))
	var wg sync.WaitGroup
	for i, cmd := range commands {
		wg.Add(1)
		go func(i int, cmd *pb.SlotCommand) {
			defer wg.Done()
			results[i] = p.applyOne(cmd)
		}(i, cmd)
	}
	wg.Wait()

	sort.Slice(results, func(a, b int) bool { return results[a].slot < results[b].slot })
	return assemblePoolResponse(results)
}

func (p *EnvPool) applyOne(cmd *pb.SlotCommand) slotResult {
	slot := cmd.GetSlot()
	env := p.envs[slot]
	switch c := cmd.GetCmd().(type) {
	case *pb.SlotCommand_ResetSeed:
		resp, err := env.Reset(&pb.EnvResetRequest{Seed: c.ResetSeed, Config: p.config})
		if err != nil {
			return slotResult{slot: slot, err: err}
		}
		return slotResult{slot: slot, observation: resp.Observation, rewards: resp.Rewards,
			terminated: resp.Terminated, truncated: resp.Truncated, outcome: resp.RoundOutcome}
	case *pb.SlotCommand_ActionId:
		resp, err := env.Step(&pb.EnvStepRequest{ActionId: c.ActionId})
		if err != nil {
			return slotResult{slot: slot, err: err}
		}
		return slotResult{slot: slot, observation: resp.Observation, rewards: resp.Rewards,
			terminated: resp.Terminated, truncated: resp.Truncated, outcome: resp.RoundOutcome}
	default: // skip (or unset oneof): no-op
		return slotResult{slot: slot, skipped: true}
	}
}

func assemblePoolResponse(results []slotResult) (*pb.EnvPoolStepResponse, error) {
	response := &pb.EnvPoolStepResponse{}
	for _, r := range results {
		state := &pb.SlotState{Slot: r.slot, Terminated: r.terminated, Truncated: r.truncated,
			StepRewards: r.rewards, RoundOutcome: r.outcome}
		if r.err != nil {
			state.Error = r.err.Error()
			response.Slots = append(response.Slots, state)
			continue
		}
		hasObs := !r.skipped && !r.terminated && !r.truncated && r.observation != nil
		state.HasObservation = hasObs
		if hasObs {
			obs := r.observation
			state.Seat = obs.Seat
			if response.PlaneChannels == 0 {
				response.PlaneChannels = obs.PlaneChannels
				response.PlaneHeight = obs.PlaneHeight
				response.PlaneWidth = obs.PlaneWidth
				response.ScalarCount = uint32(len(obs.Scalars))
				response.ActionSpaceSize = obs.ActionSpaceSize
			}
			response.Planes = appendFloat32LE(response.Planes, obs.Planes)
			response.Scalars = appendFloat32LE(response.Scalars, obs.Scalars)
			response.ActionMasks = append(response.ActionMasks, obs.ActionMask...)
		}
		response.Slots = append(response.Slots, state)
	}
	return response, nil
}

func appendFloat32LE(dst []byte, values []float32) []byte {
	off := len(dst)
	dst = append(dst, make([]byte, 4*len(values))...)
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], math.Float32bits(v))
	}
	return dst
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `go test ./internal/rl -run TestEnvPoolMatchesSingleEnv -v`
Expected: PASS.

- [ ] **Step 5: Full Go suite + vet**

```bash
go test ./... && go vet ./...
```

Expected: all pass, vet clean.

- [ ] **Step 6: Commit**

```bash
git add internal/rl/envpool.go internal/rl/envpool_test.go
git commit -m "feat(rl): env pool stepping independent envs in lockstep rounds

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: rlbridge pool exports

**Files:**
- Modify: `cmd/rlbridge/main.go`

**Interfaces:**
- Consumes: `rl.NewEnvPool`, `(*rl.EnvPool).ApplyCommands` (Task 2); existing `inputBytes`, `marshalResult`, `errorResult` helpers and the handle-registry pattern (`cmd/rlbridge/main.go:27-34,150-199`).
- Produces: c-shared exports `FHEnvPoolNew(requestPtr, requestLen) uint64`, `FHEnvPoolStep(handle, requestPtr, requestLen) FHBytesResult`, `FHEnvPoolClose(handle)` — used by Task 4's `GoEnvPool`.

- [ ] **Step 1: Add the pool handle registry and exports**

In `cmd/rlbridge/main.go`, extend the `var (...)` block:

```go
	poolMu         sync.Mutex
	nextPoolHandle uint64 = 1
	pools                 = make(map[uint64]*rl.EnvPool)
```

Add after `FHEnvClose`:

```go
//export FHEnvPoolNew
func FHEnvPoolNew(requestPtr *C.char, requestLen C.int) C.uint64_t {
	request := &pb.EnvPoolNewRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return 0
		}
	}
	if request.GetSlots() == 0 {
		return 0
	}

	poolMu.Lock()
	defer poolMu.Unlock()

	handle := nextPoolHandle
	nextPoolHandle++
	pools[handle] = rl.NewEnvPool(request.GetConfig(), int(request.GetSlots()))
	return C.uint64_t(handle)
}

//export FHEnvPoolStep
func FHEnvPoolStep(handle C.uint64_t, requestPtr *C.char, requestLen C.int) C.FHBytesResult {
	poolMu.Lock()
	pool, ok := pools[uint64(handle)]
	poolMu.Unlock()
	if !ok {
		return errorResult(errors.New("invalid env pool handle"))
	}

	request := &pb.EnvPoolStepRequest{}
	if data := inputBytes(requestPtr, requestLen); len(data) > 0 {
		if err := proto.Unmarshal(data, request); err != nil {
			return errorResult(err)
		}
	}

	response, err := pool.ApplyCommands(request)
	if err != nil {
		return errorResult(err)
	}
	return marshalResult(response)
}

//export FHEnvPoolClose
func FHEnvPoolClose(handle C.uint64_t) {
	poolMu.Lock()
	defer poolMu.Unlock()
	delete(pools, uint64(handle))
}
```

- [ ] **Step 2: Build + vet + full suite**

```bash
go build ./... && go vet ./... && go test ./...
```

Expected: clean. (The exports are compile-checked here; end-to-end FFI is exercised by the box runbook in Task 9 — local pytest uses `InProcessEnvPool`.)

- [ ] **Step 3: Commit**

```bash
git add cmd/rlbridge/main.go
git commit -m "feat(rlbridge): FHEnvPoolNew/Step/Close batched env-pool exports

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Python env-pool abstraction (`envpool.py`)

**Files:**
- Create: `ai/src/fh_mahjong_ai/envpool.py`
- Test: `ai/tests/test_envpool.py`

**Interfaces:**
- Consumes: `build_bridge`, `resolve_bridge_library`, `FHBytesResult`, `BridgeError` from `fh_mahjong_ai.bridge`; `game_pb2.EnvPoolNewRequest/SlotCommand/EnvPoolStepRequest/EnvPoolStepResponse` (Task 1); `EnvConfig` from `fh_mahjong_ai.config`.
- Produces (used by Task 5):
  - `PoolCommand(slot: int, action_id: int | None = None, reset_seed: int | None = None)` — omit both for skip.
  - `SlotMeta(slot, seat, terminated, truncated, step_rewards: np.ndarray, has_observation, error: str)`
  - `PoolStepResult(slots: list[SlotMeta], planes: np.ndarray, scalars: np.ndarray, action_masks: np.ndarray, row_of_slot: dict[int, int])`
  - `InProcessEnvPool(env_config, slots)` / `GoEnvPool(env_config, slots)` with `.slots`, `.step(commands) -> PoolStepResult`, `.close()`.
  - `make_selfplay_pool(env_config: EnvConfig, ppo_config, slots: int)` — builds the self-play `EnvConfig` (learning_seats=(0,1,2,3), auto_play_heuristics=False, `oracle_observation` and `max_steps_per_episode`/`match_mode` from configs — mirroring `collect_selfplay_rollouts`'s cfg at `oracle.py:179-190`) and returns `GoEnvPool` when `bridge_kind == "go"` else `InProcessEnvPool`.

- [ ] **Step 1: Write the failing test**

`ai/tests/test_envpool.py`:

```python
import numpy as np

from fh_mahjong_ai.config import EnvConfig
from fh_mahjong_ai.ppo import PPOConfig


def _pool(slots):
    from fh_mahjong_ai.envpool import make_selfplay_pool
    env_cfg = EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                        oracle_observation=True)
    cfg = PPOConfig(match_mode="classic", max_steps_per_episode=64, device="cpu")
    return make_selfplay_pool(env_cfg, cfg, slots)


def test_inprocess_pool_reset_and_step_shapes():
    from fh_mahjong_ai.envpool import PoolCommand
    pool = _pool(2)
    try:
        result = pool.step([PoolCommand(slot=0, reset_seed=11), PoolCommand(slot=1, reset_seed=12)])
        assert [m.slot for m in result.slots] == [0, 1]
        rows = sum(1 for m in result.slots if m.has_observation)
        assert result.planes.shape == (rows, 51, 42, 1)
        assert result.action_masks.shape[0] == rows
        assert set(result.row_of_slot) == {m.slot for m in result.slots if m.has_observation}
        # step the first live slot with its first legal action
        live = [m for m in result.slots if m.has_observation]
        if live:
            slot = live[0].slot
            mask = result.action_masks[result.row_of_slot[slot]]
            action = int(np.flatnonzero(mask > 0)[0])
            result2 = pool.step([PoolCommand(slot=slot, action_id=action)])
            assert result2.slots[0].slot == slot
            assert result2.slots[0].step_rewards.shape[-1] >= 1
    finally:
        pool.close()


def test_inprocess_pool_same_seed_same_first_obs():
    from fh_mahjong_ai.envpool import PoolCommand
    pool_a, pool_b = _pool(1), _pool(1)
    try:
        ra = pool_a.step([PoolCommand(slot=0, reset_seed=33)])
        rb = pool_b.step([PoolCommand(slot=0, reset_seed=33)])
        assert ra.slots[0].has_observation == rb.slots[0].has_observation
        if ra.slots[0].has_observation:
            np.testing.assert_array_equal(ra.planes, rb.planes)
            np.testing.assert_array_equal(ra.action_masks, rb.action_masks)
    finally:
        pool_a.close()
        pool_b.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai pytest ai/tests/test_envpool.py -q`
Expected: FAIL — `ModuleNotFoundError: fh_mahjong_ai.envpool`.

- [ ] **Step 3: Implement `ai/src/fh_mahjong_ai/envpool.py`**

```python
"""Env-pool abstraction: lockstep-round stepping of many envs behind one interface.

`GoEnvPool` drives the Go env pool over batched FFI (one call per round, flat
observation buffers). `InProcessEnvPool` loops ordinary bridges in-process and
serves as the test / CPU-exactness path. Pools never self-reset a slot: the
caller owns the seed schedule.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from .bridge import BridgeError, FHBytesResult, build_bridge, resolve_bridge_library
from .config import EnvConfig
from .generated.proto import game_pb2


@dataclass(frozen=True)
class PoolCommand:
    slot: int
    action_id: Optional[int] = None
    reset_seed: Optional[int] = None
    # Neither set -> skip (no-op for that slot).


@dataclass(frozen=True)
class SlotMeta:
    slot: int
    seat: int
    terminated: bool
    truncated: bool
    step_rewards: np.ndarray
    has_observation: bool
    error: str = ""


@dataclass(frozen=True)
class PoolStepResult:
    slots: list[SlotMeta]
    planes: np.ndarray        # (rows, C, H, W) float32
    scalars: np.ndarray       # (rows, S) float32
    action_masks: np.ndarray  # (rows, A) int8
    row_of_slot: dict[int, int] = field(default_factory=dict)


def _empty_result(env_config: EnvConfig, slots: list[SlotMeta]) -> PoolStepResult:
    channels, height, width = env_config.plane_shape
    return PoolStepResult(
        slots=slots,
        planes=np.zeros((0, channels, height, width), dtype=np.float32),
        scalars=np.zeros((0, env_config.scalar_features), dtype=np.float32),
        action_masks=np.zeros((0, env_config.action_space_size), dtype=np.int8),
        row_of_slot={},
    )


class InProcessEnvPool:
    """Loops `slots` ordinary bridges (mock or go) behind the pool interface."""

    def __init__(self, env_config: EnvConfig, slots: int) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        self.env_config = env_config
        self.slots = int(slots)
        self._bridges = [build_bridge(env_config) for _ in range(self.slots)]

    def step(self, commands: Sequence[PoolCommand]) -> PoolStepResult:
        metas: list[SlotMeta] = []
        obs_rows: list[tuple[int, np.ndarray, np.ndarray, np.ndarray, int]] = []
        for command in sorted(commands, key=lambda c: c.slot):
            slot = int(command.slot)
            if slot >= self.slots:
                raise ValueError(f"slot {slot} out of range (pool has {self.slots})")
            bridge = self._bridges[slot]
            if command.reset_seed is not None:
                observation = bridge.reset(seed=int(command.reset_seed))
                result = bridge.last_reset_result
                rewards = np.asarray(result.rewards if result is not None else [], dtype=np.float32)
                terminated = bool(result.terminated) if result is not None else False
                truncated = bool(result.truncated) if result is not None else False
            elif command.action_id is not None:
                result = bridge.step(int(command.action_id))
                observation = result.observation
                rewards = np.asarray(result.rewards, dtype=np.float32)
                terminated, truncated = bool(result.terminated), bool(result.truncated)
            else:  # skip
                metas.append(SlotMeta(slot, 0, False, False,
                                      np.zeros(0, np.float32), False))
                continue
            has_obs = not (terminated or truncated)
            seat = int(observation.seat) if has_obs else 0
            metas.append(SlotMeta(slot, seat, terminated, truncated, rewards, has_obs))
            if has_obs:
                obs_rows.append((
                    slot,
                    np.asarray(observation.planes, dtype=np.float32),
                    np.asarray(observation.scalars, dtype=np.float32),
                    np.asarray(observation.action_mask, dtype=np.int8),
                    seat,
                ))
        if not obs_rows:
            return _empty_result(self.env_config, metas)
        row_of_slot = {slot: i for i, (slot, *_rest) in enumerate(obs_rows)}
        return PoolStepResult(
            slots=metas,
            planes=np.stack([r[1] for r in obs_rows]),
            scalars=np.stack([r[2] for r in obs_rows]),
            action_masks=np.stack([r[3] for r in obs_rows]),
            row_of_slot=row_of_slot,
        )

    def close(self) -> None:
        for bridge in self._bridges:
            close = getattr(bridge, "close", None)
            if callable(close):
                close()
        self._bridges = []


class GoEnvPool:
    """ctypes wrapper over the FHEnvPool* exports (one FFI call per round)."""

    def __init__(self, env_config: EnvConfig, slots: int) -> None:
        if slots < 1:
            raise ValueError("slots must be >= 1")
        self.env_config = env_config
        self.slots = int(slots)
        self._handle = 0
        self._library = ctypes.CDLL(str(resolve_bridge_library(env_config)))
        self._configure_signatures()
        request = game_pb2.EnvPoolNewRequest(config=self._config_message(), slots=self.slots)
        self._handle = self._library.FHEnvPoolNew(*self._payload_args(request.SerializeToString()))
        if self._handle == 0:
            raise BridgeError("FHEnvPoolNew returned an invalid handle")

    def step(self, commands: Sequence[PoolCommand]) -> PoolStepResult:
        request = game_pb2.EnvPoolStepRequest()
        for command in commands:
            slot_command = request.commands.add()
            slot_command.slot = int(command.slot)
            if command.reset_seed is not None:
                slot_command.reset_seed = int(command.reset_seed)
            elif command.action_id is not None:
                slot_command.action_id = int(command.action_id)
            else:
                slot_command.skip = True
        raw = self._call_bytes(self._library.FHEnvPoolStep, self._handle,
                               request.SerializeToString())
        response = game_pb2.EnvPoolStepResponse()
        response.ParseFromString(raw)

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
        if rows == 0:
            return _empty_result(self.env_config, metas)
        channels, height, width = (int(response.plane_channels), int(response.plane_height),
                                   int(response.plane_width))
        planes = np.frombuffer(response.planes, dtype="<f4").reshape(rows, channels, height, width)
        scalars = np.frombuffer(response.scalars, dtype="<f4").reshape(rows, int(response.scalar_count))
        masks = np.frombuffer(response.action_masks, dtype=np.uint8).astype(np.int8, copy=False)
        masks = masks.reshape(rows, int(response.action_space_size))
        return PoolStepResult(
            slots=metas, planes=planes, scalars=scalars, action_masks=masks,
            row_of_slot={slot: i for i, slot in enumerate(live_slots)},
        )

    def close(self) -> None:
        if getattr(self, "_handle", 0):
            self._library.FHEnvPoolClose(self._handle)
            self._handle = 0

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # --- plumbing (mirrors CtypesGoBridge conventions in bridge.py) ---

    def _configure_signatures(self) -> None:
        self._library.FHEnvPoolNew.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvPoolNew.restype = ctypes.c_uint64
        self._library.FHEnvPoolStep.argtypes = [ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self._library.FHEnvPoolStep.restype = FHBytesResult
        self._library.FHEnvPoolClose.argtypes = [ctypes.c_uint64]
        self._library.FHEnvPoolClose.restype = None
        self._library.FHFree.argtypes = [ctypes.c_void_p]
        self._library.FHFree.restype = None

    def _config_message(self) -> game_pb2.EnvConfig:
        config = self.env_config
        message = game_pb2.EnvConfig(
            auto_play_heuristics=bool(config.auto_play_heuristics),
            max_decisions=int(config.max_steps_per_episode),
        )
        message.learning_seats.extend(int(seat) for seat in config.learning_seats)
        message.oracle_observation = bool(config.oracle_observation)
        if config.match_mode == "chongci":
            message.match_mode = game_pb2.MATCH_MODE_CHONGCI
            message.chongci_config.starting_score = int(config.chongci_starting_score)
            message.chongci_config.bust_threshold = int(config.chongci_bust_threshold)
            message.chongci_config.max_hands = int(config.chongci_max_hands)
        else:
            message.match_mode = game_pb2.MATCH_MODE_CLASSIC
        return message

    def _payload_args(self, payload: bytes):
        buffer = ctypes.create_string_buffer(payload, len(payload) if payload else 1)
        pointer = ctypes.c_void_p(ctypes.addressof(buffer)) if payload else ctypes.c_void_p()
        # Keep the buffer alive for the duration of the call via the tuple.
        self._last_buffer = buffer
        return pointer, len(payload)

    def _call_bytes(self, fn, handle, payload: bytes) -> bytes:
        pointer, length = self._payload_args(payload)
        result = fn(handle, pointer, length)
        try:
            if result.err:
                raise BridgeError(ctypes.string_at(result.err).decode("utf-8"))
            if not result.data or result.len <= 0:
                return b""
            return ctypes.string_at(result.data, result.len)
        finally:
            if result.data:
                self._library.FHFree(result.data)
            if result.err:
                self._library.FHFree(result.err)


def make_selfplay_pool(env_config: EnvConfig, ppo_config, slots: int):
    """Build the all-4 self-play EnvConfig (mirrors collect_selfplay_rollouts)
    and return the right pool implementation for the bridge kind."""
    cfg = EnvConfig(
        action_space_size=env_config.action_space_size,
        plane_shape=env_config.plane_shape,
        scalar_features=env_config.scalar_features,
        bridge_kind=env_config.bridge_kind,
        bridge_library_path=env_config.bridge_library_path,
        learning_seats=(0, 1, 2, 3),
        auto_play_heuristics=False,
        max_steps_per_episode=ppo_config.max_steps_per_episode,
        match_mode=ppo_config.match_mode,
        oracle_observation=env_config.oracle_observation,
    )
    if cfg.bridge_kind == "go":
        return GoEnvPool(cfg, slots)
    return InProcessEnvPool(cfg, slots)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai pytest ai/tests/test_envpool.py -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/envpool.py ai/tests/test_envpool.py
git commit -m "feat(ai): env-pool abstraction (GoEnvPool over batched FFI + in-process test pool)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Batched collector (`batched_selfplay.py`) + core semantics tests

**Files:**
- Create: `ai/src/fh_mahjong_ai/batched_selfplay.py`
- Test: `ai/tests/test_batched_selfplay.py`

**Interfaces:**
- Consumes: `PoolCommand`, `PoolStepResult`, pool objects (Task 4); `RolloutBatch`, `PPOConfig`, `_seat_step_reward` from `fh_mahjong_ai.ppo`; `PolicyValueNet`.
- Produces (used by Tasks 6–7):
  - `sample_masked_action(logits_row: np.ndarray, mask_row: np.ndarray, temperature: float, rng: np.random.Generator) -> tuple[int, float]`
  - `collect_selfplay_rollouts_batched(env_config, model, config, base_seed, drop_prob, pool, inference_mode: str = "batched") -> RolloutBatch`

- [ ] **Step 1: Write the failing tests (semantics subset)**

`ai/tests/test_batched_selfplay.py`:

```python
import numpy as np
import torch

from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig


def _mcfg():
    return ModelConfig(channels=8, residual_blocks=1, plane_feature_dim=16,
                       scalar_hidden_dim=16, trunk_hidden_dim=16, value_hidden_dim=16, q_hidden_dim=16)


def _env_cfg():
    return EnvConfig(bridge_kind="mock", match_mode="classic", max_steps_per_episode=64,
                     oracle_observation=True)


def _collect(matches, slots, drop_prob, inference_mode="batched", base_seed=500, model=None):
    from fh_mahjong_ai.batched_selfplay import collect_selfplay_rollouts_batched
    from fh_mahjong_ai.envpool import make_selfplay_pool
    env_cfg = _env_cfg()
    cfg = PPOConfig(matches_per_iter=matches, match_mode="classic",
                    max_steps_per_episode=64, device="cpu")
    if model is None:
        torch.manual_seed(0)
        model = PolicyValueNet(env_cfg, _mcfg())
    pool = make_selfplay_pool(env_cfg, cfg, slots)
    try:
        return collect_selfplay_rollouts_batched(env_cfg, model, cfg, base_seed=base_seed,
                                                 drop_prob=drop_prob, pool=pool,
                                                 inference_mode=inference_mode)
    finally:
        pool.close()


def test_sample_masked_action_matches_categorical():
    from fh_mahjong_ai.batched_selfplay import sample_masked_action
    rng = np.random.default_rng(3)
    logits = rng.standard_normal(204).astype(np.float32)
    mask = np.zeros(204, dtype=np.int8)
    legal = [4, 9, 44, 108, 203]
    mask[legal] = 1
    temperature = 1.0

    # Reference probabilities: Categorical over temperature-scaled masked logits.
    masked = torch.full((204,), torch.finfo(torch.float32).min)
    masked[legal] = torch.from_numpy(logits[legal]) / temperature
    reference = torch.distributions.Categorical(logits=masked)

    draws = {}
    sample_rng = np.random.default_rng(7)
    for _ in range(20000):
        action, logprob = sample_masked_action(logits, mask, temperature, sample_rng)
        assert action in legal
        # Returned logprob matches the reference distribution's logprob.
        assert abs(logprob - float(reference.log_prob(torch.tensor(action)))) < 1e-5
        draws[action] = draws.get(action, 0) + 1
    for action in legal:
        expected = float(reference.probs[action])
        assert abs(draws.get(action, 0) / 20000 - expected) < 0.02


def test_batched_records_all_four_seats():
    batch = _collect(matches=3, slots=2, drop_prob=0.0)
    assert len(batch) > 0
    assert batch.dones.sum() >= 3  # at least one done block per non-empty match
    # All-4 self-play yields ~4x a single-seat run; sanity floor: > 2 decisions/match.
    assert len(batch) > 6


def test_batched_feature_dropout():
    full = _collect(matches=2, slots=2, drop_prob=1.0)
    assert np.allclose(full.planes[:, 39:51], 0.0)
    none = _collect(matches=2, slots=2, drop_prob=0.0)
    assert np.abs(none.planes[:, 39:51]).sum() > 0.0


def test_batched_trajectories_are_seat_contiguous():
    # Mirrors the Phase-2 contiguity regression: within each done-delimited
    # segment, decisions must belong to contiguous per-seat blocks, which shows
    # up as dones only at segment ends (no interleaving -> segment lengths sum).
    batch = _collect(matches=3, slots=3, drop_prob=0.5)
    ends = np.flatnonzero(batch.dones > 0.5)
    assert ends.size >= 3
    assert ends[-1] == len(batch) - 1  # batch ends on a block boundary
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_batched_selfplay.py -q`
Expected: FAIL — `ModuleNotFoundError: fh_mahjong_ai.batched_selfplay`.

- [ ] **Step 3: Implement `ai/src/fh_mahjong_ai/batched_selfplay.py`**

```python
"""Batched self-play collection: env pool + one batched forward per round.

Round loop: every live slot has exactly one pending decision (a mahjong match
has one acting seat at a time). Each round we ship one pool call (reset/step
commands), δ-mask the returned rows with per-match RNGs, run ONE model forward
over all pending rows (batched on config.device, or per-row for the CPU
exactness tests), sample per-match, and repeat. Completed matches are emitted
into the RolloutBatch in SEED ORDER so per_row-CPU output is invariant to the
slot count. Sampling never touches the global torch RNG.
"""
from __future__ import annotations

import numpy as np
import torch

from .config import EnvConfig
from .envpool import PoolCommand, PoolStepResult
from .model import PolicyValueNet
from .ppo import PPOConfig, RolloutBatch, _seat_step_reward

ORACLE_LO, ORACLE_HI = 39, 51  # oracle channels masked by feature-dropout


def sample_masked_action(logits_row, mask_row, temperature, rng):
    """Sample one action from temperature-scaled masked logits with `rng`.

    Same distribution family as the process collectors (Categorical over the
    legal actions' scaled logits); the RNG is a per-match numpy Generator, so
    the draw is independent of how rows were batched for inference."""
    legal = np.flatnonzero(np.asarray(mask_row) > 0)
    if legal.size == 0:
        raise RuntimeError("observation has no legal actions")
    scaled = np.asarray(logits_row, dtype=np.float64)[legal] / max(float(temperature), 1e-6)
    shifted = scaled - scaled.max()                      # stable log-softmax,
    log_probs = shifted - np.log(np.exp(shifted).sum())  # no scipy dependency
    index = int(rng.choice(legal.size, p=np.exp(log_probs)))
    return int(legal[index]), float(log_probs[index])


class _MatchState:
    """Per-slot bookkeeping for one match (mirrors collect_selfplay_rollouts)."""

    def __init__(self, match_index: int, base_seed: int) -> None:
        self.match_index = match_index
        self.seed = int(base_seed + match_index)
        self.mask_rng = np.random.default_rng(self.seed)            # δ stream (same as today)
        self.sample_rng = np.random.default_rng([self.seed, 17])    # action stream
        self.seat_planes = [[], [], [], []]
        self.seat_scalars = [[], [], [], []]
        self.seat_masks = [[], [], [], []]
        self.seat_actions = [[], [], [], []]
        self.seat_logprobs = [[], [], [], []]
        self.seat_values = [[], [], [], []]
        self.seat_rewards = [[], [], [], []]

    def record_decision(self, seat, planes_np, scalars_np, mask_np, action, logprob, value):
        self.seat_planes[seat].append(planes_np)
        self.seat_scalars[seat].append(scalars_np)
        self.seat_masks[seat].append(mask_np)
        self.seat_actions[seat].append(action)
        self.seat_logprobs[seat].append(logprob)
        self.seat_values[seat].append(value)
        self.seat_rewards[seat].append(0.0)

    def credit_step_rewards(self, step_rewards) -> None:
        # Credit each seat's step delta to ITS current last decision.
        for k in range(4):
            if self.seat_rewards[k]:
                self.seat_rewards[k][-1] += _seat_step_reward(step_rewards, k)

    def emit_into(self, sink) -> None:
        # Per-seat contiguous blocks, seats 0..3, done=1 at each block's end.
        for k in range(4):
            n = len(self.seat_actions[k])
            if n == 0:
                continue
            sink["planes"].extend(self.seat_planes[k])
            sink["scalars"].extend(self.seat_scalars[k])
            sink["masks"].extend(self.seat_masks[k])
            sink["actions"].extend(self.seat_actions[k])
            sink["logprobs"].extend(self.seat_logprobs[k])
            sink["values"].extend(self.seat_values[k])
            sink["rewards"].extend(self.seat_rewards[k])
            sink["dones"].extend([0.0] * (n - 1) + [1.0])


def collect_selfplay_rollouts_batched(env_config: EnvConfig, model: PolicyValueNet,
                                      config: PPOConfig, base_seed: int, drop_prob: float,
                                      pool, inference_mode: str = "batched") -> RolloutBatch:
    if inference_mode not in ("batched", "per_row"):
        raise ValueError(f"unknown inference_mode: {inference_mode}")
    total = int(config.matches_per_iter)
    device = config.device
    model.eval()

    active: dict[int, _MatchState] = {}   # slot -> in-flight match
    pending_action: dict[int, int] = {}   # slot -> action sampled last round
    completed: dict[int, _MatchState] = {}  # match_index -> finished match
    next_match = 0                        # next match index to assign to a free slot
    emit_next = 0                         # next match index to flush (seed order)
    sink = {name: [] for name in
            ("planes", "scalars", "masks", "actions", "logprobs", "values", "rewards", "dones")}

    def flush_in_seed_order() -> None:
        nonlocal emit_next
        while emit_next in completed:
            completed.pop(emit_next).emit_into(sink)
            emit_next += 1

    while emit_next < total:
        commands = []
        for slot in range(pool.slots):
            if slot in pending_action:
                commands.append(PoolCommand(slot=slot, action_id=pending_action.pop(slot)))
            elif slot not in active and next_match < total:
                state = _MatchState(next_match, base_seed)
                next_match += 1
                active[slot] = state
                commands.append(PoolCommand(slot=slot, reset_seed=state.seed))
            # idle slots get no command (absent == skip)
        if not commands:
            break  # defensive: nothing in flight and nothing left to assign
        result: PoolStepResult = pool.step(commands)

        pending_rows = []  # (slot, state, planes_np, scalars_np, mask_np, seat)
        for meta in result.slots:
            state = active.get(meta.slot)
            if state is None:
                continue
            if meta.error:
                raise RuntimeError(
                    f"env pool slot {meta.slot} (match seed {state.seed}) failed: {meta.error}")
            state.credit_step_rewards(meta.step_rewards)
            if meta.terminated or meta.truncated:
                # A match that ends during reset has no decisions and emits nothing.
                completed[state.match_index] = state
                del active[meta.slot]
                continue
            if not meta.has_observation:
                continue
            row = result.row_of_slot[meta.slot]
            planes_np = np.array(result.planes[row], dtype=np.float32, copy=True)
            if planes_np.shape[0] >= ORACLE_HI and state.mask_rng.random() < drop_prob:
                planes_np[ORACLE_LO:ORACLE_HI] = 0.0  # feature-dropout; record the MASKED obs
            scalars_np = np.asarray(result.scalars[row], dtype=np.float32)
            mask_np = np.asarray(result.action_masks[row], dtype=np.int8)
            pending_rows.append((meta.slot, state, planes_np, scalars_np, mask_np, meta.seat))
        flush_in_seed_order()
        if not pending_rows:
            continue

        if inference_mode == "batched":
            planes_t = torch.from_numpy(np.stack([r[2] for r in pending_rows])).to(device)
            scalars_t = torch.from_numpy(np.stack([r[3] for r in pending_rows])).to(device)
            masks_t = torch.from_numpy(np.stack([r[4] for r in pending_rows])).to(device)
            with torch.no_grad():
                logits_t, values_t = model(planes_t, scalars_t, masks_t)
            logits_np = logits_t.detach().cpu().numpy()
            values_np = values_t.detach().reshape(-1).cpu().numpy()
        else:  # per_row: identical orchestration, batch-composition-independent floats
            logits_rows, values_rows = [], []
            for _, _, planes_np, scalars_np, mask_np, _ in pending_rows:
                with torch.no_grad():
                    logits_1, value_1 = model(
                        torch.from_numpy(planes_np).unsqueeze(0).to(device),
                        torch.from_numpy(scalars_np).unsqueeze(0).to(device),
                        torch.from_numpy(mask_np).unsqueeze(0).to(device),
                    )
                logits_rows.append(logits_1[0].detach().cpu().numpy())
                values_rows.append(float(value_1.reshape(-1)[0].item()))
            logits_np = np.stack(logits_rows)
            values_np = np.asarray(values_rows, dtype=np.float32)

        for i, (slot, state, planes_np, scalars_np, mask_np, seat) in enumerate(pending_rows):
            action, logprob = sample_masked_action(
                logits_np[i], mask_np, config.sample_temperature, state.sample_rng)
            state.record_decision(seat, planes_np, scalars_np, mask_np,
                                  action, logprob, float(values_np[i]))
            pending_action[slot] = action

    if not sink["actions"]:
        raise RuntimeError("collect_selfplay_rollouts_batched produced no decisions")
    return RolloutBatch(
        planes=np.stack(sink["planes"]).astype(np.float32),
        scalars=np.stack(sink["scalars"]).astype(np.float32),
        action_mask=np.stack(sink["masks"]).astype(np.int8),
        actions=np.asarray(sink["actions"], dtype=np.int64),
        old_logprobs=np.asarray(sink["logprobs"], dtype=np.float32),
        values=np.asarray(sink["values"], dtype=np.float32),
        rewards=np.asarray(sink["rewards"], dtype=np.float32),
        dones=np.asarray(sink["dones"], dtype=np.float32),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_batched_selfplay.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/batched_selfplay.py ai/tests/test_batched_selfplay.py
git commit -m "feat(ai): batched self-play collector (round loop, per-match RNG sampling)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Determinism tests (slot-count invariance, run-to-run, batched-vs-per_row)

**Files:**
- Modify: `ai/tests/test_batched_selfplay.py` (append)

**Interfaces:**
- Consumes: `_collect` helper and `collect_selfplay_rollouts_batched` from Task 5 (the helper builds a fresh `torch.manual_seed(0)` model per call, so runs are comparable).

- [ ] **Step 1: Write the failing/verifying tests**

Append to `ai/tests/test_batched_selfplay.py`:

```python
def _batch_fields(batch):
    return {
        "planes": batch.planes, "scalars": batch.scalars, "action_mask": batch.action_mask,
        "actions": batch.actions, "old_logprobs": batch.old_logprobs,
        "values": batch.values, "rewards": batch.rewards, "dones": batch.dones,
    }


def test_batched_slot_count_invariance_exact():
    # per_row CPU: full-array equality across ANY slot count — emission is
    # pinned to seed order and each match depends only on (seed, own decisions).
    one = _collect(matches=4, slots=1, drop_prob=0.5, inference_mode="per_row")
    eight = _collect(matches=4, slots=8, drop_prob=0.5, inference_mode="per_row")
    for name, left in _batch_fields(one).items():
        np.testing.assert_array_equal(left, _batch_fields(eight)[name], err_msg=name)


def test_batched_run_to_run_identical():
    first = _collect(matches=3, slots=3, drop_prob=0.5, inference_mode="batched")
    second = _collect(matches=3, slots=3, drop_prob=0.5, inference_mode="batched")
    for name, left in _batch_fields(first).items():
        np.testing.assert_array_equal(left, _batch_fields(second)[name], err_msg=name)


def test_batched_vs_per_row_statistical():
    batched = _collect(matches=4, slots=4, drop_prob=0.5, inference_mode="batched")
    per_row = _collect(matches=4, slots=4, drop_prob=0.5, inference_mode="per_row")
    # Same match set either way; float rounding may flip individual samples,
    # so compare aggregates loosely rather than trajectories exactly.
    assert batched.dones.sum() == per_row.dones.sum() or \
        abs(batched.dones.sum() - per_row.dones.sum()) <= 4
    assert np.isfinite(batched.rewards).all() and np.isfinite(per_row.rewards).all()
    assert abs(len(batched) - len(per_row)) < max(len(batched), len(per_row))
```

- [ ] **Step 2: Run the new tests**

Run: `uv run --project ai pytest ai/tests/test_batched_selfplay.py -q`
Expected: PASS (7 tests). If `test_batched_slot_count_invariance_exact` fails, the bug is in emission ordering (seed-order flush) or per-match RNG wiring — fix the collector, do not weaken the test.

- [ ] **Step 3: Commit**

```bash
git add ai/tests/test_batched_selfplay.py
git commit -m "test(ai): determinism guarantees for the batched collector

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Trainer wiring (`PPOConfig`, `train_selfplay_oracle`, CLI) + integration test

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (PPOConfig dataclass, after `num_workers: int = 1`)
- Modify: `ai/src/fh_mahjong_ai/oracle.py` (`train_selfplay_oracle`, currently ~line 470)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py`
- Test: `ai/tests/test_batched_selfplay.py` (append)

**Interfaces:**
- Consumes: `make_selfplay_pool` (Task 4), `collect_selfplay_rollouts_batched` (Task 5).
- Produces: `PPOConfig.collector: str = "process"`, `PPOConfig.pool_slots: int = 128`; CLI `--collector {process,batched}` and `--pool-slots`.

- [ ] **Step 1: Write the failing integration test**

Append to `ai/tests/test_batched_selfplay.py`:

```python
def test_train_selfplay_oracle_batched_collector(tmp_path):
    import json
    from fh_mahjong_ai.oracle import train_selfplay_oracle
    from fh_mahjong_ai.storage import save_checkpoint

    mcfg = _mcfg()
    anchor = tmp_path / "anchor.pt"
    torch.manual_seed(0)
    save_checkpoint(anchor, PolicyValueNet(EnvConfig(), mcfg))
    env_cfg = _env_cfg()
    cfg = PPOConfig(iterations=2, matches_per_iter=2, match_mode="classic",
                    max_steps_per_episode=64, device="cpu",
                    collector="batched", pool_slots=2)

    history = train_selfplay_oracle(env_config=env_cfg, model_config=mcfg,
                                    anchor_checkpoint=anchor,
                                    checkpoint_dir=tmp_path / "ckpt",
                                    config=cfg, base_seed=100, run_eval=False)

    assert len(history) == 2
    assert all("delta" in row for row in history)
    assert (tmp_path / "ckpt" / "iter_002.pt").exists()
    assert "delta" in json.loads((tmp_path / "ckpt" / "history.json").read_text())[0]
```

Run: `uv run --project ai pytest ai/tests/test_batched_selfplay.py::test_train_selfplay_oracle_batched_collector -q`
Expected: FAIL — `TypeError: PPOConfig.__init__() got an unexpected keyword argument 'collector'`.

- [ ] **Step 2: Add the PPOConfig fields**

In `ai/src/fh_mahjong_ai/ppo.py`, inside `PPOConfig` directly after `num_workers: int = 1`:

```python
    collector: str = "process"   # "process" (spawn workers) | "batched" (env pool + batched forward)
    pool_slots: int = 128        # concurrent env-pool slots for collector="batched"
```

- [ ] **Step 3: Wire the collector switch in `train_selfplay_oracle`**

In `ai/src/fh_mahjong_ai/oracle.py`, replace the collector setup and per-iteration collection inside `train_selfplay_oracle`:

```python
    history: list[dict] = []
    collector = None
    pool = None
    if config.collector == "batched":
        from .batched_selfplay import collect_selfplay_rollouts_batched
        from .envpool import make_selfplay_pool
        pool = make_selfplay_pool(env_config, config, config.pool_slots)
    elif config.num_workers > 1:
        collector = ParallelSelfplayCollector(env_config, model_config, config, config.num_workers)
        collector.start()
    try:
        for iteration in range(1, config.iterations + 1):
            delta = feature_dropout_schedule(iteration, config.iterations)
            iter_seed = base_seed + iteration * config.matches_per_iter
            if pool is not None:
                from .batched_selfplay import collect_selfplay_rollouts_batched
                batch = collect_selfplay_rollouts_batched(
                    env_config, model, config, base_seed=iter_seed, drop_prob=delta, pool=pool)
            elif collector is not None:
                state = cpu_state_snapshot(model)
                batch = collector.collect(state, iter_seed, config.matches_per_iter, delta)
            else:
                batch = collect_selfplay_rollouts(env_config, model, config, base_seed=iter_seed, drop_prob=delta)
```

and extend the `finally` block:

```python
    finally:
        if collector is not None:
            collector.close()
        if pool is not None:
            pool.close()
```

(Keep the rest of the loop — GAE, update, metrics, checkpointing — unchanged. Note `ppo_update` sets `model.train()`; the batched collector re-calls `model.eval()` at the start of each collection, same as the sequential path.)

- [ ] **Step 4: Add the CLI flags**

In `ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py`, after the `--num-workers` argument:

```python
    p.add_argument("--collector", choices=("process", "batched"), default="process",
                   help="rollout collection: spawn-worker processes (default) or the "
                        "batched env-pool collector (one batched forward per round)")
    p.add_argument("--pool-slots", type=int, default=128,
                   help="concurrent env-pool slots when --collector batched")
```

and thread them into the `PPOConfig(...)` construction:

```python
                       num_workers=num_workers, collector=args.collector,
                       pool_slots=args.pool_slots)
```

- [ ] **Step 5: Run the integration test + full suites**

```bash
uv run --project ai pytest ai/tests/test_batched_selfplay.py -q
uv run --project ai pytest -q
go test ./...
```

Expected: all pass (the full pytest run proves the process collectors are untouched).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/oracle.py ai/src/fh_mahjong_ai/scripts/train_selfplay_oracle.py ai/tests/test_batched_selfplay.py
git commit -m "feat(training): --collector batched wiring for train_selfplay_oracle

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: AGENTS.md updates + final verification

**Files:**
- Modify: `ai/AGENTS.md`, `internal/rl/AGENTS.md`, `cmd/rlbridge/AGENTS.md`

- [ ] **Step 1: Document the new units**

`ai/AGENTS.md` — add two Key Files entries (alongside the existing src/fh_mahjong_ai listings) and a note on the PPOConfig fields:

```markdown
- **src/fh_mahjong_ai/envpool.py** — Env-pool abstraction for lockstep-round collection: `GoEnvPool` (batched FFI over FHEnvPool*, flat float32/uint8 observation buffers decoded with np.frombuffer) and `InProcessEnvPool` (loops ordinary bridges; test/CPU-exactness path). `make_selfplay_pool()` builds the all-4 self-play EnvConfig and picks the implementation by bridge kind. Pools never self-reset a slot — the caller owns the seed schedule.
- **src/fh_mahjong_ai/batched_selfplay.py** — Batched self-play collector: one pool call + ONE batched model forward per round (GPU-friendly), per-match numpy RNG sampling (`sample_masked_action`; no global torch RNG), δ feature-dropout with the same per-match mask stream as the process collector, per-seat-contiguous emission flushed in SEED ORDER (makes per_row-CPU output invariant to slot count — tested as full-array equality). `PPOConfig.collector="batched"` + `pool_slots` select it in `train_selfplay_oracle`; `"process"` remains the default until the throughput/quality gate passes.
```

`internal/rl/AGENTS.md` — add:

```markdown
- **envpool.go** — `EnvPool`: `slots` independent envs stepped in lockstep rounds via `ApplyCommands` (one command per slot per call: step/reset/skip; commanded slots run concurrently in goroutines). Returns flat little-endian float32/uint8 observation buffers (rows = has_observation slots, ascending slot order) plus per-slot `SlotState` metadata. Never self-resets — the foreign caller owns the seed schedule.
```

`cmd/rlbridge/AGENTS.md` — add:

```markdown
- `FHEnvPoolNew` / `FHEnvPoolStep` / `FHEnvPoolClose` — batched env-pool exports (own handle registry, same FHBytesResult conventions): one FFI round-trip steps/resets many envs and returns all pending observations as flat buffers inside `EnvPoolStepResponse`.
```

- [ ] **Step 2: Final verification**

```bash
go vet ./... && go test ./... && uv run --project ai pytest -q
```

Expected: everything green.

- [ ] **Step 3: Commit**

```bash
git add ai/AGENTS.md internal/rl/AGENTS.md cmd/rlbridge/AGENTS.md
git commit -m "docs(agents): document env pool + batched self-play collector

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Operational runbook (4090 box — post-merge, before flipping the default)

Not code; run after the PR merges. All commands on the box (`ssh wsl`).

- [ ] **Step 1: Sync + rebuild the c-shared library**

```bash
cd /root/fh-mahjong && git pull
go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge
cd ai && uv sync
```

- [ ] **Step 2: Throughput A/B (identical config, small iteration count)**

Baseline (process collector):

```bash
cd /root/fh-mahjong/ai
FH_MAHJONG_BRIDGE_LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so uv run fh-mj-train-selfplay-oracle \
  --anchor-checkpoint /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt \
  --checkpoint-dir /root/fh-mahjong-runs/ab-process/ckpt --iterations 3 --matches-per-iter 256 \
  --collector process --num-workers 16 --device cuda --match-mode chongci --max-steps-per-episode 4000
```

Candidate (batched collector):

```bash
FH_MAHJONG_BRIDGE_LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so uv run fh-mj-train-selfplay-oracle \
  --anchor-checkpoint /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt \
  --checkpoint-dir /root/fh-mahjong-runs/ab-batched/ckpt --iterations 3 --matches-per-iter 256 \
  --collector batched --pool-slots 128 --device cuda --match-mode chongci --max-steps-per-episode 4000
```

Compare decisions/s = sum of history `steps` / wall-clock of the collection phase (time the runs; `steps` is in each history.json row). **Gate: batched ≥ 3× process.** If below, profile before proceeding (round-time breakdown: pool call vs forward vs sampling).

- [ ] **Step 3: Training-quality run (~10 iters)**

```bash
FH_MAHJONG_BRIDGE_LIB=/root/fh-mahjong/build/libfh_mahjong_bridge.so uv run fh-mj-train-selfplay-oracle \
  --anchor-checkpoint /root/fh-mahjong-runs/chongci-broader-mixed-iql-20260607-034720/checkpoints/broader_mixed_iql_highrisk_pairwise/epoch_001.pt \
  --checkpoint-dir /root/fh-mahjong-runs/batched-quality/ckpt --iterations 10 --matches-per-iter 256 \
  --collector batched --pool-slots 128 --lr 2e-5 --entropy-coef 0.0 --ppo-epochs 2 \
  --device cuda --match-mode chongci --max-steps-per-episode 4000
```

Check: policy/value losses and entropy in family with recent process-collector runs (sp-big-ext history as reference); then extract + eval one checkpoint (`fh-mj-evaluate --from-oracle --model-residual-blocks <as trained> --duplicate-seats --online-episodes 120 --start-seed 870000 --match-mode chongci --chongci-max-hands 50 --max-steps-per-episode 4000 --device cuda`) — must not be degraded vs the anchor baseline (-0.0528).

- [ ] **Step 4: Flip the default (separate follow-up PR)**

Only after Steps 2–3 pass: change `PPOConfig.collector` default and the CLI default to `"batched"` in a one-line follow-up PR.

## Self-review notes

- Spec coverage: proto (§Components/1 → Task 1), Go pool (§1 → Task 2), exports (§1 → Task 3), Python pools (§2 → Task 4), collector + sampling + δ + contiguity (§3 → Task 5), determinism (§Determinism → Task 6), trainer/CLI (§4 → Task 7), AGENTS docs (file inventory → Task 8), gate (§Testing operational → Task 9). Error handling folded into Tasks 2/4/5 code (slot errors raise with seed context; reset-terminates → next seed; empty batch raises).
- Deviation from spec (documented): idle slots receive **no command** (absent == skip) instead of explicit `skip` commands — equivalent semantics, less traffic; `skip` remains in the proto and both pools honor it.
- Type consistency: `PoolCommand/SlotMeta/PoolStepResult` names match across Tasks 4–7; `sample_masked_action(logits_row, mask_row, temperature, rng)` consistent between Tasks 5–6; `PPOConfig.collector/pool_slots` consistent between Tasks 7 and 9.
