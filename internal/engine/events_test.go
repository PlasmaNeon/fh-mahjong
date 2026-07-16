package engine

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
)

func TestPublicEventLogAppendAndAccessor(t *testing.T) {
	g := &Game{State: &pb.GameState{}}
	g.logEvent(PublicEvent{Type: EventDraw, Seat: 1, Face: 5})
	g.logEvent(PublicEvent{Type: EventDiscard, Seat: 1, Face: 5, Flags: EventFlagTsumogiri})
	events := g.PublicEvents()
	if len(events) != 2 {
		t.Fatalf("want 2 events, got %d", len(events))
	}
	if events[0].Type != EventDraw || events[1].Type != EventDiscard {
		t.Fatalf("wrong order/types: %+v", events)
	}
	if events[1].Flags&EventFlagTsumogiri == 0 {
		t.Fatalf("tsumogiri flag lost")
	}
}

func TestPublicEventLogClearedByResetRoundEvents(t *testing.T) {
	g := &Game{State: &pb.GameState{}}
	g.logEvent(PublicEvent{Type: EventDraw, Seat: 0, Face: 3})
	g.resetRoundEvents()
	if len(g.PublicEvents()) != 0 {
		t.Fatalf("log not cleared at round start")
	}
}

func TestCloneCopiesEventLogByValue(t *testing.T) {
	g := NewGame("clone-events", nil, MatchOptions{})
	g.logEvent(PublicEvent{Type: EventPon, Seat: 2, Face: 10, FromSeat: 0})
	clone := g.CloneForBranch()
	clone.logEvent(PublicEvent{Type: EventDraw, Seat: 3, Face: -1})
	if len(g.PublicEvents()) != 1 {
		t.Fatalf("clone append leaked into parent: parent has %d events", len(g.PublicEvents()))
	}
	if len(clone.PublicEvents()) != 2 {
		t.Fatalf("clone missing inherited event: has %d", len(clone.PublicEvents()))
	}
	// Mutating the parent's backing array must not show in the clone.
	g.publicEvents[0].Face = 11
	if clone.PublicEvents()[0].Face != 10 {
		t.Fatalf("clone shares backing array with parent")
	}
}

func TestFaceIndex42Mapping(t *testing.T) {
	cases := []struct {
		tile *pb.Tile
		want int
		ok   bool
	}{
		{&pb.Tile{Suit: pb.Suit_SUIT_MAN, Value: 1}, 0, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_PIN, Value: 9}, 17, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_SOU, Value: 1}, 18, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_JIHAI, Value: 7}, 33, true},
		{&pb.Tile{Suit: pb.Suit_SUIT_FLOWER, Value: 8}, 41, true},
		{nil, 0, false},
	}
	for i, c := range cases {
		got, ok := FaceIndex42(c.tile)
		if ok != c.ok || (ok && got != c.want) {
			t.Fatalf("case %d: got (%d,%v) want (%d,%v)", i, got, ok, c.want, c.ok)
		}
	}
}
