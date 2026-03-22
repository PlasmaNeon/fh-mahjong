package shanten

import "testing"

func TestHash(t *testing.T) {
	counts := []int{1, 0, 0, 0, 0, 0, 0, 0, 0}
	if got := hash(counts); got != 390625 {
		t.Errorf("hash([1,0,...,0]) = %d, want 390625", got)
	}

	counts2 := []int{0, 0, 0, 0, 0, 0, 0, 0, 1}
	if got := hash(counts2); got != 1 {
		t.Errorf("hash([0,...,0,1]) = %d, want 1", got)
	}

	counts3 := []int{4, 4, 4, 4, 4, 4, 4, 4, 4}
	if got := hash(counts3); got != 1953124 {
		t.Errorf("hash([4,...,4]) = %d, want 1953124", got)
	}
}

func TestTableGeneration(t *testing.T) {
	if len(suitTable) != 1953125 {
		t.Fatalf("suitTable size = %d, want 1953125", len(suitTable))
	}
	if len(honorTable) != 78125 {
		t.Fatalf("honorTable size = %d, want 78125", len(honorTable))
	}

	zeroHash := hash([]int{0, 0, 0, 0, 0, 0, 0, 0, 0})
	entry := suitTable[zeroHash]
	if entry[0] != 0 {
		t.Errorf("suitTable[0][0] = %d, want 0", entry[0])
	}
	if entry[5] != 2 {
		t.Errorf("suitTable[0][5] = %d, want 2 (pair needs 2 additions)", entry[5])
	}

	tripleHash := hash([]int{3, 0, 0, 0, 0, 0, 0, 0, 0})
	entry = suitTable[tripleHash]
	if entry[1] != 0 {
		t.Errorf("suitTable[3,0,...][1] = %d, want 0 (triplet formed)", entry[1])
	}

	seqHash := hash([]int{1, 1, 1, 0, 0, 0, 0, 0, 0})
	entry = suitTable[seqHash]
	if entry[1] != 0 {
		t.Errorf("suitTable[1,1,1,...][1] = %d, want 0 (sequence formed)", entry[1])
	}
}

func TestStandardShanten(t *testing.T) {
	tests := []struct {
		name   string
		counts [34]int
		wilds  int
		melds  int
		want   int
	}{
		{
			name: "complete hand: 123m 456m 789m 123p 55p",
			counts: func() [34]int {
				var c [34]int
				for i := 0; i < 9; i++ {
					c[i] = 1
				}
				c[9] = 1; c[10] = 1; c[11] = 1; c[13] = 2
				return c
			}(),
			want: -1,
		},
		{
			name: "tenpai: 123m 456m 789m 123p 5p",
			counts: func() [34]int {
				var c [34]int
				for i := 0; i < 9; i++ {
					c[i] = 1
				}
				c[9] = 1; c[10] = 1; c[11] = 1; c[13] = 1
				return c
			}(),
			want: 0,
		},
		{
			name: "tenpai: 12m 456m 789m 123p 55p (waiting 3m)",
			counts: func() [34]int {
				var c [34]int
				c[0] = 1; c[1] = 1
				c[3] = 1; c[4] = 1; c[5] = 1
				c[6] = 1; c[7] = 1; c[8] = 1
				c[9] = 1; c[10] = 1; c[11] = 1
				c[13] = 2
				return c
			}(),
			want: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Calculate(tt.counts, tt.wilds, tt.melds)
			if got != tt.want {
				t.Errorf("Calculate() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestSevenPairsShanten(t *testing.T) {
	tests := []struct {
		name   string
		counts [34]int
		wilds  int
		want   int
	}{
		{
			name: "complete seven pairs",
			counts: func() [34]int {
				var c [34]int
				c[0] = 2; c[1] = 2; c[2] = 2; c[3] = 2
				c[9] = 2; c[10] = 2; c[11] = 2
				return c
			}(),
			want: -1,
		},
		{
			name: "six pairs + 2 singles = tenpai",
			counts: func() [34]int {
				var c [34]int
				c[0] = 2; c[1] = 2; c[2] = 2; c[3] = 2
				c[9] = 2; c[10] = 2; c[11] = 1; c[12] = 1
				return c
			}(),
			want: 0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := calcSevenPairsWithWilds(tt.counts, tt.wilds)
			if got != tt.want {
				t.Errorf("calcSevenPairsWithWilds() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestIndependenceShanten(t *testing.T) {
	tests := []struct {
		name   string
		counts [34]int
		wilds  int
		want   int
	}{
		{
			name: "perfect independence: 14 tiles distance-2 separated",
			counts: func() [34]int {
				var c [34]int
				// Man: 1,4,7 (indices 0,3,6)
				c[0] = 1; c[3] = 1; c[6] = 1
				// Pin: 1,4,7 (indices 9,12,15)
				c[9] = 1; c[12] = 1; c[15] = 1
				// Sou: 1 (index 18)
				c[18] = 1
				// All 7 honors
				for i := 27; i < 34; i++ {
					c[i] = 1
				}
				return c
			}(),
			want: -1,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := calcIndependenceWithWilds(tt.counts, tt.wilds)
			if got != tt.want {
				t.Errorf("calcIndependenceWithWilds() = %d, want %d", got, tt.want)
			}
		})
	}
}

func TestWildTileShanten(t *testing.T) {
	tests := []struct {
		name   string
		counts [34]int
		wilds  int
		melds  int
		want   int
	}{
		{
			name: "1 wild completes tenpai hand",
			counts: func() [34]int {
				var c [34]int
				// 123m 456m 789m 1p 2p 5p 5p + wild = 13 + 1 wild
				for i := 0; i < 9; i++ {
					c[i] = 1
				}
				c[9] = 1; c[10] = 1
				c[13] = 2
				return c
			}(),
			wilds: 1,
			want:  -1, // wild becomes 3p → 123m 456m 789m 123p 55p
		},
		{
			name: "2 wilds reduce to tenpai",
			counts: func() [34]int {
				var c [34]int
				// 123m 456m 789m + 3 singles = 12 tiles + 2 wilds
				for i := 0; i < 9; i++ {
					c[i] = 1
				}
				c[9] = 1; c[18] = 1; c[27] = 1
				return c
			}(),
			wilds: 2,
			want:  0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Calculate(tt.counts, tt.wilds, tt.melds)
			if got != tt.want {
				t.Errorf("Calculate() = %d, want %d", got, tt.want)
			}
		})
	}
}
