package shanten

import (
	"math/rand"
	"reflect"
	"testing"

	"github.com/plasma/fh-mahjong/internal/tiles"
)

// bruteFindUsefulTiles is findUsefulTiles before route pruning, kept as the
// oracle: every candidate draw gets a full Analyze.
func bruteFindUsefulTiles(counts [34]int, numWilds int, openMelds int, currentShanten int, wildSet map[uint32]bool) ([]UsefulTile, int) {
	if currentShanten < 0 {
		currentShanten = 0
	}
	usefulTiles := make([]UsefulTile, 0, 34)
	totalUseful := 0
	for idx := 0; idx < 34; idx++ {
		suit, value := tiles.FromIndex34(idx)
		key := tiles.KeyOf(suit, value)
		remaining := 4 - counts[idx]
		if wildSet[key] {
			remaining = 4 - numWilds
		}
		if remaining <= 0 {
			continue
		}
		newShanten := 0
		if wildSet[key] {
			newShanten = Analyze(counts, numWilds+1, openMelds).Overall
		} else {
			counts[idx]++
			newShanten = Analyze(counts, numWilds, openMelds).Overall
			counts[idx]--
		}
		if newShanten < 0 {
			newShanten = 0
		}
		if newShanten < currentShanten {
			usefulTiles = append(usefulTiles, UsefulTile{Suit: suit, Value: value, Remaining: remaining})
			totalUseful += remaining
		}
	}
	return usefulTiles, totalUseful
}

// The resumed combination chain must equal calcStandard exactly, for every
// draw position and meld count, not merely agree on usefulness.
func TestStandardPrefixMatchesCalcStandard(t *testing.T) {
	ensureTables()
	rng := rand.New(rand.NewSource(7))
	for iter := 0; iter < 20000; iter++ {
		var counts [34]int
		for placed, size := 0, rng.Intn(15); placed < size; {
			if tt := rng.Intn(34); counts[tt] < maxCopies {
				counts[tt]++
				placed++
			}
		}
		m := maxMelds - rng.Intn(4)
		p := newStandardPrefix(&counts, m)
		if want := calcStandard(&counts, m); p.base != want {
			t.Fatalf("counts=%v m=%d: base %d, calcStandard %d", counts, m, p.base, want)
		}
		for idx := 0; idx < 34; idx++ {
			if counts[idx] >= maxCopies {
				continue
			}
			counts[idx]++
			if got, want := p.withDraw(&counts, idx), calcStandard(&counts, m); got != want {
				t.Fatalf("counts=%v m=%d idx=%d: withDraw %d, calcStandard %d", counts, m, idx, got, want)
			}
			counts[idx]--
		}
	}
}

func TestFindUsefulTilesMatchesUnprunedOracle(t *testing.T) {
	ensureTables()
	rng := rand.New(rand.NewSource(20260926))
	checked, useful := 0, 0
	for iter := 0; iter < 40000; iter++ {
		openMelds := 0
		if rng.Intn(3) == 0 {
			openMelds = 1 + rng.Intn(2)
		}
		wildType := -1
		wildSet := map[uint32]bool{}
		if rng.Intn(4) != 0 {
			wildType = rng.Intn(34)
			suit, value := tiles.FromIndex34(wildType)
			wildSet[tiles.KeyOf(suit, value)] = true
		}
		numWilds := 0
		if wildType >= 0 {
			numWilds = rng.Intn(4)
		}
		// 13 or 14 concealed tiles minus three per open meld, wilds included.
		size := 13 + rng.Intn(2) - 3*openMelds - numWilds
		var counts [34]int
		// Few distinct types half the time, so pairs, sets and tenpai occur.
		types := 34
		if rng.Intn(2) == 0 {
			types = 6 + rng.Intn(10)
		}
		base := rng.Intn(34)
		for placed := 0; placed < size; {
			tt := (base + rng.Intn(types)) % 34
			if tt == wildType || counts[tt] >= maxCopies {
				continue
			}
			counts[tt]++
			placed++
		}
		before := Analyze(counts, numWilds, openMelds)
		gotTiles, gotTotal := findUsefulTiles(counts, numWilds, openMelds, before, wildSet)
		wantTiles, wantTotal := bruteFindUsefulTiles(counts, numWilds, openMelds, before.Overall, wildSet)
		if gotTotal != wantTotal || !reflect.DeepEqual(gotTiles, wantTiles) {
			t.Fatalf("counts=%v wilds=%d open=%d: pruned %v (%d), oracle %v (%d)",
				counts, numWilds, openMelds, gotTiles, gotTotal, wantTiles, wantTotal)
		}
		checked++
		if wantTotal > 0 {
			useful++
		}
	}
	// Non-vacuous: most hands must have useful draws for the comparison to bite.
	if useful < checked/2 {
		t.Fatalf("only %d of %d hands had useful draws", useful, checked)
	}
}
