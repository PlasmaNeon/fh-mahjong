package shanten

import (
	"math/rand"
	"os"
	"testing"
)

// The pre-closed-form implementations, kept verbatim as the oracle: every
// placement of the wilds as natural tiles, scored by the wild-free route.

func bruteAssignWilds(counts []int, w int, startType int, fn func([]int)) {
	if w == 0 {
		fn(counts)
		return
	}
	for t := startType; t < 34; t++ {
		if counts[t] >= maxCopies {
			continue
		}
		counts[t]++
		bruteAssignWilds(counts, w-1, t, fn)
		counts[t]--
	}
}

func bruteRoute(counts [34]int, numWilds int, route func([34]int) int) int {
	if numWilds == 0 {
		return route(counts)
	}
	best := 14
	bruteAssignWilds(counts[:], numWilds, 0, func(c []int) {
		var arr [34]int
		copy(arr[:], c)
		if sht := route(arr); sht < best {
			best = sht
		}
	})
	if best < -1 {
		best = -1
	}
	return best
}

// bruteIndependence is the original calcIndependence, recomputing each suit's
// MIS with the DP instead of reading suitMIS, so the table is checked too.
func bruteIndependence(counts [34]int) int {
	totalOverlap := 0
	for suit := 0; suit < 3; suit++ {
		var has [9]int
		for i := 0; i < 9; i++ {
			if counts[suit*9+i] > 0 {
				has[i] = 1
			}
		}
		totalOverlap += maxIndependentSetOverlapDist2(has[:])
	}
	for i := 27; i < 34; i++ {
		if counts[i] > 0 {
			totalOverlap++
		}
	}
	sht := 14 - totalOverlap - 1
	if totalOverlap > 14 {
		sht = -1
	}
	if sht < -1 {
		sht = -1
	}
	return sht
}

func checkWildRoutes(t *testing.T, counts [34]int, w int) {
	t.Helper()
	if got, want := calcSevenPairsWithWilds(counts, w), bruteRoute(counts, w, calcSevenPairs); got != want {
		t.Fatalf("seven pairs counts=%v wilds=%d: closed form %d, brute force %d", counts, w, got, want)
	}
	if got, want := calcIndependenceWithWilds(counts, w), bruteRoute(counts, w, bruteIndependence); got != want {
		t.Fatalf("independence counts=%v wilds=%d: closed form %d, brute force %d", counts, w, got, want)
	}
}

// Every suit occupancy pattern, alone in the hand, with 0-4 wilds: covers
// suitMISWithWilds exhaustively, including the unextendable sets such as
// {3,7} where one wild cannot raise the MIS.
func TestWildRoutesMatchBruteForceEverySuitMask(t *testing.T) {
	for mask := 0; mask < 512; mask++ {
		for w := 0; w <= 4; w++ {
			var counts [34]int
			for i := 0; i < 9; i++ {
				if mask>>i&1 == 1 {
					counts[9+i] = 1 + i%2 // pin suit, mixed singles/pairs
				}
			}
			checkWildRoutes(t, counts, w)
		}
	}
}

// Random hands of 0-17 natural tiles (covering 13, 14, and the 15-tile
// useful-draw probe on a 14-tile hand) with 0-5 wilds, plus the
// capacity-exhausted edge. The oracle costs ~30 ms per 5-wild hand, so CI runs
// 3000 hands; SHANTEN_EXHAUSTIVE=1 runs 60000 (~10 min).
func TestWildRoutesMatchBruteForceRandomHands(t *testing.T) {
	rng := rand.New(rand.NewSource(20260925))
	iterations, fiveWildEvery := 3000, 100
	if os.Getenv("SHANTEN_EXHAUSTIVE") == "1" {
		iterations, fiveWildEvery = 60000, 10
	}
	for iter := 0; iter < iterations; iter++ {
		var counts [34]int
		tilesInHand := rng.Intn(18)
		// Bias toward few types so pairs/triples/quads and dense suits occur.
		types := 1 + rng.Intn(34)
		for n := 0; n < tilesInHand; n++ {
			tt := rng.Intn(types)
			if rng.Intn(3) == 0 {
				tt = rng.Intn(34)
			}
			if counts[tt] < maxCopies {
				counts[tt]++
			}
		}
		w := rng.Intn(5)
		if iter%fiveWildEvery == 0 {
			w = 5
		}
		checkWildRoutes(t, counts, w)
	}
	var full [34]int
	for i := range full {
		full[i] = maxCopies
	}
	full[0] = 2
	for w := 0; w <= 3; w++ {
		checkWildRoutes(t, full, w)
	}
}
