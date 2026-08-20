package rl

import (
	"fmt"
	"sort"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

// ActionCatalogVersion pins the action-ID ↔ meaning mapping below. Paipu v2
// records raw catalog IDs (PaipuDecision.ChosenID/LegalIDs) stamped with
// this version; bump it on ANY change to the constants below or to
// EncodeAction/DecodeActionID semantics, and record the old→new translation
// in docs. Guarded by TestActionCatalogPinned.
const ActionCatalogVersion = 1

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

// tileFaceIndex42 and tileFaceIndex34 are the engine's face-index helpers. The
// RL action catalog and observation encoder share the 42-face space with the
// event codec, so the mapping has exactly one definition (engine/events.go).
func tileFaceIndex42(tile *pb.Tile) (int, bool) { return engine.FaceIndex42(tile) }

func tileFaceIndex34(tile *pb.Tile) (int, bool) { return engine.FaceIndex34(tile) }

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
		actions[actionID] = tiles.CloneAction(action)
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
				Tile: tiles.CloneTile(tile),
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
	return tiles.CloneAction(action), nil
}

func DecodeActionID(state *pb.GameState, seat uint32, actionID int) (*pb.PlayerAction, error) {
	return decodeActionID(state, seat, actionID)
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
		startIndex, ok := chiiSequenceIndex(state, action)
		if !ok {
			return 0, false
		}
		return ChiiBase + startIndex, true
	default:
		return 0, false
	}
}

// chiiSequenceIndex resolves the claimed tile the same way the engine does
// (internal/engine/game.go:1104): the client submits claim actions with
// Tile unset and only MeldTiles populated, relying on the engine to infer
// the claimed tile from state.ActiveDiscard. Mirror that here so paipu v2
// can encode client-shaped chii actions instead of recording them as
// illegal (chosenId -1).
func chiiSequenceIndex(state *pb.GameState, action *pb.PlayerAction) (int, bool) {
	if action == nil {
		return 0, false
	}
	claimedTile := action.Tile
	if claimedTile == nil {
		if state == nil || state.ActiveDiscard == nil {
			return 0, false
		}
		claimedTile = state.ActiveDiscard
	}
	if claimedTile.Suit != pb.Suit_SUIT_SOU && claimedTile.Suit != pb.Suit_SUIT_PIN && claimedTile.Suit != pb.Suit_SUIT_MAN {
		return 0, false
	}

	values := []uint32{claimedTile.Value}
	for _, tile := range action.MeldTiles {
		if tile == nil || tile.Suit != claimedTile.Suit {
			return 0, false
		}
		values = append(values, tile.Value)
	}
	sort.Slice(values, func(i, j int) bool { return values[i] < values[j] })
	if len(values) != 3 || values[0]+1 != values[1] || values[1]+1 != values[2] {
		return 0, false
	}

	suitOffset := 0
	switch claimedTile.Suit {
	case pb.Suit_SUIT_MAN:
		suitOffset = 0
	case pb.Suit_SUIT_PIN:
		suitOffset = 7
	case pb.Suit_SUIT_SOU:
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

// LegalActions exposes the catalog-indexed legal action map so replay/review
// drivers can resolve recorded actions through the same legality map used by
// the RL bridge.
func LegalActions(state *pb.GameState, seat uint32) (map[int]*pb.PlayerAction, error) {
	return legalActionMap(state, seat)
}

// EncodeAction exposes catalog encoding for replay/review drivers.
func EncodeAction(state *pb.GameState, seat uint32, action *pb.PlayerAction) (int, bool) {
	return encodeAction(state, seat, action)
}

// SortedLegalIDs returns the action ids of a legal-action set in ascending
// order. The paipu-v2 supervision trace compares legal sets across the server,
// the offline generator and the review harness, so the ordering is part of the
// recorded contract, not a display detail — collect and sort in one place.
func SortedLegalIDs(legal map[int]*pb.PlayerAction) []int {
	ids := make([]int, 0, len(legal))
	for id := range legal {
		ids = append(ids, id)
	}
	sort.Ints(ids)
	return ids
}
