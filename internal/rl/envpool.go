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

	results := make([]slotResult, len(commands))
	var wg sync.WaitGroup
	for i, cmd := range commands {
		wg.Add(1)
		go func(i int, cmd *pb.SlotCommand) {
			defer wg.Done()
			results[i] = apply(cmd)
		}(i, cmd)
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
			state.Seat = r.observation.Seat
			appendObservationRow(response, r.observation)
		}
		response.Slots = append(response.Slots, state)
	}
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
			response.EventHistories = append(response.EventHistories, make([]byte, 4*pad)...)
		}
	}
}

func appendFloat32LE(dst []byte, values []float32) []byte {
	off := len(dst)
	dst = append(dst, make([]byte, 4*len(values))...)
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], math.Float32bits(v))
	}
	return dst
}

func appendUint32LE(dst []byte, values []uint32) []byte {
	off := len(dst)
	dst = append(dst, make([]byte, 4*len(values))...)
	for i, v := range values {
		binary.LittleEndian.PutUint32(dst[off+4*i:], v)
	}
	return dst
}
