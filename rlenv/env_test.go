package rlenv

import (
	"testing"

	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
	"github.com/plasma/fh-mahjong/rules/shanten"
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

func TestObservationIncludesVisibleLookaheadScalars(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
	}

	env := New(config)
	reset, err := env.Reset(&pb.EnvResetRequest{Seed: 37, Config: config})
	if err != nil {
		t.Fatalf("reset failed: %v", err)
	}

	observation := reset.Observation
	if len(observation.Scalars) != ObservationScalarCount {
		t.Fatalf("scalar count = %d, want %d", len(observation.Scalars), ObservationScalarCount)
	}

	player := env.game.State.Players[observation.Seat]
	analysis := shanten.AnalyzeHand(player.ClosedHand, len(player.OpenMelds), env.game.State.WildTiles)
	if observation.Scalars[29] != normalizeShanten(analysis.Routes.Standard) {
		t.Fatalf("standard shanten scalar = %v, want %v", observation.Scalars[29], normalizeShanten(analysis.Routes.Standard))
	}
	if observation.Scalars[30] != normalizeShanten(analysis.Routes.SevenPairs) {
		t.Fatalf("seven-pairs shanten scalar = %v, want %v", observation.Scalars[30], normalizeShanten(analysis.Routes.SevenPairs))
	}
	if observation.Scalars[31] != normalizeShanten(analysis.Routes.Independence) {
		t.Fatalf("independence shanten scalar = %v, want %v", observation.Scalars[31], normalizeShanten(analysis.Routes.Independence))
	}
	if observation.Scalars[32] != normalizeUsefulTileCount(analysis.TotalUseful) {
		t.Fatalf("ukeire scalar = %v, want %v", observation.Scalars[32], normalizeUsefulTileCount(analysis.TotalUseful))
	}
	for index := 29; index < ObservationScalarCount; index++ {
		if observation.Scalars[index] < 0 || observation.Scalars[index] > 1 {
			t.Fatalf("lookahead scalar[%d] out of range: %v", index, observation.Scalars[index])
		}
	}
}

func TestObservationIncludesChongciMatchContextScalars(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 2000,
			BustThreshold: 0,
			MaxHands:      50,
		},
	}

	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 43, Config: config}); err != nil {
		t.Fatalf("reset failed: %v", err)
	}

	env.game.State.HandNum = 10
	env.game.State.Players[0].Score = 1500
	env.game.State.Players[1].Score = 2500
	env.game.State.Players[2].Score = 1000
	env.game.State.Players[3].Score = -100
	observation, err := encodeObservation(env.game.State, 0, 0)
	if err != nil {
		t.Fatalf("encode observation failed: %v", err)
	}

	scalars := observation.Scalars
	if len(scalars) != ObservationScalarCount {
		t.Fatalf("scalar count = %d, want %d", len(scalars), ObservationScalarCount)
	}
	expected := []float32{
		1.0,
		0.2,
		0.8,
		2.0 / 3.0,
		0.5,
		0.25,
		0.75,
		1.0,
	}
	if !almostEqualSlices(scalars[42:50], expected) {
		t.Fatalf("chongci scalar tail = %v, want %v", scalars[42:50], expected)
	}
}

func TestPublicDangerDropsAfterSameTileIsVisible(t *testing.T) {
	target := &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 5}
	state := &pb.GameState{
		Players: []*pb.PlayerState{
			{Seat: 0, HandSize: 13},
			{Seat: 1, HandSize: 13},
			{Seat: 2, HandSize: 13},
			{Seat: 3, HandSize: 13},
		},
	}

	unknownDanger := publicDangerScore(state, 0, target)
	state.Players[1].Discards = []*pb.Tile{{Suit: pb.Suit_SUIT_MAN, Value: 5}}
	seenDanger := publicDangerScore(state, 0, target)

	if seenDanger >= unknownDanger {
		t.Fatalf("expected visible same-tile discard to reduce danger, got before=%v after=%v", unknownDanger, seenDanger)
	}
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

func TestGenerateHeuristicTrajectoryChongciReachesMatchEnd(t *testing.T) {
	request := &pb.TrajectoryRequest{
		Episodes:  1,
		StartSeed: 41,
		Config: &pb.EnvConfig{
			AutoPlayHeuristics: true,
			MaxDecisions:       4096,
			MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
			ChongciConfig: &pb.ChongciConfig{
				StartingScore: 2000,
				BustThreshold: 0,
				MaxHands:      1,
			},
		},
	}

	env := New(nil)
	dataset, err := env.GenerateHeuristicTrajectory(request)
	if err != nil {
		t.Fatalf("chongci dataset generation failed: %v", err)
	}
	if len(dataset.Samples) == 0 {
		t.Fatalf("expected chongci heuristic dataset to contain samples")
	}

	last := dataset.Samples[len(dataset.Samples)-1]
	if !last.Terminated {
		t.Fatalf("expected chongci trajectory to terminate at match end")
	}
	if len(last.TerminalRewards) != 4 {
		t.Fatalf("expected four chongci terminal rewards, got %v", last.TerminalRewards)
	}
	if last.Observation == nil || last.Observation.Phase == pb.GamePhase_PHASE_MATCH_END {
		t.Fatalf("terminal sample should keep the acting observation before match end")
	}
	for _, sample := range dataset.Samples {
		if !almostEqualSlices(sample.TerminalRewards, last.TerminalRewards) {
			t.Fatalf("terminal rewards drifted across chongci samples")
		}
	}
}

func TestChongciResetDeterministicAcrossMultipleHands(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       4096,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig: &pb.ChongciConfig{
			StartingScore: 100000,
			BustThreshold: 0,
			MaxHands:      2,
		},
	}

	envA := New(config)
	envB := New(config)
	responseA, err := envA.Reset(&pb.EnvResetRequest{Seed: 61, Config: config})
	if err != nil {
		t.Fatalf("envA reset failed: %v", err)
	}
	responseB, err := envB.Reset(&pb.EnvResetRequest{Seed: 61, Config: config})
	if err != nil {
		t.Fatalf("envB reset failed: %v", err)
	}
	assertResetResponseEqual(t, responseA, responseB)

	maxHandNum := envA.game.State.HandNum
	for step := 0; step < int(config.MaxDecisions); step++ {
		if responseA.Terminated || responseA.Truncated {
			break
		}
		if envA.game.State.HandNum != envB.game.State.HandNum {
			t.Fatalf("hand number mismatch at step %d: %d vs %d", step, envA.game.State.HandNum, envB.game.State.HandNum)
		}
		if envA.game.State.WallSeed != envB.game.State.WallSeed {
			t.Fatalf("wall seed mismatch at step %d", step)
		}

		seat := responseA.Observation.Seat
		action := envA.heuristic.ChooseAction(envA.game.State, seat)
		if action == nil {
			t.Fatalf("heuristic returned nil action for seat %d at step %d", seat, step)
		}
		actionID, ok := encodeAction(envA.game.State, seat, action)
		if !ok {
			t.Fatalf("cannot encode heuristic action %v for seat %d at step %d", action.Type, seat, step)
		}

		stepA, err := envA.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
		if err != nil {
			t.Fatalf("envA step %d failed: %v", step, err)
		}
		stepB, err := envB.Step(&pb.EnvStepRequest{ActionId: uint32(actionID)})
		if err != nil {
			t.Fatalf("envB step %d failed for shared action %d: %v", step, actionID, err)
		}
		assertStepResponseEqual(t, stepA, stepB)
		if envA.game.State.HandNum > maxHandNum {
			maxHandNum = envA.game.State.HandNum
		}
		responseA = &pb.EnvResetResponse{
			Observation:  stepA.Observation,
			Rewards:      stepA.Rewards,
			Terminated:   stepA.Terminated,
			Truncated:    stepA.Truncated,
			RoundOutcome: stepA.RoundOutcome,
		}
		responseB = &pb.EnvResetResponse{
			Observation:  stepB.Observation,
			Rewards:      stepB.Rewards,
			Terminated:   stepB.Terminated,
			Truncated:    stepB.Truncated,
			RoundOutcome: stepB.RoundOutcome,
		}
	}

	if maxHandNum < 2 {
		t.Fatalf("expected deterministic replay to cross into a later Chongci hand, max hand = %d", maxHandNum)
	}
	if !responseA.Terminated {
		t.Fatalf("expected two-hand Chongci match to terminate, got terminated=%t truncated=%t", responseA.Terminated, responseA.Truncated)
	}
}

func TestAdvanceToDecisionResolvesReadyInterruptWindowWithoutAutoplay(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       128,
	}

	env := New(config)
	env.game = core.NewGame("ready-interrupt-window", &rules.HometownRuleset{}, core.MatchOptions{})
	env.game.SetWallSeed(core.SeedFromUint64(101))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start failed: %v", err)
	}

	// This mirrors a WAIT_DISCARDS edge case hit during long heuristic exports:
	// no non-active interrupt seat still needs input, but the active discarder
	// has stale turn actions. The RL wrapper should resolve the interrupt
	// window instead of treating it as a non-learning-seat dead end.
	active := env.game.State.ActivePlayer
	env.game.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	env.game.State.ActiveDiscard = env.game.State.Players[active].ClosedHand[0]
	for seat, player := range env.game.State.Players {
		if uint32(seat) == active {
			player.ValidActions = []*pb.PlayerAction{{Type: pb.ActionType_ACTION_DISCARD, Tile: player.ClosedHand[0]}}
			continue
		}
		player.ValidActions = nil
	}

	response, err := env.advanceToDecision()
	if err != nil {
		t.Fatalf("advanceToDecision failed: %v", err)
	}
	if response.Terminated || response.Truncated {
		t.Fatalf("expected next decision, got terminal response: %#v", response)
	}
	if response.Observation == nil {
		t.Fatalf("expected next observation")
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

func assertResetResponseEqual(t *testing.T, lhs *pb.EnvResetResponse, rhs *pb.EnvResetResponse) {
	t.Helper()
	assertObservationEqual(t, lhs.Observation, rhs.Observation)
	assertFloatSliceEqual(t, lhs.Rewards, rhs.Rewards)
	if lhs.Terminated != rhs.Terminated || lhs.Truncated != rhs.Truncated {
		t.Fatalf("reset terminal mismatch: %#v vs %#v", lhs, rhs)
	}
	if !proto.Equal(lhs.RoundOutcome, rhs.RoundOutcome) {
		t.Fatalf("reset round outcome mismatch: %#v vs %#v", lhs.RoundOutcome, rhs.RoundOutcome)
	}
}

func assertStepResponseEqual(t *testing.T, lhs *pb.EnvStepResponse, rhs *pb.EnvStepResponse) {
	t.Helper()
	assertObservationEqual(t, lhs.Observation, rhs.Observation)
	assertFloatSliceEqual(t, lhs.Rewards, rhs.Rewards)
	if lhs.Terminated != rhs.Terminated || lhs.Truncated != rhs.Truncated {
		t.Fatalf("step terminal mismatch: %#v vs %#v", lhs, rhs)
	}
	if !proto.Equal(lhs.RoundOutcome, rhs.RoundOutcome) {
		t.Fatalf("step round outcome mismatch: %#v vs %#v", lhs.RoundOutcome, rhs.RoundOutcome)
	}
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
