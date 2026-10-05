package rl

import (
	"bytes"
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func rootRowBytes(t *testing.T, obs *pb.SeatObservation) []byte {
	t.Helper()
	packed := &pb.EnvPoolStepResponse{}
	appendObservationRow(packed, obs)
	return packed.Planes
}

func TestSearchPoolRootObservationsMatchTheLivePublicView(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, live := currentDecision(t, env)
	pool, err := NewSearchPoolWithOptions(env, 4, 99, 512, 0, SearchPoolOptions{})
	if err != nil {
		t.Fatal(err)
	}
	resp, err := pool.RootObservations()
	if err != nil {
		t.Fatal(err)
	}
	want := bytes.Repeat(rootRowBytes(t, live), 4)
	if !bytes.Equal(resp.Planes, want) {
		t.Fatalf("re-dealt clones' public root view differs from the live view")
	}
	if len(resp.Slots) != 4 || resp.Slots[3].Seat != seat || !resp.Slots[3].HasObservation {
		t.Fatalf("root slots %+v", resp.Slots)
	}
}

func TestSearchPoolOraclePlanesShowTheRedealtHands(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, live := currentDecision(t, env)
	pool, err := NewSearchPoolWithOptions(env, 4, 99, 512, 0, SearchPoolOptions{OraclePlanes: true})
	if err != nil {
		t.Fatal(err)
	}
	resp, err := pool.RootObservations()
	if err != nil {
		t.Fatal(err)
	}
	if resp.PlaneChannels != 51 {
		t.Fatalf("plane channels %d, want 51", resp.PlaneChannels)
	}
	public := rootRowBytes(t, live)
	rowBytes := 51 * ObservationPlaneHeight * 4
	trueOracle, err := encodeObservation(env.game.State, seat, env.decisionCount, true, 0, nil, 0)
	if err != nil {
		t.Fatal(err)
	}
	differsFromTruth := false
	for i := 0; i < 4; i++ {
		row := resp.Planes[i*rowBytes : (i+1)*rowBytes]
		if !bytes.Equal(row[:len(public)], public) {
			t.Fatalf("clone %d public block differs from the live view", i)
		}
		want, err := encodeObservation(pool.clones[i].env.game.State, seat, env.decisionCount, true, 0, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		if !bytes.Equal(row, rootRowBytes(t, want)) {
			t.Fatalf("clone %d oracle block is not its own re-dealt hands", i)
		}
		differsFromTruth = differsFromTruth || !bytes.Equal(row, rootRowBytes(t, trueOracle))
	}
	if !differsFromTruth {
		t.Fatalf("every clone showed the true hands; re-deal did not happen")
	}
}

func TestSearchPoolTrueStateRefusesOraclePlanesAndKeepsTheRealHands(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)
	if _, err := NewSearchPoolWithOptions(env, 2, 1, 64, 0, SearchPoolOptions{TrueState: true, OraclePlanes: true}); err == nil {
		t.Fatalf("true_state with oracle_planes must be refused")
	}
	pool, err := NewSearchPoolWithOptions(env, 2, 1, 64, 0, SearchPoolOptions{TrueState: true})
	if err != nil {
		t.Fatal(err)
	}
	for _, opp := range opponentSeats(seat) {
		live := handTileIDs(env.game.State.Players[opp].ClosedHand)
		for i := 0; i < 2; i++ {
			if !idsEqual(handTileIDs(pool.clones[i].env.game.State.Players[opp].ClosedHand), live) {
				t.Fatalf("true-state clone %d changed seat %d's hand", i, opp)
			}
		}
	}
}

func TestSearchPoolTrueStateRolloutMatchesTheLiveEnv(t *testing.T) {
	env := newStartedEnv(t, 4242)
	pool, err := NewSearchPoolWithOptions(env, 1, 1, 4000, 0, SearchPoolOptions{TrueState: true})
	if err != nil {
		t.Fatal(err)
	}
	_, liveObs := currentDecision(t, env)
	action := firstLegal(liveObs.ActionMask)
	for step := 0; step < 25; step++ {
		resp, err := pool.Step(&pb.EnvPoolStepRequest{Commands: []*pb.SlotCommand{
			{Slot: 0, Cmd: &pb.SlotCommand_ActionId{ActionId: action}}}})
		if err != nil {
			t.Fatal(err)
		}
		live, err := env.Step(&pb.EnvStepRequest{ActionId: action})
		if err != nil {
			t.Fatal(err)
		}
		slot := resp.Slots[0]
		if slot.RoundOutcome != nil || slot.Terminated || live.Terminated {
			if step < 5 {
				t.Fatalf("hand ended after %d steps; too few to compare", step)
			}
			return // the hand ended; ground truth stops here
		}
		if !bytes.Equal(resp.Planes, rootRowBytes(t, live.Observation)) {
			t.Fatalf("step %d: true-state clone diverged from the live env", step)
		}
		action = firstLegal(live.Observation.ActionMask)
	}
}

func TestSearchPoolDeterminizationIDsReproduceWorlds(t *testing.T) {
	env := newStartedEnv(t, 4242)
	seat, _ := currentDecision(t, env)
	a, err := NewSearchPoolWithOptions(env, 3, 7, 64, 0, SearchPoolOptions{DeterminizationIDs: []uint64{5, 9, 5}})
	if err != nil {
		t.Fatal(err)
	}
	b, err := NewSearchPoolWithOptions(env, 2, 7, 64, 0, SearchPoolOptions{DeterminizationIDs: []uint64{9, 5}})
	if err != nil {
		t.Fatal(err)
	}
	plain, err := NewSearchPool(env, 10, 7, 64, 10)
	if err != nil {
		t.Fatal(err)
	}
	hands := func(p *SearchPool, i int) [][]uint32 {
		out := [][]uint32{}
		for _, opp := range opponentSeats(seat) {
			out = append(out, handTileIDs(p.clones[i].env.game.State.Players[opp].ClosedHand))
		}
		return out
	}
	same := func(x, y [][]uint32) bool {
		for i := range x {
			if !idsEqual(x[i], y[i]) {
				return false
			}
		}
		return true
	}
	if !same(hands(a, 0), hands(a, 2)) || !same(hands(a, 0), hands(b, 1)) || !same(hands(a, 1), hands(b, 0)) {
		t.Fatalf("the same world id gave different worlds")
	}
	if !same(hands(a, 0), hands(plain, 5)) || !same(hands(a, 1), hands(plain, 9)) {
		t.Fatalf("world id k must equal the default pool's world k")
	}
	if same(hands(a, 0), hands(a, 1)) {
		t.Fatalf("different world ids gave the same world")
	}
}
