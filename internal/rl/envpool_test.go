package rl

import (
	"math"
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

func float32frombits(b uint32) float32 { return math.Float32frombits(b) }
