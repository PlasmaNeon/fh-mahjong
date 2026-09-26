package rl

import (
	"testing"
	"time"

	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// BenchmarkEnvPoolRound drives a 320-slot pool the way the batched B2b
// collector does -- oracle observation, 128-event window, one lockstep round
// per op, first legal action per live slot, finished slots reset -- and
// includes the response marshal, so it measures one FHEnvPoolStep call minus
// the FFI copy.
func BenchmarkEnvPoolRound(b *testing.B) {
	pool, commands, seed := newBenchPool()
	rows := 0
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		response, err := pool.ApplyCommands(&pb.EnvPoolStepRequest{Commands: commands})
		if err != nil {
			b.Fatal(err)
		}
		if _, err := proto.Marshal(response); err != nil {
			b.Fatal(err)
		}
		rows += nextBenchCommands(response, commands, &seed)
	}
	b.ReportMetric(float64(rows)/float64(b.N), "rows/op")
}

func newBenchPool() (*EnvPool, []*pb.SlotCommand, uint64) {
	const slots = 320
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		MaxDecisions:       4000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 8},
		OracleObservation:  true,
		EventHistoryWindow: 128,
	}
	pool := NewEnvPool(config, slots)
	seed := uint64(1000)
	commands := make([]*pb.SlotCommand, slots)
	for i := range commands {
		commands[i] = &pb.SlotCommand{Slot: uint32(i), Cmd: &pb.SlotCommand_ResetSeed{ResetSeed: seed}}
		seed++
	}
	return pool, commands, seed
}

// nextBenchCommands turns a response into the next round's commands (first
// legal action per live slot, a fresh seed for every finished one) and
// returns the number of live rows.
func nextBenchCommands(response *pb.EnvPoolStepResponse, commands []*pb.SlotCommand, seed *uint64) int {
	mask := int(response.ActionSpaceSize)
	row := 0
	for j, state := range response.Slots {
		if state.HasObservation {
			action := firstLegal(response.ActionMasks[row*mask : (row+1)*mask])
			commands[j] = &pb.SlotCommand{Slot: state.Slot, Cmd: &pb.SlotCommand_ActionId{ActionId: action}}
			row++
		} else {
			commands[j] = &pb.SlotCommand{Slot: state.Slot, Cmd: &pb.SlotCommand_ResetSeed{ResetSeed: *seed}}
			*seed++
		}
	}
	return row
}

// BenchmarkEnvPoolRoundPhases splits one round into the parallel env step,
// the single-threaded response assembly and the marshal.
func BenchmarkEnvPoolRoundPhases(b *testing.B) {
	pool, commands, seed := newBenchPool()
	var stepNs, assembleNs, marshalNs int64
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		t0 := time.Now()
		results, err := runSlotCommands(commands, len(pool.envs), "slots", pool.applyOne)
		if err != nil {
			b.Fatal(err)
		}
		t1 := time.Now()
		response, _ := assemblePoolResponse(results)
		t2 := time.Now()
		if _, err := proto.Marshal(response); err != nil {
			b.Fatal(err)
		}
		t3 := time.Now()
		stepNs += t1.Sub(t0).Nanoseconds()
		assembleNs += t2.Sub(t1).Nanoseconds()
		marshalNs += t3.Sub(t2).Nanoseconds()
		nextBenchCommands(response, commands, &seed)
	}
	b.ReportMetric(float64(stepNs)/float64(b.N)/1e6, "step-ms")
	b.ReportMetric(float64(assembleNs)/float64(b.N)/1e6, "assemble-ms")
	b.ReportMetric(float64(marshalNs)/float64(b.N)/1e6, "marshal-ms")
}
