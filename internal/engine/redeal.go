package engine

import (
	"fmt"
	"math/rand"
	"sort"

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
// Because the reshuffle moves every non-acting seat's tiles, their precomputed
// ValidActions (interrupt options that reference specific tile ids) become
// stale. Serving a stale meld interrupt would corrupt the hand — ResolveInterrupts
// removes MeldTiles by id-match, finds none in the new hand, and appends a
// phantom open meld without reducing the closed hand (duplicate tile ids). So
// after the redeal we refresh each non-acting seat's ValidActions against its new
// hand: at an open WAIT_DISCARDS window we recompute interrupts via the injected
// RuleEngine (the exact call offerInterrupts makes), applying the same haitei
// Ron-only filter offerInterrupts applies (shared via filterRonOnlyInterrupts)
// so a fork landing inside a haitei interrupt window never offers Chii/Pon/Kan;
// in any other phase we clear them (opponents hold no interrupts mid-turn; only
// stale entries could remain). The acting seat's ValidActions are left untouched
// — its hand did not move. The ACTIVE DISCARDER is also excluded from the
// open-window recompute and its ValidActions cleared: a player never interrupts
// its own discard (offerInterrupts always clears the discarder), and leaving it
// a freshly computed interrupt would inflate the window's expected-response
// count into a state the live engine can never reach.
//
// The refresh recomputes for EVERY non-acting seat, regardless of whether its
// PRE-redeal ValidActions were empty. Interrupt eligibility derives from the
// hidden hand, so the pre-redeal eligibility set is itself hidden information: a
// seat whose PRE-redeal hand could not respond but whose REDEALT hand can now
// Ron/Pon/Kan must be admitted to the window — gating the refresh on prior
// non-emptiness would leak the true hidden hands into which seats the rollout
// re-asks. Conversely, a seat whose refreshed interrupts come back empty simply
// drops out of the window (expectedResponses derives from len(ValidActions));
// that is correct honest behavior — the redealt hand genuinely no longer holds
// (or never held) that interrupt.
//
// Intended for use on CloneForBranch clones (search determinization), never on
// a live game.
func (g *Game) RedealUnseen(actingSeat uint32, seed uint64) error {
	return g.redealUnseen(actingSeat, seed, false)
}

// RedealUnseenForReview conditions on automatic flower reveals and canonicalizes
// the unseen pool, so seeded estimates do not depend on the replay's private
// allocation/order of those tiles. Gameplay search retains its existing contract.
func (g *Game) RedealUnseenForReview(actingSeat uint32, seed uint64) error {
	return g.redealUnseen(actingSeat, seed, true)
}

func (g *Game) redealUnseen(actingSeat uint32, seed uint64, review bool) error {
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
	if review {
		sort.Slice(pool, func(i, j int) bool { return pool[i].Id < pool[j].Id })
	}
	rng := rand.New(rand.NewSource(int64(seed)))
	rng.Shuffle(len(pool), func(i, j int) { pool[i], pool[j] = pool[j], pool[i] })

	if review {
		// Only wild flowers can remain concealed after automatic reveals. Draw
		// opponent slots uniformly from eligible tiles, then shuffle all leftovers
		// for the wall; this samples the visibility constraint without rejection.
		eligible := make([]*pb.Tile, 0, len(pool))
		flowers := make([]*pb.Tile, 0, 8)
		for _, t := range pool {
			wild := false
			for _, w := range g.State.WildTiles {
				if w.Suit == t.Suit && w.Value == t.Value {
					wild = true
					break
				}
			}
			if t.Suit == pb.Suit_SUIT_FLOWER && !wild {
				flowers = append(flowers, t)
			} else {
				eligible = append(eligible, t)
			}
		}
		handSlots := 0
		for s, p := range g.State.Players {
			if uint32(s) != actingSeat {
				handSlots += len(p.ClosedHand)
			}
		}
		if len(eligible) < handSlots {
			return fmt.Errorf("review redeal: insufficient playable unseen tiles")
		}
		wallPool := append(append([]*pb.Tile(nil), eligible[handSlots:]...), flowers...)
		rng.Shuffle(len(wallPool), func(i, j int) { wallPool[i], wallPool[j] = wallPool[j], wallPool[i] })
		pool = append(eligible[:handSlots:handSlots], wallPool...)
	}

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

	// 5. Refresh non-acting seats' ValidActions against their new hands. Stale
	// interrupt options reference tiles the reshuffle moved elsewhere; serving one
	// would corrupt the hand (see the function comment). At an open window we
	// recompute for EVERY non-acting seat (not only those with non-empty
	// pre-redeal options) — pre-redeal eligibility is hidden information, and a
	// redealt hand that gains an interrupt must be admitted (see function comment).
	// The acting seat's ValidActions are left as-is: its hand did not move.
	openWindow := g.State.Phase == pb.GamePhase_PHASE_WAIT_DISCARDS && g.State.ActiveDiscard != nil
	for s, p := range g.State.Players {
		if uint32(s) == actingSeat {
			continue
		}
		if openWindow {
			// The active discarder holds NO interrupts against its own discard —
			// the live path (offerInterrupts) always clears the discarder's
			// ValidActions, and handleInterruptAction counts every non-empty
			// ValidActions toward window completeness. If a redealt discarder hand
			// happened to "match" its own discard we would compute a spurious
			// interrupt here, inflating expectedResponses into an impossible window
			// state (the discarder is never offered, so it can never respond) and
			// diverging from the live engine. Mirror offerInterrupts: clear it.
			if uint32(s) == g.State.ActivePlayer {
				p.ValidActions = nil
				continue
			}
			interrupts := g.Rules.GetValidInterrupts(g.State, g.State.ActiveDiscard, uint32(s))
			p.ValidActions = filterRonOnlyInterrupts(interrupts, g.State.IsHaitei)
			continue
		}
		p.ValidActions = nil
	}

	// Search honesty: this clone's non-acting seats just got NEW hands, but
	// the inherited event log still stores their true pre-redeal draw faces.
	// packPublicEvent unmasks a draw's face for the DRAWING seat itself, so a
	// rollout row encoded for a redealt seat would show faces inconsistent
	// with its new hand and correlated with the live hidden world. Erase
	// them; every other observer already saw these draws as unknown, so the
	// acting (root) seat's rendered history is unchanged (tested).
	for i := range g.publicEvents {
		if g.publicEvents[i].Type == EventDraw && g.publicEvents[i].Seat != actingSeat {
			g.publicEvents[i].Face = -1
		}
	}
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
func (g *Game) WildIndicatorForTest() *pb.Tile { return g.VisibleWildIndicator() }

// VisibleWildIndicator returns a copy of the public indicator, without exposing
// the wall. Review visible-copy accounting uses this for flower indicators too.
func (g *Game) VisibleWildIndicator() *pb.Tile {
	if g == nil || g.wildIndicatorIndex < 0 || g.wildIndicatorIndex >= len(g.wall) || g.wall[g.wildIndicatorIndex] == nil {
		return nil
	}
	t := g.wall[g.wildIndicatorIndex]
	return &pb.Tile{Id: t.Id, Suit: t.Suit, Value: t.Value}
}
