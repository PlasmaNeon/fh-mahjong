package engine_test

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

func wildH7(id uint32) *pb.Tile { return &pb.Tile{Id: id, Suit: pb.Suit_SUIT_JIHAI, Value: 7} }
func wildS9(id uint32) *pb.Tile { return &pb.Tile{Id: id, Suit: pb.Suit_SUIT_SOU, Value: 9} }

// Defense in depth: even though the action generator no longer advertises wild
// kans, a forged ACTION_KAN submitted directly to the engine must be rejected —
// wild tiles cannot be used in a kan.

func TestProcessPlayerAction_RejectsForgedAddedKanOntoWildPon(t *testing.T) {
	g := engine.NewGame("t", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.State.WildTiles = []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 9}} // 9s wild
	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = 0
	p := g.State.Players[0]
	p.ClosedHand = []*pb.Tile{wildH7(101), wildH7(102)}                                        // 2 natural honor7
	p.OpenMelds = []*pb.Meld{{Type: pb.ActionType_ACTION_PON, Tiles: []*pb.Tile{wildH7(1), wildH7(2), wildS9(3)}}} // pon has a wild

	err := g.ProcessPlayerAction(0, &pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: []*pb.Tile{wildH7(101)}})
	if err == nil {
		t.Fatal("expected forged added-kan onto a wild-containing Pon to be rejected")
	}
	// Rejected before any mutation: the hand must be untouched.
	if len(p.ClosedHand) != 2 {
		t.Fatalf("rejected kan mutated the hand: ClosedHand size %d, want 2", len(p.ClosedHand))
	}
}

func TestProcessPlayerAction_RejectsForgedConcealedWildKan(t *testing.T) {
	g := engine.NewGame("t", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.State.WildTiles = []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 9}} // 9s wild
	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = 0
	p := g.State.Players[0]
	four := []*pb.Tile{wildS9(1), wildS9(2), wildS9(3), wildS9(4)} // four wild-face tiles
	p.ClosedHand = four

	err := g.ProcessPlayerAction(0, &pb.PlayerAction{Type: pb.ActionType_ACTION_KAN, MeldTiles: four})
	if err == nil {
		t.Fatal("expected forged concealed kan of a wild face to be rejected")
	}
}

func TestProcessPlayerAction_RejectsForgedDirectWildKan(t *testing.T) {
	g := engine.NewGame("t", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.State.WildTiles = []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 9}} // 9s wild
	g.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	g.State.ActivePlayer = 0
	g.State.ActiveDiscard = wildS9(9) // a wild discard being claimed
	p := g.State.Players[1]
	p.ClosedHand = []*pb.Tile{wildS9(1), wildS9(2), wildS9(3)} // three wild matches

	err := g.ProcessPlayerAction(1, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_KAN,
		Tile:      wildS9(9),
		MeldTiles: []*pb.Tile{wildS9(1), wildS9(2), wildS9(3)},
	})
	if err == nil {
		t.Fatal("expected forged direct kan on a wild discard to be rejected")
	}
}
