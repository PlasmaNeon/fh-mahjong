package engine

import (
	"fmt"
	"math/rand"

	pb "github.com/plasma/fh-mahjong/proto"
)

// RedealUnseen re-deals everything the acting seat cannot see: the three
// opponents' concealed hands and every undrawn wall tile are collected into
// one pool, shuffled with the given seed, and dealt back into the same slots.
// Everything visible to the acting seat stays fixed: its own hand, all open
// melds, flower melds, discards, the wild indicator, scores, and the wall
// count/geometry (wangpai boundary, consumed dead-wall indices, haitei index
// are positions — only undrawn tile identities move).
//
// Two hidden-information details are part of the contract:
//   - An opponent's DrawnTileId (private) is positionally remapped to the tile
//     now occupying the same slot of their hand, so engine logic never points
//     at a tile id that moved elsewhere.
//   - The interrupt queue is CLEARED: queued-but-unresolved opponent responses
//     are themselves hidden information; a rollout re-asks those seats.
//
// Intended for use on CloneForBranch clones (search determinization), never on
// a live game.
func (g *Game) RedealUnseen(actingSeat uint32, seed uint64) error {
	if g == nil || g.State == nil {
		return fmt.Errorf("redeal: nil game state")
	}
	if int(actingSeat) >= len(g.State.Players) {
		return fmt.Errorf("redeal: invalid acting seat %d", actingSeat)
	}

	// 1. Collect the unseen pool.
	var pool []*pb.Tile
	for s, p := range g.State.Players {
		if uint32(s) == actingSeat {
			continue
		}
		pool = append(pool, p.ClosedHand...)
	}
	wallIdx := g.undrawnWallIndices()
	for _, i := range wallIdx {
		pool = append(pool, g.wall[i])
	}

	// 2. Seeded shuffle (plain math/rand: search determinism, not wall replay).
	rng := rand.New(rand.NewSource(int64(seed)))
	rng.Shuffle(len(pool), func(i, j int) { pool[i], pool[j] = pool[j], pool[i] })

	// 3. Deal back: opponents' hands first (seat ascending, positional), then
	// undrawn wall slots ascending.
	k := 0
	for s, p := range g.State.Players {
		if uint32(s) == actingSeat {
			continue
		}
		var drawnPos = -1
		if p.DrawnTileId != nil {
			for pos, tile := range p.ClosedHand {
				if int32(tile.Id) == *p.DrawnTileId {
					drawnPos = pos
					break
				}
			}
		}
		for pos := range p.ClosedHand {
			p.ClosedHand[pos] = pool[k]
			k++
		}
		if drawnPos >= 0 {
			remapped := int32(p.ClosedHand[drawnPos].Id)
			p.DrawnTileId = &remapped
		}
	}
	for _, i := range wallIdx {
		g.wall[i] = pool[k]
		k++
	}

	// 4. Queued interrupt responses are hidden information — drop them.
	g.interruptQueue = make(map[uint32]*pb.PlayerAction)
	return nil
}

// undrawnWallIndices lists wall positions whose tiles are still hidden: not
// yet front-drawn, not the face-up wild indicator, not consumed by a
// dead-wall draw, and not an already-drawn haitei tile.
func (g *Game) undrawnWallIndices() []int {
	var out []int
	for i := g.wallIndex; i < len(g.wall); i++ {
		if i == g.wildIndicatorIndex {
			continue
		}
		if g.isTileConsumedByDeadWall(i) {
			continue
		}
		if g.haiteiDrawIndex >= 0 && i == g.haiteiDrawIndex {
			continue
		}
		out = append(out, i)
	}
	return out
}

// WallTilesForTest returns the undrawn wall tiles (test support: redeal
// conservation checks). Not for gameplay use.
func (g *Game) WallTilesForTest() []*pb.Tile {
	idx := g.undrawnWallIndices()
	out := make([]*pb.Tile, 0, len(idx))
	for _, i := range idx {
		out = append(out, g.wall[i])
	}
	return out
}

// WildIndicatorForTest returns the face-up wild indicator tile (test support).
func (g *Game) WildIndicatorForTest() *pb.Tile { return g.wall[g.wildIndicatorIndex] }
