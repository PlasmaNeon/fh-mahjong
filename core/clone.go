package core

import (
	pb "github.com/plasma/fh-mahjong/proto"
	"google.golang.org/protobuf/proto"
)

// CloneForBranch returns an isolated copy of the game state machine for
// deterministic what-if rollouts. The clone intentionally drops the paipu
// recorder and interrupt timer so branch evaluation cannot write replay logs or
// schedule asynchronous resolution.
func (g *Game) CloneForBranch() *Game {
	if g == nil {
		return nil
	}

	cloned := &Game{
		Rules:              g.Rules,
		wallIndex:          g.wallIndex,
		deadWallIndex:      g.deadWallIndex,
		wangpaiBoundary:    g.wangpaiBoundary,
		wildIndicatorIndex: g.wildIndicatorIndex,
		haiteiDrawIndex:    g.haiteiDrawIndex,
		interruptQueue:     cloneInterruptQueue(g.interruptQueue),
		wallSeedOverride:   cloneSeedOverride(g.wallSeedOverride),
		nextDealerOverride: cloneDealerOverride(g.nextDealerOverride),
	}
	if g.State != nil {
		cloned.State = proto.Clone(g.State).(*pb.GameState)
	}
	cloned.wall = cloneWall(g.wall)
	return cloned
}

func cloneWall(wall []*pb.Tile) []*pb.Tile {
	if len(wall) == 0 {
		return nil
	}
	cloned := make([]*pb.Tile, len(wall))
	for i, tile := range wall {
		if tile == nil {
			continue
		}
		cloned[i] = proto.Clone(tile).(*pb.Tile)
	}
	return cloned
}

func cloneInterruptQueue(queue map[uint32]*pb.PlayerAction) map[uint32]*pb.PlayerAction {
	cloned := make(map[uint32]*pb.PlayerAction, len(queue))
	for seat, action := range queue {
		if action == nil {
			cloned[seat] = nil
			continue
		}
		cloned[seat] = proto.Clone(action).(*pb.PlayerAction)
	}
	return cloned
}

func cloneSeedOverride(seed *[MT19937SeedSize]uint32) *[MT19937SeedSize]uint32 {
	if seed == nil {
		return nil
	}
	cloned := *seed
	return &cloned
}

func cloneDealerOverride(seat *uint32) *uint32 {
	if seat == nil {
		return nil
	}
	cloned := *seat
	return &cloned
}
