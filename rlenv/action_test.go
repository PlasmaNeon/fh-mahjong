package rlenv

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
