package rl

import (
	"github.com/plasma/fh-mahjong/internal/engine"
)

// Packed public-event bit layout — the single source of truth, mirrored
// verbatim in ai/src/fh_mahjong_ai/events.py. Wire-stable: never reorder.
//
//	bits  0-3  event type (engine.PublicEventType)
//	bits  4-5  actor seat RELATIVE to observer (0=self,1=right,2=across,3=left)
//	bits  6-11 face index 0-41; 63 = unknown (masked opponent draw)
//	bits 12-13 from-seat RELATIVE to observer (calls only; 0 otherwise)
//	bit  14    tsumogiri flag
//	bit  15    haitei flag
//	bits 16-31 reserved, always zero
const (
	eventSeatShift    = 4
	eventFaceShift    = 6
	eventFromShift    = 12
	eventTsumogiriBit = 1 << 14
	eventHaiteiBit    = 1 << 15

	// EventFaceUnknown is the face sentinel for information-illegal faces
	// (an opponent's draw) and absent faces.
	EventFaceUnknown = 63
)

func relativeSeatTo(observer, seat uint32) uint32 {
	return (seat + 4 - observer) % 4
}

// packPublicEvent renders one engine event for one observer. Information
// legality lives HERE: a DRAW's face is visible only to the drawing seat.
func packPublicEvent(event engine.PublicEvent, observer uint32) uint32 {
	face := uint32(EventFaceUnknown)
	if event.Face >= 0 && int(event.Face) < 42 {
		face = uint32(event.Face)
	}
	if event.Type == engine.EventDraw && event.Seat != observer {
		face = EventFaceUnknown
	}

	packed := uint32(event.Type) & 0xF
	packed |= relativeSeatTo(observer, event.Seat) << eventSeatShift
	packed |= face << eventFaceShift
	if event.FromSeat >= 0 {
		packed |= relativeSeatTo(observer, uint32(event.FromSeat)) << eventFromShift
	}
	if event.Flags&engine.EventFlagTsumogiri != 0 {
		packed |= eventTsumogiriBit
	}
	if event.Flags&engine.EventFlagHaitei != 0 {
		packed |= eventHaiteiBit
	}
	return packed
}

// renderEventHistory packs the last `window` events, oldest first.
// window == 0 returns nil: the observation stays byte-identical to pre-B1.
func renderEventHistory(events []engine.PublicEvent, observer uint32, window uint32) []uint32 {
	if window == 0 || len(events) == 0 {
		return nil
	}
	start := 0
	if len(events) > int(window) {
		start = len(events) - int(window)
	}
	out := make([]uint32, 0, len(events)-start)
	for _, event := range events[start:] {
		out = append(out, packPublicEvent(event, observer))
	}
	return out
}
