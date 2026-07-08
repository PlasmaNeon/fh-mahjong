package rules_test

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

func honor7(id uint32) *pb.Tile { return &pb.Tile{Id: id, Suit: pb.Suit_SUIT_JIHAI, Value: 7} }
func sou9(id uint32) *pb.Tile   { return &pb.Tile{Id: id, Suit: pb.Suit_SUIT_SOU, Value: 9} }

func kanCount(actions []*pb.PlayerAction) int {
	n := 0
	for _, a := range actions {
		if a.Type == pb.ActionType_ACTION_KAN {
			n++
		}
	}
	return n
}

// A Pon melded with a wild substitute ([honor7, honor7, wild-9s]) consumes only 2
// natural honor7, leaving the other 2 in hand. The added-kan generator must NOT
// offer to upgrade that Pon to a kong, because the kong would then contain the wild
// (wild tiles cannot be used in a kan). Before the fix it offered TWO added-kan
// actions (one per matching closed honor7), which the RL encoder collapses to the
// same action id -> BridgeError "duplicate action id 182 for ACTION_KAN and ACTION_KAN".
func TestGetValidActions_NoAddedKanWhenPonContainsWild(t *testing.T) {
	r := &rules.FenghuaRuleset{}
	state := &pb.GameState{
		WildTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 9}}, // 9s is wild this round
		Players: []*pb.PlayerState{{
			ClosedHand: []*pb.Tile{honor7(101), honor7(102)}, // the 2 remaining natural honor7
			OpenMelds: []*pb.Meld{{
				Type:  pb.ActionType_ACTION_PON,
				Tiles: []*pb.Tile{honor7(1), honor7(2), sou9(3)}, // pon = 2 honor7 + 1 wild
			}},
		}},
	}
	if got := kanCount(r.GetValidActions(state, 0)); got != 0 {
		t.Fatalf("expected 0 added-kan for a wild-containing Pon (wilds cannot be in a kan), got %d", got)
	}
}

// A Pon with no wilds is still upgradeable by the natural 4th tile.
func TestGetValidActions_AddedKanAllowedWhenNoWild(t *testing.T) {
	r := &rules.FenghuaRuleset{}
	state := &pb.GameState{
		WildTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 9}}, // wild is 9s, unrelated to honor7
		Players: []*pb.PlayerState{{
			ClosedHand: []*pb.Tile{honor7(104)}, // the natural 4th honor7
			OpenMelds: []*pb.Meld{{
				Type:  pb.ActionType_ACTION_PON,
				Tiles: []*pb.Tile{honor7(1), honor7(2), honor7(3)}, // clean pon
			}},
		}},
	}
	if got := kanCount(r.GetValidActions(state, 0)); got != 1 {
		t.Fatalf("expected exactly 1 added-kan for a clean Pon + natural 4th tile, got %d", got)
	}
}

// The added tile itself may not be a wild: if honor7 is the wild this round, a Pon of
// honor7 cannot be upgraded with a wild honor7.
func TestGetValidActions_NoAddedKanWhenAddedTileIsWild(t *testing.T) {
	r := &rules.FenghuaRuleset{}
	state := &pb.GameState{
		WildTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_JIHAI, Value: 7}}, // honor7 is wild this round
		Players: []*pb.PlayerState{{
			ClosedHand: []*pb.Tile{honor7(104)}, // a wild (honor7) — cannot complete a kan
			OpenMelds: []*pb.Meld{{
				Type:  pb.ActionType_ACTION_PON,
				Tiles: []*pb.Tile{honor7(1), honor7(2), honor7(3)},
			}},
		}},
	}
	if got := kanCount(r.GetValidActions(state, 0)); got != 0 {
		t.Fatalf("expected 0 added-kan when the added tile is a wild, got %d", got)
	}
}
