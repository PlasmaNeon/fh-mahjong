package rlenv

import (
	"fmt"
	"sort"

	pb "github.com/plasma/fh-mahjong/proto"
)

const (
	ActionPass         = 0
	ActionTsumo        = 1
	ActionRon          = 2
	ActionAcceptHaitei = 3
	ActionRefuseHaitei = 4

	DiscardBase  = 5
	DiscardCount = 42

	PonBase  = DiscardBase + DiscardCount
	PonCount = 34

	KanDirectBase   = PonBase + PonCount
	KanModeCount    = 34
	KanClosedBase   = KanDirectBase + KanModeCount
	KanUpgradedBase = KanClosedBase + KanModeCount

	ChiiBase  = KanUpgradedBase + KanModeCount
	ChiiCount = 21

	ActionSpaceSize = ChiiBase + ChiiCount
)

func tileFaceIndex42(tile *pb.Tile) (int, bool) {
	if tile == nil {
		return 0, false
	}

	switch tile.Suit {
	case pb.Suit_SUIT_SOU:
		if tile.Value < 1 || tile.Value > 9 {
			return 0, false
		}
		return int(tile.Value - 1), true
	case pb.Suit_SUIT_PIN:
		if tile.Value < 1 || tile.Value > 9 {
			return 0, false
		}
		return 9 + int(tile.Value-1), true
	case pb.Suit_SUIT_MAN:
		if tile.Value < 1 || tile.Value > 9 {
			return 0, false
		}
		return 18 + int(tile.Value-1), true
	case pb.Suit_SUIT_JIHAI:
		if tile.Value < 1 || tile.Value > 7 {
			return 0, false
		}
		return 27 + int(tile.Value-1), true
	case pb.Suit_SUIT_FLOWER:
		if tile.Value < 1 || tile.Value > 8 {
			return 0, false
		}
		return 34 + int(tile.Value-1), true
	default:
		return 0, false
	}
}

func tileFaceIndex34(tile *pb.Tile) (int, bool) {
	index, ok := tileFaceIndex42(tile)
	if !ok || index >= 34 {
		return 0, false
	}
	return index, true
}

func legalActionMap(state *pb.GameState, seat uint32) (map[int]*pb.PlayerAction, error) {
	if state == nil || int(seat) >= len(state.Players) {
		return nil, fmt.Errorf("invalid seat %d", seat)
	}

	player := state.Players[seat]
	actions := make(map[int]*pb.PlayerAction)
	add := func(actionID int, action *pb.PlayerAction) error {
		if existing, exists := actions[actionID]; exists {
			return fmt.Errorf("duplicate action id %d for %v and %v", actionID, existing.Type, action.Type)
		}
		actions[actionID] = cloneAction(action)
		return nil
	}

	if state.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS && len(player.ValidActions) > 0 {
		if err := add(ActionPass, &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}); err != nil {
			return nil, err
		}
	}

	if hasActionType(player.ValidActions, pb.ActionType_ACTION_TSUMO) {
		if err := add(ActionTsumo, &pb.PlayerAction{Type: pb.ActionType_ACTION_TSUMO}); err != nil {
			return nil, err
		}
	}
	if hasActionType(player.ValidActions, pb.ActionType_ACTION_RON) {
		if err := add(ActionRon, &pb.PlayerAction{Type: pb.ActionType_ACTION_RON}); err != nil {
			return nil, err
		}
	}
	if hasActionType(player.ValidActions, pb.ActionType_ACTION_ACCEPT_HAITEI) {
		if err := add(ActionAcceptHaitei, &pb.PlayerAction{Type: pb.ActionType_ACTION_ACCEPT_HAITEI}); err != nil {
			return nil, err
		}
	}
	if hasActionType(player.ValidActions, pb.ActionType_ACTION_REFUSE_HAITEI) {
		if err := add(ActionRefuseHaitei, &pb.PlayerAction{Type: pb.ActionType_ACTION_REFUSE_HAITEI}); err != nil {
			return nil, err
		}
	}

	if hasActionType(player.ValidActions, pb.ActionType_ACTION_DISCARD) {
		seen := make(map[int]bool)
		for _, tile := range sortedTilesByID(player.ClosedHand) {
			faceIndex, ok := tileFaceIndex42(tile)
			if !ok || seen[faceIndex] {
				continue
			}
			seen[faceIndex] = true
			if err := add(DiscardBase+faceIndex, &pb.PlayerAction{
				Type: pb.ActionType_ACTION_DISCARD,
				Tile: cloneTile(tile),
			}); err != nil {
				return nil, err
			}
		}
	}

	for _, action := range player.ValidActions {
		switch action.Type {
		case pb.ActionType_ACTION_DISCARD,
			pb.ActionType_ACTION_TSUMO,
			pb.ActionType_ACTION_RON,
			pb.ActionType_ACTION_ACCEPT_HAITEI,
			pb.ActionType_ACTION_REFUSE_HAITEI:
			continue
		}
		actionID, ok := encodeAction(state, seat, action)
		if !ok {
			continue
		}
		if err := add(actionID, action); err != nil {
			return nil, err
		}
	}

	return actions, nil
}

func actionMask(state *pb.GameState, seat uint32) ([]byte, error) {
	actions, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}

	mask := make([]byte, ActionSpaceSize)
	for actionID := range actions {
		mask[actionID] = 1
	}
	return mask, nil
}

func decodeActionID(state *pb.GameState, seat uint32, actionID int) (*pb.PlayerAction, error) {
	actions, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}

	action, ok := actions[actionID]
	if !ok {
		legal := make([]int, 0, len(actions))
		for candidate := range actions {
			legal = append(legal, candidate)
		}
		sort.Ints(legal)
		return nil, fmt.Errorf("illegal action id %d for seat %d; legal=%v", actionID, seat, legal)
	}
	return cloneAction(action), nil
}

func encodeAction(state *pb.GameState, seat uint32, action *pb.PlayerAction) (int, bool) {
	if action == nil {
		return 0, false
	}

	switch action.Type {
	case pb.ActionType_ACTION_PASS:
		return ActionPass, true
	case pb.ActionType_ACTION_TSUMO:
		return ActionTsumo, true
	case pb.ActionType_ACTION_RON:
		return ActionRon, true
	case pb.ActionType_ACTION_ACCEPT_HAITEI:
		return ActionAcceptHaitei, true
	case pb.ActionType_ACTION_REFUSE_HAITEI:
		return ActionRefuseHaitei, true
	case pb.ActionType_ACTION_DISCARD:
		faceIndex, ok := tileFaceIndex42(action.Tile)
		if !ok {
			return 0, false
		}
		return DiscardBase + faceIndex, true
	case pb.ActionType_ACTION_PON:
		faceIndex, ok := tileFaceIndex34(firstTile(action.MeldTiles, action.Tile))
		if !ok {
			return 0, false
		}
		return PonBase + faceIndex, true
	case pb.ActionType_ACTION_KAN:
		faceIndex, ok := tileFaceIndex34(firstTile(action.MeldTiles, action.Tile))
		if !ok {
			return 0, false
		}
		switch kanMode(state, seat, action) {
		case "direct":
			return KanDirectBase + faceIndex, true
		case "closed":
			return KanClosedBase + faceIndex, true
		case "upgraded":
			return KanUpgradedBase + faceIndex, true
		default:
			return 0, false
		}
	case pb.ActionType_ACTION_CHII:
		startIndex, ok := chiiSequenceIndex(action)
		if !ok {
			return 0, false
		}
		return ChiiBase + startIndex, true
	default:
		return 0, false
	}
}

func chiiSequenceIndex(action *pb.PlayerAction) (int, bool) {
	if action == nil || action.Tile == nil {
		return 0, false
	}
	if action.Tile.Suit != pb.Suit_SUIT_SOU && action.Tile.Suit != pb.Suit_SUIT_PIN && action.Tile.Suit != pb.Suit_SUIT_MAN {
		return 0, false
	}

	values := []uint32{action.Tile.Value}
	for _, tile := range action.MeldTiles {
		if tile == nil || tile.Suit != action.Tile.Suit {
			return 0, false
		}
		values = append(values, tile.Value)
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	if len(values) != 3 || values[0]+1 != values[1] || values[1]+1 != values[2] {
		return 0, false
	}

	suitOffset := 0
	switch action.Tile.Suit {
	case pb.Suit_SUIT_SOU:
		suitOffset = 0
	case pb.Suit_SUIT_PIN:
		suitOffset = 7
	case pb.Suit_SUIT_MAN:
		suitOffset = 14
	}
	return suitOffset + int(values[0]-1), true
}

func kanMode(state *pb.GameState, seat uint32, action *pb.PlayerAction) string {
	if state != nil && state.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS {
		return "direct"
	}
	if len(action.MeldTiles) >= 4 {
		return "closed"
	}
	return "upgraded"
}

func hasActionType(actions []*pb.PlayerAction, actionType pb.ActionType) bool {
	for _, action := range actions {
		if action.Type == actionType {
			return true
		}
	}
	return false
}

func firstTile(tiles []*pb.Tile, fallback *pb.Tile) *pb.Tile {
	if len(tiles) > 0 {
		return tiles[0]
	}
	return fallback
}

func sortedTilesByID(tiles []*pb.Tile) []*pb.Tile {
	out := append([]*pb.Tile(nil), tiles...)
	sort.Slice(out, func(i, j int) bool {
		return out[i].Id < out[j].Id
	})
	return out
}

func cloneAction(action *pb.PlayerAction) *pb.PlayerAction {
	if action == nil {
		return nil
	}
	out := &pb.PlayerAction{
		Type:           action.Type,
		Tile:           cloneTile(action.Tile),
		TargetPlayer:   action.TargetPlayer,
		IsRobbingKong:  action.IsRobbingKong,
		IsBottomTile:   action.IsBottomTile,
		IsBloomingKong: action.IsBloomingKong,
	}
	if len(action.MeldTiles) > 0 {
		out.MeldTiles = make([]*pb.Tile, len(action.MeldTiles))
		for i, tile := range action.MeldTiles {
			out.MeldTiles[i] = cloneTile(tile)
		}
	}
	return out
}

func cloneTile(tile *pb.Tile) *pb.Tile {
	if tile == nil {
		return nil
	}
	return &pb.Tile{
		Id:    tile.Id,
		Suit:  tile.Suit,
		Value: tile.Value,
	}
}
