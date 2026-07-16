package rl

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func oracleTestEnv(t *testing.T) *Env {
	t.Helper()
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 50},
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 7, Config: config}); err != nil {
		t.Fatalf("reset failed: %v", err)
	}
	return env
}

func TestOracleObservationAppendsOpponentHands(t *testing.T) {
	env := oracleTestEnv(t)
	state := env.game.State

	normal, err := encodeObservation(state, 0, 0, false, nil, 0)
	if err != nil {
		t.Fatalf("normal encode: %v", err)
	}
	oracle, err := encodeObservation(state, 0, 0, true, nil, 0)
	if err != nil {
		t.Fatalf("oracle encode: %v", err)
	}

	if normal.PlaneChannels != 39 {
		t.Fatalf("normal channels = %d, want 39", normal.PlaneChannels)
	}
	if oracle.PlaneChannels != 51 {
		t.Fatalf("oracle channels = %d, want 51", oracle.PlaneChannels)
	}

	// Prefix invariant: channels 0..38 are byte-identical.
	prefix := 39 * ObservationPlaneHeight * ObservationPlaneWidth
	for i := 0; i < prefix; i++ {
		if normal.Planes[i] != oracle.Planes[i] {
			t.Fatalf("prefix mismatch at %d: normal=%v oracle=%v", i, normal.Planes[i], oracle.Planes[i])
		}
	}

	// Appended planes equal opponents' closed-hand threshold encodings.
	// Seat 0's opponents: right=1, across=2, left=3; appended at channels 39,43,47.
	for offset, oppSeat := range []uint32{1, 2, 3} {
		baseChannel := 39 + offset*4
		counts := faceCountsFromTiles(state.Players[oppSeat].ClosedHand)
		want := make([]float32, 4*ObservationPlaneHeight*ObservationPlaneWidth)
		setThresholdPlanes(want, 0, counts) // write into a fresh 4-channel buffer
		for c := 0; c < 4; c++ {
			for f := 0; f < ObservationPlaneHeight*ObservationPlaneWidth; f++ {
				got := oracle.Planes[channelOffset(baseChannel+c)+f]
				exp := want[c*ObservationPlaneHeight*ObservationPlaneWidth+f]
				if got != exp {
					t.Fatalf("opp seat %d channel %d face %d: got %v want %v", oppSeat, c, f, got, exp)
				}
			}
		}
	}
}
