package shanten

import pb "github.com/plasma/fh-mahjong/proto"

func init() {
	generateTables()
}

func min8(a, b uint8) uint8 {
	if a < b {
		return a
	}
	return b
}

// add1 combines two suit group results using min-convolution.
func add1(lhs *[10]uint8, rhs [10]uint8, m int) {
	for j := m + 5; j >= 5; j-- {
		sht := min8(lhs[j]+rhs[0], lhs[0]+rhs[j])
		for k := 5; k < j; k++ {
			sht = min8(sht, min8(lhs[k]+rhs[j-k], lhs[j-k]+rhs[k]))
		}
		lhs[j] = sht
	}
	for j := m; j >= 0; j-- {
		sht := lhs[j] + rhs[0]
		for k := 0; k < j; k++ {
			sht = min8(sht, lhs[k]+rhs[j-k])
		}
		lhs[j] = sht
	}
}

// add2 is an optimized final combine -- only computes ret[m+5].
func add2(lhs *[10]uint8, rhs [10]uint8, m int) {
	j := m + 5
	sht := min8(lhs[j]+rhs[0], lhs[0]+rhs[j])
	for k := 5; k < j; k++ {
		sht = min8(sht, min8(lhs[k]+rhs[j-k], lhs[j-k]+rhs[k]))
	}
	lhs[j] = sht
}

// calcStandard returns tiles-to-add for standard hand (4 melds + pair).
func calcStandard(counts [34]int, m int) int {
	ret := honorTable[hash(counts[27:34])]
	add1(&ret, suitTable[hash(counts[18:27])], m)
	add1(&ret, suitTable[hash(counts[9:18])], m)
	add2(&ret, suitTable[hash(counts[0:9])], m)
	return int(ret[m+5])
}

// Calculate returns the shanten number for a closed hand.
// counts: 34-element tile count array (wild tiles EXCLUDED).
// numWilds: number of wild tiles in the closed hand.
// numOpenMelds: number of open melds (0-4).
// Returns -1 for complete hand, 0 for tenpai, 1+ for iishanten etc.
func Calculate(counts [34]int, numWilds int, numOpenMelds int) int {
	m := maxMelds - numOpenMelds

	// Standard shanten
	tilesToAdd := calcStandard(counts, m)
	best := tilesToAdd - 1 - numWilds
	if best < -1 {
		best = -1
	}

	// Seven pairs (only with no open melds)
	if numOpenMelds == 0 {
		sp := calcSevenPairsWithWilds(counts, numWilds)
		if sp < best {
			best = sp
		}
	}

	// Independence (only with no open melds)
	if numOpenMelds == 0 {
		ind := calcIndependenceWithWilds(counts, numWilds)
		if ind < best {
			best = ind
		}
	}

	return best
}

// --- Seven Pairs ---

func calcSevenPairs(counts [34]int) int {
	pair := 0
	kind := 0
	for i := 0; i < 34; i++ {
		if counts[i] > 0 {
			kind++
			if counts[i] >= 2 {
				pair++
			}
		}
	}
	sht := 7 - pair
	if kind < 7 {
		sht += 7 - kind
	}
	return sht - 1
}

func calcSevenPairsWithWilds(counts [34]int, numWilds int) int {
	if numWilds == 0 {
		return calcSevenPairs(counts)
	}
	best := 14
	assignWilds(counts[:], numWilds, 0, func(c []int) {
		var arr [34]int
		copy(arr[:], c)
		sht := calcSevenPairs(arr)
		if sht < best {
			best = sht
		}
	})
	if best < -1 {
		best = -1
	}
	return best
}

func assignWilds(counts []int, w int, startType int, fn func([]int)) {
	if w == 0 {
		fn(counts)
		return
	}
	for t := startType; t < 34; t++ {
		if counts[t] >= maxCopies {
			continue
		}
		counts[t]++
		assignWilds(counts, w-1, t, fn)
		counts[t]--
	}
}

// --- Independence (大大胡) ---

func calcIndependence(counts [34]int) int {
	totalOverlap := 0

	for suit := 0; suit < 3; suit++ {
		base := suit * 9
		var has [9]int
		for i := 0; i < 9; i++ {
			if counts[base+i] > 0 {
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

// maxIndependentSetOverlapDist2: max-weight independent set on 9-node path
// with distance-2 adjacency (i+1 and i+2 both forbidden).
func maxIndependentSetOverlapDist2(has []int) int {
	n := len(has)
	if n == 0 {
		return 0
	}
	dp := make([]int, n)
	dp[0] = has[0]
	if n > 1 {
		dp[1] = max(has[0], has[1])
	}
	if n > 2 {
		dp[2] = max(dp[1], has[2])
	}
	for i := 3; i < n; i++ {
		dp[i] = max(dp[i-1], has[i]+dp[i-3])
	}
	return dp[n-1]
}

func calcIndependenceWithWilds(counts [34]int, numWilds int) int {
	if numWilds == 0 {
		return calcIndependence(counts)
	}
	best := 14
	assignWilds(counts[:], numWilds, 0, func(c []int) {
		var arr [34]int
		copy(arr[:], c)
		sht := calcIndependence(arr)
		if sht < best {
			best = sht
		}
	})
	if best < -1 {
		best = -1
	}
	return best
}

// tileToIndex converts a protobuf Tile to the 0-33 index.
// Returns -1 for flowers (excluded from shanten).
func tileToIndex(t *pb.Tile) int {
	if t.Suit == pb.Suit_SUIT_FLOWER {
		return -1
	}
	valOffset := int(t.Value) - 1
	switch t.Suit {
	case pb.Suit_SUIT_MAN:
		return valOffset
	case pb.Suit_SUIT_PIN:
		return 9 + valOffset
	case pb.Suit_SUIT_SOU:
		return 18 + valOffset
	case pb.Suit_SUIT_JIHAI:
		return 27 + valOffset
	}
	return -1
}

// CalculateFromTiles is the high-level API for game integration.
func CalculateFromTiles(closedHand []*pb.Tile, openMelds int, wildTiles []*pb.Tile) int {
	wildSet := make(map[uint32]bool)
	for _, w := range wildTiles {
		wildSet[uint32(w.Suit)*100+w.Value] = true
	}

	var counts [34]int
	numWilds := 0
	for _, t := range closedHand {
		h := uint32(t.Suit)*100 + t.Value
		if wildSet[h] {
			numWilds++
		} else {
			idx := tileToIndex(t)
			if idx >= 0 {
				counts[idx]++
			}
		}
	}

	return Calculate(counts, numWilds, openMelds)
}
