package bot

import (
	"sort"

	pb "github.com/plasma/fh-mahjong/proto"
	"github.com/plasma/fh-mahjong/rules/shanten"
)

type Policy interface {
	ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction
}

type HeuristicPolicy struct{}

func NewHeuristicPolicy() *HeuristicPolicy {
	return &HeuristicPolicy{}
}

func (p *HeuristicPolicy) ChooseAction(state *pb.GameState, seat uint32) *pb.PlayerAction {
	if state == nil || int(seat) >= len(state.Players) {
		return nil
	}

	player := state.Players[seat]
	validActions := player.ValidActions
	if len(validActions) == 0 {
		return nil
	}

	if action := firstActionOfType(validActions, pb.ActionType_ACTION_TSUMO); action != nil {
		return action
	}
	if action := firstActionOfType(validActions, pb.ActionType_ACTION_RON); action != nil {
		return action
	}
	if action := firstActionOfType(validActions, pb.ActionType_ACTION_ACCEPT_HAITEI); action != nil {
		return action
	}

	currentAnalysis := shanten.AnalyzeHand(player.ClosedHand, len(player.OpenMelds), state.WildTiles)

	switch state.Phase {
	case pb.GamePhase_PHASE_PLAYER_TURN:
		if action := p.chooseTurnKan(player, currentAnalysis, state.WildTiles); action != nil {
			return action
		}
		return p.chooseDiscard(player, currentAnalysis, state.WildTiles)
	case pb.GamePhase_PHASE_WAIT_DISCARDS:
		if action := p.chooseInterruptKan(state, player, currentAnalysis); action != nil {
			return action
		}
		if action := p.chooseBestCall(state, seat, currentAnalysis); action != nil {
			return action
		}
		return &pb.PlayerAction{Type: pb.ActionType_ACTION_PASS}
	default:
		return nil
	}
}

func (p *HeuristicPolicy) chooseTurnKan(player *pb.PlayerState, current shanten.HandAnalysis, wildTiles []*pb.Tile) *pb.PlayerAction {
	var best *pb.PlayerAction
	for _, action := range player.ValidActions {
		if action.Type != pb.ActionType_ACTION_KAN {
			continue
		}
		if containsWildTile(action.MeldTiles, wildTiles) {
			continue
		}

		if len(action.MeldTiles) >= 4 {
			postHand := removeTiles(player.ClosedHand, action.MeldTiles)
			postRoutes := shanten.AnalyzeFromTiles(postHand, len(player.OpenMelds)+1, wildTiles)
			if postRoutes.Overall <= current.Routes.Overall {
				candidate := cloneAction(action)
				if best == nil || compareKanAction(candidate, best) < 0 {
					best = candidate
				}
			}
			continue
		}

		if current.Routes.Overall <= 0 {
			candidate := cloneAction(action)
			if best == nil || compareKanAction(candidate, best) < 0 {
				best = candidate
			}
		}
	}

	return best
}

func (p *HeuristicPolicy) chooseInterruptKan(state *pb.GameState, player *pb.PlayerState, current shanten.HandAnalysis) *pb.PlayerAction {
	if current.Routes.Overall > 0 {
		return nil
	}

	for _, action := range player.ValidActions {
		if action.Type != pb.ActionType_ACTION_KAN {
			continue
		}
		tiles := append([]*pb.Tile{}, action.MeldTiles...)
		if state.ActiveDiscard != nil {
			tiles = append(tiles, state.ActiveDiscard)
		}
		if containsWildTile(tiles, state.WildTiles) {
			continue
		}
		return cloneAction(action)
	}

	return nil
}

func (p *HeuristicPolicy) chooseBestCall(state *pb.GameState, seat uint32, current shanten.HandAnalysis) *pb.PlayerAction {
	player := state.Players[seat]
	bestRoute, unique := bestRoute(current.Routes)
	if unique && (bestRoute == routeSevenPairs || bestRoute == routeIndependence) {
		return nil
	}

	var bestCandidate *callCandidate
	for _, action := range player.ValidActions {
		if action.Type != pb.ActionType_ACTION_CHII && action.Type != pb.ActionType_ACTION_PON {
			continue
		}

		postHand := removeTiles(player.ClosedHand, action.MeldTiles)
		postAnalysis := shanten.AnalyzeHand(postHand, len(player.OpenMelds)+1, state.WildTiles)
		if len(postAnalysis.DiscardOptions) == 0 {
			continue
		}

		bestDiscard := p.bestDiscardOption(postHand, postAnalysis, state.WildTiles)
		if bestDiscard == nil {
			continue
		}

		if !callImproves(current, bestDiscard.option.After, bestDiscard.option.TotalUseful) {
			continue
		}

		candidate := &callCandidate{
			action:      cloneAction(action),
			postDiscard: bestDiscard.option,
		}
		if bestCandidate == nil || compareCallCandidate(candidate, bestCandidate) < 0 {
			bestCandidate = candidate
		}
	}

	if bestCandidate == nil {
		return nil
	}

	return bestCandidate.action
}

func (p *HeuristicPolicy) chooseDiscard(player *pb.PlayerState, current shanten.HandAnalysis, wildTiles []*pb.Tile) *pb.PlayerAction {
	best := p.bestDiscardOption(player.ClosedHand, current, wildTiles)
	if best == nil {
		return nil
	}

	return &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: best.tile,
	}
}

type discardChoice struct {
	tile   *pb.Tile
	option shanten.DiscardOption
	score  int
}

func (p *HeuristicPolicy) bestDiscardOption(hand []*pb.Tile, analysis shanten.HandAnalysis, wildTiles []*pb.Tile) *discardChoice {
	bestRoute, uniqueRoute := bestRoute(analysis.Routes)
	handCounts := tileTypeCounts(hand)

	var best *discardChoice
	for _, option := range analysis.DiscardOptions {
		tile := pickTileForDiscard(hand, option.Discard)
		if tile == nil {
			continue
		}

		damage := routeDamage(bestRoute, uniqueRoute, analysis.Routes, option.After)
		score := discardPreferenceScore(handCounts, option.Discard, option.IsWild)
		candidate := &discardChoice{
			tile:   tile,
			option: option,
			score:  score,
		}

		if best == nil || compareDiscardChoice(candidate, best, damage, routeDamage(bestRoute, uniqueRoute, analysis.Routes, best.option.After)) < 0 {
			best = candidate
		}
	}

	return best
}

func compareDiscardChoice(lhs, rhs *discardChoice, lhsDamage, rhsDamage int) int {
	if lhs.option.After.Overall != rhs.option.After.Overall {
		return lhs.option.After.Overall - rhs.option.After.Overall
	}
	if lhs.option.TotalUseful != rhs.option.TotalUseful {
		return rhs.option.TotalUseful - lhs.option.TotalUseful
	}
	if lhsDamage != rhsDamage {
		return lhsDamage - rhsDamage
	}
	if lhs.option.IsWild != rhs.option.IsWild {
		if lhs.option.IsWild {
			return 1
		}
		return -1
	}
	if lhs.score != rhs.score {
		return rhs.score - lhs.score
	}
	if lhs.tile.Suit != rhs.tile.Suit {
		return int(lhs.tile.Suit) - int(rhs.tile.Suit)
	}
	if lhs.tile.Value != rhs.tile.Value {
		return int(lhs.tile.Value - rhs.tile.Value)
	}
	return int(lhs.tile.Id - rhs.tile.Id)
}

func compareCallCandidate(lhs, rhs *callCandidate) int {
	if lhs.postDiscard.After.Overall != rhs.postDiscard.After.Overall {
		return lhs.postDiscard.After.Overall - rhs.postDiscard.After.Overall
	}
	if lhs.postDiscard.TotalUseful != rhs.postDiscard.TotalUseful {
		return rhs.postDiscard.TotalUseful - lhs.postDiscard.TotalUseful
	}
	if lhs.action.Type != rhs.action.Type {
		if lhs.action.Type == pb.ActionType_ACTION_PON {
			return -1
		}
		return 1
	}
	return compareActionTiles(lhs.action, rhs.action)
}

type callCandidate struct {
	action      *pb.PlayerAction
	postDiscard shanten.DiscardOption
}

func callImproves(current shanten.HandAnalysis, postRoutes shanten.RouteBreakdown, postUseful int) bool {
	if postRoutes.Overall < current.Routes.Overall {
		return true
	}

	return current.Routes.Overall == 0 && postRoutes.Overall == 0 && postUseful > current.TotalUseful
}

type routeKind int

const (
	routeStandard routeKind = iota
	routeSevenPairs
	routeIndependence
)

func bestRoute(routes shanten.RouteBreakdown) (routeKind, bool) {
	values := []struct {
		kind  routeKind
		value int
	}{
		{kind: routeStandard, value: routes.Standard},
		{kind: routeSevenPairs, value: routes.SevenPairs},
		{kind: routeIndependence, value: routes.Independence},
	}

	sort.Slice(values, func(i, j int) bool {
		return values[i].value < values[j].value
	})

	if len(values) < 2 || values[0].value == shanten.RouteUnavailable {
		return routeStandard, false
	}

	return values[0].kind, values[0].value < values[1].value
}

func routeDamage(route routeKind, unique bool, current, next shanten.RouteBreakdown) int {
	if !unique {
		return 0
	}

	switch route {
	case routeSevenPairs:
		return next.SevenPairs - current.SevenPairs
	case routeIndependence:
		return next.Independence - current.Independence
	default:
		return next.Standard - current.Standard
	}
}

func discardPreferenceScore(counts map[uint32]int, tile shanten.TileType, isWild bool) int {
	if isWild {
		return -1000
	}

	key := tileTypeHash(tile.Suit, tile.Value)
	count := counts[key]

	if tile.Suit == pb.Suit_SUIT_JIHAI {
		if count == 1 {
			return 80
		}
		if count == 2 {
			return 10
		}
		return 0
	}

	score := 0
	if count >= 2 {
		score -= 15
	}

	left2 := counts[tileTypeHash(tile.Suit, tile.Value-2)]
	left1 := counts[tileTypeHash(tile.Suit, tile.Value-1)]
	right1 := counts[tileTypeHash(tile.Suit, tile.Value+1)]
	right2 := counts[tileTypeHash(tile.Suit, tile.Value+2)]

	neighbors := left1 + right1
	extended := left2 + right2

	if neighbors == 0 {
		score += 45
	}
	if neighbors == 0 && extended == 0 {
		score += 15
	}

	if tile.Value == 1 || tile.Value == 9 {
		score += 15
	}
	if tile.Value == 2 || tile.Value == 8 {
		score += 8
	}

	if neighbors > 1 {
		score -= 20
	}

	return score
}

func containsWildTile(tiles []*pb.Tile, wildTiles []*pb.Tile) bool {
	wildSet := make(map[uint32]bool, len(wildTiles))
	for _, tile := range wildTiles {
		wildSet[tileTypeHash(tile.Suit, tile.Value)] = true
	}
	for _, tile := range tiles {
		if wildSet[tileTypeHash(tile.Suit, tile.Value)] {
			return true
		}
	}
	return false
}

func pickTileForDiscard(hand []*pb.Tile, target shanten.TileType) *pb.Tile {
	var best *pb.Tile
	for _, tile := range hand {
		if tile.Suit != target.Suit || tile.Value != target.Value {
			continue
		}
		if best == nil || tile.Id < best.Id {
			best = tile
		}
	}
	return best
}

func removeTiles(hand []*pb.Tile, remove []*pb.Tile) []*pb.Tile {
	remaining := make([]*pb.Tile, 0, len(hand))
	toRemove := make(map[uint32]int, len(remove))
	for _, tile := range remove {
		toRemove[tile.Id]++
	}
	for _, tile := range hand {
		if toRemove[tile.Id] > 0 {
			toRemove[tile.Id]--
			continue
		}
		remaining = append(remaining, tile)
	}
	return remaining
}

func tileTypeCounts(hand []*pb.Tile) map[uint32]int {
	counts := make(map[uint32]int)
	for _, tile := range hand {
		counts[tileTypeHash(tile.Suit, tile.Value)]++
	}
	return counts
}

func tileTypeHash(suit pb.Suit, value uint32) uint32 {
	return uint32(suit)*100 + value
}

func firstActionOfType(actions []*pb.PlayerAction, actionType pb.ActionType) *pb.PlayerAction {
	for _, action := range actions {
		if action.Type == actionType {
			return cloneAction(action)
		}
	}
	return nil
}

func cloneAction(action *pb.PlayerAction) *pb.PlayerAction {
	if action == nil {
		return nil
	}

	cloned := &pb.PlayerAction{
		Type:           action.Type,
		TargetPlayer:   action.TargetPlayer,
		IsRobbingKong:  action.IsRobbingKong,
		IsBottomTile:   action.IsBottomTile,
		IsBloomingKong: action.IsBloomingKong,
	}
	if action.Tile != nil {
		tile := *action.Tile
		cloned.Tile = &tile
	}
	if len(action.MeldTiles) > 0 {
		cloned.MeldTiles = make([]*pb.Tile, len(action.MeldTiles))
		for i, tile := range action.MeldTiles {
			if tile == nil {
				continue
			}
			copyTile := *tile
			cloned.MeldTiles[i] = &copyTile
		}
	}
	return cloned
}

func compareKanAction(lhs, rhs *pb.PlayerAction) int {
	if len(lhs.MeldTiles) != len(rhs.MeldTiles) {
		return len(lhs.MeldTiles) - len(rhs.MeldTiles)
	}
	return compareActionTiles(lhs, rhs)
}

func compareActionTiles(lhs, rhs *pb.PlayerAction) int {
	idsL := make([]uint32, 0, len(lhs.MeldTiles))
	for _, tile := range lhs.MeldTiles {
		idsL = append(idsL, tile.Id)
	}
	idsR := make([]uint32, 0, len(rhs.MeldTiles))
	for _, tile := range rhs.MeldTiles {
		idsR = append(idsR, tile.Id)
	}
	sort.Slice(idsL, func(i, j int) bool { return idsL[i] < idsL[j] })
	sort.Slice(idsR, func(i, j int) bool { return idsR[i] < idsR[j] })
	for i := 0; i < len(idsL) && i < len(idsR); i++ {
		if idsL[i] != idsR[i] {
			if idsL[i] < idsR[i] {
				return -1
			}
			return 1
		}
	}
	return len(idsL) - len(idsR)
}
