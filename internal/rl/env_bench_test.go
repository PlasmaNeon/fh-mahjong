package rl

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

// BenchmarkEnvStepChongci drives full Chongci matches the way PPO rollout
// collection does (all four seats are learning seats, picked greedily by mask),
// so the CPU profile reflects the real per-decision env.step cost: rules state
// machine + observation encoding (shanten/ukeire/danger).
func BenchmarkEnvStepChongci(b *testing.B) {
	newEnv := func() *Env {
		return New(&pb.EnvConfig{
			LearningSeats:      []uint32{0, 1, 2, 3},
			AutoPlayHeuristics: false,
			MaxDecisions:       8192,
			MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 3},
		})
	}

	firstLegal := func(mask []byte) int {
		for i, v := range mask {
			if v == 1 {
				return i
			}
		}
		return 0
	}

	b.ReportAllocs()
	b.ResetTimer()

	decisions := 0
	seed := uint64(900)
	env := newEnv()
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: env.config})
	if err != nil {
		b.Fatalf("reset: %v", err)
	}
	obs := reset.Observation
	terminated, truncated := reset.Terminated, reset.Truncated

	for i := 0; i < b.N; i++ {
		if terminated || truncated {
			seed++
			env = newEnv()
			reset, err = env.Reset(&pb.EnvResetRequest{Seed: seed, Config: env.config})
			if err != nil {
				b.Fatalf("reset: %v", err)
			}
			obs = reset.Observation
			terminated, truncated = reset.Terminated, reset.Truncated
			continue
		}
		step, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(firstLegal(obs.ActionMask))})
		if err != nil {
			b.Fatalf("step: %v", err)
		}
		obs = step.Observation
		terminated, truncated = step.Terminated, step.Truncated
		decisions++
	}
	b.ReportMetric(float64(decisions), "decisions")
}
