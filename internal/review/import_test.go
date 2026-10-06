package review

import (
	"encoding/json"
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	pb "github.com/plasma/fh-mahjong/proto"
)

// flowerWildSeed deals a flower wild indicator in the first hand.
const flowerWildSeed = 5

func flowerWildPaipu(t *testing.T) *engine.Paipu {
	t.Helper()
	p := generateHeuristicPaipuV2(t, flowerWildSeed, engine.MatchOptions{})
	if len(p.Rounds) == 0 || len(p.Rounds[0].WildTiles) == 0 || p.Rounds[0].WildTiles[0].Suit != pb.Suit_SUIT_FLOWER {
		t.Fatalf("premise: seed %d no longer deals a flower wild indicator", flowerWildSeed)
	}
	return p
}

func TestImportReconstructsAFlowerWildRound(t *testing.T) {
	data, err := json.Marshal(flowerWildPaipu(t))
	if err != nil {
		t.Fatal(err)
	}
	p, err := ValidateImport(data)
	if err != nil {
		t.Fatalf("flower-wild round rejected: %v", err)
	}
	if _, err := extractDecisions(p, 0, true); err != nil {
		t.Fatalf("flower-wild round did not reconstruct: %v", err)
	}
}

func TestValidateImportWildTileIDs(t *testing.T) {
	standard := generateHeuristicPaipuV2(t, 7, engine.MatchOptions{})
	if standard.Rounds[0].WildTiles[0].Suit == pb.Suit_SUIT_FLOWER {
		t.Fatal("premise: seed 7 should deal a standard wild indicator")
	}
	cases := []struct {
		name   string
		paipu  *engine.Paipu
		mutate func(w *engine.PaipuTile)
		ok     bool
	}{
		{"flower wild without an id (engine form)", flowerWildPaipu(t), func(w *engine.PaipuTile) {}, true},
		{"flower wild with its own flower id", flowerWildPaipu(t), func(w *engine.PaipuTile) { w.ID = 135 + w.Value }, true},
		{"flower wild with another flower's id", flowerWildPaipu(t), func(w *engine.PaipuTile) { w.ID = 136 + w.Value%8 }, false},
		{"flower wild with a standard tile id", flowerWildPaipu(t), func(w *engine.PaipuTile) { w.ID = 40 }, false},
		{"flower wild value out of range", flowerWildPaipu(t), func(w *engine.PaipuTile) { w.Value = 9 }, false},
		{"standard wild with its own id", standard, func(w *engine.PaipuTile) {}, true},
		{"standard wild with a mismatched id", standard, func(w *engine.PaipuTile) { w.ID = (w.ID + 4) % 136 }, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			data, err := json.Marshal(tc.paipu)
			if err != nil {
				t.Fatal(err)
			}
			var p engine.Paipu
			if err := json.Unmarshal(data, &p); err != nil {
				t.Fatal(err)
			}
			tc.mutate(&p.Rounds[0].WildTiles[0])
			if data, err = json.Marshal(&p); err != nil {
				t.Fatal(err)
			}
			_, err = ValidateImport(data)
			if (err == nil) != tc.ok {
				t.Fatalf("ValidateImport error = %v, want ok=%v", err, tc.ok)
			}
		})
	}
}
