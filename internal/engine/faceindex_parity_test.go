package engine

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

// Mirrors internal/review/replay.go's faceIndex42FromTileID before consolidation.
func legacyReviewFace42(id uint32) int {
	suit, value := TileFromId(id)
	switch suit {
	case pb.Suit_SUIT_MAN:
		return int(value - 1)
	case pb.Suit_SUIT_PIN:
		return 9 + int(value-1)
	case pb.Suit_SUIT_SOU:
		return 18 + int(value-1)
	case pb.Suit_SUIT_JIHAI:
		return 27 + int(value-1)
	case pb.Suit_SUIT_FLOWER:
		return 34 + int(value-1)
	default:
		return -1
	}
}

func TestFaceIndex42FromIDMatchesLegacyReview(t *testing.T) {
	for id := uint32(0); id < 144; id++ {
		want := legacyReviewFace42(id)
		got, ok := FaceIndex42FromID(id)
		if !ok {
			if want != -1 {
				t.Fatalf("id %d: new returned !ok, legacy returned %d", id, want)
			}
			continue
		}
		if got != want {
			t.Fatalf("id %d: new = %d, legacy = %d", id, got, want)
		}
	}
}

func TestFaceIndex34RejectsFlowers(t *testing.T) {
	for value := uint32(1); value <= 8; value++ {
		if _, ok := FaceIndex34(&pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: value}); ok {
			t.Fatalf("flower %d should not have a 34-face index", value)
		}
	}
	for value := uint32(1); value <= 9; value++ {
		got, ok := FaceIndex34(&pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: value})
		if !ok || got != int(value-1) {
			t.Fatalf("man %d: got %d ok=%v", value, got, ok)
		}
	}
}
