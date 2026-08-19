package rl

import (
	"fmt"
	"math/rand"
	"strings"
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

// randomLegalActionID picks a uniformly random enabled action from the mask.
func randomLegalActionID(mask []byte, rng *rand.Rand) (int, bool) {
	legal := legalIDs(mask)
	if len(legal) == 0 {
		return 0, false
	}
	return legal[rng.Intn(len(legal))], true
}

func legalIDs(mask []byte) []int {
	var out []int
	for id, en := range mask {
		if en != 0 {
			out = append(out, id)
		}
	}
	return out
}

// firstDuplicateHandTile returns the seat and tile-id of the first tile that
// appears more than once in any player's closed hand. The boolean reports
// whether a duplicate was found — tile id 0 is a real tile (the first 1s), so it
// cannot double as a "none" sentinel.
func firstDuplicateHandTile(env *Env) (seat uint32, id uint32, found bool) {
	for _, p := range env.game.State.Players {
		seen := map[uint32]bool{}
		for _, tile := range p.ClosedHand {
			if tile == nil {
				continue
			}
			if seen[tile.Id] {
				return p.Seat, tile.Id, true
			}
			seen[tile.Id] = true
		}
	}
	return 0, 0, false
}

func facesOf(ts []*pb.Tile) string {
	var b strings.Builder
	for _, x := range ts {
		if x == nil {
			b.WriteString("[nil]")
			continue
		}
		fmt.Fprintf(&b, "[%v/%d#%d]", x.Suit, x.Value, x.Id)
	}
	return b.String()
}

func dumpDupState(t *testing.T, env *Env, seed int64, err error) {
	t.Logf("=== REPRO duplicate-kan at seed=%d ===\nerr: %v", seed, err)
	st := env.game.State
	t.Logf("Wilds: %s  activePlayer=%d phase=%v", facesOf(st.WildTiles), st.ActivePlayer, st.Phase)
	if st.ActiveDiscard != nil {
		t.Logf("ActiveDiscard: %s", facesOf([]*pb.Tile{st.ActiveDiscard}))
	}
	for i, p := range st.Players {
		t.Logf("P%d closed(%d)=%s", i, len(p.ClosedHand), facesOf(p.ClosedHand))
		for _, m := range p.OpenMelds {
			t.Logf("    meld %v: %s", m.Type, facesOf(m.Tiles))
		}
	}
}

// TestFuzzActionMaskHasNoDuplicateIDs drives 300 random self-play games and
// fails if action-mask building ever emits the same action id twice, dumping
// the offending state. Originally written to reproduce a duplicate-kan bug; it
// now guards the invariant that bug violated, for every action family.
func TestFuzzActionMaskHasNoDuplicateIDs(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       3000,
		MatchMode:          pb.MatchMode_MATCH_MODE_CLASSIC,
	}
	for seed := int64(1); seed < 300; seed++ {
		env := New(config)
		rng := rand.New(rand.NewSource(seed*2654435761 + 12345))
		reset, err := env.Reset(&pb.EnvResetRequest{Seed: uint64(seed), Config: config})
		if err != nil {
			t.Fatalf("unexpected reset error at seed=%d: %v", seed, err)
		}
		obs := reset.Observation
		for step := 0; obs != nil && step < 6000; step++ {
			aid, ok := randomLegalActionID(obs.ActionMask, rng)
			if !ok {
				break
			}
			seat := obs.Seat
			var actDesc string
			if a, derr := decodeActionID(env.game.State, seat, aid); derr == nil {
				actDesc = fmt.Sprintf("%v tile=%s meld=%s", a.Type, facesOf([]*pb.Tile{a.Tile}), facesOf(a.MeldTiles))
			}
			sr, err := env.Step(&pb.EnvStepRequest{ActionId: uint32(aid)})
			if err != nil {
				// Actions come from the current legal mask, so ANY step error is a
				// regression — the duplicate-action id is just the one we started from.
				dumpDupState(t, env, seed, err)
				t.Fatalf("unexpected step error at seed=%d step=%d (action %s): %v", seed, step, actDesc, err)
			}
			// The invariant: no tile id may appear twice in any hand.
			if s, dup, found := firstDuplicateHandTile(env); found {
				t.Logf("caused by seat=%d action: %s", seat, actDesc)
				dumpDupState(t, env, seed, fmt.Errorf("duplicate tile id %d in hand", dup))
				t.Fatalf("tile #%d duplicated in P%d hand at seed=%d step=%d", dup, s, seed, step)
			}
			if sr.Terminated || sr.Truncated {
				break
			}
			obs = sr.Observation
		}
	}
}
