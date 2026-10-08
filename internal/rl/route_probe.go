package rl

import (
	"fmt"

	"github.com/plasma/fh-mahjong/internal/rules/shanten"
	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

// RouteProbe reports a seat's shanten on each hand route and, for every legal
// discard, the route shanten after it — the route study's view of a decision
// (fh-mj-benchmark --route-study). It only reads the live state.
func (e *Env) RouteProbe(request *pb.RouteProbeRequest) (*pb.RouteProbe, error) {
	if e.game == nil || e.game.State == nil {
		return nil, fmt.Errorf("environment must be reset before probing routes")
	}
	return routeProbe(e.game.State, request.GetSeat())
}

func routeProbe(state *pb.GameState, seat uint32) (*pb.RouteProbe, error) {
	if int(seat) >= len(state.Players) {
		return nil, fmt.Errorf("invalid seat %d", seat)
	}
	player := state.Players[seat]
	analysis := shanten.AnalyzeHand(player.ClosedHand, len(player.OpenMelds), state.WildTiles)
	legal, err := legalActionMap(state, seat)
	if err != nil {
		return nil, err
	}
	options := make(map[int]shanten.DiscardOption, len(analysis.DiscardOptions))
	for _, option := range analysis.DiscardOptions {
		if face, ok := tileFaceIndex42(&pb.Tile{Suit: option.Discard.Suit, Value: option.Discard.Value}); ok {
			options[face] = option
		}
	}
	probe := &pb.RouteProbe{
		Seat:          seat,
		Routes:        routeShanten(analysis.Routes),
		WildCount:     uint32(tiles.CountWilds(player.ClosedHand, tiles.WildSet(state.WildTiles))),
		OpenMeldCount: uint32(len(player.OpenMelds)),
	}
	for _, actionID := range SortedLegalIDs(legal) {
		if actionID < DiscardBase || actionID >= DiscardBase+DiscardCount {
			continue
		}
		option, ok := options[actionID-DiscardBase]
		if !ok {
			return nil, fmt.Errorf("legal discard %d has no shanten option", actionID)
		}
		probe.Discards = append(probe.Discards, &pb.DiscardRoute{
			ActionId: uint32(actionID),
			After:    routeShanten(option.After),
			IsWild:   option.IsWild,
		})
	}
	return probe, nil
}

func routeShanten(routes shanten.RouteBreakdown) *pb.RouteShanten {
	return &pb.RouteShanten{
		Overall:      int32(routes.Overall),
		Standard:     int32(routes.Standard),
		SevenPairs:   int32(routes.SevenPairs),
		Independence: int32(routes.Independence),
	}
}
