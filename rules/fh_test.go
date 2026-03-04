package rules_test

import (
	"testing"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules"
)

// --- Utility Functions ---

// wildState creates a GameState with the given tile designated as the wild tile type.
func wildState(suit pb.Suit, value uint32) *pb.GameState {
	return &pb.GameState{
		WildTiles: []*pb.Tile{{Suit: suit, Value: value}},
	}
}

// --- Non-Scoring Tests ---

func TestHometownRuleset_InitialWall(t *testing.T) {
	r := &rules.HometownRuleset{}
	wall := r.GetInitialWall()
	// 3 suits * 9 values * 4 tiles = 108, 7 jihai * 4 tiles = 28 → Total = 136
	if len(wall) != 136 {
		t.Errorf("Expected wall size 136, got %d", len(wall))
	}
}

func TestHometownRuleset_Priority(t *testing.T) {
	r := &rules.HometownRuleset{}
	actions := map[uint32]*pb.PlayerAction{
		1: {Type: pb.ActionType_ACTION_CHII},
		2: {Type: pb.ActionType_ACTION_RON},
	}
	winner, action := r.ResolveInterruptPriority(actions)
	if winner != 2 {
		t.Errorf("Expected Ron to win (seat 2), got seat %d", winner)
	}
	if action == nil || action.Type != pb.ActionType_ACTION_RON {
		t.Errorf("Expected RON action to win")
	}
}

// --- Variant: Common Win (朋胡) ---
// Standard 4 melds + 1 pair, no special patterns.
// Scoring: Base(1) + WildBonus + Common(1) + [Tsumo(1)] + [SingleWait(1)]
func TestHometownRuleset_CommonWin(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: chii(2s3s4s), chii(4p5p6p), chii(7m8m9m), pon(2z), pair(3z)
	// 3 suits + jihai → not pure/mixed one suit; has chii → not all pon.
	// Win tile 3z is a single wait (单吊).
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 4},    // 4s
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},    // 5p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},    // 6p
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},    // 7m
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},    // 8m
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},    // 9m
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z (South)
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 3}, // 3z (West) — single wait tile
		}
		// Wild = 9s (not naturally in hand). Replace pon members to inject wild tiles.
		if wilds >= 1 {
			hand[10] = &pb.Tile{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 2z
		}
		if wilds >= 2 {
			hand[11] = &pb.Tile{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 2z
		}
		if wilds >= 3 {
			hand[9] = &pb.Tile{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 2z
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 3} // 3z
	ws := wildState(pb.Suit_SUIT_SOU, 9)                            // wild = 9s

	t.Run("0 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+SingleWait(1) = 5
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("0 Wilds / Ron fails minimum", func(t *testing.T) {
		// Base(1)+NoWild(1)+Common(1)+SingleWait(1) = 4 → achieves 4-pt Ron minimum now!
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 4 {
			t.Errorf("want 4, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+1Wild(1)+Common(1)+SingleWait(1) = 5
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+Common(1)+SingleWait(1) = 6
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 6 {
			t.Errorf("want 6, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+Common(1)+SingleWait(1) = 154
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 155 {
			t.Errorf("want 155, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Independence (大大胡) ---
// 14 unique disconnected tiles. No pairs, no melds.
// Scoring: Base(1) + WildBonus + Independence(50) + [Tsumo(1)]
func TestHometownRuleset_Independence(t *testing.T) {
	r := &rules.HometownRuleset{}

	// 1s4s7s, 2p5p8p, 3m6m9m, 1z2z3z4z + winTile=5z(Haku/白)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 4},    // 4s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 7},    // 7s
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 2},    // 2p
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},    // 5p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 8},    // 8p
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 3},    // 3m
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 6},    // 6m
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},    // 9m
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z (East)
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z (South)
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 3}, // 3z (West)
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 4}, // 4z (North)
		}
		// Wild = 9p (not in hand). Wild tiles fill any missing unique slot.
		if wilds >= 1 {
			hand[0] = &pb.Tile{Id: 1, Suit: pb.Suit_SUIT_PIN, Value: 9} // replace 1s
		}
		if wilds >= 2 {
			hand[1] = &pb.Tile{Id: 2, Suit: pb.Suit_SUIT_PIN, Value: 9} // replace 4s
		}
		if wilds >= 3 {
			hand[2] = &pb.Tile{Id: 3, Suit: pb.Suit_SUIT_PIN, Value: 9} // replace 7s
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 5} // 5z (Haku/白)
	ws := wildState(pb.Suit_SUIT_PIN, 9)                            // wild = 9p

	t.Run("0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+Independence(50) = 52
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 52 {
			t.Errorf("want 52, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+Independence(50) = 52
		// Note: Tame wild does NOT apply because 9p (wild face value) is adjacent to 8p in the hand
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 52 {
			t.Errorf("want 52, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Ron", func(t *testing.T) {
		// Base(1)+2Wilds(2)+Independence(50) = 53
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, false)
		if !ok || s != 53 {
			t.Errorf("want 53, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// 3 wilds in an Independence hand also form valid Seven Pairs (jokers pair the singles)
		// Base(1)+Tsumo(1)+3Wilds(150)+StraightSevenPairs(150) = 302
		// (SevenPairs > Independence, so the engine picks SevenPairs)
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 302 {
			t.Errorf("want 302, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Straight Seven Pairs (七对头 - 无搭) ---
// 7 pairs, no wild tiles → 150 points.
// With wild tiles → Wild Seven Pairs, 50 points.
func TestHometownRuleset_SevenPairs(t *testing.T) {
	r := &rules.HometownRuleset{}

	// 7 pairs: 1s1s, 2s2s, 3p3p, 4p4p, 5m5m, 6m6m, 1z(+winTile 1z)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 3},    // 3p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 3},    // 3p
			{Id: 7, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
			{Id: 8, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 5},    // 5m
			{Id: 10, Suit: pb.Suit_SUIT_MAN, Value: 5},   // 5m
			{Id: 11, Suit: pb.Suit_SUIT_MAN, Value: 6},   // 6m
			{Id: 12, Suit: pb.Suit_SUIT_MAN, Value: 6},   // 6m
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z (East) — single wait
		}
		// Wild = 9s (not in hand, avoids dragon pon interference).
		if wilds >= 1 {
			hand[1] = &pb.Tile{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 1s
		}
		if wilds >= 2 {
			hand[3] = &pb.Tile{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 2s
		}
		if wilds >= 3 {
			hand[5] = &pb.Tile{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 3p
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 1} // 1z (East)
	ws := wildState(pb.Suit_SUIT_SOU, 9)                            // wild = 9s

	t.Run("Straight / 0 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+StraightSevenPairs(150) = 153
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, true)
		if !ok || s != 153 {
			t.Errorf("want 153, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+WildSevenPairs(50) = 52
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 52 {
			t.Errorf("want 52, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 2 Wilds / Ron", func(t *testing.T) {
		// Base(1)+2Wilds(2)+WildSevenPairs(50) = 53
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, false)
		if !ok || s != 53 {
			t.Errorf("want 53, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+WildSevenPairs(50) = 202
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 202 {
			t.Errorf("want 202, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Closed Bomb (暗炸) ---
// Seven Pairs containing 4 identical tiles (a "bomb"). Closed = Tsumo (not claimed).
func TestHometownRuleset_ClosedBomb(t *testing.T) {
	r := &rules.HometownRuleset{}

	// 4x1s (bomb), 2p2p, 3p3p, 5p5p, 6p6p, 4p + win4p
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},  // 1s — bomb (×4)
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},  // 1s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1},  // 1s
			{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 1},  // 1s
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 2},  // 2p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 2},  // 2p
			{Id: 7, Suit: pb.Suit_SUIT_PIN, Value: 3},  // 3p
			{Id: 8, Suit: pb.Suit_SUIT_PIN, Value: 3},  // 3p
			{Id: 9, Suit: pb.Suit_SUIT_PIN, Value: 5},  // 5p
			{Id: 10, Suit: pb.Suit_SUIT_PIN, Value: 5}, // 5p
			{Id: 11, Suit: pb.Suit_SUIT_PIN, Value: 6}, // 6p
			{Id: 12, Suit: pb.Suit_SUIT_PIN, Value: 6}, // 6p
			{Id: 13, Suit: pb.Suit_SUIT_PIN, Value: 4}, // 4p — single wait
		}
		// Wild = 1m (not in hand).
		if wilds >= 1 {
			hand[4] = &pb.Tile{Id: 5, Suit: pb.Suit_SUIT_MAN, Value: 1} // replace 2p
		}
		if wilds >= 2 {
			hand[6] = &pb.Tile{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 1} // replace 3p
		}
		if wilds >= 3 {
			hand[8] = &pb.Tile{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 1} // replace 5p
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_PIN, Value: 4} // 4p
	ws := wildState(pb.Suit_SUIT_MAN, 1)                          // wild = 1m

	t.Run("Straight / 0 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+StraightSevenPairs(150)+ClosedBomb(100) = 253
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, true)
		if !ok || s != 253 {
			t.Errorf("want 253, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 1 Wild / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+1Wild(1)+WildSevenPairs(50)+ClosedBomb(100) = 153
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, true)
		if !ok || s != 153 {
			t.Errorf("want 153, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+WildSevenPairs(50)+ClosedBomb(100) = 154
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 154 {
			t.Errorf("want 154, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+WildSevenPairs(50)+ClosedBomb(100) = 302
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 302 {
			t.Errorf("want 302, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Straight Loner (大吊车) ---
// 4 open melds + 1 tile in hand, winning tile completes pair (single wait).
func TestHometownRuleset_Loner(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Open melds: chii(1p2p3p), chii(4p5p6p), chii(7p8p9p), pon(1m1m1m)
	openMelds := []*pb.Meld{
		{Type: pb.ActionType_ACTION_CHII, Tiles: []*pb.Tile{{Suit: pb.Suit_SUIT_PIN, Value: 1}, {Suit: pb.Suit_SUIT_PIN, Value: 2}, {Suit: pb.Suit_SUIT_PIN, Value: 3}}},
		{Type: pb.ActionType_ACTION_CHII, Tiles: []*pb.Tile{{Suit: pb.Suit_SUIT_PIN, Value: 4}, {Suit: pb.Suit_SUIT_PIN, Value: 5}, {Suit: pb.Suit_SUIT_PIN, Value: 6}}},
		{Type: pb.ActionType_ACTION_CHII, Tiles: []*pb.Tile{{Suit: pb.Suit_SUIT_PIN, Value: 7}, {Suit: pb.Suit_SUIT_PIN, Value: 8}, {Suit: pb.Suit_SUIT_PIN, Value: 9}}},
		{Type: pb.ActionType_ACTION_PON, Tiles: []*pb.Tile{{Suit: pb.Suit_SUIT_MAN, Value: 1}, {Suit: pb.Suit_SUIT_MAN, Value: 1}, {Suit: pb.Suit_SUIT_MAN, Value: 1}}},
	}

	// Closed hand is 1 tile. Wild = 7z (Chun/中).
	mkHand := func(wilds int) []*pb.Tile {
		if wilds >= 1 {
			return []*pb.Tile{{Id: 1, Suit: pb.Suit_SUIT_JIHAI, Value: 7}} // 7z (wild)
		}
		return []*pb.Tile{{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 5}} // 5s
	}
	mkWin := func(wilds int) *pb.Tile {
		if wilds >= 1 {
			return &pb.Tile{Id: 2, Suit: pb.Suit_SUIT_JIHAI, Value: 7} // 7z (wild pair)
		}
		return &pb.Tile{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 5} // 5s
	}
	ws := wildState(pb.Suit_SUIT_JIHAI, 7) // wild = 7z

	t.Run("Straight / 0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+Common(1)+StraightLoner(100) = 103
		s, _, ok := r.EvaluateHand(mkHand(0), openMelds, mkWin(0), nil, 0, false)
		if !ok || s != 103 {
			t.Errorf("want 103, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 1 Wild / Ron", func(t *testing.T) {
		// With 1 wild (the closed tile is wild, winTile is also wild → 2 wilds in fullHand)
		// Base(1)+2Wilds(2)+Common(1)+WildLoner(50) = 54
		s, _, ok := r.EvaluateHand(mkHand(1), openMelds, mkWin(1), ws, 0, false)
		if !ok || s != 55 {
			t.Errorf("want 55, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: All Pon (大对对) ---
// 4 pon/kan + 1 pair, no chii. Straight (no wild) = 100, Wild = 50.
// Win tile 2z is a single wait (单吊).
func TestHometownRuleset_AllPung(t *testing.T) {
	r := &rules.HometownRuleset{}

	// pon(1s), pon(2p), pon(3m), pon(1z), pair(2z)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 2},    // 2p
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 2},    // 2p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 2},    // 2p
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 3},    // 3m
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 3},    // 3m
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 3},    // 3m
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z (East)
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z (South) — single wait
		}
		// Wild = 9s
		if wilds >= 1 {
			hand[2] = &pb.Tile{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 1s
		}
		if wilds >= 2 {
			hand[5] = &pb.Tile{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 2p
		}
		if wilds >= 3 {
			hand[8] = &pb.Tile{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 9} // replace 3m
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 2} // 2z (South)
	ws := wildState(pb.Suit_SUIT_SOU, 9)                            // wild = 9s

	t.Run("Straight / 0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+StraightAllPung(100)+SingleWait(1) = 103
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 103 {
			t.Errorf("want 103, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+WildAllPung(50)+SingleWait(1) = 53
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 53 {
			t.Errorf("want 53, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+WildAllPung(50) = 54
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 55 {
			t.Errorf("want 55, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Wild / 3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+WildAllPung(50) = 202
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 203 {
			t.Errorf("want 203, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Mixed One Suit (混一色) ---
// All tiles from one numbered suit (sou) + jihai. 70 points.
// Win tile 5z is a single wait (单吊).
func TestHometownRuleset_MixedOneSuit(t *testing.T) {
	r := &rules.HometownRuleset{}

	// pon(1s), pon(2s), pon(3s), chii(7s8s9s), pair(5z)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 7, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 8, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 7},   // 7s
			{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 8},   // 8s
			{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 9},   // 9s
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 5}, // 5z (Haku/白) — single wait
		}
		// Wild = 9m (different suit; wild tile is transparent to mixed-suit check)
		if wilds >= 1 {
			hand[2] = &pb.Tile{Id: 3, Suit: pb.Suit_SUIT_MAN, Value: 9} // replace 1s
		}
		if wilds >= 2 {
			hand[5] = &pb.Tile{Id: 6, Suit: pb.Suit_SUIT_MAN, Value: 9} // replace 2s
		}
		if wilds >= 3 {
			hand[8] = &pb.Tile{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9} // replace 3s
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 5} // 5z (Haku/白)
	ws := wildState(pb.Suit_SUIT_MAN, 9)                            // wild = 9m

	t.Run("0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+MixedOneSuit(70)+SingleWait(1) = 73
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 73 {
			t.Errorf("want 73, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+MixedOneSuit(70)+SingleWait(1) = 73
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 73 {
			t.Errorf("want 73, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+MixedOneSuit(70)+SingleWait(1) = 75
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 75 {
			t.Errorf("want 75, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Hand is all pongs with jokers completing pongs → also triggers WildAllPung(50)
		// Base(1)+Tsumo(1)+3Wilds(150)+WildAllPung(50)+MixedOneSuit(70) = 272
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 273 {
			t.Errorf("want 273, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Pure One Suit (清一色) ---
// All tiles from exactly one numbered suit (no jihai). 150 points.
// Hand: chii(1s2s3s), chii(4s5s6s), chii(7s8s9s), pon(1s), pair(5s).
// Win tile 5s completes a gap wait (嵌): hand has 4s6s waiting for 5s.
func TestHometownRuleset_PureOneSuit(t *testing.T) {
	r := &rules.HometownRuleset{}

	// chii(1s2s3s), chii(4s5s6s), chii(7s8s9s), pon(1s), pair(5s)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},  // 1s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 2},  // 2s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 3},  // 3s
			{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 4},  // 4s
			{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 5},  // 5s
			{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 6},  // 6s
			{Id: 7, Suit: pb.Suit_SUIT_SOU, Value: 7},  // 7s
			{Id: 8, Suit: pb.Suit_SUIT_SOU, Value: 8},  // 8s
			{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 9},  // 9s
			{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 1}, // 1s
			{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 1}, // 1s
			{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 1}, // 1s
			{Id: 13, Suit: pb.Suit_SUIT_SOU, Value: 5}, // 5s — gap wait (4s6s waiting for 5s)
		}
		// Wild = 1p (different suit; wild tile is transparent to pure-suit check)
		if wilds >= 1 {
			hand[1] = &pb.Tile{Id: 2, Suit: pb.Suit_SUIT_PIN, Value: 1} // replace 2s
		}
		if wilds >= 2 {
			hand[4] = &pb.Tile{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 1} // replace 5s
		}
		if wilds >= 3 {
			hand[7] = &pb.Tile{Id: 8, Suit: pb.Suit_SUIT_PIN, Value: 1} // replace 8s
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_SOU, Value: 5} // 5s (gap wait)
	ws := wildState(pb.Suit_SUIT_PIN, 1)                          // wild = 1p

	t.Run("0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+PureOneSuit(150)+GapWait(1) = 153
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 153 {
			t.Errorf("want 153, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+PureOneSuit(150)+GapWait(1) = 153
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 153 {
			t.Errorf("want 153, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+PureOneSuit(150)+GapWait(1) = 155
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 155 {
			t.Errorf("want 155, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+PureOneSuit(150)+GapWait(1) = 303
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 303 {
			t.Errorf("want 303, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Completed All Jihai (清老头) ---
// All tiles are jihai + forms valid standard hand (all pon). 800 points.
// Win tile 5z is a single wait (单吊).
func TestHometownRuleset_CompletedAllHonors(t *testing.T) {
	r := &rules.HometownRuleset{}

	// pon(1z), pon(2z), pon(3z), pon(4z), pair(5z)
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z (East)
			{Id: 2, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z
			{Id: 3, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z
			{Id: 4, Suit: pb.Suit_SUIT_JIHAI, Value: 2},  // 2z (South)
			{Id: 5, Suit: pb.Suit_SUIT_JIHAI, Value: 2},  // 2z
			{Id: 6, Suit: pb.Suit_SUIT_JIHAI, Value: 2},  // 2z
			{Id: 7, Suit: pb.Suit_SUIT_JIHAI, Value: 3},  // 3z (West)
			{Id: 8, Suit: pb.Suit_SUIT_JIHAI, Value: 3},  // 3z
			{Id: 9, Suit: pb.Suit_SUIT_JIHAI, Value: 3},  // 3z
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 4}, // 4z (North)
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 4}, // 4z
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 4}, // 4z
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 5}, // 5z (Haku/白) — single wait
		}
		// Wild = 1s (non-jihai; wild tile is transparent to all-jihai check)
		if wilds >= 1 {
			hand[2] = &pb.Tile{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1} // replace 1z
		}
		if wilds >= 2 {
			hand[5] = &pb.Tile{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 1} // replace 2z
		}
		if wilds >= 3 {
			hand[8] = &pb.Tile{Id: 9, Suit: pb.Suit_SUIT_SOU, Value: 1} // replace 3z
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 5} // 5z (Haku/白)
	ws := wildState(pb.Suit_SUIT_SOU, 1)                            // wild = 1s

	t.Run("0 Wilds / Ron", func(t *testing.T) {
		// Base(1)+NoWild(1)+AllPung(100)+CompletedAllHonors(800)+SingleWait(1) = 903
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, false)
		if !ok || s != 903 {
			t.Errorf("want 903, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Ron", func(t *testing.T) {
		// Base(1)+1Wild(1)+WildAllPung(50)+CompletedAllHonors(800)+SingleWait(1) = 853
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, false)
		if !ok || s != 853 {
			t.Errorf("want 853, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+WildAllPung(50)+CompletedAllHonors(800) = 854
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 855 {
			t.Errorf("want 855, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+WildAllPung(50)+CompletedAllHonors(800) = 1002
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 1003 {
			t.Errorf("want 1003, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Flower Bonus (4 Flowers = 150 pts) ---
func TestHometownRuleset_FlowerBonus(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: chii(2s3s4s), chii(4p5p6p), chii(7m8m9m), pon(1z), single(4z)
	// Wild = 9s
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 4},    // 4s
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},    // 5p
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},    // 6p
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},    // 7m
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},    // 8m
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},    // 9m
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 4}, // 4z (single wait)
		}
		if wilds >= 1 {
			hand[10] = &pb.Tile{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 1z
		}
		if wilds >= 2 {
			hand[11] = &pb.Tile{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 1z
		}
		if wilds >= 3 {
			hand[9] = &pb.Tile{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 1z
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 4}
	ws := wildState(pb.Suit_SUIT_SOU, 9)
	flowerState := func(base *pb.GameState) *pb.GameState {
		if base == nil {
			base = &pb.GameState{}
		}
		base.Players = []*pb.PlayerState{
			{FlowerMelds: []*pb.Tile{{}, {}, {}, {}}}, // 4 flowers
		}
		return base
	}

	t.Run("0 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+4Flowers(150)+SingleWait(1) = 155
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, flowerState(nil), 0, true)
		if !ok || s != 155 {
			t.Errorf("want 155, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+1Wild(1)+Common(1)+4Flowers(150)+SingleWait(1) = 155
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, flowerState(ws), 0, true)
		if !ok || s != 155 {
			t.Errorf("want 155, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+Common(1)+4Flowers(150)+SingleWait(1) = 156
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, flowerState(ws), 0, true)
		if !ok || s != 156 {
			t.Errorf("want 156, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+Common(1)+4Flowers(150)+SingleWait(1) = 304
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, flowerState(ws), 0, true)
		if !ok || s != 305 {
			t.Errorf("want 305, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Dragon Pung (中发白碰出) ---
// +1 for each dragon pon (5z=Hatsu/発, 6z=Chun/中, 7z=Haku/白).
func TestHometownRuleset_DragonPung(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: pon(5z/Hatsu), chii(1s2s3s), chii(4p5p6p), chii(7m8m9m), single(1z)
	// Wild = 9s
	mkHand := func(wilds int) []*pb.Tile {
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_JIHAI, Value: 5},  // 5z (Hatsu)
			{Id: 2, Suit: pb.Suit_SUIT_JIHAI, Value: 5},  // 5z
			{Id: 3, Suit: pb.Suit_SUIT_JIHAI, Value: 5},  // 5z
			{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
			{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
			{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
			{Id: 7, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
			{Id: 8, Suit: pb.Suit_SUIT_PIN, Value: 5},    // 5p
			{Id: 9, Suit: pb.Suit_SUIT_PIN, Value: 6},    // 6p
			{Id: 10, Suit: pb.Suit_SUIT_MAN, Value: 7},   // 7m
			{Id: 11, Suit: pb.Suit_SUIT_MAN, Value: 8},   // 8m
			{Id: 12, Suit: pb.Suit_SUIT_MAN, Value: 9},   // 9m
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // 1z (single wait)
		}
		// Wild = 9s. Replace non-chii-start tiles to keep DP solvable.
		if wilds >= 1 {
			hand[10] = &pb.Tile{Id: 11, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 8m
		}
		if wilds >= 2 {
			hand[11] = &pb.Tile{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 9m
		}
		if wilds >= 3 {
			hand[9] = &pb.Tile{Id: 10, Suit: pb.Suit_SUIT_SOU, Value: 9} // was 7m
		}
		return hand
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 1}
	ws := wildState(pb.Suit_SUIT_SOU, 9)

	t.Run("0 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+DragonPung(1)+SingleWait(1) = 6
		s, _, ok := r.EvaluateHand(mkHand(0), nil, winTile, nil, 0, true)
		if !ok || s != 6 {
			t.Errorf("want 6, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("1 Wild / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+1Wild(1)+Common(1)+DragonPung(1)+SingleWait(1) = 6
		s, _, ok := r.EvaluateHand(mkHand(1), nil, winTile, ws, 0, true)
		if !ok || s != 6 {
			t.Errorf("want 6, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("2 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+2Wilds(2)+Common(1)+DragonPung(1)+SingleWait(1) = 7
		s, _, ok := r.EvaluateHand(mkHand(2), nil, winTile, ws, 0, true)
		if !ok || s != 7 {
			t.Errorf("want 7, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("3 Wilds / Tsumo", func(t *testing.T) {
		// Base(1)+Tsumo(1)+3Wilds(150)+Common(1)+DragonPung(1)+SingleWait(1) = 155
		s, _, ok := r.EvaluateHand(mkHand(3), nil, winTile, ws, 0, true)
		if !ok || s != 156 {
			t.Errorf("want 156, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Wind Pung (位风/圈风/正风) ---
func TestHometownRuleset_WindPung(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: pon(East/1z), chii(1s2s3s), chii(4p5p6p), chii(7m8m9m), pair(2z)
	// Wait: 2z (pair call)
	hand := []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z (East pon)
		{Id: 2, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z
		{Id: 3, Suit: pb.Suit_SUIT_JIHAI, Value: 1},  // 1z
		{Id: 4, Suit: pb.Suit_SUIT_SOU, Value: 1},    // 1s
		{Id: 5, Suit: pb.Suit_SUIT_SOU, Value: 2},    // 2s
		{Id: 6, Suit: pb.Suit_SUIT_SOU, Value: 3},    // 3s
		{Id: 7, Suit: pb.Suit_SUIT_PIN, Value: 4},    // 4p
		{Id: 8, Suit: pb.Suit_SUIT_PIN, Value: 5},    // 5p
		{Id: 9, Suit: pb.Suit_SUIT_PIN, Value: 6},    // 6p
		{Id: 10, Suit: pb.Suit_SUIT_MAN, Value: 7},   // 7m
		{Id: 11, Suit: pb.Suit_SUIT_MAN, Value: 8},   // 8m
		{Id: 12, Suit: pb.Suit_SUIT_MAN, Value: 9},   // 9m
		{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // 2z (single wait)
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 2} // 2z

	t.Run("Seat Wind", func(t *testing.T) {
		// Seat=East(1), Prevailing=South(2). pon of 1z → SeatWind(+1)
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+SeatWind(1)+SingleWait(1) = 6
		state := &pb.GameState{
			PrevailingWind: 2,
			Players:        []*pb.PlayerState{{SeatWind: 1}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 6 {
			t.Errorf("want 6, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Prevailing Wind", func(t *testing.T) {
		// Seat=South(2), Prevailing=East(1). pon of 1z → PrevailingWind(+1)
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+PrevailingWind(1)+SingleWait(1) = 6
		state := &pb.GameState{
			PrevailingWind: 1,
			Players:        []*pb.PlayerState{{SeatWind: 2}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 6 {
			t.Errorf("want 6, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Right Wind", func(t *testing.T) {
		// Seat=East(1), Prevailing=East(1). pon of 1z → RightWind(+2)
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+RightWind(2)+SingleWait(1) = 7
		state := &pb.GameState{
			PrevailingWind: 1,
			Players:        []*pb.PlayerState{{SeatWind: 1}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 7 {
			t.Errorf("want 7, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Own Flower (花) +2 ---
func TestHometownRuleset_OwnFlower(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: chii(2s3s4s), chii(4p5p6p), chii(7m8m9m), pon(2z), single(3z)
	// Wait: 3z (single wait)
	hand := []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 2},
		{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 3},
		{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 4},
		{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
		{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},
		{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},
		{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
		{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},
		{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},
		{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 3},
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 3}

	t.Run("One Own Flower", func(t *testing.T) {
		// Player seat=0 (East, wind=1). One flower with Value=1 matches.
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+OwnFlower(2)+SingleWait(1) = 7
		state := &pb.GameState{
			Players: []*pb.PlayerState{{
				SeatWind:    1,
				FlowerMelds: []*pb.Tile{{Value: 1}},
			}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 7 {
			t.Errorf("want 7, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("No Own Flower", func(t *testing.T) {
		// Player seat=0 (East, wind=1). Flower Value=2 doesn't match.
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+SingleWait(1) = 5
		state := &pb.GameState{
			Players: []*pb.PlayerState{{
				SeatWind:    1,
				FlowerMelds: []*pb.Tile{{Value: 2}},
			}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Kong Bonuses ---
func TestHometownRuleset_KongBonuses(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Base hand: chii(2s3s4s), chii(4p5p6p), chii(7m8m9m), pon(2z), single(3z)
	// Wait: 3z (single wait)
	hand := []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 2},
		{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 3},
		{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 4},
		{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
		{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},
		{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},
		{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
		{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},
		{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},
		{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 3},
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 3}

	t.Run("Budding Direct Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BuddingDirectKong(50)+SingleWait(1) = 55
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBuddingDirectKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 55 {
			t.Errorf("want 55, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Blooming Direct Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BloomingDirectKong(100)+SingleWait(1) = 105
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBloomingDirectKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 105 {
			t.Errorf("want 105, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Budding Closed Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BuddingClosedKong(100)+SingleWait(1) = 105
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBuddingClosedKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 105 {
			t.Errorf("want 105, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Blooming Closed Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BloomingClosedKong(150)+SingleWait(1) = 155
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBloomingClosedKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 155 {
			t.Errorf("want 155, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Blooming Risky Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BloomingRiskyKong(200)+SingleWait(1) = 205
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBloomingRiskyKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 205 {
			t.Errorf("want 205, got %d (canWin=%v)", s, ok)
		}
	})
	t.Run("Blooming Flower Kong", func(t *testing.T) {
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+BloomingFlowerKong(50)+SingleWait(1) = 55
		state := &pb.GameState{
			Players: []*pb.PlayerState{{HasBloomingFlowerKong: true}},
		}
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 55 {
			t.Errorf("want 55, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Wait Patterns (边，嵌，单吊, 对倒) ---
// Extra +1 for specific wait patterns.
func TestHometownRuleset_WaitPatterns(t *testing.T) {
	r := &rules.HometownRuleset{}

	t.Run("Single Pair Wait (单吊)", func(t *testing.T) {
		// 13 tiles: chii(1s2s3s), chii(4p5p6p), chii(7m8m9m), pon(1z), single(2z).
		// Wait: 2z.
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 2},
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 3},
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 2}, // The single waiting for a pair
		}
		winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 2}
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+SingleWait(1) = 5
		s, _, ok := r.EvaluateHand(hand, nil, winTile, nil, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})

	t.Run("Gap Wait (嵌)", func(t *testing.T) {
		// 13 tiles: pon(1s), pon(4p), pon(7m), pair(1z), 4s, 6s.
		// Wait: 5s.
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 12, Suit: pb.Suit_SUIT_SOU, Value: 4},
			{Id: 13, Suit: pb.Suit_SUIT_SOU, Value: 6},
		}
		winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_SOU, Value: 5}
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+GapWait(1) = 5
		s, _, ok := r.EvaluateHand(hand, nil, winTile, nil, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})

	t.Run("Edge Wait (边)", func(t *testing.T) {
		// 13 tiles: pon(1s), pon(4p), pon(7m), pair(1z), 1p, 2p.
		// Wait: 3p (edge wait: 1,2 waiting for 3, or 8,9 waiting for 7).
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 12, Suit: pb.Suit_SUIT_PIN, Value: 1},
			{Id: 13, Suit: pb.Suit_SUIT_PIN, Value: 2},
		}
		winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_PIN, Value: 3}
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+EdgeWait(1) = 5
		s, _, ok := r.EvaluateHand(hand, nil, winTile, nil, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})

	t.Run("Pair Call (对倒)", func(t *testing.T) {
		// 13 tiles: chii(1s2s3s), chii(4p5p6p), chii(7m8m9m), pair(1z), pair(2z).
		// Wait: 1z or 2z (to complete the pon). Using 2z as winTile.
		hand := []*pb.Tile{
			{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},
			{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 2},
			{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 3},
			{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 4},
			{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},
			{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 6},
			{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 7},
			{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 8},
			{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},
			{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
			{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
			{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		}
		winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 2}
		// Base(1)+Tsumo(1)+NoWild(1)+Common(1)+PairCall(1) = 5
		s, _, ok := r.EvaluateHand(hand, nil, winTile, nil, 0, true)
		if !ok || s != 5 {
			t.Errorf("want 5, got %d (canWin=%v)", s, ok)
		}
	})
}

// --- Variant: Uncompleted Eight Flowers (八花直胡) ---
func TestHometownRuleset_UncompletedEightFlowers(t *testing.T) {
	r := &rules.HometownRuleset{}

	// Hand does NOT form a valid majhong hand (junk hand).
	// But player has 8 flowers.
	hand := []*pb.Tile{
		{Id: 1, Suit: pb.Suit_SUIT_SOU, Value: 1},
		{Id: 2, Suit: pb.Suit_SUIT_SOU, Value: 4},
		{Id: 3, Suit: pb.Suit_SUIT_SOU, Value: 7},
		{Id: 4, Suit: pb.Suit_SUIT_PIN, Value: 2},
		{Id: 5, Suit: pb.Suit_SUIT_PIN, Value: 5},
		{Id: 6, Suit: pb.Suit_SUIT_PIN, Value: 8},
		{Id: 7, Suit: pb.Suit_SUIT_MAN, Value: 3},
		{Id: 8, Suit: pb.Suit_SUIT_MAN, Value: 6},
		{Id: 9, Suit: pb.Suit_SUIT_MAN, Value: 9},
		{Id: 10, Suit: pb.Suit_SUIT_JIHAI, Value: 1},
		{Id: 11, Suit: pb.Suit_SUIT_JIHAI, Value: 1}, // pair
		{Id: 12, Suit: pb.Suit_SUIT_JIHAI, Value: 2},
		{Id: 13, Suit: pb.Suit_SUIT_JIHAI, Value: 3},
	}
	winTile := &pb.Tile{Id: 14, Suit: pb.Suit_SUIT_JIHAI, Value: 4}

	state := &pb.GameState{
		Players: []*pb.PlayerState{{
			FlowerMelds: []*pb.Tile{{}, {}, {}, {}, {}, {}, {}, {}}, // 8 flowers
		}},
	}

	t.Run("Junk Hand + 8 Flowers", func(t *testing.T) {
		// Valid win despite junk hand. Output: 400 pts
		s, _, ok := r.EvaluateHand(hand, nil, winTile, state, 0, true)
		if !ok || s != 400 {
			t.Errorf("want 400, got %d (canWin=%v)", s, ok)
		}
	})
}
