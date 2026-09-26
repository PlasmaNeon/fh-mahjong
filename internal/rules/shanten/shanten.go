package shanten

import (
	"sync"

	"github.com/plasma/fh-mahjong/internal/tiles"
	pb "github.com/plasma/fh-mahjong/proto"
)

var once sync.Once

func ensureTables() {
	once.Do(generateTables)
}

// Prewarm builds the shanten lookup tables if they have not been built yet.
// The first table build is expensive (it enumerates every suit/honor hand
// shape), so callers on a latency-sensitive path — notably the room's initial
// BroadcastState — would otherwise pay the full cost inline, leaving the client
// stuck on "Waiting for server to deal" until it finishes. Servers should call
// this once at startup (off the request path) so the first real game is fast.
// It is safe to call from multiple goroutines and is a no-op once warmed.
func Prewarm() {
	ensureTables()
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
func calcStandard(counts *[34]int, m int) int {
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
	ensureTables()
	m := maxMelds - numOpenMelds

	// Standard shanten
	tilesToAdd := calcStandard(&counts, m)
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

// wildCapacity is how many wilds can be placed on counts without any type
// exceeding maxCopies. A placement of every wild is required for a route to
// be scored at all; below capacity the route is unreachable (14).
func wildCapacity(counts *[34]int) int {
	capacity := 0
	for _, c := range counts {
		if c < maxCopies {
			capacity += maxCopies - c
		}
	}
	return capacity
}

// calcSevenPairsWithWilds is the best seven-pairs shanten over every way of
// placing numWilds wilds as natural tiles, in closed form.
//
// calcSevenPairs is 13 - pairs - min(kinds, 7), so a placement is scored by
// how much it raises pairs + min(kinds, 7). One wild raises it by at most one:
// on an empty type it adds a kind (worth one only while kinds < 7), on a single
// it adds a pair, anywhere else nothing. If n empty types receive a wild, the
// kind gain is min(n, 7-kinds) and at most singles+n types can cross 1->2,
// using at most numWilds-n wilds, so the gain is bounded by
// min(n, d) + min(numWilds-n, singles+n) and that bound is met by filling n
// empties and pairing singles. Leftover wilds only have to fit somewhere.
func calcSevenPairsWithWilds(counts [34]int, numWilds int) int {
	if numWilds == 0 {
		return calcSevenPairs(counts)
	}
	if wildCapacity(&counts) < numWilds {
		return 14
	}
	pair, kind, singles := 0, 0, 0
	for _, c := range counts {
		if c > 0 {
			kind++
			if c >= 2 {
				pair++
			} else {
				singles++
			}
		}
	}
	deficit := max(0, 7-kind)
	empties := 34 - kind
	bestGain := 0
	for n := 0; n <= min(numWilds, empties); n++ {
		gain := min(n, deficit) + min(numWilds-n, singles+n)
		bestGain = max(bestGain, gain)
	}
	sht := 13 - pair - min(kind, 7) - bestGain
	if sht < -1 {
		sht = -1
	}
	return sht
}

// --- Independence (大大胡) ---

// suitMIS[mask] is the maximum independent set of the 9-position suit whose
// occupied positions are the bits of mask, under the distance-2 conflict
// (members at least 3 apart). suitMISWithWilds[mask][k] is the best MIS after
// adding at most k positions. Both are exact enumerations over the 512 masks,
// so the wild route below needs no search at call time.
var (
	suitMIS          [512]uint8
	suitMISWithWilds [512][4]uint8
)

func init() {
	for mask := 0; mask < 512; mask++ {
		var has [9]int
		for i := 0; i < 9; i++ {
			has[i] = (mask >> i) & 1
		}
		suitMIS[mask] = uint8(maxIndependentSetOverlapDist2(has[:]))
	}
	for mask := 0; mask < 512; mask++ {
		for add := 0; add < 512; add++ {
			if add&mask != 0 {
				continue
			}
			k := bitCount9(add)
			if k > 3 {
				continue
			}
			v := suitMIS[mask|add]
			for kk := k; kk <= 3; kk++ {
				if v > suitMISWithWilds[mask][kk] {
					suitMISWithWilds[mask][kk] = v
				}
			}
		}
	}
}

func bitCount9(x int) int {
	n := 0
	for ; x != 0; x &= x - 1 {
		n++
	}
	return n
}

func suitMask(counts *[34]int, base int) int {
	mask := 0
	for i := 0; i < 9; i++ {
		if counts[base+i] > 0 {
			mask |= 1 << i
		}
	}
	return mask
}

func independenceShanten(totalOverlap int) int {
	sht := 14 - totalOverlap - 1
	if totalOverlap > 14 {
		sht = -1
	}
	if sht < -1 {
		sht = -1
	}
	return sht
}

func calcIndependence(counts [34]int) int {
	totalOverlap := 0
	for suit := 0; suit < 3; suit++ {
		totalOverlap += int(suitMIS[suitMask(&counts, suit*9)])
	}
	for i := 27; i < 34; i++ {
		if counts[i] > 0 {
			totalOverlap++
		}
	}
	return independenceShanten(totalOverlap)
}

// maxIndependentSetOverlapDist2: max-weight independent set on 9-node path
// with distance-2 adjacency (i+1 and i+2 both forbidden). Only used to build
// suitMIS.
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

// calcIndependenceWithWilds is the best independence shanten over every way
// of placing numWilds wilds as natural tiles. A wild only matters where it
// lands on an absent type: in a suit it can raise that suit's MIS (read from
// suitMISWithWilds, exact per suit), on an absent honor it adds one. The suits
// and honors are independent, so the best split of the wilds across the four
// groups is an exhaustive search over at most (numWilds+1)^3 splits.
// A wild placed where it gains nothing still has to fit (wildCapacity).
func calcIndependenceWithWilds(counts [34]int, numWilds int) int {
	if numWilds == 0 {
		return calcIndependence(counts)
	}
	if wildCapacity(&counts) < numWilds {
		return 14
	}
	var masks [3]int
	base := 0
	for suit := 0; suit < 3; suit++ {
		masks[suit] = suitMask(&counts, suit*9)
		base += int(suitMIS[masks[suit]])
	}
	honors := 0
	for i := 27; i < 34; i++ {
		if counts[i] > 0 {
			honors++
		}
	}
	base += honors
	gainIn := func(suit, k int) int {
		m := masks[suit]
		return int(suitMISWithWilds[m][min(k, 3)]) - int(suitMIS[m])
	}
	bestGain := 0
	for a := 0; a <= numWilds; a++ {
		ga := gainIn(0, a)
		for b := 0; a+b <= numWilds; b++ {
			gb := gainIn(1, b)
			for c := 0; a+b+c <= numWilds; c++ {
				gain := ga + gb + gainIn(2, c) + min(numWilds-a-b-c, 7-honors)
				bestGain = max(bestGain, gain)
			}
		}
	}
	return independenceShanten(base + bestGain)
}

// CalculateFromTiles is the high-level API for game integration.
func CalculateFromTiles(closedHand []*pb.Tile, openMelds int, wildTiles []*pb.Tile) int {
	ensureTables()
	wildSet := make(map[uint32]bool)
	for _, w := range wildTiles {
		wildSet[tiles.KeyOf(w.Suit, w.Value)] = true
	}

	var counts [34]int
	numWilds := 0
	for _, t := range closedHand {
		h := tiles.KeyOf(t.Suit, t.Value)
		if wildSet[h] {
			numWilds++
		} else {
			idx := tiles.Index34(t)
			if idx >= 0 {
				counts[idx]++
			}
		}
	}

	return Calculate(counts, numWilds, openMelds)
}
