package storage

import "testing"

func TestPlacementsFromScores(t *testing.T) {
	cases := []struct {
		name   string
		scores [4]int32
		want   [4]uint
	}{
		{"strict order", [4]int32{40, 30, 20, 10}, [4]uint{1, 2, 3, 4}},
		{"seat order preserved", [4]int32{10, 20, 30, 40}, [4]uint{4, 3, 2, 1}},
		{"ties share the best place and skip the next", [4]int32{30, 30, 20, 10}, [4]uint{1, 1, 3, 4}},
		{"three-way tie", [4]int32{30, 30, 30, 10}, [4]uint{1, 1, 1, 4}},
		{"all equal", [4]int32{0, 0, 0, 0}, [4]uint{1, 1, 1, 1}},
		{"negative scores rank normally", [4]int32{-10, -20, 5, -20}, [4]uint{2, 3, 1, 3}},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := PlacementsFromScores(tc.scores); got != tc.want {
				t.Fatalf("PlacementsFromScores(%v) = %v, want %v", tc.scores, got, tc.want)
			}
		})
	}
}
