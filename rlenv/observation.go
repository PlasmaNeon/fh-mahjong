package rlenv

import (
	"math"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules/shanten"
)

const (
	ObservationPlaneChannels = 39
	ObservationPlaneHeight   = 42
	ObservationPlaneWidth    = 1
	ObservationScalarCount   = 42
)

func encodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64) (*pb.SeatObservation, error) {
	mask, err := actionMask(state, seat)
	if err != nil {
		return nil, err
	}

	planes := make([]float32, ObservationPlaneChannels*ObservationPlaneHeight*ObservationPlaneWidth)
	scalars := make([]float32, ObservationScalarCount)

	self := state.Players[seat]
	rightSeat := (seat + 1) % 4
	acrossSeat := (seat + 2) % 4
	leftSeat := (seat + 3) % 4

	selfClosed := faceCountsFromTiles(self.ClosedHand)
	selfOpen := faceCountsFromMelds(self.OpenMelds)
	selfFlowers := faceCountsFromTiles(self.FlowerMelds)
	selfDiscards := faceCountsFromTiles(self.Discards)

	right := state.Players[rightSeat]
	rightOpen := faceCountsFromMelds(right.OpenMelds)
	rightFlowers := faceCountsFromTiles(right.FlowerMelds)
	rightDiscards := faceCountsFromTiles(right.Discards)

	across := state.Players[acrossSeat]
	acrossOpen := faceCountsFromMelds(across.OpenMelds)
	acrossFlowers := faceCountsFromTiles(across.FlowerMelds)
	acrossDiscards := faceCountsFromTiles(across.Discards)

	left := state.Players[leftSeat]
	leftOpen := faceCountsFromMelds(left.OpenMelds)
	leftFlowers := faceCountsFromTiles(left.FlowerMelds)
	leftDiscards := faceCountsFromTiles(left.Discards)

	setThresholdPlanes(planes, 0, selfClosed)
	setThresholdPlanes(planes, 4, selfOpen)
	setRawCountPlane(planes, 8, selfFlowers, 1)
	setRawCountPlane(planes, 9, selfDiscards, 4)

	setThresholdPlanes(planes, 10, rightOpen)
	setRawCountPlane(planes, 14, rightFlowers, 1)
	setRawCountPlane(planes, 15, rightDiscards, 4)

	setThresholdPlanes(planes, 16, acrossOpen)
	setRawCountPlane(planes, 20, acrossFlowers, 1)
	setRawCountPlane(planes, 21, acrossDiscards, 4)

	setThresholdPlanes(planes, 22, leftOpen)
	setRawCountPlane(planes, 26, leftFlowers, 1)
	setRawCountPlane(planes, 27, leftDiscards, 4)

	setPresencePlane(planes, 28, faceCountsFromTile(state.ActiveDiscard))
	setPresencePlane(planes, 29, faceCountsFromTiles(state.WildTiles))
	setActionFamilyPlane(planes, 30, mask, "discard")
	setActionFamilyPlane(planes, 31, mask, "pon")
	setActionFamilyPlane(planes, 32, mask, "kan-direct")
	setActionFamilyPlane(planes, 33, mask, "kan-closed")
	setActionFamilyPlane(planes, 34, mask, "kan-upgraded")
	setActionFamilyPlane(planes, 35, mask, "chii")
	setRawCountPlane(planes, 36, selfClosed, 4)
	setRawCountPlane(planes, 37, publicSeenCounts(state), 4)
	setRawCountPlane(planes, 38, aggregateDiscards(state), 4)

	scalars[0] = normalizeUint(self.SeatWind, 4)
	scalars[1] = normalizeUint(state.PrevailingWind, 4)
	scalars[2] = float32(relativeSeat(seat, state.ActivePlayer)) / 3.0
	scalars[3] = float32(state.Phase) / 4.0
	scalars[4] = float32(state.WallCount) / 144.0
	scalars[5] = float32(state.WangpaiTilesLeft) / 24.0
	scalars[6] = float32(state.DiceSum) / 12.0
	if state.IsHaitei {
		scalars[7] = 1
	}
	scalars[8] = float32(self.HandSize) / 14.0
	scalars[9] = normalizeScore(self.Score)
	scalars[10] = float32(len(self.OpenMelds)) / 4.0
	scalars[11] = float32(len(self.FlowerMelds)) / 8.0
	scalars[12] = float32(right.HandSize) / 14.0
	scalars[13] = normalizeScore(right.Score)
	scalars[14] = float32(len(right.OpenMelds)) / 4.0
	scalars[15] = float32(len(right.FlowerMelds)) / 8.0
	scalars[16] = float32(across.HandSize) / 14.0
	scalars[17] = normalizeScore(across.Score)
	scalars[18] = float32(len(across.OpenMelds)) / 4.0
	scalars[19] = float32(len(across.FlowerMelds)) / 8.0
	scalars[20] = float32(left.HandSize) / 14.0
	scalars[21] = normalizeScore(left.Score)
	scalars[22] = float32(len(left.OpenMelds)) / 4.0
	scalars[23] = float32(len(left.FlowerMelds)) / 8.0
	if faceIndex, ok := tileFaceIndex42(state.ActiveDiscard); ok {
		scalars[24] = float32(faceIndex) / 41.0
	}
	selfAnalysis := shanten.AnalyzeHand(self.ClosedHand, len(self.OpenMelds), state.WildTiles)
	scalars[25] = normalizeShanten(selfAnalysis.Routes.Overall)
	scalars[26] = float32(len(right.Discards)) / 40.0
	scalars[27] = float32(len(across.Discards)) / 40.0
	scalars[28] = float32(len(left.Discards)) / 40.0
	scalars[29] = normalizeShanten(selfAnalysis.Routes.Standard)
	scalars[30] = normalizeShanten(selfAnalysis.Routes.SevenPairs)
	scalars[31] = normalizeShanten(selfAnalysis.Routes.Independence)
	scalars[32] = normalizeUsefulTileCount(selfAnalysis.TotalUseful)

	bestDiscard := bestVisibleDiscardLookahead(selfAnalysis)
	if bestDiscard != nil {
		scalars[33] = normalizeShanten(bestDiscard.After.Overall)
		scalars[34] = normalizeUsefulTileCount(bestDiscard.TotalUseful)
		scalars[35] = normalizeRouteDelta(bestDiscard.After.Overall - selfAnalysis.Routes.Overall)
		if bestDiscard.IsWild {
			scalars[37] = 1
		}
		if discardTile := tileFromType(bestDiscard.Discard); discardTile != nil {
			scalars[40] = publicDangerScore(state, seat, discardTile)
		}
	}
	scalars[36] = float32(countWildTiles(self.ClosedHand, state.WildTiles)) / 4.0
	scalars[38] = visibleScorePotential(self, selfAnalysis, state.WildTiles)
	if state.ActiveDiscard != nil {
		scalars[39] = publicDangerScore(state, seat, state.ActiveDiscard)
	}
	scalars[41] = legalDiscardDangerRange(state, seat, mask)

	return &pb.SeatObservation{
		Seat:            seat,
		Planes:          planes,
		PlaneChannels:   ObservationPlaneChannels,
		PlaneHeight:     ObservationPlaneHeight,
		PlaneWidth:      ObservationPlaneWidth,
		Scalars:         scalars,
		ActionMask:      mask,
		ActionSpaceSize: ActionSpaceSize,
		DecisionIndex:   decisionIndex,
		Phase:           state.Phase,
		ActivePlayer:    state.ActivePlayer,
	}, nil
}

func EncodeObservation(state *pb.GameState, seat uint32, decisionIndex uint64) (*pb.SeatObservation, error) {
	return encodeObservation(state, seat, decisionIndex)
}

func emptyObservation(state *pb.GameState, decisionIndex uint64) *pb.SeatObservation {
	activePlayer := uint32(0)
	phase := pb.GamePhase_PHASE_INIT
	if state != nil {
		activePlayer = state.ActivePlayer
		phase = state.Phase
	}

	return &pb.SeatObservation{
		Seat:            activePlayer,
		Planes:          make([]float32, ObservationPlaneChannels*ObservationPlaneHeight*ObservationPlaneWidth),
		PlaneChannels:   ObservationPlaneChannels,
		PlaneHeight:     ObservationPlaneHeight,
		PlaneWidth:      ObservationPlaneWidth,
		Scalars:         make([]float32, ObservationScalarCount),
		ActionMask:      make([]byte, ActionSpaceSize),
		ActionSpaceSize: ActionSpaceSize,
		DecisionIndex:   decisionIndex,
		Phase:           phase,
		ActivePlayer:    activePlayer,
	}
}

func faceCountsFromTile(tile *pb.Tile) [42]int {
	var counts [42]int
	if faceIndex, ok := tileFaceIndex42(tile); ok {
		counts[faceIndex]++
	}
	return counts
}

func faceCountsFromTiles(tiles []*pb.Tile) [42]int {
	var counts [42]int
	for _, tile := range tiles {
		if faceIndex, ok := tileFaceIndex42(tile); ok {
			counts[faceIndex]++
		}
	}
	return counts
}

func faceCountsFromMelds(melds []*pb.Meld) [42]int {
	var counts [42]int
	for _, meld := range melds {
		for _, tile := range meld.Tiles {
			if faceIndex, ok := tileFaceIndex42(tile); ok {
				counts[faceIndex]++
			}
		}
	}
	return counts
}

func setThresholdPlanes(planes []float32, baseChannel int, counts [42]int) {
	for threshold := 1; threshold <= 4; threshold++ {
		channel := baseChannel + threshold - 1
		for faceIndex, count := range counts {
			if count >= threshold {
				planes[channelOffset(channel)+faceIndex] = 1
			}
		}
	}
}

func setRawCountPlane(planes []float32, channel int, counts [42]int, denom float32) {
	if denom <= 0 {
		denom = 1
	}
	for faceIndex, count := range counts {
		planes[channelOffset(channel)+faceIndex] = float32(count) / denom
	}
}

func setPresencePlane(planes []float32, channel int, counts [42]int) {
	for faceIndex, count := range counts {
		if count > 0 {
			planes[channelOffset(channel)+faceIndex] = 1
		}
	}
}

func setActionFamilyPlane(planes []float32, channel int, mask []byte, family string) {
	switch family {
	case "discard":
		for actionID := DiscardBase; actionID < DiscardBase+DiscardCount; actionID++ {
			if mask[actionID] == 1 {
				planes[channelOffset(channel)+(actionID-DiscardBase)] = 1
			}
		}
	case "pon":
		for actionID := PonBase; actionID < PonBase+PonCount; actionID++ {
			if mask[actionID] == 1 {
				planes[channelOffset(channel)+(actionID-PonBase)] = 1
			}
		}
	case "kan-direct":
		for actionID := KanDirectBase; actionID < KanDirectBase+KanModeCount; actionID++ {
			if mask[actionID] == 1 {
				planes[channelOffset(channel)+(actionID-KanDirectBase)] = 1
			}
		}
	case "kan-closed":
		for actionID := KanClosedBase; actionID < KanClosedBase+KanModeCount; actionID++ {
			if mask[actionID] == 1 {
				planes[channelOffset(channel)+(actionID-KanClosedBase)] = 1
			}
		}
	case "kan-upgraded":
		for actionID := KanUpgradedBase; actionID < KanUpgradedBase+KanModeCount; actionID++ {
			if mask[actionID] == 1 {
				planes[channelOffset(channel)+(actionID-KanUpgradedBase)] = 1
			}
		}
	case "chii":
		for actionID := ChiiBase; actionID < ChiiBase+ChiiCount; actionID++ {
			if mask[actionID] != 1 {
				continue
			}
			seqIndex := actionID - ChiiBase
			suitOffset := (seqIndex / 7) * 9
			start := seqIndex % 7
			for offset := 0; offset < 3; offset++ {
				planes[channelOffset(channel)+suitOffset+start+offset] = 1
			}
		}
	}
}

func publicSeenCounts(state *pb.GameState) [42]int {
	var counts [42]int
	for _, player := range state.Players {
		addCounts(&counts, faceCountsFromTiles(player.Discards))
		addCounts(&counts, faceCountsFromMelds(player.OpenMelds))
		addCounts(&counts, faceCountsFromTiles(player.FlowerMelds))
	}
	addCounts(&counts, faceCountsFromTile(state.ActiveDiscard))
	addCounts(&counts, faceCountsFromTiles(state.WildTiles))
	return counts
}

func aggregateDiscards(state *pb.GameState) [42]int {
	var counts [42]int
	for _, player := range state.Players {
		addCounts(&counts, faceCountsFromTiles(player.Discards))
	}
	return counts
}

func addCounts(dst *[42]int, src [42]int) {
	for i, count := range src {
		dst[i] += count
	}
}

func bestVisibleDiscardLookahead(analysis shanten.HandAnalysis) *shanten.DiscardOption {
	if len(analysis.DiscardOptions) == 0 {
		return nil
	}
	return &analysis.DiscardOptions[0]
}

func countWildTiles(tiles []*pb.Tile, wildTiles []*pb.Tile) int {
	wildSet := make(map[uint32]bool, len(wildTiles))
	for _, tile := range wildTiles {
		wildSet[tileTypeKey(tile)] = true
	}

	count := 0
	for _, tile := range tiles {
		if wildSet[tileTypeKey(tile)] {
			count++
		}
	}
	return count
}

func tileFromType(tileType shanten.TileType) *pb.Tile {
	if tileType.Suit == pb.Suit_SUIT_UNKNOWN || tileType.Value == 0 {
		return nil
	}
	return &pb.Tile{Suit: tileType.Suit, Value: tileType.Value}
}

func visibleScorePotential(player *pb.PlayerState, analysis shanten.HandAnalysis, wildTiles []*pb.Tile) float32 {
	if player == nil {
		return 0
	}

	score := 1 + len(player.FlowerMelds)
	wildCount := countWildTiles(player.ClosedHand, wildTiles)
	switch {
	case wildCount >= 3:
		score += 50
	case wildCount == 2:
		score += 2
	case wildCount == 1:
		score += 1
	default:
		score += 1
	}

	if len(player.OpenMelds) == 0 {
		score += 2
	}
	if analysis.Routes.Standard <= 0 {
		score += 5
	}
	if analysis.Routes.SevenPairs <= 1 {
		score += 20
	}
	if analysis.Routes.Independence <= 1 {
		score += 20
	}

	return clamp01(float32(score) / 100.0)
}

func publicDangerScore(state *pb.GameState, observerSeat uint32, tile *pb.Tile) float32 {
	if state == nil || tile == nil {
		return 0
	}

	seen := publicSeenCounts(state)
	faceIndex, ok := tileFaceIndex42(tile)
	if !ok {
		return 0
	}

	danger := float32(0.2)
	seenCopies := seen[faceIndex]
	switch {
	case seenCopies <= 0:
		danger += 0.3
	case seenCopies == 1:
		danger += 0.18
	case seenCopies == 2:
		danger += 0.08
	default:
		danger -= 0.05
	}

	for offset := uint32(1); offset < 4; offset++ {
		opponentSeat := (observerSeat + offset) % 4
		if int(opponentSeat) >= len(state.Players) {
			continue
		}
		opponent := state.Players[opponentSeat]
		danger += float32(len(opponent.OpenMelds)) * 0.04
		if len(opponent.Discards) < 12 {
			danger += float32(12-len(opponent.Discards)) * 0.01
		}
		if opponent.HandSize <= 4 {
			danger += 0.04
		}
	}

	return clamp01(danger)
}

func legalDiscardDangerRange(state *pb.GameState, seat uint32, mask []byte) float32 {
	if state == nil || int(seat) >= len(state.Players) {
		return 0
	}

	minDanger := float32(1)
	maxDanger := float32(0)
	found := false
	for actionID := DiscardBase; actionID < DiscardBase+DiscardCount && actionID < len(mask); actionID++ {
		if mask[actionID] != 1 {
			continue
		}
		tile := firstTileForFace(state.Players[seat].ClosedHand, actionID-DiscardBase)
		if tile == nil {
			continue
		}
		danger := publicDangerScore(state, seat, tile)
		if danger < minDanger {
			minDanger = danger
		}
		if danger > maxDanger {
			maxDanger = danger
		}
		found = true
	}
	if !found {
		return 0
	}
	return clamp01(maxDanger - minDanger)
}

func firstTileForFace(tiles []*pb.Tile, faceIndex int) *pb.Tile {
	for _, tile := range tiles {
		if index, ok := tileFaceIndex42(tile); ok && index == faceIndex {
			return tile
		}
	}
	return nil
}

func channelOffset(channel int) int {
	return channel * ObservationPlaneHeight * ObservationPlaneWidth
}

func relativeSeat(observer uint32, target uint32) uint32 {
	return (target + 4 - observer) % 4
}

func normalizeUint(value uint32, denom float32) float32 {
	if denom <= 0 {
		return 0
	}
	return float32(value) / denom
}

func normalizeScore(score int32) float32 {
	return float32(score) / 50000.0
}

func normalizeShanten(value int) float32 {
	if value == shanten.RouteUnavailable {
		return 1
	}
	clamped := float32(maxInt(-1, minInt(8, value)) + 1)
	return clamped / 9.0
}

func normalizeUsefulTileCount(value int) float32 {
	return clamp01(float32(maxInt(0, value)) / 64.0)
}

func normalizeRouteDelta(value int) float32 {
	return clamp01((float32(maxInt(-4, minInt(4, value))) + 4.0) / 8.0)
}

func tileTypeKey(tile *pb.Tile) uint32 {
	if tile == nil {
		return 0
	}
	return uint32(tile.Suit)*100 + tile.Value
}

func clamp01(value float32) float32 {
	if value < 0 {
		return 0
	}
	if value > 1 {
		return 1
	}
	return value
}

func minInt(lhs int, rhs int) int {
	if lhs < rhs {
		return lhs
	}
	return rhs
}

func maxInt(lhs int, rhs int) int {
	if lhs > rhs {
		return lhs
	}
	return rhs
}

func cloneObservation(observation *pb.SeatObservation) *pb.SeatObservation {
	if observation == nil {
		return nil
	}

	return &pb.SeatObservation{
		Seat:            observation.Seat,
		Planes:          append([]float32(nil), observation.Planes...),
		PlaneChannels:   observation.PlaneChannels,
		PlaneHeight:     observation.PlaneHeight,
		PlaneWidth:      observation.PlaneWidth,
		Scalars:         append([]float32(nil), observation.Scalars...),
		ActionMask:      append([]byte(nil), observation.ActionMask...),
		ActionSpaceSize: observation.ActionSpaceSize,
		DecisionIndex:   observation.DecisionIndex,
		Phase:           observation.Phase,
		ActivePlayer:    observation.ActivePlayer,
	}
}

func almostEqualSlices(lhs []float32, rhs []float32) bool {
	if len(lhs) != len(rhs) {
		return false
	}
	for i := range lhs {
		if math.Abs(float64(lhs[i]-rhs[i])) > 1e-6 {
			return false
		}
	}
	return true
}
