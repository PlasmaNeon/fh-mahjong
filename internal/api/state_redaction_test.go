package api

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

// TestRedactedStateForSeatObfuscatesOpponentDiscards checks the in-play
// redaction: an opponent's hand is hidden, and the discard id is remapped
// through the obfuscation map while its face stays visible. The viewer's own
// seat and the engine's master state are left untouched.
func TestRedactedStateForSeatObfuscatesOpponentDiscards(t *testing.T) {
	r := &Room{TileObfuscationMap: map[uint32]uint32{
		5:  1005, // viewer hand
		7:  1007, // viewer discard
		10: 1010, // opponent hand
		20: 1020, // opponent discard
		30: 1030, // opponent drawn
	}}

	drawn := int32(30)
	master := &pb.GameState{Players: []*pb.PlayerState{
		{
			Seat:       0, // viewer
			ClosedHand: []*pb.Tile{{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 1}},
			Discards:   []*pb.Tile{{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 2}},
		},
		{
			Seat:        1, // opponent
			ClosedHand:  []*pb.Tile{{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 3}},
			Discards:    []*pb.Tile{{Id: 20, Suit: pb.Suit_SUIT_PIN, Value: 4}},
			DrawnTileId: &drawn,
			Shanten:     2,
		},
	}}

	opp := r.redactedStateForSeat(master, 0, true).Players[1]

	if opp.ClosedHand[0].Id != 1010 || opp.ClosedHand[0].Suit != pb.Suit_SUIT_UNKNOWN || opp.ClosedHand[0].Value != 0 {
		t.Errorf("opponent hand not hidden: id=%d suit=%v value=%d", opp.ClosedHand[0].Id, opp.ClosedHand[0].Suit, opp.ClosedHand[0].Value)
	}
	if opp.DrawnTileId == nil || *opp.DrawnTileId != 1030 {
		t.Errorf("opponent drawn id = %v, want 1030", opp.DrawnTileId)
	}
	// Discard id obfuscated, face preserved.
	if opp.Discards[0].Id != 1020 {
		t.Errorf("opponent discard id = %d, want 1020 (obfuscated)", opp.Discards[0].Id)
	}
	if opp.Discards[0].Suit != pb.Suit_SUIT_PIN || opp.Discards[0].Value != 4 {
		t.Errorf("opponent discard face changed: suit=%v value=%d, want PIN/4", opp.Discards[0].Suit, opp.Discards[0].Value)
	}

	// Viewer's own seat untouched (real ids keep the self-discard flight working).
	self := r.redactedStateForSeat(master, 0, true).Players[0]
	if self.ClosedHand[0].Id != 5 || self.Discards[0].Id != 7 {
		t.Errorf("viewer seat redacted: hand=%d discard=%d, want 5/7", self.ClosedHand[0].Id, self.Discards[0].Id)
	}

	// Clone only; master is untouched.
	if master.Players[1].Discards[0].Id != 20 || master.Players[1].ClosedHand[0].Id != 10 {
		t.Errorf("master mutated: discard=%d hand=%d", master.Players[1].Discards[0].Id, master.Players[1].ClosedHand[0].Id)
	}
}

// TestRedactedStateForSeatRevealsHandsButKeepsDiscardsStable is the round-end
// case: hands are revealed (concealHands=false) but opponent discard ids must
// stay remapped, identical to the in-play value. The flight overlay renders
// above the round-result modal, so if a discard id flipped fake->real at the
// reveal the client would fly every opponent discard from the hand center on
// top of the result screen.
func TestRedactedStateForSeatRevealsHandsButKeepsDiscardsStable(t *testing.T) {
	r := &Room{TileObfuscationMap: map[uint32]uint32{10: 1010, 20: 1020}}
	mk := func() *pb.GameState {
		return &pb.GameState{Players: []*pb.PlayerState{
			{Seat: 0},
			{
				Seat:       1,
				ClosedHand: []*pb.Tile{{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 3}},
				Discards:   []*pb.Tile{{Id: 20, Suit: pb.Suit_SUIT_PIN, Value: 4}},
			},
		}}
	}

	inPlay := r.redactedStateForSeat(mk(), 0, true).Players[1]
	revealed := r.redactedStateForSeat(mk(), 0, false).Players[1]

	// Hand is revealed at round end.
	if revealed.ClosedHand[0].Id != 10 || revealed.ClosedHand[0].Suit != pb.Suit_SUIT_SOU {
		t.Errorf("hand not revealed: id=%d suit=%v", revealed.ClosedHand[0].Id, revealed.ClosedHand[0].Suit)
	}
	// Discard id is identical in-play and at reveal (no churn -> no spurious flights).
	if revealed.Discards[0].Id != inPlay.Discards[0].Id {
		t.Fatalf("discard id changed across reveal: play=%d reveal=%d", inPlay.Discards[0].Id, revealed.Discards[0].Id)
	}
	if revealed.Discards[0].Id != 1020 {
		t.Errorf("discard id = %d, want 1020", revealed.Discards[0].Id)
	}
}

// TestRedactedStateForSeatDiscardContinuity is the core animation invariant: the
// same physical tile id carries the same obfuscated id while concealed in the
// hand and after it is discarded, so the client links the two renders and flies
// the discard from the real tile slot.
func TestRedactedStateForSeatDiscardContinuity(t *testing.T) {
	r := &Room{TileObfuscationMap: map[uint32]uint32{42: 1042}}

	pre := &pb.GameState{Players: []*pb.PlayerState{
		{Seat: 0},
		{Seat: 1, ClosedHand: []*pb.Tile{{Id: 42, Suit: pb.Suit_SUIT_PIN, Value: 5}}},
	}}
	post := &pb.GameState{Players: []*pb.PlayerState{
		{Seat: 0},
		{Seat: 1, Discards: []*pb.Tile{{Id: 42, Suit: pb.Suit_SUIT_PIN, Value: 5}}},
	}}

	handID := r.redactedStateForSeat(pre, 0, true).Players[1].ClosedHand[0].Id
	discardID := r.redactedStateForSeat(post, 0, true).Players[1].Discards[0].Id

	if handID != discardID {
		t.Fatalf("hand id %d != discard id %d: discard flight cannot track the tile", handID, discardID)
	}
}
