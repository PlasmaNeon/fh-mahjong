package rl

import (
	"math/rand"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// assertServingParity is the gate-layer-1 assertion: the exported serving
// encoder EncodeObservationWithEvents must be proto.Equal AND marshal
// byte-equal to the internal eval-path chokepoint encodeObservation(..., false, ...)
// for identical inputs. Any future divergence between the two call sites
// (e.g. someone adding a serving-only transform) fails this test.
func assertServingParity(t *testing.T, state *pb.GameState, seat uint32, decisionIndex uint64, events []engine.PublicEvent, window uint32) {
	t.Helper()

	want, err := encodeObservation(state, seat, decisionIndex, false, events, window)
	if err != nil {
		t.Fatalf("encodeObservation: %v", err)
	}
	got, err := EncodeObservationWithEvents(state, seat, decisionIndex, events, window)
	if err != nil {
		t.Fatalf("EncodeObservationWithEvents: %v", err)
	}

	if !proto.Equal(want, got) {
		t.Fatalf("EncodeObservationWithEvents diverges from encodeObservation (proto.Equal false)\nwant=%+v\ngot=%+v", want, got)
	}

	wantRaw, err := proto.Marshal(want)
	if err != nil {
		t.Fatalf("marshal want: %v", err)
	}
	gotRaw, err := proto.Marshal(got)
	if err != nil {
		t.Fatalf("marshal got: %v", err)
	}
	if len(wantRaw) != len(gotRaw) {
		t.Fatalf("marshal length differs: want %d got %d", len(wantRaw), len(gotRaw))
	}
	for i := range wantRaw {
		if wantRaw[i] != gotRaw[i] {
			t.Fatalf("marshal bytes differ at offset %d: want 0x%02X got 0x%02X", i, wantRaw[i], gotRaw[i])
		}
	}
}

// TestServingParity_WindowZeroMatchesLegacy pins window=0 output to be
// byte-identical to the pre-B1 3-arg EncodeObservation, in addition to the
// eval-path parity assertion.
func TestServingParity_WindowZeroMatchesLegacy(t *testing.T) {
	env := newSeededHistoryEnv(t, 1, 0)
	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("no current action seat")
	}
	state := env.game.State
	events := env.game.PublicEvents()

	assertServingParity(t, state, seat, env.decisionCount, events, 0)

	legacy, err := EncodeObservation(state, seat, env.decisionCount)
	if err != nil {
		t.Fatalf("EncodeObservation: %v", err)
	}
	withEvents, err := EncodeObservationWithEvents(state, seat, env.decisionCount, events, 0)
	if err != nil {
		t.Fatalf("EncodeObservationWithEvents: %v", err)
	}
	legacyRaw, err := proto.Marshal(legacy)
	if err != nil {
		t.Fatalf("marshal legacy: %v", err)
	}
	withEventsRaw, err := proto.Marshal(withEvents)
	if err != nil {
		t.Fatalf("marshal withEvents: %v", err)
	}
	if len(legacyRaw) != len(withEventsRaw) {
		t.Fatalf("window=0: byte length differs from legacy EncodeObservation: %d vs %d", len(legacyRaw), len(withEventsRaw))
	}
	for i := range legacyRaw {
		if legacyRaw[i] != withEventsRaw[i] {
			t.Fatalf("window=0: byte %d differs from legacy EncodeObservation", i)
		}
	}
}

// TestServingParity_FreshRoundStart covers a fresh round start with no
// events at all — the events slice is empty/nil.
func TestServingParity_FreshRoundStart(t *testing.T) {
	env := newSeededHistoryEnv(t, 2, 128)
	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("no current action seat")
	}
	assertServingParity(t, env.game.State, seat, env.decisionCount, nil, 128)
}

// TestServingParity_TailTruncation covers a synthetic event log longer than
// the configured window, exercising renderEventHistory's tail-truncation
// path identically through both call sites.
func TestServingParity_TailTruncation(t *testing.T) {
	env := newSeededHistoryEnv(t, 3, 128)
	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("no current action seat")
	}

	const window = uint32(128)
	longLog := make([]engine.PublicEvent, 0, window*2)
	for i := 0; i < int(window)*2; i++ {
		longLog = append(longLog, engine.PublicEvent{
			Type:     engine.EventDiscard,
			Seat:     uint32(i % 4),
			Face:     int16(i % 42),
			FromSeat: -1,
		})
	}
	if uint32(len(longLog)) <= window {
		t.Fatalf("premise: synthetic log %d must exceed window %d", len(longLog), window)
	}

	assertServingParity(t, env.game.State, seat, env.decisionCount, longLog, window)
}

// TestServingParity_RoundTransitionFirstDecision drives a seeded game to the
// first decision of a NEW round (i.e. right after a round boundary, when the
// per-round event log has just reset) and checks parity there.
func TestServingParity_RoundTransitionFirstDecision(t *testing.T) {
	// Classic mode is a capped 1-hand match (terminates instead of
	// transitioning), so a multi-round mode is needed to observe a round
	// boundary within budget.
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		EventHistoryWindow: 128,
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 4, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	rng := rand.New(rand.NewSource(4))
	obs := env.lastObservationForTest()
	if obs == nil {
		t.Fatalf("no initial observation")
	}
	prevLen := len(env.game.PublicEvents())
	found := false
	for step := 0; step < 3000 && obs != nil; step++ {
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil {
			t.Fatalf("step %d: %v", step, err)
		}
		if sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
		// The per-round event log resets at a round boundary (contract:
		// per-round reset), so a shrinking log length signals a fresh round's
		// first decision.
		curLen := len(env.game.PublicEvents())
		if curLen < prevLen {
			found = true
			break
		}
		prevLen = curLen
	}
	if !found {
		t.Skipf("premise: seed 4 never reached a new round within budget")
	}

	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("no current action seat after round transition")
	}
	assertServingParity(t, env.game.State, seat, env.decisionCount, env.game.PublicEvents(), 128)
}

// TestServingParity_PlayerTurn covers a normal PHASE_PLAYER_TURN decision
// reached by driving a seeded env with random legal actions.
func TestServingParity_PlayerTurn(t *testing.T) {
	env := newSeededHistoryEnv(t, 5, 128)
	rng := rand.New(rand.NewSource(5))
	obs := env.lastObservationForTest()
	found := false
	for step := 0; step < 500 && obs != nil; step++ {
		if env.game.State.Phase == pb.GamePhase_PHASE_PLAYER_TURN {
			found = true
			break
		}
		aid, ok := randomLegalActionID(obs.ActionMask, rng)
		if !ok {
			break
		}
		sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
		if err != nil {
			t.Fatalf("step %d: %v", step, err)
		}
		if sr.Terminated || sr.Truncated {
			break
		}
		obs = sr.Observation
	}
	if !found {
		t.Skipf("premise: seed 5 never reached PHASE_PLAYER_TURN within budget")
	}

	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("no current action seat")
	}
	assertServingParity(t, env.game.State, seat, env.decisionCount, env.game.PublicEvents(), 128)
}

// TestServingParity_WaitDiscardsInterrupt covers a WAIT_DISCARDS interrupt
// decision, constructed the same way as
// TestSearchPool_RootActionPinnedToRootSeat: hand-build a discard window and
// grant one seat a live PON so it has a non-trivial interrupt action mask.
func TestServingParity_WaitDiscardsInterrupt(t *testing.T) {
	env := New(&pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
		EventHistoryWindow: 128,
	})
	env.game = engine.NewGame("serving-parity-wait-discards", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.SetWallSeed(engine.SeedFromUint64(6))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}

	const discarder = uint32(0)
	const ponSeat = uint32(2)

	discard := &pb.Tile{Id: 9001, Suit: pb.Suit_SUIT_MAN, Value: 5}
	state := env.game.State
	state.ActivePlayer = discarder
	state.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	state.ActiveDiscard = discard
	state.IsHaitei = false

	r1 := &pb.Tile{Id: 9101, Suit: discard.Suit, Value: discard.Value}
	r2 := &pb.Tile{Id: 9102, Suit: discard.Suit, Value: discard.Value}
	state.Players[ponSeat].ClosedHand = append(state.Players[ponSeat].ClosedHand, r1, r2)
	state.Players[ponSeat].ValidActions = env.game.Rules.GetValidInterrupts(state, discard, ponSeat)
	for _, s := range []uint32{1, 3} {
		state.Players[s].ValidActions = nil
	}

	seat, ok := env.currentActionSeat()
	if !ok || seat != ponSeat {
		t.Fatalf("premise: currentActionSeat=(%d,%v), want %d", seat, ok, ponSeat)
	}

	assertServingParity(t, state, ponSeat, env.decisionCount, env.game.PublicEvents(), 128)
}
