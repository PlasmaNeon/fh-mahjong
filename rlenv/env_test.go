package rlenv

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

func TestDeterministicResetAndStep(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
	}

	envA := New(config)
	envB := New(config)

	resetA, err := envA.Reset(&pb.EnvResetRequest{Seed: 17, Config: config})
	if err != nil {
		t.Fatalf("envA reset failed: %v", err)
	}
	resetB, err := envB.Reset(&pb.EnvResetRequest{Seed: 17, Config: config})
	if err != nil {
		t.Fatalf("envB reset failed: %v", err)
	}

	assertObservationEqual(t, resetA.Observation, resetB.Observation)

	actionID := firstLegalActionID(resetA.Observation.ActionMask)
	stepA, err := envA.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
	if err != nil {
		t.Fatalf("envA step failed: %v", err)
	}
	stepB, err := envB.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
	if err != nil {
		t.Fatalf("envB step failed: %v", err)
	}

	assertObservationEqual(t, stepA.Observation, stepB.Observation)
	assertFloatSliceEqual(t, stepA.Rewards, stepB.Rewards)
	if stepA.Terminated != stepB.Terminated || stepA.Truncated != stepB.Truncated {
		t.Fatalf("step terminal mismatch: %#v vs %#v", stepA, stepB)
	}
}

func TestActionRoundTripForCurrentMask(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
	}

	env := New(config)
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 23, Config: config})
	if err != nil {
		t.Fatalf("reset failed: %v", err)
	}

	seat := reset.Observation.Seat
	for actionID, enabled := range reset.Observation.ActionMask {
		if enabled == 0 {
			continue
		}
		action, err := decodeActionID(env.game.State, seat, actionID)
		if err != nil {
			t.Fatalf("decode failed for action %d: %v", actionID, err)
		}
		encoded, ok := encodeAction(env.game.State, seat, action)
		if !ok {
			t.Fatalf("encode failed for action %d", actionID)
		}
		if encoded != actionID {
			t.Fatalf("action %d round-tripped to %d", actionID, encoded)
		}
	}
}

func TestObservationIgnoresHiddenOpponentTiles(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
	}

	env := New(config)
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 29, Config: config})
	if err != nil {
		t.Fatalf("reset failed: %v", err)
	}

	seat := reset.Observation.Seat
	stateA := proto.Clone(env.game.State).(*pb.GameState)
	stateB := proto.Clone(env.game.State).(*pb.GameState)

	opponentSeat := (seat + 1) % 4
	stateB.Players[opponentSeat].ClosedHand = []*pb.Tile{
		{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 1},
		{Id: 901, Suit: pb.Suit_SUIT_MAN, Value: 2},
		{Id: 902, Suit: pb.Suit_SUIT_MAN, Value: 3},
		{Id: 903, Suit: pb.Suit_SUIT_PIN, Value: 4},
	}
	stateB.Players[opponentSeat].HandSize = stateA.Players[opponentSeat].HandSize

	observationA, err := encodeObservation(stateA, seat, 0)
	if err != nil {
		t.Fatalf("encode observation A failed: %v", err)
	}
	observationB, err := encodeObservation(stateB, seat, 0)
	if err != nil {
		t.Fatalf("encode observation B failed: %v", err)
	}

	assertObservationEqual(t, observationA, observationB)
}

func TestGenerateHeuristicTrajectoryDeterministic(t *testing.T) {
	request := &pb.TrajectoryRequest{
		Episodes:  1,
		StartSeed: 31,
		Config: &pb.EnvConfig{
			AutoPlayHeuristics: true,
			MaxDecisions:       128,
		},
	}

	envA := New(nil)
	envB := New(nil)

	datasetA, err := envA.GenerateHeuristicTrajectory(request)
	if err != nil {
		t.Fatalf("datasetA generation failed: %v", err)
	}
	datasetB, err := envB.GenerateHeuristicTrajectory(request)
	if err != nil {
		t.Fatalf("datasetB generation failed: %v", err)
	}

	if !proto.Equal(datasetA, datasetB) {
		t.Fatalf("heuristic trajectory export is not deterministic")
	}
	if len(datasetA.Samples) == 0 {
		t.Fatalf("expected heuristic dataset to contain samples")
	}

	terminalRewards := datasetA.Samples[len(datasetA.Samples)-1].TerminalRewards
	if len(terminalRewards) != 4 {
		t.Fatalf("expected four terminal rewards, got %v", terminalRewards)
	}
	terminalOutcome := datasetA.Samples[len(datasetA.Samples)-1].TerminalOutcome
	if datasetA.Samples[len(datasetA.Samples)-1].Terminated && terminalOutcome == nil {
		t.Fatalf("expected terminal sample to include round outcome")
	}

	sawIntermediateStep := false
	for _, sample := range datasetA.Samples {
		if !almostEqualSlices(sample.TerminalRewards, terminalRewards) {
			t.Fatalf("terminal rewards drifted across samples")
		}
		if terminalOutcome != nil && sample.TerminalOutcome == nil {
			t.Fatalf("terminal outcome missing from sample")
		}
		if sample.Terminated || sample.Truncated {
			continue
		}
		sawIntermediateStep = true
		if !almostEqualSlices(sample.Rewards, []float32{0, 0, 0, 0}) {
			t.Fatalf("expected intermediate step rewards to remain immediate rewards, got %v", sample.Rewards)
		}
	}
	if !sawIntermediateStep {
		t.Fatalf("expected at least one non-terminal sample in heuristic dataset")
	}
}

func firstLegalActionID(mask []byte) int {
	for actionID, enabled := range mask {
		if enabled == 1 {
			return actionID
		}
	}
	return -1
}

func assertObservationEqual(t *testing.T, lhs *pb.SeatObservation, rhs *pb.SeatObservation) {
	t.Helper()

	if lhs.Seat != rhs.Seat || lhs.Phase != rhs.Phase || lhs.ActivePlayer != rhs.ActivePlayer || lhs.DecisionIndex != rhs.DecisionIndex {
		t.Fatalf("observation metadata mismatch: %#v vs %#v", lhs, rhs)
	}
	if lhs.PlaneChannels != rhs.PlaneChannels || lhs.PlaneHeight != rhs.PlaneHeight || lhs.PlaneWidth != rhs.PlaneWidth || lhs.ActionSpaceSize != rhs.ActionSpaceSize {
		t.Fatalf("observation shape mismatch: %#v vs %#v", lhs, rhs)
	}
	if !almostEqualSlices(lhs.Planes, rhs.Planes) {
		t.Fatalf("observation planes differ")
	}
	if !almostEqualSlices(lhs.Scalars, rhs.Scalars) {
		t.Fatalf("observation scalars differ")
	}
	if string(lhs.ActionMask) != string(rhs.ActionMask) {
		t.Fatalf("observation masks differ")
	}
}

func assertFloatSliceEqual(t *testing.T, lhs []float32, rhs []float32) {
	t.Helper()
	if !almostEqualSlices(lhs, rhs) {
		t.Fatalf("float slices differ: %v vs %v", lhs, rhs)
	}
}
