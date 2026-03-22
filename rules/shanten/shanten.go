package shanten

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
	tilesToAdd := calcStandard(counts, m)
	sht := tilesToAdd - 1 - numWilds
	if sht < -1 {
		sht = -1
	}
	return sht
}
