package tiles

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func tile(suit pb.Suit, value uint32, id uint32) *pb.Tile {
	return &pb.Tile{Id: id, Suit: suit, Value: value}
}

func TestKey(t *testing.T) {
	if got := KeyOf(pb.Suit_SUIT_PIN, 5); got != uint32(pb.Suit_SUIT_PIN)*100+5 {
		t.Fatalf("KeyOf = %d", got)
	}
	if got := Key(tile(pb.Suit_SUIT_PIN, 5, 42)); got != KeyOf(pb.Suit_SUIT_PIN, 5) {
		t.Fatalf("Key ignores id mismatch: %d", got)
	}
	if got := Key(nil); got != 0 {
		t.Fatalf("Key(nil) = %d, want 0", got)
	}
}

func TestIndex34RoundTrip(t *testing.T) {
	cases := []struct {
		suit  pb.Suit
		value uint32
		idx   int
	}{
		{pb.Suit_SUIT_MAN, 1, 0},
		{pb.Suit_SUIT_MAN, 9, 8},
		{pb.Suit_SUIT_PIN, 1, 9},
		{pb.Suit_SUIT_SOU, 1, 18},
		{pb.Suit_SUIT_JIHAI, 1, 27},
		{pb.Suit_SUIT_JIHAI, 7, 33},
	}
	for _, c := range cases {
		if got := Index34Of(c.suit, c.value); got != c.idx {
			t.Fatalf("Index34Of(%v,%d) = %d, want %d", c.suit, c.value, got, c.idx)
		}
		gotSuit, gotValue := FromIndex34(c.idx)
		if gotSuit != c.suit || gotValue != c.value {
			t.Fatalf("FromIndex34(%d) = (%v,%d), want (%v,%d)", c.idx, gotSuit, gotValue, c.suit, c.value)
		}
	}
	if got := Index34(tile(pb.Suit_SUIT_FLOWER, 3, 137)); got != -1 {
		t.Fatalf("Index34(flower) = %d, want -1", got)
	}
	if got := Index34(nil); got != -1 {
		t.Fatalf("Index34(nil) = %d, want -1", got)
	}
}

func TestIndex34OfRejectsOutOfRange(t *testing.T) {
	cases := []struct {
		suit  pb.Suit
		value uint32
	}{
		{pb.Suit_SUIT_MAN, 0},   // below minimum (would underflow to -1)
		{pb.Suit_SUIT_PIN, 0},   // below minimum (would collide with MAN_9 = 8)
		{pb.Suit_SUIT_MAN, 10},  // above suit max (would collide with PIN_1 = 9)
		{pb.Suit_SUIT_JIHAI, 8}, // above jihai max (would be 34, off the board)
		{pb.Suit_SUIT_FLOWER, 3},
		{pb.Suit_SUIT_UNKNOWN, 1},
	}
	for _, c := range cases {
		if got := Index34Of(c.suit, c.value); got != -1 {
			t.Fatalf("Index34Of(%v,%d) = %d, want -1", c.suit, c.value, got)
		}
	}
}

func TestFromIndex34RejectsOutOfRange(t *testing.T) {
	for _, idx := range []int{-1, -100, 34, 99} {
		suit, value := FromIndex34(idx)
		if suit != pb.Suit_SUIT_UNKNOWN || value != 0 {
			t.Fatalf("FromIndex34(%d) = (%v,%d), want (SUIT_UNKNOWN,0)", idx, suit, value)
		}
	}
}

func TestCloneTile(t *testing.T) {
	src := tile(pb.Suit_SUIT_SOU, 4, 99)
	dst := CloneTile(src)
	if dst == src {
		t.Fatal("CloneTile returned same pointer")
	}
	if dst.Id != src.Id || dst.Suit != src.Suit || dst.Value != src.Value {
		t.Fatalf("CloneTile mismatch: %+v", dst)
	}
	if CloneTile(nil) != nil {
		t.Fatal("CloneTile(nil) != nil")
	}
}

func TestCloneActionDeepCopiesTiles(t *testing.T) {
	src := &pb.PlayerAction{
		Type:           pb.ActionType_ACTION_KAN,
		Tile:           tile(pb.Suit_SUIT_MAN, 2, 1),
		TargetPlayer:   3,
		IsRobbingKong:  true,
		IsBottomTile:   true,
		IsBloomingKong: true,
		MeldTiles:      []*pb.Tile{tile(pb.Suit_SUIT_MAN, 2, 2), tile(pb.Suit_SUIT_MAN, 2, 3)},
	}
	dst := CloneAction(src)
	if dst == src || dst.Tile == src.Tile || &dst.MeldTiles[0] == &src.MeldTiles[0] {
		t.Fatal("CloneAction shares memory with source")
	}
	dst.MeldTiles[0].Value = 9
	if src.MeldTiles[0].Value != 2 {
		t.Fatal("CloneAction mutated source meld tile")
	}
	if dst.Type != src.Type || dst.TargetPlayer != src.TargetPlayer ||
		!dst.IsRobbingKong || !dst.IsBottomTile || !dst.IsBloomingKong {
		t.Fatalf("CloneAction scalar mismatch: %+v", dst)
	}
	if CloneAction(nil) != nil {
		t.Fatal("CloneAction(nil) != nil")
	}
}

func TestWildSetAndCountWilds(t *testing.T) {
	wilds := []*pb.Tile{
		tile(pb.Suit_SUIT_MAN, 5, 0),
		tile(pb.Suit_SUIT_FLOWER, 6, 1),
		nil,
	}
	set := WildSet(wilds)
	if len(set) != 2 {
		t.Fatalf("WildSet size = %d, want 2 (nil skipped)", len(set))
	}
	if !set[KeyOf(pb.Suit_SUIT_MAN, 5)] || !set[KeyOf(pb.Suit_SUIT_FLOWER, 6)] {
		t.Fatal("WildSet missing expected faces")
	}
	if empty := WildSet(nil); empty == nil || len(empty) != 0 {
		t.Fatalf("WildSet(nil) = %v, want empty non-nil map", empty)
	}

	hand := []*pb.Tile{
		tile(pb.Suit_SUIT_MAN, 5, 10),    // wild
		tile(pb.Suit_SUIT_MAN, 5, 11),    // wild (same face, different id)
		tile(pb.Suit_SUIT_PIN, 5, 12),    // not wild (face key includes suit)
		tile(pb.Suit_SUIT_FLOWER, 6, 13), // wild flower
		nil,
	}
	if got := CountWilds(hand, set); got != 3 {
		t.Fatalf("CountWilds = %d, want 3", got)
	}
	if got := CountWilds(hand, WildSet(nil)); got != 0 {
		t.Fatalf("CountWilds with empty set = %d, want 0", got)
	}
}
