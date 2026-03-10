package core

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

type flowerAutoRevealRules struct{}

func (r *flowerAutoRevealRules) Name() string { return "flower-auto-reveal-test" }

func (r *flowerAutoRevealRules) GetInitialWall() []*pb.Tile { return nil }

func (r *flowerAutoRevealRules) EvaluateHand(hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) (int32, []*pb.ScoreEntry, bool) {
	return 0, nil, false
}

func (r *flowerAutoRevealRules) CalculatePayouts(totalScore int32, winType pb.ActionType, winnerSeat uint32, discarderSeat uint32) []*pb.PlayerPayout {
	return nil
}

func (r *flowerAutoRevealRules) GetValidActions(state *pb.GameState, playerSeat uint32) []*pb.PlayerAction {
	player := state.Players[playerSeat]
	var flowerActions []*pb.PlayerAction
	for _, t := range player.ClosedHand {
		if t.Suit == pb.Suit_SUIT_FLOWER {
			isWild := false
			for _, w := range state.WildTiles {
				if w.Suit == pb.Suit_SUIT_FLOWER && w.Value == t.Value {
					isWild = true
					break
				}
			}
			if !isWild {
				flowerActions = append(flowerActions, &pb.PlayerAction{
					Type:      pb.ActionType_ACTION_FLOWER_REVEAL,
					MeldTiles: []*pb.Tile{t},
				})
			}
		}
	}
	if len(flowerActions) > 0 {
		return flowerActions
	}

	return []*pb.PlayerAction{{Type: pb.ActionType_ACTION_DISCARD}}
}

func (r *flowerAutoRevealRules) GetValidInterrupts(state *pb.GameState, discardedTile *pb.Tile, playerSeat uint32) []*pb.PlayerAction {
	player := state.Players[playerSeat]
	matches := make([]*pb.Tile, 0, 3)
	for _, t := range player.ClosedHand {
		if t.Suit == discardedTile.Suit && t.Value == discardedTile.Value {
			matches = append(matches, t)
		}
	}
	if len(matches) >= 2 {
		return []*pb.PlayerAction{{
			Type:      pb.ActionType_ACTION_PON,
			MeldTiles: matches[:2],
		}}
	}
	return nil
}

func (r *flowerAutoRevealRules) ResolveInterruptPriority(actions map[uint32]*pb.PlayerAction) (uint32, *pb.PlayerAction) {
	for seat, action := range actions {
		return seat, action
	}
	return 0, nil
}

func TestExecuteSystemDraw_AutoRevealsAllNonWildFlowers(t *testing.T) {
	g := NewGame("test-auto-flower", &flowerAutoRevealRules{})
	seat := uint32(0)

	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = seat
	g.State.WildTiles = []*pb.Tile{{Id: 205, Suit: pb.Suit_SUIT_FLOWER, Value: 5}}

	player := g.State.Players[seat]
	player.ClosedHand = []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_MAN, Value: 1},
		{Id: 2, Suit: pb.Suit_SUIT_MAN, Value: 2},
		{Id: 3, Suit: pb.Suit_SUIT_MAN, Value: 3},
		{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 1},
		{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 2},
		{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 3},
		{Id: 7, Suit: pb.Suit_SUIT_SOU, Value: 1},
		{Id: 8, Suit: pb.Suit_SUIT_SOU, Value: 2},
		{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 3},
		{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 201, Suit: pb.Suit_SUIT_FLOWER, Value: 1},
	}
	player.HandSize = uint32(len(player.ClosedHand))

	g.wall = []*pb.Tile{
		{Id: 202, Suit: pb.Suit_SUIT_FLOWER, Value: 2}, // live draw -> reveal
		{Id: 99, Suit: pb.Suit_SUIT_MAN, Value: 9},     // unused live wall tile
		{Id: 204, Suit: pb.Suit_SUIT_FLOWER, Value: 4}, // wild indicator (not drawn)
		{Id: 102, Suit: pb.Suit_SUIT_PIN, Value: 9},    // later dead-wall draw if needed
		{Id: 100, Suit: pb.Suit_SUIT_MAN, Value: 4},    // 1st replacement
		{Id: 101, Suit: pb.Suit_SUIT_SOU, Value: 4},    // 2nd replacement
	}
	g.wallIndex = 0
	g.deadWallIndex = 0
	g.wangpaiBoundary = 2
	g.wildIndicatorIndex = 2
	g.haiteiDrawIndex = -1
	g.State.WallCount = 5
	g.updateWangpaiTilesLeft()

	if err := g.ExecuteSystemDraw(seat); err != nil {
		t.Fatalf("ExecuteSystemDraw failed: %v", err)
	}

	if len(player.FlowerMelds) != 2 {
		t.Fatalf("expected 2 auto-revealed flowers, got %d", len(player.FlowerMelds))
	}
	if player.FlowerMelds[0].Value != 1 || player.FlowerMelds[1].Value != 2 {
		t.Fatalf("unexpected flower meld values: %+v", player.FlowerMelds)
	}
	if len(player.ClosedHand) != 14 {
		t.Fatalf("expected hand to remain at 14 tiles after replacement draws, got %d", len(player.ClosedHand))
	}
	if player.HandSize != 14 {
		t.Fatalf("expected public hand size 14, got %d", player.HandSize)
	}
	if player.DrawnTileId == nil || *player.DrawnTileId != 101 {
		t.Fatalf("expected drawn tile id to end on final replacement 101, got %+v", player.DrawnTileId)
	}
	if len(player.ValidActions) != 1 || player.ValidActions[0].Type != pb.ActionType_ACTION_DISCARD {
		t.Fatalf("expected final valid actions to be discard-only, got %+v", player.ValidActions)
	}
	if g.State.WangpaiTilesLeft != 1 {
		t.Fatalf("expected 1 drawable wangpai tile left, got %d", g.State.WangpaiTilesLeft)
	}
}

func TestExecuteSystemDraw_DoesNotAutoRevealWildFlower(t *testing.T) {
	g := NewGame("test-wild-flower", &flowerAutoRevealRules{})
	seat := uint32(0)

	g.State.Phase = pb.GamePhase_PHASE_PLAYER_TURN
	g.State.ActivePlayer = seat
	g.State.WildTiles = []*pb.Tile{{Id: 205, Suit: pb.Suit_SUIT_FLOWER, Value: 5}}

	player := g.State.Players[seat]
	player.ClosedHand = []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_MAN, Value: 1},
		{Id: 2, Suit: pb.Suit_SUIT_MAN, Value: 2},
		{Id: 3, Suit: pb.Suit_SUIT_MAN, Value: 3},
		{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 1},
		{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 2},
		{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 3},
		{Id: 7, Suit: pb.Suit_SUIT_SOU, Value: 1},
		{Id: 8, Suit: pb.Suit_SUIT_SOU, Value: 2},
		{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 3},
		{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
	}
	player.HandSize = uint32(len(player.ClosedHand))

	g.wall = []*pb.Tile{
		{Id: 203, Suit: pb.Suit_SUIT_FLOWER, Value: 5}, // live draw -> wild flower, keep in hand
		{Id: 99, Suit: pb.Suit_SUIT_MAN, Value: 9},
		{Id: 204, Suit: pb.Suit_SUIT_FLOWER, Value: 4},
		{Id: 102, Suit: pb.Suit_SUIT_PIN, Value: 9},
		{Id: 100, Suit: pb.Suit_SUIT_MAN, Value: 4},
		{Id: 101, Suit: pb.Suit_SUIT_SOU, Value: 4},
	}
	g.wallIndex = 0
	g.deadWallIndex = 0
	g.wangpaiBoundary = 2
	g.wildIndicatorIndex = 2
	g.haiteiDrawIndex = -1
	g.State.WallCount = 5
	g.updateWangpaiTilesLeft()

	if err := g.ExecuteSystemDraw(seat); err != nil {
		t.Fatalf("ExecuteSystemDraw failed: %v", err)
	}

	if len(player.FlowerMelds) != 0 {
		t.Fatalf("expected no auto-revealed flowers for wild flower draw, got %d", len(player.FlowerMelds))
	}
	if len(player.ClosedHand) != 14 {
		t.Fatalf("expected hand to keep the wild flower and remain at 14 tiles, got %d", len(player.ClosedHand))
	}
	if player.DrawnTileId == nil || *player.DrawnTileId != 203 {
		t.Fatalf("expected drawn tile id to stay on wild flower draw 203, got %+v", player.DrawnTileId)
	}
}

func TestResolveInterrupts_AutoRevealsClaimersNonWildFlowers(t *testing.T) {
	g := NewGame("test-claim-auto-flower", &flowerAutoRevealRules{})

	discarderSeat := uint32(0)
	claimerSeat := uint32(1)
	discardedTile := &pb.Tile{Id: 900, Suit: pb.Suit_SUIT_MAN, Value: 3}
	claimTileA := &pb.Tile{Id: 901, Suit: pb.Suit_SUIT_MAN, Value: 3}
	claimTileB := &pb.Tile{Id: 902, Suit: pb.Suit_SUIT_MAN, Value: 3}
	heldFlower := &pb.Tile{Id: 903, Suit: pb.Suit_SUIT_FLOWER, Value: 2}
	replacement := &pb.Tile{Id: 904, Suit: pb.Suit_SUIT_PIN, Value: 9}

	g.State.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	g.State.ActivePlayer = discarderSeat
	g.State.ActiveDiscard = discardedTile
	g.State.WildTiles = []*pb.Tile{{Id: 999, Suit: pb.Suit_SUIT_FLOWER, Value: 5}}
	g.State.Players[claimerSeat].ClosedHand = []*pb.Tile{
		claimTileA,
		claimTileB,
		heldFlower,
	}
	g.State.Players[claimerSeat].HandSize = 3
	g.State.Players[claimerSeat].ValidActions = []*pb.PlayerAction{{
		Type:      pb.ActionType_ACTION_PON,
		MeldTiles: []*pb.Tile{claimTileA, claimTileB},
	}}
	g.State.Players[discarderSeat].Discards = []*pb.Tile{discardedTile}
	g.wall = []*pb.Tile{
		{Id: 998, Suit: pb.Suit_SUIT_FLOWER, Value: 4}, // wild indicator
		replacement,                                    // dead wall supplement after flower reveal
	}
	g.wallIndex = 0
	g.deadWallIndex = 0
	g.wangpaiBoundary = 0
	g.wildIndicatorIndex = 0
	g.haiteiDrawIndex = -1
	g.State.WallCount = 1
	g.updateWangpaiTilesLeft()
	g.interruptQueue[claimerSeat] = &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_PON,
		MeldTiles: []*pb.Tile{claimTileA, claimTileB},
	}

	g.ResolveInterrupts()

	claimer := g.State.Players[claimerSeat]
	if len(claimer.OpenMelds) != 1 || claimer.OpenMelds[0].Type != pb.ActionType_ACTION_PON {
		t.Fatalf("expected claimed pon meld, got %+v", claimer.OpenMelds)
	}
	if len(claimer.FlowerMelds) != 1 || claimer.FlowerMelds[0].Id != heldFlower.Id {
		t.Fatalf("expected held flower to auto-reveal after pon, got %+v", claimer.FlowerMelds)
	}
	if len(claimer.ClosedHand) != 1 || claimer.ClosedHand[0].Id != replacement.Id {
		t.Fatalf("expected dead-wall replacement to remain in hand, got %+v", claimer.ClosedHand)
	}
	if claimer.DrawnTileId == nil || *claimer.DrawnTileId != int32(replacement.Id) {
		t.Fatalf("expected drawn tile id to point at flower replacement %d, got %+v", replacement.Id, claimer.DrawnTileId)
	}
	if len(claimer.ValidActions) != 1 || claimer.ValidActions[0].Type != pb.ActionType_ACTION_DISCARD {
		t.Fatalf("expected discard-only valid actions after auto-reveal, got %+v", claimer.ValidActions)
	}
}
