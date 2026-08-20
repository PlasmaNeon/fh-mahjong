package rl

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestTileFaceIndexMatchesRulesBackendOrder(t *testing.T) {
	tests := []struct {
		name string
		tile *pb.Tile
		want int
	}{
		{"1m", &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}, 0},
		{"9m", &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 9}, 8},
		{"1p", &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1}, 9},
		{"9p", &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 9}, 17},
		{"1s", &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}, 18},
		{"9s", &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 9}, 26},
		{"east", &pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: 1}, 27},
		{"chun", &pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: 7}, 33},
		{"spring", &pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: 1}, 34},
		{"bamboo flower", &pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: 8}, 41},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := tileFaceIndex42(tc.tile)
			if !ok {
				t.Fatalf("tileFaceIndex42(%s) returned !ok", tc.name)
			}
			if got != tc.want {
				t.Fatalf("tileFaceIndex42(%s) = %d, want %d", tc.name, got, tc.want)
			}
		})
	}
}

func TestEncodeTileActionsUseRulesBackendTileOrder(t *testing.T) {
	tests := []struct {
		name   string
		action *pb.PlayerAction
		want   int
	}{
		{
			name:   "discard 1m",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_DISCARD, Tile: &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}},
			want:   DiscardBase,
		},
		{
			name:   "discard 1p",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_DISCARD, Tile: &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1}},
			want:   DiscardBase + 9,
		},
		{
			name:   "discard 1s",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_DISCARD, Tile: &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}},
			want:   DiscardBase + 18,
		},
		{
			name:   "pon 1m",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_PON, Tile: &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}},
			want:   PonBase,
		},
		{
			name:   "pon 1p",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_PON, Tile: &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1}},
			want:   PonBase + 9,
		},
		{
			name:   "pon 1s",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_PON, Tile: &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}},
			want:   PonBase + 18,
		},
		{
			name:   "chii 1m2m3m",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_CHII, Tile: &pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}, MeldTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_MAN, Value: 2}, {Suit: pb.Suit_SUIT_MAN, Value: 3}}},
			want:   ChiiBase,
		},
		{
			name:   "chii 1p2p3p",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_CHII, Tile: &pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 1}, MeldTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_PIN, Value: 2}, {Suit: pb.Suit_SUIT_PIN, Value: 3}}},
			want:   ChiiBase + 7,
		},
		{
			name:   "chii 1s2s3s",
			action: &pb.PlayerAction{Type: pb.ActionType_ACTION_CHII, Tile: &pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}, MeldTiles: []*pb.Tile{{Suit: pb.Suit_SUIT_SOU, Value: 2}, {Suit: pb.Suit_SUIT_SOU, Value: 3}}},
			want:   ChiiBase + 14,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, ok := encodeAction(nil, 0, tc.action)
			if !ok {
				t.Fatalf("encodeAction(%s) returned !ok", tc.name)
			}
			if got != tc.want {
				t.Fatalf("encodeAction(%s) = %d, want %d", tc.name, got, tc.want)
			}
		})
	}
}

// TestEncodeChiiClientShapeUsesActiveDiscard covers the production bug: the
// web client submits chii claims with Tile unset, sending only MeldTiles
// (the two hand tiles); the engine (internal/engine/game.go:1104) infers the
// claimed tile from state.ActiveDiscard. EncodeAction must mirror that
// inference instead of refusing the action.
func TestEncodeChiiClientShapeUsesActiveDiscard(t *testing.T) {
	// Claimed discard is 7p; hand tiles are 5p, 6p (client shape: Tile nil).
	state := &pb.GameState{
		ActiveDiscard: &pb.Tile{Id: 96, Suit: pb.Suit_SUIT_PIN, Value: 7},
	}
	action := &pb.PlayerAction{
		Type: pb.ActionType_ACTION_CHII,
		Tile: nil,
		MeldTiles: []*pb.Tile{
			{Id: 91, Suit: pb.Suit_SUIT_PIN, Value: 5},
			{Id: 93, Suit: pb.Suit_SUIT_PIN, Value: 6},
		},
	}

	got, ok := encodeAction(state, 0, action)
	if !ok {
		t.Fatalf("encodeAction(client-shaped chii) returned !ok")
	}
	want := ChiiBase + 11 // pin suitOffset 7 + (lowest value 5 - 1) = 11 -> id 194
	if got != want {
		t.Fatalf("encodeAction(client-shaped chii) = %d, want %d", got, want)
	}
	if want != 194 {
		t.Fatalf("sanity check failed: expected id 194 to match production legal set, got %d", want)
	}
}

// TestEncodeChiiClientShapeNilActiveDiscardFails ensures we don't guess a
// claimed tile out of thin air when there's nothing to infer it from.
func TestEncodeChiiClientShapeNilActiveDiscardFails(t *testing.T) {
	action := &pb.PlayerAction{
		Type: pb.ActionType_ACTION_CHII,
		Tile: nil,
		MeldTiles: []*pb.Tile{
			{Suit: pb.Suit_SUIT_PIN, Value: 5},
			{Suit: pb.Suit_SUIT_PIN, Value: 6},
		},
	}

	// Nil state.
	if _, ok := encodeAction(nil, 0, action); ok {
		t.Fatalf("encodeAction(client-shaped chii, nil state) = ok, want !ok")
	}

	// State with nil ActiveDiscard.
	state := &pb.GameState{}
	if _, ok := encodeAction(state, 0, action); ok {
		t.Fatalf("encodeAction(client-shaped chii, nil ActiveDiscard) = ok, want !ok")
	}
}

// TestEncodeChiiRoundTripsThroughDecode confirms the client-shaped chii id
// matches what DecodeActionID would offer as the legal action for the same
// state, closing the loop described in the production incident (legal set
// contained 194 but EncodeAction of the human's chii returned !ok).
func TestEncodeChiiRoundTripsThroughDecode(t *testing.T) {
	discard := &pb.Tile{Id: 96, Suit: pb.Suit_SUIT_PIN, Value: 7}
	state := &pb.GameState{
		Phase:         pb.GamePhase_PHASE_WAIT_DISCARDS,
		ActiveDiscard: discard,
		Players: []*pb.PlayerState{
			{
				ValidActions: []*pb.PlayerAction{
					{
						Type: pb.ActionType_ACTION_CHII,
						Tile: discard,
						MeldTiles: []*pb.Tile{
							{Id: 91, Suit: pb.Suit_SUIT_PIN, Value: 5},
							{Id: 93, Suit: pb.Suit_SUIT_PIN, Value: 6},
						},
					},
				},
			},
		},
	}

	clientAction := &pb.PlayerAction{
		Type: pb.ActionType_ACTION_CHII,
		Tile: nil,
		MeldTiles: []*pb.Tile{
			{Id: 91, Suit: pb.Suit_SUIT_PIN, Value: 5},
			{Id: 93, Suit: pb.Suit_SUIT_PIN, Value: 6},
		},
	}

	got, ok := EncodeAction(state, 0, clientAction)
	if !ok {
		t.Fatalf("EncodeAction(client-shaped chii) returned !ok")
	}

	decoded, err := DecodeActionID(state, 0, got)
	if err != nil {
		t.Fatalf("DecodeActionID(%d) returned error: %v", got, err)
	}

	roundTripped, ok := EncodeAction(state, 0, decoded)
	if !ok {
		t.Fatalf("EncodeAction(decoded action) returned !ok")
	}
	if roundTripped != got {
		t.Fatalf("round trip mismatch: encoded %d, decoded then re-encoded %d", got, roundTripped)
	}
}

func TestSortedLegalIDsAscendingAndComplete(t *testing.T) {
	legal := map[int]*pb.PlayerAction{
		42: {}, 7: {}, 200: {}, 0: {},
	}
	got := SortedLegalIDs(legal)
	want := []int{0, 7, 42, 200}
	if len(got) != len(want) {
		t.Fatalf("SortedLegalIDs returned %d ids, want %d", len(got), len(want))
	}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("SortedLegalIDs = %v, want %v", got, want)
		}
	}
}

func TestSortedLegalIDsEmptyIsNonNil(t *testing.T) {
	// Callers marshal this straight into paipu JSON; a nil slice would encode
	// as null where an empty legal set should encode as [].
	if got := SortedLegalIDs(map[int]*pb.PlayerAction{}); got == nil {
		t.Fatal("SortedLegalIDs returned nil for an empty legal set")
	}
}
