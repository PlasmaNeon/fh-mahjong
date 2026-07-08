package rules

import (
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

// FenghuaRuleset implements the engine.RuleEngine interface.
type FenghuaRuleset struct{}

func (r *FenghuaRuleset) Name() string {
	return "Fenghua Rules"
}

func (r *FenghuaRuleset) GetInitialWall() []*pb.Tile {
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

	// Flower tiles (1=Spring/春, 2=Summer/夏, 3=Autumn/秋, 4=Winter/冬,
	//               5=Plum/梅, 6=Orchid/兰, 7=Chrysanthemum/菊, 8=Bamboo/竹)
	// 8 unique tiles, one of each
	for v := uint32(1); v <= 8; v++ {
		wall = append(wall, &pb.Tile{
			Id:    idCount,
			Suit:  pb.Suit_SUIT_FLOWER,
			Value: v,
		})
		idCount++
	}

	return wall
}

// EvaluateHand scores a candidate winning hand and reports whether it wins.
// It runs a fixed pipeline of stages, each owned by a handEvaluation method:
// base/wild bonuses, the best structural route, honor/suit extremes, flowers
// (including the eight-flower override), dragon/wind pungs, kong-completion
// bonuses, and finally the 4-point Ron minimum. Entry order is user-visible
// in the score breakdown, so stages append in this fixed order.
func (r *FenghuaRuleset) EvaluateHand(hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) (int32, []*pb.ScoreEntry, bool) {
	e := newHandEvaluation(r, hand, openMelds, winTile, state, playerSeat, isTsumo)

	entries := e.baseAndWildEntries()

	routeEntries, canWin := e.bestStructuralRoute()
	entries = append(entries, routeEntries...)

	entries, canWin = e.appendHonorSuitEntries(entries, canWin)
	entries, canWin = e.applyFlowers(entries, canWin)

	if !canWin {
		return 0, nil, false
	}

	entries = e.appendDragonAndWindEntries(entries)
	entries = e.appendKongFlagEntries(entries)

	totalPoints := int32(0)
	for _, entry := range entries {
		totalPoints += entry.Points
	}

	if !isTsumo && !meetsRonMinimum(entries) {
		return totalPoints, entries, false
	}

	return totalPoints, entries, true
}

// handEvaluation carries one EvaluateHand call's context through its stages.
type handEvaluation struct {
	rules            *FenghuaRuleset
	hand             []*pb.Tile
	fullHand         []*pb.Tile // hand + Ron win tile (tsumo hands already contain it)
	openMelds        []*pb.Meld
	winTile          *pb.Tile
	effectiveWinTile *pb.Tile // winTile, or the inferred drawn tile on tsumo
	state            *pb.GameState
	playerSeat       uint32
	isTsumo          bool

	wildHashes   map[uint32]bool
	wildsInHand  int
	isFlowerWild bool
	// hasWinningSize gates every normal structural route: the effective tile
	// count must be exactly 14 (each open meld, kongs included, stands in for
	// one three-tile component — replacement draws keep the arithmetic exact).
	// Eight Flowers is the explicit incomplete-hand exception.
	hasWinningSize bool
}

func newHandEvaluation(r *FenghuaRuleset, hand []*pb.Tile, openMelds []*pb.Meld, winTile *pb.Tile, state *pb.GameState, playerSeat uint32, isTsumo bool) *handEvaluation {
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

	e := &handEvaluation{
		rules:            r,
		hand:             hand,
		fullHand:         fullHand,
		openMelds:        openMelds,
		winTile:          winTile,
		effectiveWinTile: effectiveWinTile,
		state:            state,
		playerSeat:       playerSeat,
		isTsumo:          isTsumo,
		wildHashes:       make(map[uint32]bool),
		hasWinningSize:   len(fullHand)+3*len(openMelds) == 14,
	}

	if state != nil {
		e.wildHashes = tiles.WildSet(state.WildTiles)
		for _, w := range state.WildTiles {
			if w.Suit == pb.Suit_SUIT_UNKNOWN || w.Suit > pb.Suit_SUIT_JIHAI {
				e.isFlowerWild = true
			}
		}
	}
	// Count wild tiles (excluding Ron win tile — it acts as a normal tile)
	e.wildsInHand = tiles.CountWilds(hand, e.wildHashes)
	// If Tsumo, the drawn winning tile is part of our concealed hand and counts as wild
	if isTsumo && winTile != nil && e.wildHashes[tiles.KeyOf(winTile.Suit, winTile.Value)] {
		e.wildsInHand++
	}

	return e
}

// baseAndWildEntries emits the always-awarded base point, the tsumo bonus,
// the wild-count bonuses (无搭/一搭/二搭/三百搭), and the tame-wild bonus
// (还搭: the hand would also win with its wilds treated as normal tiles).
func (e *handEvaluation) baseAndWildEntries() []*pb.ScoreEntry {
	entries := make([]*pb.ScoreEntry, 0)

	entries = append(entries, NewScoreEntry(PatternBasePoint, 1))
	if e.isTsumo {
		entries = append(entries, NewScoreEntry(PatternTsumo, 1))
	}

	if e.wildsInHand == 0 {
		entries = append(entries, NewScoreEntry(PatternNoWildTiles, 1))
	} else if e.wildsInHand == 1 {
		entries = append(entries, NewScoreEntry(PatternOneWildTile, 1))
	} else if e.wildsInHand == 2 {
		entries = append(entries, NewScoreEntry(PatternTwoWildTiles, 2))
	} else if e.wildsInHand == 3 {
		if e.isFlowerWild {
			entries = append(entries, NewScoreEntry(PatternThreeFlowerWildTiles, 300))
		} else {
			entries = append(entries, NewScoreEntry(PatternThreeNormalWildTiles, 150))
		}
	}

	if e.isTameWild() {
		entries = append(entries, NewScoreEntry(PatternTameWildTiles, 1))
	}

	return entries
}

func (e *handEvaluation) isTameWild() bool {
	if e.wildsInHand == 0 {
		return false
	}
	emptyWilds := make(map[uint32]bool)
	return e.rules.canFormStandardHand(e.fullHand, emptyWilds, true) ||
		(len(e.openMelds) == 0 && e.rules.isSevenPairs(e.fullHand, emptyWilds)) ||
		(len(e.openMelds) == 0 && e.rules.isIndependence(e.fullHand, emptyWilds))
}

// scoredRoute is one mutually exclusive structural interpretation of the hand.
type scoredRoute struct {
	score   int32
	entries []*pb.ScoreEntry
}

func routeOf(entries []*pb.ScoreEntry) *scoredRoute {
	total := int32(0)
	for _, entry := range entries {
		total += entry.Points
	}
	return &scoredRoute{score: total, entries: entries}
}

// bestStructuralRoute evaluates the three mutually exclusive core shapes —
// Independence (大大胡), Seven Pairs (七对), Standard (4 melds + pair) — and
// returns the highest-scoring one. Ties keep the earlier route in that order.
func (e *handEvaluation) bestStructuralRoute() ([]*pb.ScoreEntry, bool) {
	var best *scoredRoute
	for _, route := range []*scoredRoute{e.independenceRoute(), e.sevenPairsRoute(), e.standardRoute()} {
		if route == nil {
			continue
		}
		if best == nil || route.score > best.score {
			best = route
		}
	}
	if best == nil {
		return nil, false
	}
	return best.entries, true
}

func (e *handEvaluation) independenceRoute() *scoredRoute {
	if !e.hasWinningSize || len(e.openMelds) != 0 || !e.rules.isIndependence(e.fullHand, e.wildHashes) {
		return nil
	}
	re := make([]*pb.ScoreEntry, 0)
	// Base Independence is always +50
	re = append(re, NewScoreEntry(PatternIndependence, 50))
	// Seven Stars bonus stacks on top (closed +100, open +50)
	if e.rules.hasAllSevenHonors(e.fullHand) {
		if e.isTsumo {
			re = append(re, NewScoreEntry(PatternClosedSevenStars, 100))
		} else {
			re = append(re, NewScoreEntry(PatternOpenSevenStars, 50))
		}
	}
	// Without-suit bonus stacks independently (+100), combinable with Seven Stars
	if e.rules.isMissingASuit(e.fullHand) {
		re = append(re, NewScoreEntry(PatternIndependenceMissingSuit, 100))
	}
	return routeOf(re)
}

func (e *handEvaluation) sevenPairsRoute() *scoredRoute {
	if !e.hasWinningSize || len(e.openMelds) != 0 || !e.rules.isSevenPairs(e.fullHand, e.wildHashes) {
		return nil
	}
	re := make([]*pb.ScoreEntry, 0)
	if e.wildsInHand == 0 {
		re = append(re, NewScoreEntry(PatternStraightSevenPairs, 150))
	} else {
		re = append(re, NewScoreEntry(PatternWildSevenPairs, 50))
	}
	if bombCount := e.rules.countIdenticalFours(e.fullHand); bombCount > 0 {
		if e.isTsumo {
			re = append(re, NewScoreEntry(PatternClosedBomb, 100))
		} else {
			re = append(re, NewScoreEntry(PatternOpenBomb, 50))
		}
	}
	return routeOf(re)
}

func (e *handEvaluation) standardRoute() *scoredRoute {
	if !e.hasWinningSize || !e.rules.canFormStandardHand(e.fullHand, e.wildHashes, true) {
		return nil
	}
	re := make([]*pb.ScoreEntry, 0)

	isAllPung := e.rules.isAllPung(e.fullHand, e.openMelds, e.wildHashes)
	isAllChow := e.rules.isAllChow(e.fullHand, e.openMelds, e.wildHashes)
	isPureSuit := e.rules.isPureOneSuit(e.fullHand, e.openMelds, e.wildHashes)
	isMixedSuit := e.rules.isMixedOneSuit(e.fullHand, e.openMelds, e.wildHashes)

	// Common Win (朋胡): four runs (sequences) and a pair of eyes.
	// Excluded when pure/mixed one-suit patterns apply (those are scored separately).
	if isAllChow && !isPureSuit && !isMixedSuit {
		re = append(re, NewScoreEntry(PatternCommonWin, 1))
	}

	// Wait pattern bonus — single wait/pair call (边嵌单吊对倒)
	if e.effectiveWinTile != nil && e.rules.evalWaitPattern(e.hand, e.effectiveWinTile, e.wildHashes) > 0 {
		re = append(re, NewScoreEntry(PatternSinglePairCall, 1))
	}
	if len(e.openMelds) == 4 {
		if e.wildsInHand == 0 {
			re = append(re, NewScoreEntry(PatternStraightLoner, 100))
		} else {
			re = append(re, NewScoreEntry(PatternWildLoner, 50))
		}
	}

	if isAllPung {
		if e.wildsInHand == 0 {
			re = append(re, NewScoreEntry(PatternStraightAllPung, 100))
		} else {
			re = append(re, NewScoreEntry(PatternWildAllPung, 50))
		}
	}

	return routeOf(re)
}

// appendHonorSuitEntries handles the honor/suit extremes: a structurally
// invalid all-honor hand can still win as 乱老头; a structural win upgrades
// with 清老头, 清一色, or 混一色.
func (e *handEvaluation) appendHonorSuitEntries(entries []*pb.ScoreEntry, canWin bool) ([]*pb.ScoreEntry, bool) {
	if !canWin {
		if e.rules.isUncompletedAllHonors(e.fullHand, e.openMelds, e.wildHashes) {
			canWin = true
			entries = append(entries, NewScoreEntry(PatternUncompletedAllHonors, 400))
		}
		return entries, canWin
	}
	if e.rules.isCompletedAllHonors(e.fullHand, e.openMelds, e.wildHashes) {
		entries = append(entries, NewScoreEntry(PatternCompletedAllHonors, 800))
	} else if e.rules.isPureOneSuit(e.fullHand, e.openMelds, e.wildHashes) {
		entries = append(entries, NewScoreEntry(PatternPureOneSuit, 150))
	} else if e.rules.isMixedOneSuit(e.fullHand, e.openMelds, e.wildHashes) {
		entries = append(entries, NewScoreEntry(PatternMixedOneSuit, 70))
	}
	return entries, canWin
}

func (e *handEvaluation) myFlowers() []*pb.Tile {
	if e.state == nil || e.state.Players == nil {
		return nil
	}
	if int(e.playerSeat) >= len(e.state.Players) {
		return nil
	}
	ps := e.state.Players[e.playerSeat]
	if ps == nil {
		return nil
	}
	return ps.FlowerMelds
}

// applyFlowers emits the flower bonuses. Eight flowers on a non-winning hand
// is a direct win that OVERRIDES everything accumulated so far (八花直胡 is
// just 400 + own flowers); on a winning hand it stacks as 八花搓胡.
func (e *handEvaluation) applyFlowers(entries []*pb.ScoreEntry, canWin bool) ([]*pb.ScoreEntry, bool) {
	myFlowers := e.myFlowers()

	if len(myFlowers) == 8 {
		if !canWin {
			canWin = true
			entries = []*pb.ScoreEntry{NewScoreEntry(PatternUncompletedEightFlowers, 400)}
		} else {
			entries = append(entries, NewScoreEntry(PatternCompletedEightFlowers, 800))
		}
	} else if len(myFlowers) >= 4 {
		entries = append(entries, NewScoreEntry(PatternFourFlowers, 150))
	}

	if flowerBonus := getFlowerBonuses(myFlowers, e.playerSeat, e.state); flowerBonus > 0 {
		entries = append(entries, NewScoreEntry(PatternOwnFlower, flowerBonus))
	}

	return entries, canWin
}

// appendDragonAndWindEntries emits dragon-pung (中发白碰出) and wind-pung
// (正风/位风/圈风) bonuses.
func (e *handEvaluation) appendDragonAndWindEntries(entries []*pb.ScoreEntry) []*pb.ScoreEntry {
	if dragonPoints := e.rules.countDragonPungs(e.fullHand, e.openMelds, e.wildHashes); dragonPoints > 0 {
		entries = append(entries, NewScoreEntry(PatternDragonPung, dragonPoints))
	}

	if e.state == nil {
		return entries
	}
	var seatWind uint32
	if int(e.playerSeat) < len(e.state.Players) && e.state.Players[e.playerSeat] != nil {
		seatWind = e.state.Players[e.playerSeat].SeatWind
	}
	prevailingWind := e.state.PrevailingWind
	if seatWind > 0 && e.rules.hasPungOfValue(e.fullHand, e.openMelds, pb.Suit_SUIT_JIHAI, seatWind) {
		if seatWind == prevailingWind {
			entries = append(entries, NewScoreEntry(PatternRightWind, 2))
		} else {
			entries = append(entries, NewScoreEntry(PatternSeatWind, 1))
		}
	}
	if prevailingWind > 0 && prevailingWind != seatWind && e.rules.hasPungOfValue(e.fullHand, e.openMelds, pb.Suit_SUIT_JIHAI, prevailingWind) {
		entries = append(entries, NewScoreEntry(PatternPrevailingWind, 1))
	}
	return entries
}

// appendKongFlagEntries emits kong-completion bonuses from the player's flags.
// Budding and blooming are mutually exclusive per kong type: a kong that
// bloomed (won on its supplementary tile) scores the blooming bonus only.
func (e *handEvaluation) appendKongFlagEntries(entries []*pb.ScoreEntry) []*pb.ScoreEntry {
	if e.state == nil || int(e.playerSeat) >= len(e.state.Players) {
		return entries
	}
	ps := e.state.Players[e.playerSeat]
	if ps == nil {
		return entries
	}
	if ps.HasBloomingDirectKong {
		entries = append(entries, NewScoreEntry(PatternBloomingDirectKong, 100))
	} else if ps.HasBuddingDirectKong {
		entries = append(entries, NewScoreEntry(PatternBuddingDirectKong, 50))
	}
	if ps.HasBloomingClosedKong {
		entries = append(entries, NewScoreEntry(PatternBloomingClosedKong, 150))
	} else if ps.HasBuddingClosedKong {
		entries = append(entries, NewScoreEntry(PatternBuddingClosedKong, 100))
	}
	if ps.HasBloomingRiskyKong {
		entries = append(entries, NewScoreEntry(PatternBloomingRiskyKong, 200))
	} else if ps.HasBuddingRiskyKong {
		entries = append(entries, NewScoreEntry(PatternBuddingRiskyKong, 100))
	}
	if ps.HasBloomingFlowerKong {
		entries = append(entries, NewScoreEntry(PatternBloomingFlowerKong, 50))
	}
	return entries
}

// meetsRonMinimum enforces the Fenghua 4-point Ron minimum. Reward bonuses
// (Four Flowers, Own Flower, kan-completion bonuses) are awarded but do NOT
// count toward the minimum — they describe lucky tile collection, not the
// playing hand. Tsumo has no minimum (callers skip this check).
func meetsRonMinimum(entries []*pb.ScoreEntry) bool {
	qualifying := int32(0)
	for _, entry := range entries {
		if isRewardPattern(entry) {
			continue
		}
		qualifying += entry.Points
	}
	return qualifying >= 4
}

// isRewardPattern reports whether a scoring entry is a "reward" bonus
// (flower collection, kan completion) that is awarded but does not count
// toward the 4-point Ron minimum. Classified by stable pattern id, never by
// display name — see rewardPatternIds in patterns.go.
func isRewardPattern(entry *pb.ScoreEntry) bool {
	return rewardPatternIds[entry.PatternId]
}

// CalculatePayouts computes per-player payment amounts based on Fenghua rules.
// Tsumo: each of 3 losers pays S×2, winner receives S×6.
// Ron: discarder pays S×2, other two pay S×1, winner receives S×4.
func (r *FenghuaRuleset) CalculatePayouts(totalScore int32, winType pb.ActionType, winnerSeat uint32, discarderSeat uint32) []*pb.PlayerPayout {
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
func (r *FenghuaRuleset) isIndependence(hand []*pb.Tile, wildHashes map[uint32]bool) bool {
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
func (r *FenghuaRuleset) isSevenPairs(hand []*pb.Tile, wildHashes map[uint32]bool) bool {
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

// tilesToTehai34 converts a slice of tiles into a [34]int tehai count array (Mortal layout).
// Wild tiles are counted separately and excluded from the array.
// Returns (tehai counts, wild tile count).
func (r *FenghuaRuleset) tilesToTehai34(tileSlice []*pb.Tile, wildHashes map[uint32]bool) ([34]int, int) {
	var counts [34]int
	wilds := 0
	for _, t := range tileSlice {
		hash := tiles.KeyOf(t.Suit, t.Value)
		if wildHashes[hash] {
			wilds++
		} else if idx := tiles.Index34(t); idx >= 0 {
			counts[idx]++
		}
	}
	return counts, wilds
}

// canFormStandardHand determines if the tiles can form 4 melds (chii/pon/kan) and 1 pair.
// Uses a flat-array DFS/DP backtracking approach (Mortal-style tehai) with wild tile substitution.
// allowChow=false forces pon-only evaluation (for all-pon hand detection).
func (r *FenghuaRuleset) canFormStandardHand(hand []*pb.Tile, wildHashes map[uint32]bool, allowChow bool) bool {
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
func (r *FenghuaRuleset) checkMeldsFast(counts *[34]int, startIdx int, wilds int, allowChow bool) bool {
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

func (r *FenghuaRuleset) GetValidActions(state *pb.GameState, playerSeat uint32) []*pb.PlayerAction {
	var actions []*pb.PlayerAction

	player := state.Players[playerSeat]

	// --- Haitei restriction ---
	// During haitei, the player can only Tsumo (if winning) or Discard the drawn tile.
	// No Flower Reveal, no Kan, no other actions.
	if state.IsHaitei {
		// Check for Tsumo
		_, _, canWin := r.EvaluateHand(player.ClosedHand, player.OpenMelds, nil, state, playerSeat, true)
		if canWin {
			actions = append(actions, &pb.PlayerAction{
				Type: pb.ActionType_ACTION_TSUMO,
			})
		}
		// Always allow discard (of the drawn tile)
		actions = append(actions, &pb.PlayerAction{
			Type: pb.ActionType_ACTION_DISCARD,
		})
		return actions
	}

	// Non-wild flowers are auto-revealed by the core state machine before valid
	// actions reach the client. Wild flowers stay in the closed hand normally.

	// The player can always discard
	actions = append(actions, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
	})

	// Tsumo is only legal if the player has actually drawn a tile this turn
	// (DrawnTileId set by wall draw / kan replacement / haitei accept). After
	// a Pon or Chii steal the player has not drawn, so the hand-completing tile
	// they took came from another seat's discard — that's a Ron, not a Tsumo,
	// and would have had to be declared at the interrupt window. Allowing
	// Tsumo here would let a player retroactively turn the discarded tile into
	// a self-draw and bypass the Ron's 4-point minimum (rules.md).
	if player.DrawnTileId != nil {
		_, _, canWin := r.EvaluateHand(player.ClosedHand, player.OpenMelds, nil, state, playerSeat, true)
		if canWin {
			actions = append(actions, &pb.PlayerAction{
				Type: pb.ActionType_ACTION_TSUMO,
			})
		}
	}

	// Check for Concealed Kongs (4 of a kind in hand).
	// Tiles in the closed hand each carry a unique instance Id, so we must
	// group by tile face (Suit+Value) to detect four of a kind.
	type faceKey struct {
		suit  pb.Suit
		value uint32
	}
	counts := make(map[faceKey][]*pb.Tile)
	for _, t := range player.ClosedHand {
		if t.Suit == pb.Suit_SUIT_FLOWER {
			continue
		}
		k := faceKey{t.Suit, t.Value}
		counts[k] = append(counts[k], t)
	}

	// Wild tiles (搭) cannot be used in a kan. A tile is wild when its face
	// (Suit+Value) matches one of this round's wild indicators.
	wildSet := tiles.WildSet(state.WildTiles)
	isWild := func(tile *pb.Tile) bool {
		return tile != nil && wildSet[tiles.KeyOf(tile.Suit, tile.Value)]
	}

	for face, tileGroup := range counts {
		// A concealed kong of a wild face is illegal (the kong would be all wilds).
		if len(tileGroup) == 4 && !wildSet[tiles.KeyOf(face.suit, face.value)] {
			actions = append(actions, &pb.PlayerAction{
				Type:      pb.ActionType_ACTION_KAN,
				MeldTiles: tileGroup,
			})
		}
	}

	// Upgraded (added) Kongs: add the matching 4th tile to an existing open Pon.
	// Skipped when the added tile is a wild, or when the Pon itself contains a wild
	// (a Pon melded from wild tiles at face value) — either way the resulting kong
	// would contain a wild tile, which the Fenghua rules forbid.
	for _, t := range player.ClosedHand {
		if isWild(t) {
			continue
		}
		for _, m := range player.OpenMelds {
			if m.Type != pb.ActionType_ACTION_PON || len(m.Tiles) == 0 {
				continue
			}
			if m.Tiles[0].Suit != t.Suit || m.Tiles[0].Value != t.Value {
				continue
			}
			if meldContainsWild(m, isWild) {
				continue
			}
			actions = append(actions, &pb.PlayerAction{
				Type:      pb.ActionType_ACTION_KAN,
				MeldTiles: []*pb.Tile{t},
			})
		}
	}

	return actions
}

// meldContainsWild reports whether any tile in the meld is a wild.
func meldContainsWild(m *pb.Meld, isWild func(*pb.Tile) bool) bool {
	for _, tile := range m.Tiles {
		if isWild(tile) {
			return true
		}
	}
	return false
}

func (r *FenghuaRuleset) GetValidInterrupts(state *pb.GameState, discardedTile *pb.Tile, playerSeat uint32) []*pb.PlayerAction {
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

	// 2. Check Kang (Needs 3 matching tiles). Wild tiles cannot be used in a kan;
	// the claimed tile and its 3 in-hand matches share a face, so a wild discard
	// would make the entire kong wild.
	discardIsWild := tiles.WildSet(state.WildTiles)[tiles.KeyOf(discardedTile.Suit, discardedTile.Value)]
	if len(matchingTiles) == 3 && !discardIsWild {
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

func (r *FenghuaRuleset) ResolveInterruptPriority(actions map[uint32]*pb.PlayerAction) (uint32, *pb.PlayerAction) {
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

	for seat := uint32(0); seat < 4; seat++ {
		action := actions[seat]
		if action == nil {
			continue
		}
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

func (r *FenghuaRuleset) hasAllSevenHonors(hand []*pb.Tile) bool {
	honorCounts := make(map[uint32]bool)
	for _, t := range hand {
		if t.Suit == pb.Suit_SUIT_JIHAI {
			honorCounts[t.Value] = true
		}
	}
	return len(honorCounts) == 7
}

func (r *FenghuaRuleset) isMissingASuit(hand []*pb.Tile) bool {
	suits := make(map[pb.Suit]bool)
	for _, t := range hand {
		if t.Suit != pb.Suit_SUIT_JIHAI {
			suits[t.Suit] = true
		}
	}
	// Missing at least one of the 3 main suits
	return len(suits) < 3
}

func (r *FenghuaRuleset) countIdenticalFours(hand []*pb.Tile) int {
	counts := make(map[uint32]int)
	bombs := 0
	for _, t := range hand {
		hash := tiles.KeyOf(t.Suit, t.Value)
		counts[hash]++
		if counts[hash] == 4 {
			bombs++
		}
	}
	return bombs
}

func (r *FenghuaRuleset) isAllPung(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
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
func (r *FenghuaRuleset) isAllChow(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
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
func (r *FenghuaRuleset) checkChowOnlyMelds(counts *[34]int, startIdx int, wilds int) bool {
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

func (r *FenghuaRuleset) isUncompletedAllHonors(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	// 乱老头 ignores meld structure, so it must enforce the 14-tile winning
	// size itself (each open meld stands in for 3 tiles; kong replacements
	// keep the arithmetic intact). Without this, a short all-honor/wild
	// hand — e.g. an empty hand plus a lone wild discard — counts as a win.
	if len(hand)+3*len(openMelds) != 14 {
		return false
	}
	for _, m := range openMelds {
		for _, t := range m.Tiles {
			if t.Suit != pb.Suit_SUIT_JIHAI {
				return false
			}
		}
	}
	for _, t := range hand {
		hash := tiles.KeyOf(t.Suit, t.Value)
		if wildHashes[hash] {
			continue // Wild tiles adapt to any jihai
		}
		if t.Suit != pb.Suit_SUIT_JIHAI {
			return false
		}
	}
	return true
}

func (r *FenghuaRuleset) isCompletedAllHonors(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	if !r.isUncompletedAllHonors(hand, openMelds, wildHashes) {
		return false
	}
	return r.canFormStandardHand(hand, wildHashes, true) || r.isSevenPairs(hand, wildHashes)
}

// isPureOneSuit checks for 清一色: all tiles from exactly one numbered suit (man/pin/sou, no jihai).
// Wild tiles are transparent — they do not break the suit constraint.
func (r *FenghuaRuleset) isPureOneSuit(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
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
		hash := tiles.KeyOf(t.Suit, t.Value)
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

func (r *FenghuaRuleset) isMixedOneSuit(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) bool {
	var targetSuit pb.Suit = pb.Suit_SUIT_UNKNOWN
	hasHonors := false
	hasSuit := false

	checkTile := func(t *pb.Tile) bool {
		hash := tiles.KeyOf(t.Suit, t.Value)
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
func (r *FenghuaRuleset) countDragonPungs(hand []*pb.Tile, openMelds []*pb.Meld, wildHashes map[uint32]bool) int32 {
	var points int32
	for _, dragonVal := range []uint32{5, 6, 7} {
		if r.hasPungOfValue(hand, openMelds, pb.Suit_SUIT_JIHAI, dragonVal) {
			points += 1
		}
	}
	return points
}

// hasPungOfValue checks if a pon (3+ tiles) of the given suit+value exists in hand or open melds.
func (r *FenghuaRuleset) hasPungOfValue(hand []*pb.Tile, openMelds []*pb.Meld, suit pb.Suit, value uint32) bool {
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
func (r *FenghuaRuleset) evalWaitPattern(hand []*pb.Tile, winTile *pb.Tile, wildHashes map[uint32]bool) int {
	if winTile == nil {
		return 0
	}

	counts, wilds := r.tilesToTehai34(hand, wildHashes)
	winIdx := tiles.Index34(winTile)
	if winIdx < 0 {
		return 0
	}
	winHash := tiles.KeyOf(winTile.Suit, winTile.Value)
	winIsWild := wildHashes[winHash]

	// If the hand contains 14 tiles (Tsumo case where winTile was already appended to ClosedHand),
	// we must remove the winTile from counts to evaluate the original 13-tile hand's wait pattern.
	if len(hand) == 14 {
		if winIsWild {
			wilds--
		} else if winIdx >= 0 && counts[winIdx] > 0 {
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

		idxA := tiles.Index34Of(winTile.Suit, valA)
		idxB := tiles.Index34Of(winTile.Suit, valB)
		if idxA < 0 || idxB < 0 {
			return false
		}

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
