package rl

import (
	"encoding/binary"
	"fmt"
	"math"
	"runtime"
	"slices"
	"sort"
	"sync"
	"sync/atomic"

	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// EnvPool holds `slots` independent environments stepped in lockstep rounds by
// a single foreign caller. Each ApplyCommands call applies at most one command
// (step / reset / skip) per slot; commanded slots are processed concurrently
// (each env is touched only by its own goroutine). The pool never self-resets:
// the caller owns the seed schedule.
type EnvPool struct {
	config *pb.EnvConfig
	envs   []*Env

	// StepMarshaled's buffers, reused across rounds: a 320-slot round packs and
	// marshals ~3 MB twice, and fresh large allocations every round cost more in
	// span allocation and page faults (madvise) than the copies themselves.
	mu      sync.Mutex
	scratch poolScratch
}

// poolScratch holds reusable response buffers. Everything in them is valid only
// until the next StepMarshaled call on the same pool.
type poolScratch struct {
	planes, scalars, masks, counts, events, out []byte
}

// sized returns buf resliced to n bytes, reallocating only when it is too small.
// The contents are stale; callers overwrite every byte or clear it.
func sized(buf *[]byte, n int) []byte {
	if cap(*buf) < n {
		*buf = make([]byte, n)
	}
	*buf = (*buf)[:n]
	return *buf
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

// runSlotCommands validates a batch of per-slot commands and applies them
// concurrently, one goroutine per commanded slot, returning the results in slot
// order. Shared by EnvPool.ApplyCommands and SearchPool.Step: both pools accept
// at most one command per slot and both must return slot-ordered results,
// because the Python side zips the response against its own slot list.
//
// slotNoun appears in the out-of-range error ("slots" for the env pool,
// "clones" for the search pool).
func runSlotCommands(commands []*pb.SlotCommand, slotCount int, slotNoun string, apply func(*pb.SlotCommand) slotResult) ([]slotResult, error) {
	seen := make(map[uint32]bool, len(commands))
	for _, cmd := range commands {
		if int(cmd.GetSlot()) >= slotCount {
			return nil, fmt.Errorf("slot %d out of range (pool has %d %s)", cmd.GetSlot(), slotCount, slotNoun)
		}
		if seen[cmd.GetSlot()] {
			return nil, fmt.Errorf("duplicate command for slot %d", cmd.GetSlot())
		}
		seen[cmd.GetSlot()] = true
	}

	// At most GOMAXPROCS workers pull commands off a shared counter. One
	// goroutine per slot (hundreds per round) spent a large share of the round
	// in the scheduler and in regrowing each new goroutine's stack through the
	// observation encoder; a worker keeps its grown stack across commands.
	// Each env is still touched by exactly one goroutine per call.
	results := make([]slotResult, len(commands))
	workers := min(len(commands), runtime.GOMAXPROCS(0))
	var next atomic.Int64
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for {
				i := int(next.Add(1) - 1)
				if i >= len(commands) {
					return
				}
				results[i] = apply(commands[i])
			}
		}()
	}
	wg.Wait()

	sort.Slice(results, func(a, b int) bool { return results[a].slot < results[b].slot })
	return results, nil
}

func (p *EnvPool) ApplyCommands(request *pb.EnvPoolStepRequest) (*pb.EnvPoolStepResponse, error) {
	results, err := runSlotCommands(request.GetCommands(), len(p.envs), "slots", p.applyOne)
	if err != nil {
		return nil, err
	}
	return assemblePoolResponse(results, nil)
}

// StepMarshaled is ApplyCommands followed by proto.Marshal, byte-identical to it
// (TestStepMarshaledMatchesApplyCommands), with the flat observation buffers and
// the marshal output reused across calls. The returned bytes are valid only until
// the next StepMarshaled call on this pool; the caller must copy them first.
func (p *EnvPool) StepMarshaled(request *pb.EnvPoolStepRequest) ([]byte, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	results, err := runSlotCommands(request.GetCommands(), len(p.envs), "slots", p.applyOne)
	if err != nil {
		return nil, err
	}
	response, err := assemblePoolResponse(results, &p.scratch)
	if err != nil {
		return nil, err
	}
	out, err := proto.MarshalOptions{}.MarshalAppend(p.scratch.out[:0], response)
	if err != nil {
		return nil, err
	}
	p.scratch.out = out
	return out, nil
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

// assemblePoolResponse builds the response; with a non-nil scratch the flat
// buffers alias it (see poolScratch).
func assemblePoolResponse(results []slotResult, scratch *poolScratch) (*pb.EnvPoolStepResponse, error) {
	response := &pb.EnvPoolStepResponse{Slots: make([]*pb.SlotState, 0, len(results))}
	var observations []*pb.SeatObservation
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
			state.Seat = r.observation.Seat
			observations = append(observations, r.observation)
		}
		response.Slots = append(response.Slots, state)
	}
	packObservationRows(response, observations, scratch)
	return response, nil
}

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
			off := len(response.EventHistories)
			response.EventHistories = slices.Grow(response.EventHistories, 4*pad)[:off+4*pad]
			clear(response.EventHistories[off:])
		}
	}
}

// packObservationRows writes the rows exactly as successive
// appendObservationRow calls would (pinned by
// TestPackObservationRowsMatchesAppend), but sizes every buffer once and
// fills disjoint row ranges from GOMAXPROCS workers: packing ~3 MB of
// float32s one row at a time was a single-threaded ~1 ms per round.
func packObservationRows(response *pb.EnvPoolStepResponse, observations []*pb.SeatObservation, scratch *poolScratch) {
	if len(observations) == 0 {
		return
	}
	first := observations[0]
	response.PlaneChannels = first.PlaneChannels
	response.PlaneHeight = first.PlaneHeight
	response.PlaneWidth = first.PlaneWidth
	response.ScalarCount = uint32(len(first.Scalars))
	response.ActionSpaceSize = first.ActionSpaceSize
	response.EventHistoryWindow = first.EventHistoryWindow
	window := int(first.EventHistoryWindow)

	// Byte offset of each row in each buffer; row i spans [off[i], off[i+1]).
	n := len(observations)
	planeOff := make([]int, n+1)
	scalarOff := make([]int, n+1)
	maskOff := make([]int, n+1)
	eventOff := make([]int, n+1)
	for i, obs := range observations {
		planeOff[i+1] = planeOff[i] + 4*len(obs.Planes)
		scalarOff[i+1] = scalarOff[i] + 4*len(obs.Scalars)
		maskOff[i+1] = maskOff[i] + len(obs.ActionMask)
		if window > 0 {
			eventOff[i+1] = eventOff[i] + 4*max(window, len(obs.EventHistory))
		}
	}
	if scratch == nil {
		scratch = &poolScratch{}
	}
	// Planes, scalars, masks and counts are fully overwritten below.
	response.Planes = sized(&scratch.planes, planeOff[n])
	response.Scalars = sized(&scratch.scalars, scalarOff[n])
	response.ActionMasks = sized(&scratch.masks, maskOff[n])
	if window > 0 {
		response.EventCounts = sized(&scratch.counts, 4*n)
		// Zeroed, so each row's tail padding is in place.
		response.EventHistories = sized(&scratch.events, eventOff[n])
		clear(response.EventHistories)
	}

	workers := min(n, runtime.GOMAXPROCS(0))
	var wg sync.WaitGroup
	for w := 0; w < workers; w++ {
		wg.Add(1)
		go func(lo, hi int) {
			defer wg.Done()
			for i := lo; i < hi; i++ {
				obs := observations[i]
				putFloat32LE(response.Planes[planeOff[i]:], obs.Planes)
				putFloat32LE(response.Scalars[scalarOff[i]:], obs.Scalars)
				copy(response.ActionMasks[maskOff[i]:], obs.ActionMask)
				if window > 0 {
					binary.LittleEndian.PutUint32(response.EventCounts[4*i:], uint32(len(obs.EventHistory)))
					putUint32LE(response.EventHistories[eventOff[i]:], obs.EventHistory)
				}
			}
		}(w*n/workers, (w+1)*n/workers)
	}
	wg.Wait()
}

func putFloat32LE(dst []byte, values []float32) {
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[4*i:], math.Float32bits(v))
	}
}

func putUint32LE(dst []byte, values []uint32) {
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[4*i:], v)
	}
}

func appendFloat32LE(dst []byte, values []float32) []byte {
	off := len(dst)
	dst = slices.Grow(dst, 4*len(values))[:off+4*len(values)]
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], math.Float32bits(v))
	}
	return dst
}

func appendUint32LE(dst []byte, values []uint32) []byte {
	off := len(dst)
	dst = slices.Grow(dst, 4*len(values))[:off+4*len(values)]
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], v)
	}
	return dst
}
