package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// newStartedEnv builds a live Env at its first decision point using the shared
// pool test config (39ch, four learning seats, Chongci MaxHands=2, no autoplay).
func newStartedEnv(t *testing.T, seed uint64) *Env {
	t.Helper()
	env := New(poolTestConfig())
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: seed, Config: poolTestConfig()}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	return env
}

// currentDecision returns the acting seat and its observation at the live env's
// current decision point — encoded exactly the way the pool encodes clone obs.
func currentDecision(t *testing.T, env *Env) (uint32, *pb.SeatObservation) {
	t.Helper()
	seat, ok := env.currentActionSeat()
	if !ok {
		t.Fatalf("env is not at a decision point")
	}
	obs, err := encodeObservation(env.game.State, seat, env.decisionCount, false)
	if err != nil {
		t.Fatalf("encode observation: %v", err)
	}
	return seat, obs
}

func bytesEqual(a, b []float32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func handTileIDs(hand []*pb.Tile) []uint32 {
	ids := make([]uint32, 0, len(hand))
	for _, tile := range hand {
		ids = append(ids, tile.Id)
	}
	return ids
}

func opponentSeats(acting uint32) []uint32 {
	seats := make([]uint32, 0, 3)
	for s := uint32(0); s < 4; s++ {
		if s != acting {
			seats = append(seats, s)
		}
	}
	return seats
}

func idsEqual(a, b []uint32) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

// firstLegalFromResponse extracts the first legal action id for the single
// active row of a pool step response.
func firstLegalFromResponse(resp *pb.EnvPoolStepResponse) (uint32, bool) {
	n := int(resp.ActionSpaceSize)
	if n == 0 || len(resp.ActionMasks) < n {
		return 0, false
	}
	for i := 0; i < n; i++ {
		if resp.ActionMasks[i] == 1 {
			return uint32(i), true
		}
	}
	return 0, false
}

func TestSearchPool_ActingSeatObservationInvariant(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 6, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	for i := 0; i < 6; i++ {
		cloneObs := pool.cloneObservationForTest(i, seat)
		if cloneObs == nil {
			t.Fatalf("clone %d: nil observation", i)
		}
		if !bytesEqual(obs.Planes, cloneObs.Planes) || !bytesEqual(obs.Scalars, cloneObs.Scalars) {
			t.Fatalf("clone %d: acting seat observation differs — determinization leaked", i)
		}
	}
}

func TestSearchPool_OpponentHandsDifferAcrossClones(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)

	pool, err := NewSearchPool(env, 6, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	opps := opponentSeats(seat)
	differs := false
	for i := 0; i < len(pool.clones) && !differs; i++ {
		for j := i + 1; j < len(pool.clones) && !differs; j++ {
			for _, opp := range opps {
				a := handTileIDs(pool.clones[i].env.game.State.Players[opp].ClosedHand)
				b := handTileIDs(pool.clones[j].env.game.State.Players[opp].ClosedHand)
				if !idsEqual(a, b) {
					differs = true
					break
				}
			}
		}
	}
	if !differs {
		t.Fatalf("all clones share identical opponent hands — determinization did not vary")
	}
}

func TestSearchPool_SeedDeterminism(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)

	poolA, err := NewSearchPool(env, 6, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer poolA.Close()
	poolB, err := NewSearchPool(env, 6, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer poolB.Close()

	opps := opponentSeats(seat)
	for i := range poolA.clones {
		for _, opp := range opps {
			a := handTileIDs(poolA.clones[i].env.game.State.Players[opp].ClosedHand)
			b := handTileIDs(poolB.clones[i].env.game.State.Players[opp].ClosedHand)
			if !idsEqual(a, b) {
				t.Fatalf("clone %d seat %d differs between same-seed pools", i, opp)
			}
		}
	}
}

func TestSearchPool_RejectsOracleEnv(t *testing.T) {
	config := poolTestConfig()
	config.OracleObservation = true
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 4242, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	if _, err := NewSearchPool(env, 4, 99, 512); err == nil {
		t.Fatalf("expected error creating pool from oracle env")
	}
}

func TestSearchPool_NilEnvRejected(t *testing.T) {
	if _, err := NewSearchPool(nil, 4, 99, 512); err == nil {
		t.Fatalf("expected error for nil env")
	}
}

func TestSearchPool_RoundEndEmitsNextHandObs(t *testing.T) {
	env := newStartedEnv(t, 4242)
	_, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 4096)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	actionID, ok := firstLegalFromResponse(&pb.EnvPoolStepResponse{
		ActionSpaceSize: obs.ActionSpaceSize, ActionMasks: obs.ActionMask,
	})
	if !ok {
		t.Fatalf("no legal action at branch point")
	}

	sawRoundEnd := false
	for step := 0; step < 5000; step++ {
		resp, err := pool.Step(&pb.EnvPoolStepRequest{
			Commands: []*pb.SlotCommand{{Slot: 0, Cmd: &pb.SlotCommand_ActionId{ActionId: actionID}}},
		})
		if err != nil {
			t.Fatalf("step: %v", err)
		}
		state := resp.Slots[0]
		if state.Error != "" {
			t.Fatalf("slot error: %s", state.Error)
		}
		if state.RoundOutcome != nil && !state.Terminated {
			if !state.HasObservation {
				t.Fatalf("round ended but no next-hand observation carried")
			}
			sawRoundEnd = true
			break
		}
		if state.Terminated || state.Truncated {
			t.Fatalf("clone ended (term=%t trunc=%t) before any non-terminal round end",
				state.Terminated, state.Truncated)
		}
		if !state.HasObservation {
			t.Fatalf("no observation and not terminal at step %d", step)
		}
		next, ok := firstLegalFromResponse(resp)
		if !ok {
			t.Fatalf("no legal action at step %d", step)
		}
		actionID = next
	}
	if !sawRoundEnd {
		t.Fatalf("never reached a non-terminal round end")
	}
}

func TestSearchPool_DecisionCapTruncatesWithObs(t *testing.T) {
	env := newStartedEnv(t, 4242)
	_, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 1)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	actionID, ok := firstLegalFromResponse(&pb.EnvPoolStepResponse{
		ActionSpaceSize: obs.ActionSpaceSize, ActionMasks: obs.ActionMask,
	})
	if !ok {
		t.Fatalf("no legal action at branch point")
	}

	resp, err := pool.Step(&pb.EnvPoolStepRequest{
		Commands: []*pb.SlotCommand{{Slot: 0, Cmd: &pb.SlotCommand_ActionId{ActionId: actionID}}},
	})
	if err != nil {
		t.Fatalf("step: %v", err)
	}
	state := resp.Slots[0]
	if state.Error != "" {
		t.Fatalf("slot error: %s", state.Error)
	}
	if !state.Truncated {
		t.Fatalf("expected truncated after decision cap, got term=%t trunc=%t", state.Terminated, state.Truncated)
	}
	if !state.HasObservation {
		t.Fatalf("decision-cap truncation must carry the cap-state observation")
	}
}

func TestSearchPool_ResetCommandIsError(t *testing.T) {
	env := newStartedEnv(t, 4242)
	pool, err := NewSearchPool(env, 2, 99, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	resp, err := pool.Step(&pb.EnvPoolStepRequest{
		Commands: []*pb.SlotCommand{{Slot: 0, Cmd: &pb.SlotCommand_ResetSeed{ResetSeed: 7}}},
	})
	if err != nil {
		t.Fatalf("step returned pool-level error: %v", err)
	}
	if resp.Slots[0].Error == "" {
		t.Fatalf("reset command must produce a per-slot error")
	}
	// Pool keeps working: a skip on the other slot succeeds.
	if _, err := pool.Step(&pb.EnvPoolStepRequest{
		Commands: []*pb.SlotCommand{{Slot: 1, Cmd: &pb.SlotCommand_Skip{Skip: true}}},
	}); err != nil {
		t.Fatalf("pool broke after reset error: %v", err)
	}
}

// TestSearchPool_InterruptWindowReAsked pins the cross-task contract: when the
// pool is created at a WAIT_DISCARDS point where a seat had already queued an
// interrupt response, RedealUnseen clears the clone's interrupt queue, so every
// interrupt-window seat (including the previously-queued one) must be re-asked
// as a policy decision rather than silently resolved.
func TestSearchPool_InterruptWindowReAsked(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
	}
	env := New(config)
	env.game = engine.NewGame("interrupt-reask", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.SetWallSeed(engine.SeedFromUint64(101))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	env.lastScores = snapshotScores(env.game.State)

	active := env.game.State.ActivePlayer
	discardTile := env.game.State.Players[active].ClosedHand[0]
	seatA := (active + 1) % 4
	seatB := (active + 2) % 4

	// Inject a matching pair into two opponents so both hold a PON interrupt.
	a1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	a2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	b1 := &pb.Tile{Id: discardTile.Id + 3000, Suit: discardTile.Suit, Value: discardTile.Value}
	b2 := &pb.Tile{Id: discardTile.Id + 4000, Suit: discardTile.Suit, Value: discardTile.Value}
	env.game.State.Players[seatA].ClosedHand = append(env.game.State.Players[seatA].ClosedHand, a1, a2)
	env.game.State.Players[seatB].ClosedHand = append(env.game.State.Players[seatB].ClosedHand, b1, b2)

	if err := env.game.ProcessPlayerAction(active, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD, Tile: discardTile,
	}); err != nil {
		t.Fatalf("discard: %v", err)
	}
	if env.game.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		t.Fatalf("expected WAIT_DISCARDS after discard, got %v", env.game.State.Phase)
	}

	// Queue seat A's PON; seat B leaves the window open (unresponded).
	if err := env.game.ProcessPlayerAction(seatA, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_PON, MeldTiles: []*pb.Tile{a1, a2},
	}); err != nil {
		t.Fatalf("queue A pon: %v", err)
	}
	if env.game.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		t.Fatalf("window resolved prematurely, phase=%v", env.game.State.Phase)
	}
	if !env.game.InterruptQueued(seatA) {
		t.Fatalf("seat A should be queued in the live env")
	}
	if _, ok := env.currentActionSeat(); !ok {
		t.Fatalf("live env should surface an interrupt decision")
	}

	pool, err := NewSearchPool(env, 3, 7, 512)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	for i, clone := range pool.clones {
		if clone.env.game.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
			t.Fatalf("clone %d: window silently resolved, phase=%v", i, clone.env.game.State.Phase)
		}
		if clone.env.game.InterruptQueued(seatA) {
			t.Fatalf("clone %d: seat A still queued — must be re-asked after redeal", i)
		}
		if _, ok := clone.env.currentActionSeat(); !ok {
			t.Fatalf("clone %d: no interrupt decision surfaced — window resolved silently", i)
		}
	}
}
