// Package tiles holds the canonical tile encodings shared across the engine:
// the per-tile-type key (suit*100+value, ignoring tile id), the 0-33
// standard-tile index used by the shanten/scoring code, and lightweight
// deep-clone helpers for proto Tile/PlayerAction values used on the bot and
// RL hot paths. It imports only the proto package so every other package may
// depend on it without import cycles.
package tiles

import pb "github.com/plasma/fh-mahjong/proto"

// KeyOf returns the canonical per-tile-type key, suit*100+value. It uniquely
// identifies a tile face (ignoring the physical tile id) and matches the
// hashing used by the shanten, scoring and bot code.
func KeyOf(suit pb.Suit, value uint32) uint32 {
	return uint32(suit)*100 + value
}

// Key returns KeyOf(t.Suit, t.Value); a nil tile yields 0.
func Key(t *pb.Tile) uint32 {
	if t == nil {
		return 0
	}
	return KeyOf(t.Suit, t.Value)
}

// Index34Of maps a standard man/pin/sou/jihai tile to its 0-33 index, or -1
// for flowers, unknown suits, and out-of-range values (value < 1, or above the
// suit's maximum: 9 for man/pin/sou, 7 for jihai). The range guards keep a bad
// value from silently colliding with another suit's index band.
func Index34Of(suit pb.Suit, value uint32) int {
	if value < 1 {
		return -1
	}
	v := int(value) - 1
	switch suit {
	case pb.Suit_SUIT_MAN:
		if value <= 9 {
			return v
		}
	case pb.Suit_SUIT_PIN:
		if value <= 9 {
			return 9 + v
		}
	case pb.Suit_SUIT_SOU:
		if value <= 9 {
			return 18 + v
		}
	case pb.Suit_SUIT_JIHAI:
		if value <= 7 {
			return 27 + v
		}
	}
	return -1
}

// Index34 returns Index34Of(t.Suit, t.Value); a nil tile yields -1.
func Index34(t *pb.Tile) int {
	if t == nil {
		return -1
	}
	return Index34Of(t.Suit, t.Value)
}

// FromIndex34 is the inverse of Index34Of for indices 0-33; any index outside
// that range yields (SUIT_UNKNOWN, 0).
func FromIndex34(idx int) (pb.Suit, uint32) {
	switch {
	case idx < 0 || idx >= 34:
		return pb.Suit_SUIT_UNKNOWN, 0
	case idx < 9:
		return pb.Suit_SUIT_MAN, uint32(idx + 1)
	case idx < 18:
		return pb.Suit_SUIT_PIN, uint32(idx - 9 + 1)
	case idx < 27:
		return pb.Suit_SUIT_SOU, uint32(idx - 18 + 1)
	default:
		return pb.Suit_SUIT_JIHAI, uint32(idx - 27 + 1)
	}
}

// WildSet builds a face-key lookup (see KeyOf) for a round's wild tiles.
// Nil tiles are skipped; a nil or empty slice yields an empty, non-nil map.
func WildSet(wilds []*pb.Tile) map[uint32]bool {
	set := make(map[uint32]bool, len(wilds))
	for _, w := range wilds {
		if w == nil {
			continue
		}
		set[KeyOf(w.Suit, w.Value)] = true
	}
	return set
}

// CountWilds returns how many tiles in hand match the wild set by face.
func CountWilds(hand []*pb.Tile, wildSet map[uint32]bool) int {
	count := 0
	for _, t := range hand {
		if t != nil && wildSet[KeyOf(t.Suit, t.Value)] {
			count++
		}
	}
	return count
}

// CloneTile returns a deep copy of t (id/suit/value); nil yields nil.
//
// Fields are enumerated by hand rather than using proto.Clone because this
// package may import only the project's proto bindings (not the protobuf
// runtime), per the package's import constraint. Keep the field list in sync
// with the Tile message in proto/game.proto when it changes.
func CloneTile(t *pb.Tile) *pb.Tile {
	if t == nil {
		return nil
	}
	return &pb.Tile{Id: t.Id, Suit: t.Suit, Value: t.Value}
}

// CloneAction returns a deep copy of a, including its Tile and MeldTiles;
// nil yields nil. Like CloneTile, the scalar fields are enumerated by hand
// (proto.Clone is unavailable here) — keep them in sync with the PlayerAction
// message in proto/game.proto.
func CloneAction(a *pb.PlayerAction) *pb.PlayerAction {
	if a == nil {
		return nil
	}
	out := &pb.PlayerAction{
		Type:           a.Type,
		Tile:           CloneTile(a.Tile),
		TargetPlayer:   a.TargetPlayer,
		IsRobbingKong:  a.IsRobbingKong,
		IsBottomTile:   a.IsBottomTile,
		IsBloomingKong: a.IsBloomingKong,
	}
	if len(a.MeldTiles) > 0 {
		out.MeldTiles = make([]*pb.Tile, len(a.MeldTiles))
		for i, tile := range a.MeldTiles {
			out.MeldTiles[i] = CloneTile(tile)
		}
	}
	return out
}
