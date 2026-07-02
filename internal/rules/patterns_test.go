package rules

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestPatternRegistry(t *testing.T) {
	t.Run("every reward id has a display name", func(t *testing.T) {
		for id := range rewardPatternIds {
			if _, ok := patternDisplayNames[id]; !ok {
				t.Errorf("reward pattern %q missing from patternDisplayNames", id)
			}
		}
	})

	t.Run("NewScoreEntry carries id and display name", func(t *testing.T) {
		e := NewScoreEntry(PatternPureOneSuit, 150)
		if e.PatternId != PatternPureOneSuit || e.PatternName != "Pure One Suit (清一色)" || e.Points != 150 {
			t.Errorf("unexpected entry: %+v", e)
		}
	})

	t.Run("unknown id falls back to the id, not blank", func(t *testing.T) {
		e := NewScoreEntry("not_a_pattern", 1)
		if e.PatternName != "not_a_pattern" {
			t.Errorf("want fallback to id, got %q", e.PatternName)
		}
	})

	t.Run("live evaluation stamps ids on every entry", func(t *testing.T) {
		// Simple pure-one-suit standard hand: 111m 234m 345m 678m 99m + 9m.
		r := &FenghuaRuleset{}
		mk := func(id, v uint32) *pb.Tile {
			return &pb.Tile{Id: id, Suit: pb.Suit_SUIT_MAN, Value: v}
		}
		hand := []*pb.Tile{
			mk(1, 1), mk(2, 1), mk(3, 1),
			mk(4, 2), mk(5, 3), mk(6, 4),
			mk(7, 3), mk(8, 4), mk(9, 5),
			mk(10, 6), mk(11, 7), mk(12, 8),
			mk(13, 9),
		}
		winTile := mk(14, 9)
		_, entries, ok := r.EvaluateHand(hand, nil, winTile, nil, 0, false)
		if !ok {
			t.Fatalf("expected winning hand")
		}
		for _, e := range entries {
			if e.PatternId == "" {
				t.Errorf("entry %q has no pattern id", e.PatternName)
			}
			if want, known := patternDisplayNames[e.PatternId]; known && e.PatternName != want {
				t.Errorf("entry id %q: name %q does not match registry %q", e.PatternId, e.PatternName, want)
			}
		}
	})
}
