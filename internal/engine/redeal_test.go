package engine_test

import (
	"sort"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// startedGame deals a real seeded game so wall geometry (wangpai, wild
// indicator) is authentic, then returns it with seat 0 to act.
func startedGame(t *testing.T, seed uint64) *engine.Game {
	t.Helper()
	g := engine.NewGame("redeal-test", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	g.SetWallSeed(engine.SeedFromUint64(seed))
	g.SetNextDealer(0)
	if err := g.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	return g
}

func tileKeys(tiles []*pb.Tile) []uint32 {
	keys := make([]uint32, 0, len(tiles))
	for _, tile := range tiles {
		keys = append(keys, tile.Id)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	return keys
}

func handsEqual(a, b []*pb.Tile) bool {
	if len(a) != len(b) {
		return false
	}
	ka, kb := tileKeys(a), tileKeys(b)
	for i := range ka {
		if ka[i] != kb[i] {
			return false
		}
	}
	return true
}

func TestRedealUnseen_VisibleStateFixedAndPoolConserved(t *testing.T) {
	g := startedGame(t, 42)
	clone := g.CloneForBranch()

	before := clone.CloneForBranch() // snapshot
	if err := clone.RedealUnseen(0, 7); err != nil {
		t.Fatalf("redeal: %v", err)
	}

	// Acting seat's own hand identical (ids, order irrelevant but keep ids).
	if !handsEqual(before.State.Players[0].ClosedHand, clone.State.Players[0].ClosedHand) {
		t.Fatal("acting seat's hand changed")
	}
	// Opponents' hand SIZES unchanged.
	for s := 1; s < 4; s++ {
		if len(before.State.Players[s].ClosedHand) != len(clone.State.Players[s].ClosedHand) {
			t.Fatalf("seat %d hand size changed", s)
		}
	}
	// Global tile-id multiset conserved across hands+wall (nothing created/lost):
	collect := func(g2 *engine.Game) []uint32 {
		var all []*pb.Tile
		for _, p := range g2.State.Players {
			all = append(all, p.ClosedHand...)
		}
		return append(tileKeys(all), tileKeys(g2.WallTilesForTest())...)
	}
	a, b := collect(before), collect(clone)
	if len(a) != len(b) {
		t.Fatalf("tile count changed: %d vs %d", len(a), len(b))
	}
	sort.Slice(a, func(i, j int) bool { return a[i] < a[j] })
	sort.Slice(b, func(i, j int) bool { return b[i] < b[j] })
	for i := range a {
		if a[i] != b[i] {
			t.Fatal("tile multiset not conserved")
		}
	}
	// Wall geometry: wild indicator tile identity unchanged (it is visible).
	if before.WildIndicatorForTest().Id != clone.WildIndicatorForTest().Id {
		t.Fatal("wild indicator changed — it is visible and must not be redealt")
	}
	// WallCount (visible) unchanged.
	if before.State.WallCount != clone.State.WallCount {
		t.Fatal("visible wall count changed")
	}
}

func TestRedealUnseen_OpponentsDifferAcrossSeeds(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 1); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 2); err != nil {
		t.Fatal(err)
	}
	differ := false
	for s := 1; s < 4; s++ {
		if !handsEqual(a.State.Players[s].ClosedHand, b.State.Players[s].ClosedHand) {
			differ = true
		}
	}
	if !differ {
		t.Fatal("different seeds produced identical opponent hands")
	}
}

func TestRedealUnseen_SeedDeterminism(t *testing.T) {
	g := startedGame(t, 42)
	a := g.CloneForBranch()
	b := g.CloneForBranch()
	if err := a.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	if err := b.RedealUnseen(0, 9); err != nil {
		t.Fatal(err)
	}
	for s := 1; s < 4; s++ {
		ka := tileKeys(a.State.Players[s].ClosedHand)
		kb := tileKeys(b.State.Players[s].ClosedHand)
		for i := range ka {
			if ka[i] != kb[i] {
				t.Fatalf("seat %d differs under same seed", s)
			}
		}
	}
}

func TestRedealUnseen_RejectsBadSeat(t *testing.T) {
	g := startedGame(t, 42)
	if err := g.CloneForBranch().RedealUnseen(4, 1); err == nil {
		t.Fatal("expected error for seat 4")
	}
}
