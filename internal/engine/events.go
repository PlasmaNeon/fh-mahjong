package engine

import (
	pb "github.com/plasma/fh-mahjong/proto"
)

// PublicEventType enumerates the public event vocabulary rendered into RL
// observations. Values are wire-stable: they are bit-packed into uint32s
// shared with Python (ai/src/fh_mahjong_ai/events.py) — never renumber.
type PublicEventType uint8

const (
	EventDraw       PublicEventType = 0
	EventDiscard    PublicEventType = 1
	EventChii       PublicEventType = 2
	EventPon        PublicEventType = 3
	EventKanOpen    PublicEventType = 4
	EventKanClosed  PublicEventType = 5
	EventKanUpgrade PublicEventType = 6
	EventFlower     PublicEventType = 7
)

const (
	EventFlagTsumogiri uint8 = 1 << 0
	EventFlagHaitei    uint8 = 1 << 1
)

// PublicEvent is one entry of the per-round public event log. The engine
// stores TRUE faces (own draws included); information legality (masking
// opponents' draw faces) is enforced at observation-encode time, not here.
type PublicEvent struct {
	Type     PublicEventType
	Seat     uint32 // absolute seat; made observer-relative at encode time
	Face     int16  // FaceIndex42 index, -1 = none (e.g. a draw whose face is not public)
	FromSeat int32  // absolute discarder for CHII/PON/KAN_OPEN; -1 otherwise
	Flags    uint8
}

// FaceIndex42 maps a tile to the 42-face index used across the RL stack
// (man 0-8, pin 9-17, sou 18-26, jihai 27-33, flower 34-41).
func FaceIndex42(tile *pb.Tile) (int, bool) {
	if tile == nil {
		return 0, false
	}
	switch tile.Suit {
	case pb.Suit_SUIT_MAN:
		if tile.Value >= 1 && tile.Value <= 9 {
			return int(tile.Value - 1), true
		}
	case pb.Suit_SUIT_PIN:
		if tile.Value >= 1 && tile.Value <= 9 {
			return 9 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_SOU:
		if tile.Value >= 1 && tile.Value <= 9 {
			return 18 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_JIHAI:
		if tile.Value >= 1 && tile.Value <= 7 {
			return 27 + int(tile.Value-1), true
		}
	case pb.Suit_SUIT_FLOWER:
		if tile.Value >= 1 && tile.Value <= 8 {
			return 34 + int(tile.Value-1), true
		}
	}
	return 0, false
}

func faceOf(tile *pb.Tile) int16 {
	if idx, ok := FaceIndex42(tile); ok {
		return int16(idx)
	}
	return -1
}

// logEvent appends to the current round's public event log. Unlike the paipu
// Recorder this is ALWAYS on — RL envs never attach a recorder but do need
// the public record.
func (g *Game) logEvent(event PublicEvent) {
	g.publicEvents = append(g.publicEvents, event)
}

// resetRoundEvents truncates the log at round start (round context lives in
// the observation scalars; history is per-round by design).
func (g *Game) resetRoundEvents() {
	g.publicEvents = g.publicEvents[:0]
}

// PublicEvents returns the current round's public event log, oldest first.
// Callers must treat it as read-only.
func (g *Game) PublicEvents() []PublicEvent {
	return g.publicEvents
}
