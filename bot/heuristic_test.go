package bot

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestHeuristicBotKeepsPairsForSevenPairs(t *testing.T) {
	policy := NewHeuristicPolicy()
	state := discardState(
		tiles(
			tm(1), tm(1),
			tm(2), tm(2),
			tm(3), tm(3),
			tm(4), tm(4),
			tm(5), tm(5),
			tm(6), tm(6),
			tm(7), tm(8),
		),
		nil,
	)

	action := policy.ChooseAction(state, 0)
	assertDiscard(t, action)
	if action.Tile.Value != 7 && action.Tile.Value != 8 {
		t.Fatalf("expected bot to discard one of the singles, got %v", action.Tile)
	}
}

func TestHeuristicBotKeepsIndependenceShape(t *testing.T) {
	policy := NewHeuristicPolicy()
	state := discardState(
		tiles(
			tm(1), tm(1), tm(4), tm(7),
			tp(1), tp(4), tp(7),
			ts(1), ts(4),
			tz(1), tz(2), tz(3), tz(4), tz(5),
		),
		nil,
	)

	action := policy.ChooseAction(state, 0)
	assertDiscard(t, action)
	if action.Tile.Suit != pb.Suit_SUIT_MAN || action.Tile.Value != 1 {
		t.Fatalf("expected bot to discard 1m pair tile to preserve independence, got %v", action.Tile)
	}
}

func TestHeuristicBotAvoidsDiscardingWildWhenEquivalent(t *testing.T) {
	policy := NewHeuristicPolicy()
	state := discardState(
		tiles(
			tz(1), tz(1),
			tz(2), tz(2),
			tz(3), tz(3),
			tz(4), tz(4),
			tz(5), tz(5),
			tz(6), tz(6),
			tm(7), tm(9),
		),
		[]*pb.Tile{{Suit: pb.Suit_SUIT_MAN, Value: 9}},
	)

	action := policy.ChooseAction(state, 0)
	assertDiscard(t, action)
	if action.Tile.Value != 7 {
		t.Fatalf("expected bot to keep the wild tile and discard 7m, got %v", action.Tile)
	}
}

func TestHeuristicBotPassesPonWhenSevenPairsBest(t *testing.T) {
	policy := NewHeuristicPolicy()
	hand := tiles(
		tm(1), tm(1),
		tm(2), tm(2),
		tm(3), tm(3),
		tm(4), tm(4),
		tm(5), tm(5),
		tm(7), tm(7),
		tm(8),
	)
	state := interruptState(hand, []*pb.PlayerAction{
		{
			Type:      pb.ActionType_ACTION_PON,
			MeldTiles: []*pb.Tile{hand[10], hand[11]},
		},
		{Type: pb.ActionType_ACTION_PASS},
	})

	action := policy.ChooseAction(state, 0)
	if action == nil || action.Type != pb.ActionType_ACTION_PASS {
		t.Fatalf("expected bot to pass on pon to preserve seven pairs, got %+v", action)
	}
}

func TestHeuristicBotChoosesPonWhenItImproves(t *testing.T) {
	policy := NewHeuristicPolicy()
	hand := tiles(
		tm(1), tm(1),
		tm(2), tm(3), tm(4),
		tm(5), tm(6), tm(7),
		tp(4), tp(5),
		tp(8),
		ts(9), ts(9),
	)
	state := interruptState(hand, []*pb.PlayerAction{
		{
			Type:      pb.ActionType_ACTION_PON,
			MeldTiles: []*pb.Tile{hand[0], hand[1]},
		},
		{Type: pb.ActionType_ACTION_PASS},
	})

	action := policy.ChooseAction(state, 0)
	if action == nil || action.Type != pb.ActionType_ACTION_PON {
		t.Fatalf("expected bot to pon when it improves shanten, got %+v", action)
	}
}

func TestHeuristicBotSkipsWildKan(t *testing.T) {
	policy := NewHeuristicPolicy()
	hand := tiles(
		tz(1), tz(1),
		tz(2), tz(2),
		tz(3), tz(3),
		tz(4), tz(4),
		tz(5), tz(5),
		tz(6), tz(6),
		tm(7), tm(9),
	)
	state := discardState(hand, []*pb.Tile{{Suit: pb.Suit_SUIT_MAN, Value: 9}})
	state.Players[0].ValidActions = append(state.Players[0].ValidActions, &pb.PlayerAction{
		Type:      pb.ActionType_ACTION_KAN,
		MeldTiles: []*pb.Tile{hand[13]},
	})

	action := policy.ChooseAction(state, 0)
	assertDiscard(t, action)
	if action.Tile.Value != 7 {
		t.Fatalf("expected bot to skip wild kan and discard 7m, got %+v", action)
	}
}

func TestHeuristicBotIsDeterministic(t *testing.T) {
	policy := NewHeuristicPolicy()
	state := discardState(
		tiles(
			tm(1), tm(1),
			tm(2), tm(2),
			tm(3), tm(3),
			tm(4), tm(4),
			tm(5), tm(5),
			tm(6), tm(6),
			tm(7), tm(8),
		),
		nil,
	)

	first := policy.ChooseAction(state, 0)
	second := policy.ChooseAction(state, 0)
	assertDiscard(t, first)
	assertDiscard(t, second)
	if first.Tile.Id != second.Tile.Id {
		t.Fatalf("expected deterministic discard, got %d then %d", first.Tile.Id, second.Tile.Id)
	}
}

func TestHeuristicBotDiscardsDrawnTileDuringHaitei(t *testing.T) {
	policy := NewHeuristicPolicy()
	hand := tiles(
		tm(1), tm(1), tm(4), tm(7),
		tp(1), tp(4), tp(7),
		ts(1), ts(4),
		tz(1), tz(2), tz(3), tz(4), tz(5),
	)
	drawnTile := hand[len(hand)-1]
	drawnID := int32(drawnTile.Id)
	state := discardState(hand, nil)
	state.IsHaitei = true
	state.Players[0].DrawnTileId = &drawnID

	action := policy.ChooseAction(state, 0)
	assertDiscard(t, action)
	if action.Tile.Id != drawnTile.Id {
		t.Fatalf("expected haitei discard to use drawn tile %d, got %+v", drawnTile.Id, action.Tile)
	}
}

func discardState(hand []*pb.Tile, wildTiles []*pb.Tile) *pb.GameState {
	return &pb.GameState{
		Phase: pb.GamePhase_PHASE_PLAYER_TURN,
		Players: []*pb.PlayerState{
			{
				Seat:       0,
				ClosedHand: hand,
				OpenMelds:  []*pb.Meld{},
				ValidActions: []*pb.PlayerAction{
					{Type: pb.ActionType_ACTION_DISCARD},
				},
			},
		},
		WildTiles: wildTiles,
	}
}

func interruptState(hand []*pb.Tile, validActions []*pb.PlayerAction) *pb.GameState {
	return &pb.GameState{
		Phase:        pb.GamePhase_PHASE_WAIT_DISCARDS,
		ActivePlayer: 1,
		ActiveDiscard: &pb.Tile{
			Id:    999,
			Suit:  pb.Suit_SUIT_MAN,
			Value: 7,
		},
		Players: []*pb.PlayerState{
			{
				Seat:         0,
				ClosedHand:   hand,
				OpenMelds:    []*pb.Meld{},
				ValidActions: validActions,
			},
			{Seat: 1},
		},
	}
}

func tiles(specs ...*pb.Tile) []*pb.Tile {
	hand := make([]*pb.Tile, len(specs))
	for i, tile := range specs {
		copyTile := *tile
		copyTile.Id = uint32(i + 1)
		hand[i] = &copyTile
	}
	return hand
}

func tm(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: value} }
func tp(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: value} }
func ts(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: value} }
func tz(value uint32) *pb.Tile { return &pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: value} }

func assertDiscard(t *testing.T, action *pb.PlayerAction) {
	t.Helper()
	if action == nil || action.Type != pb.ActionType_ACTION_DISCARD || action.Tile == nil {
		t.Fatalf("expected discard action, got %+v", action)
	}
}
