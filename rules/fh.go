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

func (r *HometownRuleset) EvaluateHand(hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) (int32, []*pb.ScoreEntry, bool) {
	effectiveWinTile := winTile
	if isTsumo && effectiveWinTile == nil {
		effectiveWinTile = resolveTsumoWinTile(hand, state, playerSeat)
	}

	// Build the full 14-tile hand for pattern evaluation.
	fullHand := make([]*pb.Tile, 0, len(hand)+1)
	fullHand = append(fullHand, hand...)
	if winTile != nil {
		fullHand = append(fullHand, winTile)
	}

	// Breakdown entries accumulated throughout evaluation
	entries := make([]*pb.ScoreEntry, 0)

	// --- 1. Identify Wild Tiles & Tame State ---
	wildsInHand := 0
	isFlowerWild := false
	wildHashes := make(map[uint32]bool)
	if state != nil && len(state.WildTiles) > 0 {
		for _, w := range state.WildTiles {
			hash := uint32(w.Suit)*100 + w.Value
			wildHashes[hash] = true
			if w.Suit == pb.Suit_SUIT_UNKNOWN || w.Suit > pb.Suit_SUIT_JIHAI {
				isFlowerWild = true
			}
		}
	}
	// Count wild tiles (excluding Ron win tile — it acts as a normal tile)
	for _, t := range hand {
		hash := uint32(t.Suit)*100 + t.Value
		if wildHashes[hash] {
			wildsInHand++
		}
	}
	// If Tsumo, the drawn winning tile is part of our concealed hand and counts as wild
	if isTsumo && winTile != nil {
		hash := uint32(winTile.Suit)*100 + winTile.Value
		if wildHashes[hash] {
			wildsInHand++
		}
	}

	// Base point (坐台) — always awarded
	entries = append(entries, &pb.ScoreEntry{PatternName: "Base Point (坐台)", Points: 1})
	if isTsumo {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Tsumo (自摸)", Points: 1})
	}

	// --- 3. Evaluate High-Level Hand Structures (Mutually Exclusive Cores) ---
	canWin := false

	isIndependence := len(openMelds) == 0 && r.isIndependence(fullHand, wildHashes)
	isSevenPairs := len(openMelds) == 0 && r.isSevenPairs(fullHand, wildHashes)
	isStandard := r.canFormStandardHand(fullHand, wildHashes, true)

	// --- 1.5. Calculate Tame Wild (还搭) ---
	isTame := false
	if wildsInHand > 0 {
		emptyWilds := make(map[uint32]bool)
		if r.canFormStandardHand(fullHand, emptyWilds, true) ||
			(len(openMelds) == 0 && r.isSevenPairs(fullHand, emptyWilds)) ||
			(len(openMelds) == 0 && r.isIndependence(fullHand, emptyWilds)) {
			isTame = true
		}
	}

	// --- 2. Wild Tile Point Bonuses ---
	if wildsInHand == 0 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "No Wild Tiles (无搭)", Points: 1})
	} else if wildsInHand == 1 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "One Wild Tile (一搭)", Points: 1})
	} else if wildsInHand == 2 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Two Wild Tiles (二搭)", Points: 2})
	} else if wildsInHand == 3 {
		if isFlowerWild {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Three Flower Wild Tiles (三花三百搭)", Points: 300})
		} else {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Three Normal Wild Tiles (普通三百搭)", Points: 150})
		}
	}
	if isTame {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Tame Wild Tiles (还搭)", Points: 1})
	}

	// --- Structural route evaluation (pick highest-scoring route) ---
	type scoredRoute struct {
		score   int32
		entries []*pb.ScoreEntry
	}
	var bestRoute *scoredRoute

	if isIndependence {
		canWin = true
		re := make([]*pb.ScoreEntry, 0)
		// Base Independence is always +50
		re = append(re, &pb.ScoreEntry{PatternName: "Independence (大大胡)", Points: 50})
		// Seven Stars bonus stacks on top (closed +100, open +50)
		if r.hasAllSevenHonors(fullHand) {
			if isTsumo {
				re = append(re, &pb.ScoreEntry{PatternName: "Closed Seven Stars (暗七星)", Points: 100})
			} else {
				re = append(re, &pb.ScoreEntry{PatternName: "Open Seven Stars (明七星)", Points: 50})
			}
		}
		// Without-suit bonus stacks independently (+100), combinable with Seven Stars
		if r.isMissingASuit(fullHand) {
			re = append(re, &pb.ScoreEntry{PatternName: "Independence Without Suit (缺色)", Points: 100})
		}
		routeTotal := int32(0)
		for _, e := range re {
			routeTotal += e.Points
		}
		if bestRoute == nil || routeTotal > bestRoute.score {
			bestRoute = &scoredRoute{score: routeTotal, entries: re}
		}
	}

	if isSevenPairs {
		canWin = true
		re := make([]*pb.ScoreEntry, 0)
		if wildsInHand == 0 {
			re = append(re, &pb.ScoreEntry{PatternName: "Straight Seven Pairs (七对头无搭)", Points: 150})
		} else {
			re = append(re, &pb.ScoreEntry{PatternName: "Wild Seven Pairs (七对头有搭)", Points: 50})
		}
		if bombCount := r.countIdenticalFours(fullHand); bombCount > 0 {
			if isTsumo {
				re = append(re, &pb.ScoreEntry{PatternName: "Closed Bomb (暗炸)", Points: 100})
			} else {
				re = append(re, &pb.ScoreEntry{PatternName: "Open Bomb (明炸)", Points: 50})
			}
		}
		routeTotal := int32(0)
		for _, e := range re {
			routeTotal += e.Points
		}
		if bestRoute == nil || routeTotal > bestRoute.score {
			bestRoute = &scoredRoute{score: routeTotal, entries: re}
		}
	}

	if isStandard {
		canWin = true
		re := make([]*pb.ScoreEntry, 0)

		isAllPung := r.isAllPung(fullHand, openMelds, wildHashes)
		isAllChow := r.isAllChow(fullHand, openMelds, wildHashes)
		isPureSuit := r.isPureOneSuit(fullHand, openMelds, wildHashes)
		isMixedSuit := r.isMixedOneSuit(fullHand, openMelds, wildHashes)

		// Common Win (朋胡): four runs (sequences) and a pair of eyes.
		// Excluded when pure/mixed one-suit patterns apply (those are scored separately).
		if isAllChow && !isPureSuit && !isMixedSuit {
			re = append(re, &pb.ScoreEntry{PatternName: "Common Win (朋胡)", Points: 1})
		}

		// Wait pattern bonus — single wait/pair call (边嵌单吊对倒)
		hasSingleCall := effectiveWinTile != nil && r.evalWaitPattern(hand, effectiveWinTile, wildHashes) > 0
		if hasSingleCall {
			re = append(re, &pb.ScoreEntry{PatternName: "Single/Pair Call (边嵌单吊对倒)", Points: 1})
		}
		if len(openMelds) == 4 {
			if wildsInHand == 0 {
				re = append(re, &pb.ScoreEntry{PatternName: "Straight Loner (大吊车无搭)", Points: 100})
			} else {
				re = append(re, &pb.ScoreEntry{PatternName: "Wild Loner (大吊车有搭)", Points: 50})
			}
		}

		if isAllPung {
			if wildsInHand == 0 {
				re = append(re, &pb.ScoreEntry{PatternName: "Straight All Pung (大对对无搭)", Points: 100})
			} else {
				re = append(re, &pb.ScoreEntry{PatternName: "Wild All Pung (大对对有搭)", Points: 50})
			}
		}

		routeTotal := int32(0)
		for _, e := range re {
			routeTotal += e.Points
		}
		if bestRoute == nil || routeTotal > bestRoute.score {
			bestRoute = &scoredRoute{score: routeTotal, entries: re}
		}
	}

	// Merge best structural route into entries
	if bestRoute != nil {
		entries = append(entries, bestRoute.entries...)
	}

	// If no standard structural shapes matched, check for absolute extremes.
	if !canWin {
		if r.isUncompletedAllHonors(fullHand, openMelds, wildHashes) {
			canWin = true
			entries = append(entries, &pb.ScoreEntry{PatternName: "Uncompleted All Honors (乱老头)", Points: 400})
		}
	} else {
		if r.isCompletedAllHonors(fullHand, openMelds, wildHashes) {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Completed All Honors (清老头)", Points: 800})
		} else if r.isPureOneSuit(fullHand, openMelds, wildHashes) {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Pure One Suit (清一色)", Points: 150})
		} else if r.isMixedOneSuit(fullHand, openMelds, wildHashes) {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Mixed One Suit (混一色)", Points: 70})
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

	if len(myFlowers) == 8 {
		if !canWin {
			canWin = true
			// Override: clear all previous entries, it's just 400 + own flower
			entries = []*pb.ScoreEntry{}
			entries = append(entries, &pb.ScoreEntry{PatternName: "Uncompleted Eight Flowers (八花直胡)", Points: 400})
		} else {
			entries = append(entries, &pb.ScoreEntry{PatternName: "Completed Eight Flowers (八花搓胡)", Points: 800})
		}
	} else if len(myFlowers) >= 4 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Four Flowers (四花)", Points: 150})
	}

	flowerBonus := getFlowerBonuses(myFlowers, playerSeat, state)
	if flowerBonus > 0 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Own Flower (花)", Points: flowerBonus})
	}

	if !canWin {
		return 0, nil, false
	}

	// --- 4. Dragon Pon Bonuses (中发白碰出) ---
	dragonPoints := r.countDragonPungs(fullHand, openMelds, wildHashes)
	if dragonPoints > 0 {
		entries = append(entries, &pb.ScoreEntry{PatternName: "Dragon Pung (中发白碰出)", Points: dragonPoints})
	}

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
					entries = append(entries, &pb.ScoreEntry{PatternName: "Right Wind (正风)", Points: 2})
				} else {
					entries = append(entries, &pb.ScoreEntry{PatternName: "Seat Wind (位风)", Points: 1})
				}
			}
		}
		if prevailingWind > 0 && prevailingWind != seatWind {
			if r.hasPungOfValue(fullHand, openMelds, pb.Suit_SUIT_JIHAI, prevailingWind) {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Prevailing Wind (圈风)", Points: 1})
			}
		}
	}

	// --- 6. Kong Bonuses (杠牌加分) ---
	if state != nil && int(playerSeat) < len(state.Players) {
		ps := state.Players[playerSeat]
		if ps != nil {
			if ps.HasBuddingDirectKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Budding Direct Kong (直杠不开花)", Points: 50})
			}
			if ps.HasBloomingDirectKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Blooming Direct Kong (直杠开花)", Points: 100})
			}
			if ps.HasBuddingClosedKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Budding Closed Kong (暗杠不开花)", Points: 100})
			}
			if ps.HasBloomingClosedKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Blooming Closed Kong (暗杠开花)", Points: 150})
			}
			if ps.HasBuddingRiskyKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Budding Risky Kong (风险杠不开花)", Points: 100})
			}
			if ps.HasBloomingRiskyKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Blooming Risky Kong (风险杠开花)", Points: 200})
			}
			if ps.HasBloomingFlowerKong {
				entries = append(entries, &pb.ScoreEntry{PatternName: "Blooming Flower Kong (花杠杠开)", Points: 50})
			}
		}
	}

	// Sum total from all entries
	totalPoints := int32(0)
	for _, e := range entries {
		totalPoints += e.Points
	}

	// Fenghua Minimum Win Points Enforcement ---
	// Ron requires 4 total points minimum. Tsumo has no minimum.
	if !isTsumo && totalPoints < 4 {
		return totalPoints, entries, false
	}

	return totalPoints, entries, true
}

// CalculatePayouts computes per-player payment amounts based on Fenghua rules.
// Tsumo: each of 3 losers pays S×2, winner receives S×6.
// Ron: discarder pays S×2, other two pay S×1, winner receives S×4.
func (r *HometownRuleset) CalculatePayouts(totalScore int32, winType pb.ActionType, winnerSeat uint32, discarderSeat uint32) []*pb.PlayerPayout {
	payouts := make([]*pb.PlayerPayout, 4)
	S := totalScore

	if winType == pb.ActionType_ACTION_TSUMO {
		for seat := uint32(0); seat < 4; seat++ {
			if seat == winnerSeat {
				payouts[seat] = &pb.PlayerPayout{Seat: seat, Amount: S * 6}
			} else {
				payouts[seat] = &pb.PlayerPayout{Seat: seat, Amount: -(S * 2)}
			}
		}
	} else {
		// Ron
		for seat := uint32(0); seat < 4; seat++ {
			if seat == winnerSeat {
				payouts[seat] = &pb.PlayerPayout{Seat: seat, Amount: S * 4}
			} else if seat == discarderSeat {
				payouts[seat] = &pb.PlayerPayout{Seat: seat, Amount: -(S * 2)}
			} else {
				payouts[seat] = &pb.PlayerPayout{Seat: seat, Amount: -(S * 1)}
			}
		}
	}
	return payouts
}

// isIndependence checks for strictly 14 disconnected tiles (no pairs, no melds, no partial runs).
func (r *HometownRuleset) isIndependence(hand []*pb.Tile, wildHashes map[uint32]bool) bool {
	if len(hand) != 14 {
		return false
	}
	counts, _ := r.tilesToTehai34(hand, wildHashes)

	for i := 0; i < 34; i++ {
		if counts[i] > 1 {
			return false // No pairs or triplets allowed
		}
		if counts[i] == 1 {
			// Check for adjacent sequences. Jihai (27-33) can't sequence, so only check man/pin/sou
			if i < 27 {
				suitBlockStart := (i / 9) * 9
				suitBlockEnd := suitBlockStart + 8

				// Abutting sequence (e.g. 1m, 2m)
				if i+1 <= suitBlockEnd && counts[i+1] > 0 {
					return false
				}
				// Skipping sequence / gap (e.g. 1m, 3m)
				if i+2 <= suitBlockEnd && counts[i+2] > 0 {
					return false
				}
			}
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
	_, _, canWin := r.EvaluateHand(player.ClosedHand, player.OpenMelds, nil, state, playerSeat, true)
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

	// Upgraded Kongs: Check if we have a tile in our ClosedHand that matches an existing open Pon
	for _, t := range player.ClosedHand {
		for _, m := range player.OpenMelds {
			if m.Type == pb.ActionType_ACTION_PON && len(m.Tiles) > 0 {
				if m.Tiles[0].Suit == t.Suit && m.Tiles[0].Value == t.Value {
					actions = append(actions, &pb.PlayerAction{
						Type:      pb.ActionType_ACTION_KAN,
						MeldTiles: []*pb.Tile{t},
					})
				}
			}
		}
	}

	return actions
}

func (r *HometownRuleset) GetValidInterrupts(state *pb.GameState, discardedTile *pb.Tile, playerSeat uint32) []*pb.PlayerAction {
	var actions []*pb.PlayerAction
	player := state.Players[playerSeat]
	discarderSeat := state.ActivePlayer

	// 1. Check Ron (can this discard complete my hand?)
	_, _, canWin := r.EvaluateHand(player.ClosedHand, player.OpenMelds, discardedTile, state, playerSeat, false)

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

// isAllChow checks for Common Win (朋胡): Four runs (sequences) and a pair of eyes.
// All open melds must be CHII and closed hand must decompose into chow-only melds + a pair.
func (r *HometownRuleset) isAllChow(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	// Open melds must all be chii — any pon/kan disqualifies.
	for _, m := range openMelds {
		if m.Type != pb.ActionType_ACTION_CHII {
			return false
		}
	}
	// Decompose closed hand into chow-only melds + a pair
	if len(hand)%3 != 2 {
		return false
	}
	counts, wilds := r.tilesToTehai34(hand, wildHashes)
	for i := 0; i < 34; i++ {
		needed := 2 - counts[i]
		if needed < 0 {
			needed = 0
		}
		if wilds >= needed {
			tilesToSubtract := 2 - needed
			counts[i] -= tilesToSubtract
			if r.checkChowOnlyMelds(&counts, 0, wilds-needed) {
				return true
			}
			counts[i] += tilesToSubtract
		}
	}
	return false
}

// checkChowOnlyMelds is a DFS helper that tries to consume all tiles using only chow (sequence) melds.
func (r *HometownRuleset) checkChowOnlyMelds(counts *[34]int, startIdx int, wilds int) bool {
	if wilds < 0 {
		return false
	}
	for i := startIdx; i < 34; i++ {
		if counts[i] == 0 {
			continue
		}
		// Jihai (indices >= 27) cannot form sequences, so fail.
		if i >= 27 || i%9 > 6 {
			return false
		}
		// Try chow (sequence)
		needNext1 := 1
		if counts[i+1] > 0 {
			needNext1 = 0
		}
		needNext2 := 1
		if counts[i+2] > 0 {
			needNext2 = 0
		}
		totalNeeded := needNext1 + needNext2
		if wilds >= totalNeeded {
			counts[i]--
			if needNext1 == 0 {
				counts[i+1]--
			}
			if needNext2 == 0 {
				counts[i+2]--
			}
			if r.checkChowOnlyMelds(counts, i, wilds-totalNeeded) {
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
		// Cannot form a chow with this tile — fail.
		return false
	}
	return true
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
	if winTile == nil {
		return 0
	}

	counts, wilds := r.tilesToTehai34(hand, wildHashes)
	winIdx := tileToIndex(winTile)
	winHash := uint32(winTile.Suit)*100 + winTile.Value
	winIsWild := wildHashes[winHash]

	// If the hand contains 14 tiles (Tsumo case where winTile was already appended to ClosedHand),
	// we must remove the winTile from counts to evaluate the original 13-tile hand's wait pattern.
	if len(hand) == 14 {
		if winIsWild {
			wilds--
		} else if counts[winIdx] > 0 {
			counts[winIdx]--
		} else {
			return 0 // Malformed hand
		}
	} else if len(hand) != 13 {
		return 0
	}

	// isValidHand: checks if a 14-tile configuration (counts + wilds) forms a valid standard hand.
	// Uses a local copy of counts so it doesn't mutate the caller's array.
	isValidHand := func(testCounts [34]int, testWilds int) bool {
		for i := 0; i < 34; i++ {
			if testCounts[i] == 0 && testWilds < 2 {
				continue
			}
			neededForPair := 2 - testCounts[i]
			if neededForPair < 0 {
				neededForPair = 0
			}
			if testWilds >= neededForPair {
				testCounts[i] -= (2 - neededForPair)
				if r.checkMeldsFast(&testCounts, 0, testWilds-neededForPair, true) {
					return true
				}
				testCounts[i] += (2 - neededForPair)
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
		// If the remaining 12 tiles can form 4 melds, it's a valid single wait.
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds, true) {
			return 1
		}
	} else if winIsWild && singleWaitWilds >= 2 {
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds-2, true) {
			return 1
		}
	} else if singleWaitCounts[winIdx] == 1 && singleWaitWilds >= 1 {
		singleWaitCounts[winIdx] -= 1
		if r.checkMeldsFast(&singleWaitCounts, 0, singleWaitWilds-1, true) {
			return 1
		}
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
		if isValidHand(pairCallCounts, pairCallWilds) {
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
			// The original win tile is already implicitly consumed since we started from the 13-tile hand
			// and conceptually combined valA, winTile, valB into a meld.
			return isValidHand(testCounts, testWilds)
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

func resolveTsumoWinTile(hand []*pb.Tile, state *pb.GameState, playerSeat uint32) *pb.Tile {
	if state == nil || int(playerSeat) >= len(state.Players) || state.Players[playerSeat] == nil {
		return nil
	}

	drawnTileID := state.Players[playerSeat].DrawnTileId
	if drawnTileID == nil {
		return nil
	}

	for _, tile := range hand {
		if int32(tile.Id) == *drawnTileID {
			return tile
		}
	}

	return nil
}
