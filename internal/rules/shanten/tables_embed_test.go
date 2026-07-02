package shanten

import (
	"bytes"
	"compress/gzip"
	"os"
	"testing"
)

// TestRegenerateEmbeddedTables rewrites shanten_tables.bin.gz from the DFS
// generators. It is skipped unless SHANTEN_REGEN=1, so it never runs in CI. To
// regenerate after changing table generation, run:
//
//	SHANTEN_REGEN=1 go test ./internal/rules/shanten -run TestRegenerateEmbeddedTables
//
// then re-run the suite (which recompiles the embed) and commit the new file.
func TestRegenerateEmbeddedTables(t *testing.T) {
	if os.Getenv("SHANTEN_REGEN") != "1" {
		t.Skip("set SHANTEN_REGEN=1 to regenerate the embedded tables")
	}
	raw := serializeTables(generateSuitTable(), generateHonorTable())
	var buf bytes.Buffer
	zw, err := gzip.NewWriterLevel(&buf, gzip.BestCompression)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := zw.Write(raw); err != nil {
		t.Fatal(err)
	}
	if err := zw.Close(); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile("shanten_tables.bin.gz", buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	t.Logf("wrote shanten_tables.bin.gz: %d bytes compressed (%d raw)", buf.Len(), len(raw))
}

// TestEmbeddedTablesMatchGeneratedExactly guarantees the committed embedded
// tables are byte-identical to the DFS generators. A mismatched table would
// silently corrupt every hand evaluation, so this must always pass.
func TestEmbeddedTablesMatchGeneratedExactly(t *testing.T) {
	suit, honor, err := loadEmbeddedTables()
	if err != nil {
		t.Fatalf("loadEmbeddedTables: %v (regenerate with SHANTEN_REGEN=1)", err)
	}
	wantSuit, wantHonor := generateSuitTable(), generateHonorTable()
	if len(suit) != len(wantSuit) || len(honor) != len(wantHonor) {
		t.Fatalf("lengths: suit %d/%d honor %d/%d", len(suit), len(wantSuit), len(honor), len(wantHonor))
	}
	for i := range wantSuit {
		if suit[i] != wantSuit[i] {
			t.Fatalf("suit[%d] = %v, want %v", i, suit[i], wantSuit[i])
		}
	}
	for i := range wantHonor {
		if honor[i] != wantHonor[i] {
			t.Fatalf("honor[%d] = %v, want %v", i, honor[i], wantHonor[i])
		}
	}
}
