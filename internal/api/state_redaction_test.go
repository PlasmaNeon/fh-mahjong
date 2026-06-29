package api

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

// redactionMaster builds an in-play state: a viewer (seat 0) and an opponent
// (seat 1) whose first concealed tile is also their drawn tile, plus a public
// discard, a wall seed, and per-seat valid_actions carrying real concealed tiles.
func redactionMaster() *pb.GameState {
	drawn := int32(10) // opponent's drawn tile == first concealed tile (real id 10)
	return &pb.GameState{
		WallSeed: "deterministic-seed",
		Players: []*pb.PlayerState{
			{
				Seat:       0, // viewer
				ClosedHand: []*pb.Tile{{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 1}},
				Discards:   []*pb.Tile{{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 2}},
				ValidActions: []*pb.PlayerAction{{
					Type: pb.ActionType_ACTION_DISCARD,
					Tile: &pb.Tile{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 1},
				}},
			},
			{
				Seat: 1, // opponent
				ClosedHand: []*pb.Tile{
					{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 3},
					{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 4},
				},
				Discards:    []*pb.Tile{{Id: 20, Suit: pb.Suit_SUIT_PIN, Value: 4}},
				DrawnTileId: &drawn,
				Shanten:     2,
				ValidActions: []*pb.PlayerAction{{
					Type:      pb.ActionType_ACTION_KAN,
					MeldTiles: []*pb.Tile{{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 4}},
				}},
			},
		},
	}
}

// In-play redaction: the opponent's hand + drawn tile are anonymized, but their
// public discards keep real ids and faces, the wall seed and the opponent's
// valid_actions are dropped, and the viewer's own seat + the master are untouched.
func TestRedactedStateForSeatInPlay(t *testing.T) {
	master := redactionMaster()

	redacted := redactedStateForSeat(master, 0, true)
	opp := redacted.Players[1]

	// Closed hand fully anonymized.
	for _, tile := range opp.ClosedHand {
		if tile.Suit != pb.Suit_SUIT_UNKNOWN || tile.Value != 0 || tile.Id < 1000 {
			t.Fatalf("opponent hand not hidden: %+v", tile)
		}
	}
	// Drawn tile obfuscated and internally consistent with its concealed slot
	// (so the frontend can still locate the drawn slot this broadcast).
	if opp.DrawnTileId == nil || *opp.DrawnTileId < 1000 {
		t.Fatalf("opponent drawn id not obfuscated: %v", opp.DrawnTileId)
	}
	if uint32(*opp.DrawnTileId) != opp.ClosedHand[0].Id {
		t.Fatalf("drawn id %d not consistent with concealed slot %d", *opp.DrawnTileId, opp.ClosedHand[0].Id)
	}
	// Discards keep REAL ids + faces (public; per-broadcast rotation means a real
	// discard id can't be correlated to a concealed fake id).
	if opp.Discards[0].Id != 20 || opp.Discards[0].Suit != pb.Suit_SUIT_PIN || opp.Discards[0].Value != 4 {
		t.Fatalf("opponent discard altered: %+v", opp.Discards[0])
	}
	// valid_actions dropped (would leak the concealed meld tile).
	if len(opp.ValidActions) != 0 {
		t.Fatalf("opponent valid_actions leaked: %+v", opp.ValidActions)
	}
	if opp.Shanten != 0 {
		t.Fatalf("opponent shanten not cleared: %d", opp.Shanten)
	}
	// Wall seed scrubbed for everyone.
	if redacted.WallSeed != "" {
		t.Fatalf("wall seed leaked: %q", redacted.WallSeed)
	}

	// Viewer's own seat untouched (real ids keep the self-discard flight working).
	self := redacted.Players[0]
	if self.ClosedHand[0].Id != 5 || self.Discards[0].Id != 7 || len(self.ValidActions) != 1 {
		t.Fatalf("viewer seat redacted: %+v", self)
	}

	// Clone only; master untouched.
	if master.Players[1].ClosedHand[0].Id != 10 || master.WallSeed == "" || len(master.Players[1].ValidActions) == 0 {
		t.Fatalf("master mutated by redaction")
	}
}

// At round/match end (concealHands=false) opponents' hands are revealed so
// players see the result; discards and seed handling are unchanged.
func TestRedactedStateForSeatRevealsHandsAtRoundEnd(t *testing.T) {
	revealed := redactedStateForSeat(redactionMaster(), 0, false).Players[1]

	if revealed.ClosedHand[0].Id != 10 || revealed.ClosedHand[0].Suit != pb.Suit_SUIT_SOU {
		t.Fatalf("hand not revealed at round end: %+v", revealed.ClosedHand[0])
	}
	if revealed.Discards[0].Id != 20 {
		t.Fatalf("discard id altered at reveal: %d", revealed.Discards[0].Id)
	}
	// valid_actions still dropped for non-viewers even at round end.
	if len(revealed.ValidActions) != 0 {
		t.Fatalf("opponent valid_actions leaked at reveal: %+v", revealed.ValidActions)
	}
}

// Each call re-randomizes the obfuscation, so a concealed tile never keeps a
// stable fake id across broadcasts (defeats cross-turn tracking + discard
// de-anonymization).
func TestRedactedStateForSeatRotatesPerCall(t *testing.T) {
	master := redactionMaster()
	a := redactedStateForSeat(master, 0, true).Players[1].ClosedHand
	rotated := false
	for i := 0; i < 20 && !rotated; i++ {
		b := redactedStateForSeat(master, 0, true).Players[1].ClosedHand
		for j := range a {
			if a[j].Id != b[j].Id {
				rotated = true
				break
			}
		}
	}
	if !rotated {
		t.Fatal("obfuscation did not rotate across redaction calls")
	}
}
