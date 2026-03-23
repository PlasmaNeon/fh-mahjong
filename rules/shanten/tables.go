package shanten

const (
	suitSize  = 9
	honorSize = 7
	maxCopies = 4
	maxMelds  = 4
	maxSht    = 14
)

var suitTable [][10]uint8
var honorTable [][10]uint8

func hash(counts []int) int {
	h := counts[0]
	for i := 1; i < len(counts); i++ {
		h = 5*h + counts[i]
	}
	return h
}

func calcDistance(current, target []int) uint8 {
	d := 0
	for i := range current {
		if target[i] > current[i] {
			d += target[i] - current[i]
		}
	}
	return uint8(d)
}

func isValidTarget(target []int) bool {
	for _, v := range target {
		if v > maxCopies {
			return false
		}
	}
	return true
}

type meld [3]int

func dfs(current, target []int, m, minMid int, melds []meld, sht *[10]uint8) {
	for tid := range current {
		target[tid] += 2
		if isValidTarget(target) {
			dist := calcDistance(current, target)
			if dist < sht[m+5] {
				sht[m+5] = dist
			}
		}
		target[tid] -= 2
	}

	if m >= maxMelds {
		return
	}

	for mid := minMid; mid < len(melds); mid++ {
		ml := melds[mid]
		target[ml[0]]++
		target[ml[1]]++
		target[ml[2]]++

		if isValidTarget(target) {
			dist := calcDistance(current, target)
			if dist < sht[m+1] {
				sht[m+1] = dist
			}
			if dist < sht[maxMelds+5] {
				dfs(current, target, m+1, mid, melds, sht)
			}
		}

		target[ml[0]]--
		target[ml[1]]--
		target[ml[2]]--
	}
}

func generateSuitTable() [][10]uint8 {
	n := 1
	for i := 0; i < suitSize; i++ {
		n *= 5
	}
	table := make([][10]uint8, n)

	melds := make([]meld, 0, 16)
	for tid := 0; tid < suitSize; tid++ {
		melds = append(melds, meld{tid, tid, tid})
	}
	for tid := 0; tid < suitSize-2; tid++ {
		melds = append(melds, meld{tid, tid + 1, tid + 2})
	}

	hand := make([]int, suitSize)
	target := make([]int, suitSize)
	var enumerate func(pos int)
	enumerate = func(pos int) {
		if pos == suitSize {
			h := hash(hand)
			var sht [10]uint8
			for i := range sht {
				sht[i] = maxSht
			}
			sht[0] = 0
			dfs(hand, target, 0, 0, melds, &sht)
			table[h] = sht
			return
		}
		for v := 0; v <= maxCopies; v++ {
			hand[pos] = v
			enumerate(pos + 1)
		}
	}
	enumerate(0)
	return table
}

func generateHonorTable() [][10]uint8 {
	n := 1
	for i := 0; i < honorSize; i++ {
		n *= 5
	}
	table := make([][10]uint8, n)

	melds := make([]meld, 0, 7)
	for tid := 0; tid < honorSize; tid++ {
		melds = append(melds, meld{tid, tid, tid})
	}

	hand := make([]int, honorSize)
	target := make([]int, honorSize)
	var enumerate func(pos int)
	enumerate = func(pos int) {
		if pos == honorSize {
			h := hash(hand)
			var sht [10]uint8
			for i := range sht {
				sht[i] = maxSht
			}
			sht[0] = 0
			dfs(hand, target, 0, 0, melds, &sht)
			table[h] = sht
			return
		}
		for v := 0; v <= maxCopies; v++ {
			hand[pos] = v
			enumerate(pos + 1)
		}
	}
	enumerate(0)
	return table
}

func generateTables() {
	suitTable = generateSuitTable()
	honorTable = generateHonorTable()
}
