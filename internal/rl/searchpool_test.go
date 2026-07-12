package rl

import (
	"bytes"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// assertEmittedRowEncodesSeat asserts that the single observation row carried by
// resp byte-for-byte equals EncodeObservation(state, seat, decisionCount) — the
// exact planes/scalars/mask a direct encode of `seat` produces — and that the
// SlotState advertises that seat. Bootstrap rows (round-end / truncation) must
// encode the ROOT seat, so this is how we pin the seat identity of the emitted
// value-bootstrap observation.
func assertEmittedRowEncodesSeat(t *testing.T, resp *pb.EnvPoolStepResponse, state *pb.GameState, seat uint32, decisionCount uint64) {
	t.Helper()
	want, err := encodeObservation(state, seat, decisionCount, false)
	if err != nil {
		t.Fatalf("direct encode of seat %d: %v", seat, err)
	}
	packed := &pb.EnvPoolStepResponse{}
	appendObservationRow(packed, want)
	if !bytes.Equal(resp.Planes, packed.Planes) {
		t.Fatalf("emitted planes differ from EncodeObservation(seat=%d) — bootstrap row encoded for the wrong seat", seat)
	}
	if !bytes.Equal(resp.Scalars, packed.Scalars) {
		t.Fatalf("emitted scalars differ from EncodeObservation(seat=%d) — bootstrap row encoded for the wrong seat", seat)
	}
	if !bytes.Equal(resp.ActionMasks, packed.ActionMasks) {
		t.Fatalf("emitted action mask differs from EncodeObservation(seat=%d) — bootstrap row encoded for the wrong seat", seat)
	}
	if resp.Slots[0].Seat != seat {
		t.Fatalf("emitted SlotState.Seat=%d, want root seat %d", resp.Slots[0].Seat, seat)
	}
}

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

	pool, err := NewSearchPool(env, 6, 99, 512, 0)
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

	pool, err := NewSearchPool(env, 6, 99, 512, 0)
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

	poolA, err := NewSearchPool(env, 6, 99, 512, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer poolA.Close()
	poolB, err := NewSearchPool(env, 6, 99, 512, 0)
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

// TestSearchPool_PairedDeterminizationsShareWorld pins the common-random-numbers
// pairing (LEAK 2 fix): with K determinizations and M*K clones, clone i and
// clone i+K belong to the SAME determinization group (k = i % K) and must hold a
// byte-identical hidden world post-redeal, while different groups (different k)
// must differ — otherwise pairing would be vacuous.
func TestSearchPool_PairedDeterminizationsShareWorld(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)

	const K, M = 3, 2
	pool, err := NewSearchPool(env, M*K, 99, 512, K)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	opps := opponentSeats(seat)
	// Same k across candidate groups -> identical world.
	for k := 0; k < K; k++ {
		for _, opp := range opps {
			a := handTileIDs(pool.clones[k].env.game.State.Players[opp].ClosedHand)
			b := handTileIDs(pool.clones[k+K].env.game.State.Players[opp].ClosedHand)
			if !idsEqual(a, b) {
				t.Fatalf("k=%d seat %d: paired clones %d and %d have different worlds — CRN pairing broken",
					k, opp, k, k+K)
			}
		}
	}
	// Different k -> distinct worlds (pairing is not degenerate).
	distinct := false
	for _, opp := range opps {
		a := handTileIDs(pool.clones[0].env.game.State.Players[opp].ClosedHand)
		b := handTileIDs(pool.clones[1].env.game.State.Players[opp].ClosedHand)
		if !idsEqual(a, b) {
			distinct = true
			break
		}
	}
	if !distinct {
		t.Fatalf("determinization groups k=0 and k=1 share a world — K worlds collapsed to 1")
	}
}

// TestSearchPool_CloneWorldIndependentOfLiveSeed pins the honesty guarantee
// behind LEAK 2: the clone worlds AND their sampled futures must be derived from
// the POOL seed, never from the live env's baseSeed. Two source envs reset with
// the same seed share identical game state; we then vary ONLY one env's baseSeed
// (an in-package mutation, the cheapest honest way to diverge the "future" the
// live env would deal). Post-fix, both pools' clone-0 rollouts cross a Chongci
// round boundary to byte-identical next-hand hands. Pre-fix (clone baseSeed
// copied from the live env) the next-hand wall is seeded from the differing live
// baseSeed, so the post-boundary hands DIVERGE — this equality assertion fails.
func TestSearchPool_CloneWorldIndependentOfLiveSeed(t *testing.T) {
	envA := newStartedEnv(t, 4242)
	envB := newStartedEnv(t, 4242)

	// Identical state premise (opponent hands equal at the branch point).
	for s := uint32(0); s < 4; s++ {
		if !idsEqual(handTileIDs(envA.game.State.Players[s].ClosedHand),
			handTileIDs(envB.game.State.Players[s].ClosedHand)) {
			t.Fatalf("premise broken: seat %d differs between same-seed resets", s)
		}
	}
	// Diverge ONLY the live future seed.
	if envA.baseSeed == 0 {
		envA.baseSeed = 1
	}
	envB.baseSeed = envA.baseSeed + 0xDEADBEEF

	nextHandHands := func(env *Env) []uint32 {
		pool, err := NewSearchPool(env, 1, 99, 4096, 1)
		if err != nil {
			t.Fatal(err)
		}
		defer pool.Close()
		_, obs := currentDecision(t, env)
		actionID, ok := firstLegalFromResponse(&pb.EnvPoolStepResponse{
			ActionSpaceSize: obs.ActionSpaceSize, ActionMasks: obs.ActionMask,
		})
		if !ok {
			t.Fatalf("no legal action at branch point")
		}
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
				// Clone state is now the NEXT hand; capture the dealt hands.
				var ids []uint32
				for s := uint32(0); s < 4; s++ {
					ids = append(ids, handTileIDs(pool.clones[0].env.game.State.Players[s].ClosedHand)...)
				}
				return ids
			}
			if state.Terminated || state.Truncated {
				t.Fatalf("clone ended (term=%t trunc=%t) before a non-terminal round end",
					state.Terminated, state.Truncated)
			}
			next, ok := firstLegalFromResponse(resp)
			if !ok {
				t.Fatalf("no legal action at step %d", step)
			}
			actionID = next
		}
		t.Fatalf("never reached a non-terminal round end")
		return nil
	}

	a := nextHandHands(envA)
	b := nextHandHands(envB)
	if !idsEqual(a, b) {
		t.Fatal("clone next-hand world depends on the live env's baseSeed — future leaked into the rollout")
	}
}

func TestSearchPool_RejectsOracleEnv(t *testing.T) {
	config := poolTestConfig()
	config.OracleObservation = true
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 4242, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	if _, err := NewSearchPool(env, 4, 99, 512, 0); err == nil {
		t.Fatalf("expected error creating pool from oracle env")
	}
}

func TestSearchPool_NilEnvRejected(t *testing.T) {
	if _, err := NewSearchPool(nil, 4, 99, 512, 0); err == nil {
		t.Fatalf("expected error for nil env")
	}
}

func TestSearchPool_RoundEndEmitsNextHandObs(t *testing.T) {
	env := newStartedEnv(t, 4242)
	_, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 4096, 0)
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

// TestSearchPool_RoundEndBootstrapEncodesRootSeat pins the seat identity of the
// round-end value-bootstrap row: it MUST be the ROOT seat's view (the seat being
// searched), not the next hand's acting seat. Seed 23 is chosen so the next
// hand's first acting seat (2) differs from the root seat (3) under Chongci
// dealer succession — so encoding the acting seat would produce a byte-different
// observation and this test would (and does, pre-fix) fail.
func TestSearchPool_RoundEndBootstrapEncodesRootSeat(t *testing.T) {
	env := newStartedEnv(t, 23)
	rootSeat, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 4096, 0)
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
			clone := pool.clones[0].env
			// Guard the test's own premise: the next acting seat must differ
			// from root, else the assertion cannot distinguish the two encodings.
			if actingSeat, ok := clone.currentActionSeat(); ok && actingSeat == rootSeat {
				t.Fatalf("seed premise broken: next acting seat == root seat %d; pick a seed where they diverge", rootSeat)
			}
			// The emitted bootstrap row must be the ROOT seat's view.
			assertEmittedRowEncodesSeat(t, resp, clone.game.State, rootSeat, clone.decisionCount)
			return
		}
		if state.Terminated || state.Truncated {
			t.Fatalf("clone ended (term=%t trunc=%t) before any non-terminal round end",
				state.Terminated, state.Truncated)
		}
		next, ok := firstLegalFromResponse(resp)
		if !ok {
			t.Fatalf("no legal action at step %d", step)
		}
		actionID = next
	}
	t.Fatalf("never reached a non-terminal round end")
}

// TestSearchPool_MatchEndAttachesOutcome drives a clone all the way to
// PHASE_MATCH_END and asserts the terminal SlotState still carries the
// final-round RoundOutcome — the MATCH_END return path attaches payout metadata
// symmetric with the classic-terminal path, rather than discarding it.
func TestSearchPool_MatchEndAttachesOutcome(t *testing.T) {
	// MaxHands=1 Chongci: the single decision that ends round 1 rolls straight
	// through PHASE_ROUND_END into PHASE_MATCH_END within one advanceClone call,
	// so the clone returns terminated directly (rather than being marked done at a
	// separate round-end return, which a multi-hand match does after hand 1).
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
		MatchMode:          pb.MatchMode_MATCH_MODE_CHONGCI,
		ChongciConfig:      &pb.ChongciConfig{StartingScore: 2000, BustThreshold: 0, MaxHands: 1},
	}
	env := New(config)
	if _, err := env.Reset(&pb.EnvResetRequest{Seed: 4242, Config: config}); err != nil {
		t.Fatalf("reset: %v", err)
	}
	_, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 100000, 0)
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

	sawTerminated := false
	for step := 0; step < 20000; step++ {
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
		if state.Terminated {
			if state.RoundOutcome == nil {
				t.Fatalf("match end must attach the final-round outcome, got nil")
			}
			sawTerminated = true
			break
		}
		if state.Truncated {
			t.Fatalf("clone truncated (cap too low) before match end")
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
	if !sawTerminated {
		t.Fatalf("clone never reached match end")
	}
}

func TestSearchPool_DecisionCapTruncatesWithObs(t *testing.T) {
	env := newStartedEnv(t, 4242)
	_, obs := currentDecision(t, env)

	pool, err := NewSearchPool(env, 1, 99, 1, 0)
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

	// The cap-state row is a VALUE-BOOTSTRAP row: it must be the ROOT seat's
	// view, not whoever is on the clock at the cap. With seed 4242 / cap 1 the
	// root seat (3) is not the acting seat at the cap (0), so encoding the acting
	// seat would produce a byte-different observation.
	rootSeat, _ := currentDecision(t, env)
	clone := pool.clones[0].env
	if actingSeat, ok := clone.currentActionSeat(); ok && actingSeat == rootSeat {
		t.Fatalf("seed premise broken: cap acting seat == root seat %d; pick params where they diverge", rootSeat)
	}
	assertEmittedRowEncodesSeat(t, resp, clone.game.State, rootSeat, clone.decisionCount)
}

func TestSearchPool_ResetCommandIsError(t *testing.T) {
	env := newStartedEnv(t, 4242)
	pool, err := NewSearchPool(env, 2, 99, 512, 0)
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

	pool, err := NewSearchPool(env, 3, 7, 512, 0)
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

// seatHasTileIDConflict returns the first tile id that appears more than once
// across a seat's ClosedHand and open-meld tiles — the corruption signature of a
// phantom meld appended without reducing the closed hand.
func seatHasTileIDConflict(p *pb.PlayerState) (uint32, bool) {
	seen := make(map[uint32]bool)
	for _, t := range p.ClosedHand {
		if seen[t.Id] {
			return t.Id, true
		}
		seen[t.Id] = true
	}
	for _, m := range p.OpenMelds {
		for _, t := range m.Tiles {
			if seen[t.Id] {
				return t.Id, true
			}
			seen[t.Id] = true
		}
	}
	return 0, false
}

// TestSearchPool_InterruptWindowExecutable is the executable-consistency half of
// the re-ask contract: after RedealUnseen refreshes each non-acting seat's
// ValidActions against its new hand, a surfaced meld interrupt must actually be
// stepped without corrupting state. Before the redeal.go fix, stale ValidActions
// referenced tiles the reshuffle moved away, so ResolveInterrupts appended a
// phantom open meld WITHOUT reducing the closed hand (duplicate tile ids). Here
// we drive each clone's interrupt window to resolution — choosing a PON when the
// refreshed mask offers one — and assert no per-slot error and no duplicate tile
// ids across any seat's ClosedHand+melds; when a meld was actually made, its
// maker's closed hand must have shrunk.
func TestSearchPool_InterruptWindowExecutable(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
	}
	env := New(config)
	env.game = engine.NewGame("interrupt-exec", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.SetWallSeed(engine.SeedFromUint64(101))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	env.lastScores = snapshotScores(env.game.State)

	active := env.game.State.ActivePlayer
	discardTile := env.game.State.Players[active].ClosedHand[0]
	seatA := (active + 1) % 4
	seatB := (active + 2) % 4

	// Give two opponents a matching pair each so both hold a PON of the discard.
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
	if err := env.game.ProcessPlayerAction(seatA, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_PON, MeldTiles: []*pb.Tile{a1, a2},
	}); err != nil {
		t.Fatalf("queue A pon: %v", err)
	}
	if _, ok := env.currentActionSeat(); !ok {
		t.Fatalf("live env should surface an interrupt decision")
	}

	pool, err := NewSearchPool(env, 6, 7, 512, 0)
	if err != nil {
		t.Fatal(err)
	}
	defer pool.Close()

	meldsMade := 0
	for i, clone := range pool.clones {
		// Snapshot each seat's closed-hand size before we drive the window so we
		// can prove a meld reduced the maker's hand.
		preLen := make([]int, len(clone.env.game.State.Players))
		for s, p := range clone.env.game.State.Players {
			preLen[s] = len(p.ClosedHand)
		}

		preMelds := make([]int, len(clone.env.game.State.Players))
		for s, p := range clone.env.game.State.Players {
			preMelds[s] = len(p.OpenMelds)
		}

		// Drive the interrupt window to resolution. Each surfaced seat picks a
		// PON if its refreshed mask offers one, else passes.
		for step := 0; step < 8; step++ {
			seat, ok := clone.env.currentActionSeat()
			if !ok {
				break
			}
			if clone.env.game.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
				break
			}
			legal, err := legalActionMap(clone.env.game.State, seat)
			if err != nil {
				t.Fatalf("clone %d: legalActionMap seat %d: %v", i, seat, err)
			}
			chosen := ActionPass
			for id, act := range legal {
				if act.Type == pb.ActionType_ACTION_PON {
					chosen = id
					break
				}
			}
			resp, err := pool.Step(&pb.EnvPoolStepRequest{
				Commands: []*pb.SlotCommand{{Slot: uint32(i), Cmd: &pb.SlotCommand_ActionId{ActionId: uint32(chosen)}}},
			})
			if err != nil {
				t.Fatalf("clone %d: pool step: %v", i, err)
			}
			var slotState *pb.SlotState
			for _, ss := range resp.Slots {
				if ss.Slot == uint32(i) {
					slotState = ss
					break
				}
			}
			if slotState == nil {
				t.Fatalf("clone %d: no slot result", i)
			}
			if slotState.Error != "" {
				t.Fatalf("clone %d: refreshed interrupt not executable: %s", i, slotState.Error)
			}
		}

		// Consistency: no duplicate tile ids anywhere (the phantom-meld signature).
		for s, p := range clone.env.game.State.Players {
			if id, dup := seatHasTileIDConflict(p); dup {
				t.Fatalf("clone %d seat %d: duplicate tile id %d across hand+melds — phantom meld", i, s, id)
			}
		}

		// If any seat gained an open meld, its closed hand must have shrunk (a
		// real PON consumes two hand tiles; the phantom-meld bug left it unchanged).
		for s, p := range clone.env.game.State.Players {
			if len(p.OpenMelds) > preMelds[s] {
				if len(p.ClosedHand) >= preLen[s] {
					t.Fatalf("clone %d seat %d: gained a meld but closed hand did not shrink (%d -> %d) — phantom meld",
						i, s, preLen[s], len(p.ClosedHand))
				}
				meldsMade++
			}
		}
	}

	if meldsMade == 0 {
		t.Fatalf("no clone executed a meld interrupt — test did not exercise the meld-application path")
	}
}
