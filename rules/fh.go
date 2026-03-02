package rules

import (
	pb "github.com/plasma/fh-mahjong/proto"
)

// HometownRuleset implements the core.RuleEngine interface.
type HometownRuleset struct{}

func (r *HometownRuleset) Name() string {
	return "Hometown Custom Rules"
}

func (r *HometownRuleset) GetInitialWall() []*pb.Tile {
	var wall []*pb.Tile
	idCount := uint32(0)

	// Proto suit constants map to display names: SUIT_SOU=sou(s), SUIT_MAN=man(m), SUIT_PIN=pin(p), SUIT_JIHAI=jihai(z)
	suits := []pb.Suit{pb.Suit_SUIT_SOU, pb.Suit_SUIT_MAN, pb.Suit_SUIT_PIN}

	// Add 4 of each tile 1-9 for the 3 main suits
	for _, suit := range suits {
		for v := uint32(1); v <= 9; v++ {
			for i := 0; i < 4; i++ {
				wall = append(wall, &pb.Tile{
					Id:    idCount,
					Suit:  suit,
					Value: v,
				})
				idCount++
			}
		}
	}

	// Jihai (1z=East, 2z=South, 3z=West, 4z=North, 5z=Haku/白, 6z=Hatsu/発, 7z=Chun/中)
	for v := uint32(1); v <= 7; v++ {
		for i := 0; i < 4; i++ {
			wall = append(wall, &pb.Tile{
				Id:    idCount,
				Suit:  pb.Suit_SUIT_JIHAI,
				Value: v,
			})
			idCount++
		}
	}

	return wall
}

func (r *HometownRuleset) EvaluateHand(hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) (int32, bool) {
	// Build the full 14-tile hand for pattern evaluation.
	// The winTile is always part of the complete hand.
	fullHand := make([]*pb.Tile, 0, len(hand)+1)
	fullHand = append(fullHand, hand...)
	fullHand = append(fullHand, winTile)

	// --- 1. Identify Wild Tiles & Tame State ---
	// Fenghua uses specific dynamic wild tiles (e.g., from the round start).
	// We count how many tiles in the hand match the ID of any tile in `state.WildTiles`.
	wildsInHand := 0
	isFlowerWild := false
	wildHashes := make(map[uint32]bool)
	if state != nil && len(state.WildTiles) > 0 {
		for _, w := range state.WildTiles {
			hash := uint32(w.Suit)*100 + w.Value
			wildHashes[hash] = true
			if w.Suit == pb.Suit_SUIT_UNKNOWN || w.Suit > pb.Suit_SUIT_JIHAI {
				isFlowerWild = true // A suit beyond Honors is usually Flower in standard numbering, or explicit Flower struct.
			}
		}
	}
	for _, t := range fullHand {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			wildsInHand++
		}
	}

	totalPoints := int32(1) // Base point (坐台)
	if isTsumo {
		totalPoints += 1 // Win by own tile (自摸)
	}

	// --- 3. Evaluate High-Level Hand Structures (Mutually Exclusive Cores) ---
	canWin := false

	isIndependence := len(openMelds) == 0 && r.isIndependence(fullHand, wildHashes)
	isSevenPairs := len(openMelds) == 0 && r.isSevenPairs(fullHand, wildHashes)
	isStandard := r.canFormStandardHand(fullHand, wildHashes, true) // 4 melds + 1 pair

	// --- 1.5. Calculate Tame Wild (还搭) ---
	// Wild tiles are tame when used at their natural face value in a meld.
	// This is true when the hand forms a valid structure even treating wild tiles as ordinary tiles.
	isTame := false
	if wildsInHand > 0 {
		emptyWilds := make(map[uint32]bool)
		if r.canFormStandardHand(fullHand, emptyWilds, true) ||
			(len(openMelds) == 0 && r.isSevenPairs(fullHand, emptyWilds)) ||
			(len(openMelds) == 0 && r.isIndependence(fullHand, emptyWilds)) {
			isTame = true
		}
	}

	// --- 2. Wild Tile Point Bonuses (无搭/一搭/二搭/还搭/普通三百搭/三花三百搭) ---
	if wildsInHand == 0 {
		totalPoints += 1 // No wild tiles (无搭)
	} else if wildsInHand == 1 {
		totalPoints += 1 // One wild tile (一搭)
	} else if wildsInHand == 2 {
		totalPoints += 2 // Two wild tiles (二搭)
	} else if wildsInHand == 3 {
		if isFlowerWild {
			totalPoints += 300 // Three flower wild tiles (三花三百搭)
		} else {
			totalPoints += 150 // Three normal wild tiles (普通三百搭)
		}
	}
	if isTame {
		totalPoints += 1 // Tame wild tiles (还搭)
	}

	maxStrScore := int32(0)

	if isIndependence {
		canWin = true
		routeScore := int32(0)
		// Variants: Open Seven Stars (100), Closed Seven Stars (150), Without Suit (150), Base (50)
		if r.hasAllSevenHonors(fullHand) {
			if isTsumo {
				routeScore += 150 // Closed seven stars
			} else {
				routeScore += 100 // Open seven stars
			}
		} else if r.isMissingASuit(fullHand) {
			routeScore += 150 // Independence without a suit
		} else {
			routeScore += 50 // Standard Independence (大大胡)
		}
		if routeScore > maxStrScore {
			maxStrScore = routeScore
		}
	}

	if isSevenPairs {
		canWin = true
		routeScore := int32(0)
		// Variants: Straight (150) vs Wild (50)
		if wildsInHand == 0 {
			routeScore += 150
		} else {
			routeScore += 50
		}
		// Simplified check for Bombs in 7 pairs (4 identical tiles).
		if bombCount := r.countIdenticalFours(fullHand); bombCount > 0 {
			if isTsumo {
				routeScore += 100 // Closed bomb
			} else {
				routeScore += 50 // Open bomb
			}
		}
		if routeScore > maxStrScore {
			maxStrScore = routeScore
		}
	}

	if isStandard {
		canWin = true
		routeScore := int32(0)

		isAllPung := r.isAllPung(fullHand, openMelds, wildHashes)
		isPureSuit := r.isPureOneSuit(fullHand, openMelds, wildHashes)
		isMixedSuit := r.isMixedOneSuit(fullHand, openMelds, wildHashes)

		if !isAllPung && !isPureSuit && !isMixedSuit {
			routeScore += 1 // Common win (朋胡) — only when no higher structural pattern applies
		}

		// Check Loner (大吊车) — 4 open melds, 1 tile in hand + winTile = 2 closed tiles total
		if len(openMelds) == 4 {
			if wildsInHand == 0 {
				routeScore += 100 // Straight loner (无搭)
			} else {
				routeScore += 50 // Wild loner (有搭)
			}
		}

		// Check All Pon (大对对) — 4 pon/kan + 1 pair, no chii
		if isAllPung {
			if wildsInHand == 0 {
				routeScore += 100 // Straight all pon (无搭)
			} else {
				routeScore += 50 // Wild all pon (有搭)
			}
		}

		// Wait pattern bonus — single wait/pair call (边嵌单吊对倒)
		if r.evalWaitPattern(hand, winTile, wildHashes) > 0 {
			routeScore += 1 // Edge/gap/single/pair-call wait (边，嵌，单吊, 对倒)
		}

		if routeScore > maxStrScore {
			maxStrScore = routeScore
		}
	}

	totalPoints += maxStrScore

	// If it matches none of the standard structural shapes, check for absolute extremes.
	if !canWin {
		if r.isUncompletedAllHonors(fullHand, openMelds, wildHashes) {
			canWin = true
			totalPoints += 400 // Uncompleted all jihai (乱老头)
		}
	} else {
		// If it's a standard hand or seven pairs, it could ALSO qualify for suit patterns.
		if r.isCompletedAllHonors(fullHand, openMelds, wildHashes) {
			totalPoints += 800 // Completed all jihai (清老头)
		} else if r.isPureOneSuit(fullHand, openMelds, wildHashes) {
			totalPoints += 150 // Pure one suit (清一色)
		} else if r.isMixedOneSuit(fullHand, openMelds, wildHashes) {
			totalPoints += 70 // Mixed one suit (混一色)
		}
	}

	// --- 7. Flower Bonuses & Eight Flower Win ---
	var myFlowers []*pb.Tile
	if state != nil && state.Players != nil {
		if int(playerSeat) < len(state.Players) {
			ps := state.Players[playerSeat]
			if ps != nil {
				myFlowers = ps.FlowerMelds
			}
		}
	}

	// Uncompleted Eight Flowers (八花直胡) - instant win without regular sets
	if len(myFlowers) == 8 {
		if !canWin {
			canWin = true
			totalPoints = int32(0) // Override base and wild points, it's just 400 + own flower
			totalPoints += 400
		} else {
			totalPoints += 800 // Completed eight flowers (八花搓胡)
		}
	} else if len(myFlowers) >= 4 {
		totalPoints += 150 // Four flowers (四花)
	}

	totalPoints += getFlowerBonuses(myFlowers, playerSeat, state)

	if !canWin {
		return 0, false
	}

	// --- 4. Dragon Pon Bonuses (中发白碰出) ---
	// 5z=Haku(白/White Dragon), 6z=Hatsu(発/Green Dragon), 7z=Chun(中/Red Dragon)
	totalPoints += r.countDragonPungs(fullHand, openMelds, wildHashes)

	// --- 5. Wind Pon Bonuses (位风/圈风/正风) ---
	if state != nil {
		var seatWind, prevailingWind uint32
		if int(playerSeat) < len(state.Players) && state.Players[playerSeat] != nil {
			seatWind = state.Players[playerSeat].SeatWind
		}
		prevailingWind = state.PrevailingWind
		if seatWind > 0 {
			if r.hasPungOfValue(fullHand, openMelds, pb.Suit_SUIT_JIHAI, seatWind) {
				if seatWind == prevailingWind {
					totalPoints += 2 // Right wind (正风)
				} else {
					totalPoints += 1 // Seat wind (位风)
				}
			}
		}
		if prevailingWind > 0 && prevailingWind != seatWind {
			if r.hasPungOfValue(fullHand, openMelds, pb.Suit_SUIT_JIHAI, prevailingWind) {
				totalPoints += 1 // Prevailing wind (圈风)
			}
		}
	}

	// --- 6. Kong Bonuses (杠牌加分) ---
	// These require contextual flags from the game loop.
	if state != nil && int(playerSeat) < len(state.Players) {
		ps := state.Players[playerSeat]
		if ps != nil {
			if ps.HasBuddingDirectKong {
				totalPoints += 50
			}
			if ps.HasBloomingDirectKong {
				totalPoints += 100
			}
			if ps.HasBuddingClosedKong {
				totalPoints += 100
			}
			if ps.HasBloomingClosedKong {
				totalPoints += 150
			}
			if ps.HasBuddingRiskyKong {
				totalPoints += 100
			}
			if ps.HasBloomingRiskyKong {
				totalPoints += 200
			}
			if ps.HasBloomingFlowerKong {
				totalPoints += 50
			}
		}
	}

	// Fenghua Minimum Win Points Enforcement ---
	// Ron requires 4 total points minimum. Tsumo has no minimum.
	if !isTsumo && totalPoints < 4 {
		return totalPoints, false
	}

	return totalPoints, true
}

// isIndependence checks for strictly 14 disconnected tiles (no pairs, no melds, no partial runs).
func (r *HometownRuleset) isIndependence(hand []*pb.Tile, wildHashes map[uint32]bool) bool {
	if len(hand) != 14 {
		return false
	}
	counts := make(map[uint32]int)
	for _, t := range hand {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			continue // Wild tiles can fill any missing unique slot
		}
		counts[hash]++
		if counts[hash] > 1 {
			return false // duplicate tile found
		}
	}
	return true
}

// isSevenPairs checks for exactly 7 pairs.
func (r *HometownRuleset) isSevenPairs(hand []*pb.Tile, wildHashes map[uint32]bool) bool {
	if len(hand) != 14 {
		return false
	}
	counts, wilds := r.tilesToTehai34(hand, wildHashes)
	singles := 0
	for _, c := range counts {
		singles += c % 2
	}
	// Wild tiles can fill in unpaired singles
	return wilds >= singles
}

// tileToIndex converts a tile to a Mortal-aligned 0-33 index for tehai array processing.
// Layout: man(0-8), pin(9-17), sou(18-26), jihai(27-33)
// Proto names: SUIT_MAN=man, SUIT_PIN=pin, SUIT_SOU=sou, SUIT_JIHAI=jihai
func tileToIndex(t *pb.Tile) int {
	valOffset := int(t.Value) - 1
	switch t.Suit {
	case pb.Suit_SUIT_MAN: // man (万子) 1m-9m → 0-8
		return valOffset
	case pb.Suit_SUIT_PIN: // pin (筒子) 1p-9p → 9-17
		return 9 + valOffset
	case pb.Suit_SUIT_SOU: // sou (索子) 1s-9s → 18-26
		return 18 + valOffset
	case pb.Suit_SUIT_JIHAI: // jihai (字牌) 1z-7z → 27-33
		return 27 + valOffset
	}
	return 0
}

// tilesToTehai34 converts a slice of tiles into a [34]int tehai count array (Mortal layout).
// Wild tiles are counted separately and excluded from the array.
// Returns (tehai counts, wild tile count).
func (r *HometownRuleset) tilesToTehai34(tiles []*pb.Tile, wildHashes map[uint32]bool) ([34]int, int) {
	var counts [34]int
	wilds := 0
	for _, t := range tiles {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			wilds++
		} else {
			counts[tileToIndex(t)]++
		}
	}
	return counts, wilds
}

// canFormStandardHand determines if the tiles can form 4 melds (chii/pon/kan) and 1 pair.
// Uses a flat-array DFS/DP backtracking approach (Mortal-style tehai) with wild tile substitution.
// allowChow=false forces pon-only evaluation (for all-pon hand detection).
func (r *HometownRuleset) canFormStandardHand(hand []*pb.Tile, wildHashes map[uint32]bool, allowChow bool) bool {
	if len(hand)%3 != 2 {
		return false
	}

	counts, wilds := r.tilesToTehai34(hand, wildHashes)

	// Try every index as the pair tile; wild tiles can substitute for missing pair members.
	for i := 0; i < 34; i++ {
		needed := 2 - counts[i]
		if needed < 0 {
			needed = 0
		}

		if wilds >= needed {
			tilesToSubtract := 2 - needed
			counts[i] -= tilesToSubtract
			if r.checkMeldsFast(&counts, 0, wilds-needed, allowChow) {
				return true
			}
			counts[i] += tilesToSubtract
		}
	}

	return false
}

// checkMeldsFast is the recursive DFS helper for standard hand evaluation.
// Tries to form pon (triplets) and chii (sequences) consuming all tiles in the tehai array.
// Wild tiles substitute freely for any missing tile in a meld.
func (r *HometownRuleset) checkMeldsFast(counts *[34]int, startIdx int, wilds int, allowChow bool) bool {
	if wilds < 0 {
		return false
	}

	for i := startIdx; i < 34; i++ {
		if counts[i] == 0 {
			continue
		}

		// Try pon (triplet)
		neededForPon := 0
		if counts[i] < 3 {
			neededForPon = 3 - counts[i]
		}

		if wilds >= neededForPon {
			tilesToRemove := 3 - neededForPon
			counts[i] -= tilesToRemove
			if r.checkMeldsFast(counts, i, wilds-neededForPon, allowChow) {
				counts[i] += tilesToRemove
				return true
			}
			counts[i] += tilesToRemove
		}

		// Try chii (sequence). Jihai (indices >= 27) cannot form sequences.
		// i%9 <= 6 ensures i+1 and i+2 are within the same suit block.
		if allowChow && i < 27 && i%9 <= 6 {
			needNext1 := 1
			if counts[i+1] > 0 {
				needNext1 = 0
			}
			needNext2 := 1
			if counts[i+2] > 0 {
				needNext2 = 0
			}

			totalNeededForChii := needNext1 + needNext2
			if wilds >= totalNeededForChii {
				counts[i]--
				if needNext1 == 0 {
					counts[i+1]--
				}
				if needNext2 == 0 {
					counts[i+2]--
				}

				if r.checkMeldsFast(counts, i, wilds-totalNeededForChii, allowChow) {
					counts[i]++
					if needNext1 == 0 {
						counts[i+1]++
					}
					if needNext2 == 0 {
						counts[i+2]++
					}
					return true
				}

				counts[i]++
				if needNext1 == 0 {
					counts[i+1]++
				}
				if needNext2 == 0 {
					counts[i+2]++
				}
			}
		}

		// Neither pon nor chii can consume this tile — this branch fails.
		return false
	}

	return true
}

func (r *HometownRuleset) GetValidActions(state *pb.GameState, playerSeat uint32) []*pb.PlayerAction {
	var actions []*pb.PlayerAction

	// The player can always discard
	actions = append(actions, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
	})

	player := state.Players[playerSeat]

	// Check if the 14-tile hand is a winning hand (Tsumo)
	_, canWin := r.EvaluateHand(player.ClosedHand, player.OpenMelds, nil, state, playerSeat, true)
	if canWin {
		actions = append(actions, &pb.PlayerAction{
			Type: pb.ActionType_ACTION_TSUMO,
		})
	}

	// Check for Closed/Upgraded Kongs (4 of a kind in hand)
	counts := make(map[uint32][]*pb.Tile)
	for _, t := range player.ClosedHand {
		counts[t.Id] = append(counts[t.Id], t)
	}

	for _, tiles := range counts {
		if len(tiles) == 4 {
			actions = append(actions, &pb.PlayerAction{
				Type:      pb.ActionType_ACTION_KAN,
				MeldTiles: tiles,
			})
		}
	}

	return actions
}

func (r *HometownRuleset) GetValidInterrupts(state *pb.GameState, discardedTile *pb.Tile, playerSeat uint32) []*pb.PlayerAction {
	var actions []*pb.PlayerAction
	player := state.Players[playerSeat]
	discarderSeat := state.ActivePlayer

	// 1. Check Ron (can this discard complete my hand?)
	// We simulate adding the discarded tile to the closed hand
	simulatedHand := append([]*pb.Tile{}, player.ClosedHand...)
	simulatedHand = append(simulatedHand, discardedTile)

	_, canWin := r.EvaluateHand(simulatedHand, player.OpenMelds, discardedTile, state, playerSeat, false)

	// Disabled 4-point minimum for UI testing
	if canWin {
		actions = append(actions, &pb.PlayerAction{
			Type:         pb.ActionType_ACTION_RON,
			Tile:         discardedTile,
			TargetPlayer: discarderSeat,
		})
	}

	// Group closed hand by Suit+Value to easily find matches
	matchingTiles := []*pb.Tile{}
	for _, t := range player.ClosedHand {
		if t.Suit == discardedTile.Suit && t.Value == discardedTile.Value {
			matchingTiles = append(matchingTiles, t)
		}
	}

	// 2. Check Kang (Needs 3 matching tiles)
	if len(matchingTiles) == 3 {
		actions = append(actions, &pb.PlayerAction{
			Type:         pb.ActionType_ACTION_KAN,
			Tile:         discardedTile,
			MeldTiles:    matchingTiles,
			TargetPlayer: discarderSeat,
		})
	}

	// 3. Check Pong (Needs 2+ matching tiles)
	if len(matchingTiles) >= 2 {
		actions = append(actions, &pb.PlayerAction{
			Type:         pb.ActionType_ACTION_PON,
			Tile:         discardedTile,
			MeldTiles:    matchingTiles[:2],
			TargetPlayer: discarderSeat,
		})
	}

	// 4. Check Chii (Only allowed if discarded by the player immediately to the left)
	isLeftSeatDiscard := (playerSeat+3)%4 == discarderSeat
	if isLeftSeatDiscard && discardedTile.Suit != pb.Suit_SUIT_JIHAI && discardedTile.Suit != pb.Suit_SUIT_UNKNOWN {
		val := discardedTile.Value

		var minus2, minus1, plus1, plus2 *pb.Tile
		for _, t := range player.ClosedHand {
			if t.Suit == discardedTile.Suit {
				if t.Value == val-2 {
					minus2 = t
				}
				if t.Value == val-1 {
					minus1 = t
				}
				if t.Value == val+1 {
					plus1 = t
				}
				if t.Value == val+2 {
					plus2 = t
				}
			}
		}

		// Sequence [n-2, n-1, DISCARD]
		if minus2 != nil && minus1 != nil {
			actions = append(actions, &pb.PlayerAction{
				Type:         pb.ActionType_ACTION_CHII,
				Tile:         discardedTile,
				MeldTiles:    []*pb.Tile{minus2, minus1},
				TargetPlayer: discarderSeat,
			})
		}
		// Sequence [n-1, DISCARD, n+1]
		if minus1 != nil && plus1 != nil {
			actions = append(actions, &pb.PlayerAction{
				Type:         pb.ActionType_ACTION_CHII,
				Tile:         discardedTile,
				MeldTiles:    []*pb.Tile{minus1, plus1},
				TargetPlayer: discarderSeat,
			})
		}
		// Sequence [DISCARD, n+1, n+2]
		if plus1 != nil && plus2 != nil {
			actions = append(actions, &pb.PlayerAction{
				Type:         pb.ActionType_ACTION_CHII,
				Tile:         discardedTile,
				MeldTiles:    []*pb.Tile{plus1, plus2},
				TargetPlayer: discarderSeat,
			})
		}
	}

	return actions
}

func (r *HometownRuleset) ResolveInterruptPriority(actions map[uint32]*pb.PlayerAction) (uint32, *pb.PlayerAction) {
	// Simple priority resolution: RON > KONG/PONG > CHOW
	var prioritySeat uint32
	var highestAction *pb.PlayerAction
	highestWeight := 0

	weights := map[pb.ActionType]int{
		pb.ActionType_ACTION_CHII: 1,
		pb.ActionType_ACTION_PON:  2,
		pb.ActionType_ACTION_KAN:  3,
		pb.ActionType_ACTION_RON:  4,
	}

	for seat, action := range actions {
		w := weights[action.Type]
		if w > highestWeight {
			highestWeight = w
			highestAction = action
			prioritySeat = seat
		}
	}

	return prioritySeat, highestAction
}

// --- Helpers for Fenghua Special Patterns ---

func (r *HometownRuleset) hasAllSevenHonors(hand []*pb.Tile) bool {
	honorCounts := make(map[uint32]bool)
	for _, t := range hand {
		if t.Suit == pb.Suit_SUIT_JIHAI {
			honorCounts[t.Value] = true
		}
	}
	return len(honorCounts) == 7
}

func (r *HometownRuleset) isMissingASuit(hand []*pb.Tile) bool {
	suits := make(map[pb.Suit]bool)
	for _, t := range hand {
		if t.Suit != pb.Suit_SUIT_JIHAI {
			suits[t.Suit] = true
		}
	}
	// Missing at least one of the 3 main suits
	return len(suits) < 3
}

func (r *HometownRuleset) countIdenticalFours(hand []*pb.Tile) int {
	counts := make(map[uint32]int)
	bombs := 0
	for _, t := range hand {
		hash := uint32(t.Suit)*100 + t.Value
		counts[hash]++
		if counts[hash] == 4 {
			bombs++
		}
	}
	return bombs
}

func (r *HometownRuleset) isAllPung(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	// Open melds must all be pon or kan — any chii disqualifies.
	for _, m := range openMelds {
		if m.Type == pb.ActionType_ACTION_CHII {
			return false
		}
	}
	// Evaluate with allowChow=false to force pon-only decomposition
	return r.canFormStandardHand(hand, wildHashes, false)
}

func (r *HometownRuleset) isUncompletedAllHonors(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	for _, m := range openMelds {
		for _, t := range m.Tiles {
			if t.Suit != pb.Suit_SUIT_JIHAI {
				return false
			}
		}
	}
	for _, t := range hand {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			continue // Wild tiles adapt to any jihai
		}
		if t.Suit != pb.Suit_SUIT_JIHAI {
			return false
		}
	}
	return true
}

func (r *HometownRuleset) isCompletedAllHonors(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	if !r.isUncompletedAllHonors(hand, openMelds, wildHashes) {
		return false
	}
	return r.canFormStandardHand(hand, wildHashes, true) || r.isSevenPairs(hand, wildHashes)
}

// isPureOneSuit checks for 清一色: all tiles from exactly one numbered suit (man/pin/sou, no jihai).
// Wild tiles are transparent — they do not break the suit constraint.
func (r *HometownRuleset) isPureOneSuit(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	var targetSuit pb.Suit = pb.Suit_SUIT_UNKNOWN
	for _, m := range openMelds {
		for _, t := range m.Tiles {
			if targetSuit == pb.Suit_SUIT_UNKNOWN {
				targetSuit = t.Suit
			} else if t.Suit != targetSuit {
				return false
			}
		}
	}
	for _, t := range hand {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			continue // Wild tile does not constrain the target suit
		}
		if targetSuit == pb.Suit_SUIT_UNKNOWN {
			targetSuit = t.Suit
		} else if t.Suit != targetSuit {
			return false
		}
	}
	return targetSuit != pb.Suit_SUIT_JIHAI && targetSuit != pb.Suit_SUIT_UNKNOWN
}

func (r *HometownRuleset) isMixedOneSuit(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	var targetSuit pb.Suit = pb.Suit_SUIT_UNKNOWN
	hasHonors := false
	hasSuit := false

	checkTile := func(t *pb.Tile) bool {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			return true // Wild tile can be any suit — does not break the constraint
		}
		if t.Suit == pb.Suit_SUIT_JIHAI {
			hasHonors = true
			return true
		}
		if targetSuit == pb.Suit_SUIT_UNKNOWN {
			targetSuit = t.Suit
			hasSuit = true
		} else if t.Suit != targetSuit {
			return false // Second numbered suit found — not mixed one suit
		}
		return true
	}

	for _, m := range openMelds {
		for _, t := range m.Tiles {
			if !checkTile(t) {
				return false
			}
		}
	}
	for _, t := range hand {
		if !checkTile(t) {
			return false
		}
	}

	return hasSuit && hasHonors
}

// countDragonPungs counts pon bonuses for dragon tiles (中发白碰出).
// Dragons: 5z=Haku(白), 6z=Hatsu(発), 7z=Chun(中). Each dragon pon awards +1.
func (r *HometownRuleset) countDragonPungs(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) int32 {
	var points int32
	for _, dragonVal := range []uint32{5, 6, 7} {
		if r.hasPungOfValue(hand, openMelds, pb.Suit_SUIT_JIHAI, dragonVal) {
			points += 1
		}
	}
	return points
}

// hasPungOfValue checks if a pon (3+ tiles) of the given suit+value exists in hand or open melds.
func (r *HometownRuleset) hasPungOfValue(hand []*pb.Tile, openMelds []*pb.Meld, suit pb.Suit, value uint32) bool {
	count := 0
	for _, t := range hand {
		if t.Suit == suit && t.Value == value {
			count++
		}
	}
	for _, m := range openMelds {
		if m.Type == pb.ActionType_ACTION_PON || m.Type == pb.ActionType_ACTION_KAN {
			if len(m.Tiles) > 0 && m.Tiles[0].Suit == suit && m.Tiles[0].Value == value {
				return true
			}
		}
	}
	return count >= 3
}

func getFlowerBonuses(myFlowers []*pb.Tile, playerSeat uint32, state *pb.GameState) int32 {
	var points int32
	if state != nil && int(playerSeat) < len(state.Players) && state.Players[playerSeat] != nil {
		seatWind := state.Players[playerSeat].SeatWind
		if seatWind > 0 {
			for _, f := range myFlowers {
				if f.Value == seatWind {
					points += 2 // Own flower
				}
			}
		}
	}
	return points
}

// evalWaitPattern returns 1 if the final wait was a restricted pattern that awards +1 point.
// Covered wait patterns:
//  1. Single wait (单吊): 13 tiles form exactly 4 complete melds; waiting only for the pair tile.
//  2. Pair call (对倒): Two pairs in hand; waiting for either to become a pon.
//  3. Gap wait (嵌): Waiting for the middle tile of a chii (e.g. 1s3s waiting for 2s).
//  4. Edge wait (边): Waiting for 3 to complete 1,2 or for 7 to complete 8,9 in any suited tile.
func (r *HometownRuleset) evalWaitPattern(hand []*pb.Tile, winTile *pb.Tile, wildHashes map[uint32]bool) int {
	if len(hand) != 13 {
		return 0
	}

	counts, wilds := r.tilesToTehai34(hand, wildHashes)
	winIdx := tileToIndex(winTile)
	winHash := uint32(winTile.Suit)*100 + winTile.Value
	winIsWild := wildHashes[winHash]

	// isValidHand: checks if a 14-tile configuration (counts + wilds) forms a valid standard hand.
	isValidHand := func(testCounts *[34]int, testWilds int) bool {
		for i := 0; i < 34; i++ {
			if testCounts[i] == 0 && testWilds < 2 {
				continue
			}
			neededForPair := 2 - testCounts[i]
			if neededForPair < 0 {
				neededForPair = 0
			}
			if testWilds >= neededForPair {
				tilesToRemove := 2 - neededForPair
				testCounts[i] -= tilesToRemove
				if r.checkMeldsFast(testCounts, 0, testWilds-neededForPair, true) {
					testCounts[i] += tilesToRemove
					return true
				}
				testCounts[i] += tilesToRemove
			}
		}
		return false
	}

	// 1. Single wait (单吊): the 13 tiles form exactly 4 melds; winTile completes the pair alone.
	singleWaitCounts := counts
	singleWaitWilds := wilds
	if winIsWild {
		singleWaitWilds++
	} else {
		singleWaitCounts[winIdx]++
	}
	if !winIsWild && singleWaitCounts[winIdx] >= 2 {
		singleWaitCounts[winIdx] -= 2
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds, true) {
			return 1
		}
		singleWaitCounts[winIdx] += 2
	} else if winIsWild && singleWaitWilds >= 2 {
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds-2, true) {
			return 1
		}
	} else if singleWaitCounts[winIdx] == 1 && singleWaitWilds >= 1 {
		singleWaitCounts[winIdx] -= 1
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds-1, true) {
			return 1
		}
		singleWaitCounts[winIdx] += 1
	}

	// 2. Pair call (对倒): winning tile forms a pon; the remaining tiles form a valid hand with a pair.
	pairCallCounts := counts
	pairCallWilds := wilds
	if winIsWild {
		pairCallWilds++
	} else {
		pairCallCounts[winIdx]++
	}
	canFormPon := false
	if !winIsWild {
		if pairCallCounts[winIdx] >= 3 {
			pairCallCounts[winIdx] -= 3
			canFormPon = true
		} else if pairCallCounts[winIdx] == 2 && pairCallWilds >= 1 {
			pairCallCounts[winIdx] -= 2
			pairCallWilds--
			canFormPon = true
		}
	}
	// Wild win tile is ambiguous for pair call — skip for now
	if canFormPon {
		if isValidHand(&pairCallCounts, pairCallWilds) {
			return 1
		}
	}

	// Chii-based waits require a numbered suit tile
	if winTile.Suit == pb.Suit_SUIT_JIHAI || winTile.Suit == pb.Suit_SUIT_UNKNOWN || winIsWild {
		return 0
	}

	val := winTile.Value

	// checkChiiWait: forces a chii with (valA, winTile, valB) and checks if the remainder is valid.
	checkChiiWait := func(valA, valB uint32) bool {
		testCounts := counts
		testWilds := wilds

		idxA := tileToIndex(&pb.Tile{Suit: winTile.Suit, Value: valA})
		idxB := tileToIndex(&pb.Tile{Suit: winTile.Suit, Value: valB})

		neededWilds := 0
		if testCounts[idxA] > 0 {
			testCounts[idxA]--
		} else {
			neededWilds++
		}
		if testCounts[idxB] > 0 {
			testCounts[idxB]--
		} else {
			neededWilds++
		}

		if testWilds >= neededWilds {
			testWilds -= neededWilds
			return isValidHand(&testCounts, testWilds)
		}
		return false
	}

	// 3. Gap wait (嵌): waiting for X, hand has X-1 and X+1
	if val > 1 && val < 9 {
		if checkChiiWait(val-1, val+1) {
			return 1
		}
	}

	// 4. Edge wait (边): 1,2 waiting for 3 — or — 8,9 waiting for 7
	if val == 3 {
		if checkChiiWait(1, 2) {
			return 1
		}
	} else if val == 7 {
		if checkChiiWait(8, 9) {
			return 1
		}
	}

	return 0
}
