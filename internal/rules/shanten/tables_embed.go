package shanten

import (
	"bytes"
	"compress/gzip"
	_ "embed"
	"fmt"
	"io"
)

// shanten_tables.bin.gz holds the precomputed suit/honor shanten tables so a
// process does not pay the ~14s DFS generation on first use. Regenerate it with
// TestRegenerateEmbeddedTables (SHANTEN_REGEN=1) after changing table generation.
//
//go:embed shanten_tables.bin.gz
var embeddedTablesGz []byte

func pow5(n int) int {
	r := 1
	for i := 0; i < n; i++ {
		r *= 5
	}
	return r
}

// serializeTables flattens the honor table then the suit table into a single
// contiguous byte slice (each [10]uint8 entry is 10 bytes; honor first).
func serializeTables(suit, honor [][10]uint8) []byte {
	buf := make([]byte, (len(honor)+len(suit))*10)
	off := 0
	for i := range honor {
		off += copy(buf[off:], honor[i][:])
	}
	for i := range suit {
		off += copy(buf[off:], suit[i][:])
	}
	return buf
}

func deserializeTable(data []byte, n int) [][10]uint8 {
	t := make([][10]uint8, n)
	for i := 0; i < n; i++ {
		copy(t[i][:], data[i*10:i*10+10])
	}
	return t
}

// loadEmbeddedTables gunzips and splits the embedded precomputed tables. Any
// error (empty/corrupt/size-mismatch embed) is returned so callers can fall
// back to runtime generation rather than serve wrong tables.
func loadEmbeddedTables() (suit, honor [][10]uint8, err error) {
	if len(embeddedTablesGz) == 0 {
		return nil, nil, fmt.Errorf("shanten: embedded tables are empty")
	}
	zr, err := gzip.NewReader(bytes.NewReader(embeddedTablesGz))
	if err != nil {
		return nil, nil, fmt.Errorf("shanten: open embedded tables: %w", err)
	}
	defer zr.Close()
	data, err := io.ReadAll(zr)
	if err != nil {
		return nil, nil, fmt.Errorf("shanten: read embedded tables: %w", err)
	}
	nHonor, nSuit := pow5(honorSize), pow5(suitSize)
	if want := (nHonor + nSuit) * 10; len(data) != want {
		return nil, nil, fmt.Errorf("shanten: embedded tables are %d bytes, want %d", len(data), want)
	}
	honor = deserializeTable(data[:nHonor*10], nHonor)
	suit = deserializeTable(data[nHonor*10:], nSuit)
	return suit, honor, nil
}
