package core_test

import (
	"testing"

	"github.com/plasma/fh-mahjong/core"
	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

func TestGameInitialization(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r)

	if g.State.Phase != pb.GamePhase_PHASE_INIT {
		t.Errorf("Expected PHASE_INIT, got %v", g.State.Phase)
	}
	if len(g.State.Players) != 4 {
		t.Errorf("Expected 4 players, got %d", len(g.State.Players))
	}
}

func TestGameStartAndDeal(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r)

	err := g.Start()
	if err != nil {
		t.Fatalf("Failed to start game: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Errorf("Expected PHASE_PLAYER_TURN, got %v", g.State.Phase)
	}

	for i := 0; i < 4; i++ {
		// East draws a tile on turn start, so East has 14
		expectedSize := uint32(13)
		if i == 0 {
			expectedSize = 14
		}
		if g.State.Players[i].HandSize != expectedSize {
			t.Errorf("Player %d expected hand size %d, got %d", i, expectedSize, g.State.Players[i].HandSize)
		}
	}
}

func TestDiscardAction(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r)
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0] // pick the first tile to discard

	// Inject a matching pair into South's hand so the game recognizes a VALID PONG interrupt and enters PHASE_WAIT_DISCARDS
	southSeat := (activePlayer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[southSeat].ClosedHand = append(g.State.Players[southSeat].ClosedHand, clone1, clone2)

	action := &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	}

	err := g.ProcessPlayerAction(activePlayer, action)
	if err != nil {
		t.Fatalf("Failed to process discard: %v", err)
	}

	if g.State.Phase != pb.GamePhase_PHASE_WAIT_DISCARDS {
		t.Errorf("Expected PHASE_WAIT_DISCARDS after discard, got %v", g.State.Phase)
	}

	if len(g.State.Players[activePlayer].Discards) != 1 {
		t.Errorf("Expected player %d to have 1 discard, got %d", activePlayer, len(g.State.Players[activePlayer].Discards))
	}
}

func TestDirectedMelds(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r)
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0]

	err := g.ProcessPlayerAction(activePlayer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	})
	if err != nil {
		t.Fatalf("Failed to discard: %v", err)
	}

	// Inject a pair into South's hand manually so they can call Pon
	southSeat := (activePlayer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[southSeat].ClosedHand = append(g.State.Players[southSeat].ClosedHand, clone1, clone2)

	err = g.ProcessPlayerAction(southSeat, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_PON,
		MeldTiles: []*pb.Tile{clone1, clone2},
	})
	if err != nil {
		t.Fatalf("Failed to interrupt: %v", err)
	}

	g.ResolveInterrupts()

	melds := g.State.Players[southSeat].OpenMelds
	if len(melds) != 1 {
		t.Fatalf("Expected 1 open meld, got %d", len(melds))
	}

	meld := melds[0]
	// If active is 0, south is 1. (0 - 1 + 4) % 4 = 3 (LEFT)
	if meld.CalledDirection != pb.MeldDirection_MELD_DIRECTION_LEFT {
		t.Errorf("Expected MELD_DIRECTION_LEFT (3), got %v", meld.CalledDirection)
	}

	if meld.CalledTileId != discardTile.Id {
		t.Errorf("Expected called tile ID %d, got %d", discardTile.Id, meld.CalledTileId)
	}
}

func TestDeadWallKanDraw(t *testing.T) {
	r := &rules.HometownRuleset{}
	g := core.NewGame("test-uuid", r)
	g.Start()

	activePlayer := g.State.ActivePlayer
	playerHand := g.State.Players[activePlayer].ClosedHand
	discardTile := playerHand[0]

	southSeat := (activePlayer + 1) % 4
	// South MUST already hold 3 matching tiles to trigger the waiting window for a valid Kan.
	clone1 := &pb.Tile{Id: discardTile.Id + 100, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 200, Suit: discardTile.Suit, Value: discardTile.Value}
	clone3 := &pb.Tile{Id: discardTile.Id + 300, Suit: discardTile.Suit, Value: discardTile.Value}

	southPlayer := g.State.Players[southSeat]
	southPlayer.ClosedHand = append(southPlayer.ClosedHand, clone1, clone2, clone3)
	initialHandSize := len(southPlayer.ClosedHand)
	initialWallCount := g.State.WallCount

	// Player 0 discards a tile
	err := g.ProcessPlayerAction(activePlayer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	})
	if err != nil {
		t.Fatalf("Failed to discard: %v", err)
	}
	// South has already had the triplet injected before the discard.
	// Proceed directly to the Kan call.

	// South calls Kan on the discard
	err = g.ProcessPlayerAction(southSeat, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_KAN,
		MeldTiles: []*pb.Tile{clone1, clone2, clone3},
	})
	if err != nil {
		t.Fatalf("Failed to interrupt Kan: %v", err)
	}

	g.ResolveInterrupts()

	// Verify Melds
	if len(southPlayer.OpenMelds) != 1 {
		t.Fatalf("Expected 1 open meld for South player")
	}
	if southPlayer.OpenMelds[0].Type != pb.ActionType_ACTION_KAN {
		t.Errorf("Expected MELD type KAN")
	}

	// Verify Dead Wall Draw functionality
	// Hand size should have decreased by 3 (the meld tiles removed)
	// and increased by 1 (the dead wall draw). Total: initial - 2
	expectedHandSize := initialHandSize - 2
	if len(southPlayer.ClosedHand) != expectedHandSize {
		t.Errorf("Expected hand size %d, got %d", expectedHandSize, len(southPlayer.ClosedHand))
	}

	// Wall count should have decreased by 1 due to the Dead Wall Draw
	if g.State.WallCount != initialWallCount-1 {
		t.Errorf("Expected wall count %d, got %d", initialWallCount-1, g.State.WallCount)
	}

	// It should now be South player's turn to discard
	if g.State.ActivePlayer != southSeat {
		t.Errorf("Expected active player %d, got %d", southSeat, g.State.ActivePlayer)
	}
	if g.State.Phase != pb.GamePhase_PHASE_PLAYER_TURN {
		t.Errorf("Expected phase PHASE_PLAYER_TURN after Kan, got %v", g.State.Phase)
	}
}
