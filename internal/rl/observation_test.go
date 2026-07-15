package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// countFaceInPublicZones counts physical copies of a face visible in public
// zones, iterating the state directly — an implementation independent of
// publicSeenCounts, so the test cannot share a bug with the code under test.
// ActiveDiscard is deliberately NOT a zone: during a claim window the tile
// already sits in the discarder's Discards.
func countFaceInPublicZones(state *pb.GameState, faceIndex int) int {
	total := 0
	countTiles := func(ts []*pb.Tile) {
		for _, tile := range ts {
			if idx, ok := tileFaceIndex42(tile); ok && idx == faceIndex {
				total++
			}
		}
	}
	for _, p := range state.Players {
		countTiles(p.Discards)
		for _, meld := range p.OpenMelds {
			countTiles(meld.Tiles)
		}
		countTiles(p.FlowerMelds)
	}
	countTiles(state.WildTiles)
	return total
}

// TestPublicSeenCounts_ActiveDiscardNotDoubleCounted: a tile that sits in a
// player's Discards AND is the ActiveDiscard (the invariant state during every
// WAIT_DISCARDS window) must be counted exactly once.
func TestPublicSeenCounts_ActiveDiscardNotDoubleCounted(t *testing.T) {
	discard := &pb.Tile{Id: 9001, Suit: pb.Suit_SUIT_MAN, Value: 5}
	state := &pb.GameState{
		Players: []*pb.PlayerState{{}, {}, {}, {}},
	}
	state.Players[0].Discards = []*pb.Tile{discard}
	state.ActiveDiscard = discard

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	counts := publicSeenCounts(state)
	if counts[faceIndex] != 1 {
		t.Fatalf("claimable discard counted %d times in publicSeenCounts, want exactly 1", counts[faceIndex])
	}
}

// TestEncodeObservation_SeenPlaneCountsClaimedTileOnce builds a real
// WAIT_DISCARDS interrupt window (mirroring handleDiscard's append-then-set
// sequence) and asserts plane 37's value for the claimed face equals the
// number of PHYSICAL copies visible in public zones — counted independently.
// Before the fix this fails: the encoder reports one extra copy.
func TestEncodeObservation_SeenPlaneCountsClaimedTileOnce(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
	}
	env := New(config)
	env.game = engine.NewGame("obs-double-count", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.SetWallSeed(engine.SeedFromUint64(7))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	state := env.game.State

	const discarder = uint32(0)
	const observer = uint32(2)

	// Mirror handleDiscard: append to Discards, THEN set ActiveDiscard.
	discard := &pb.Tile{Id: 9001, Suit: pb.Suit_SUIT_MAN, Value: 5}
	state.Players[discarder].Discards = append(state.Players[discarder].Discards, discard)
	state.ActivePlayer = discarder
	state.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	state.ActiveDiscard = discard
	state.IsHaitei = false

	// Observer holds a matching pair -> PON eligible: a REAL interrupt decision.
	r1 := &pb.Tile{Id: 9101, Suit: discard.Suit, Value: discard.Value}
	r2 := &pb.Tile{Id: 9102, Suit: discard.Suit, Value: discard.Value}
	state.Players[observer].ClosedHand = append(state.Players[observer].ClosedHand, r1, r2)
	state.Players[observer].ValidActions = env.game.Rules.GetValidInterrupts(state, discard, observer)
	if len(state.Players[observer].ValidActions) == 0 {
		t.Fatalf("premise broken: observer has no interrupt actions — not a claim window")
	}

	obs, err := EncodeObservation(state, observer, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	// r1/r2 are in the observer's CLOSED hand — not public. Public copies of
	// this face = the discard itself + whatever Start() dealt into public
	// zones (normally zero, but count independently rather than assume).
	wantCopies := countFaceInPublicZones(state, faceIndex)
	got := obs.Planes[channelOffset(37)+faceIndex]
	want := float32(wantCopies) / 4.0
	if got != want {
		t.Fatalf("plane 37 seen count for claimed face = %v (%.0f copies), want %v (%d copies)",
			got, got*4, want, wantCopies)
	}
}

// TestPublicSeenCounts_NonWindowStateUnchanged: with no ActiveDiscard (the
// normal PLAYER_TURN state), counts come from the piles alone — the fix must
// not change this path.
func TestPublicSeenCounts_NonWindowStateUnchanged(t *testing.T) {
	discard := &pb.Tile{Id: 9002, Suit: pb.Suit_SUIT_SOU, Value: 3}
	state := &pb.GameState{
		Players: []*pb.PlayerState{{}, {}, {}, {}},
	}
	state.Players[1].Discards = []*pb.Tile{discard}
	state.ActiveDiscard = nil

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	counts := publicSeenCounts(state)
	if counts[faceIndex] != 1 {
		t.Fatalf("discard counted %d times with nil ActiveDiscard, want 1", counts[faceIndex])
	}
}
