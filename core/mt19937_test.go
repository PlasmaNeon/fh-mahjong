package core

import (
	"bytes"
	"os"
	"strconv"
	"strings"
	"testing"
)

func parseRustU32Array(content string) ([]uint32, error) {
	c := strings.Trim(content, " \n\r\t[]")
	parts := strings.Split(c, ",")
	var res []uint32
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		p = strings.TrimSuffix(p, "u32")
		val, err := strconv.ParseUint(p, 0, 32)
		if err != nil {
			return nil, err
		}
		res = append(res, uint32(val))
	}
	return res, nil
}

func parseRustU8Array(content string) ([]byte, error) {
	c := strings.Trim(content, " \n\r\t[]")
	parts := strings.Split(c, ",")
	var res []byte
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		p = strings.TrimSuffix(p, "u8")
		val, err := strconv.ParseUint(p, 0, 8)
		if err != nil {
			return nil, err
		}
		res = append(res, byte(val))
	}
	return res, nil
}

func TestTenhouShuffleExactMatch(t *testing.T) {
	seedB64, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.seed_str")
	expectedSeedStr, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.seed_u32")
	expectedSrcStr, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.src_u32")
	expectedRndStr, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.rnd_u32")
	expectedWall136Str, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.wall136")

	expectedSeed, _ := parseRustU32Array(string(expectedSeedStr))
	expectedSrc, _ := parseRustU32Array(string(expectedSrcStr))
	expectedRnd, _ := parseRustU32Array(string(expectedRndStr))
	expectedWall136, _ := parseRustU8Array(string(expectedWall136Str))

	cleanB64 := strings.Trim(string(seedB64), "\"\n\r\t ")
	seed, err := SeedFromBase64(cleanB64)
	if err != nil {
		t.Fatalf("SeedFromBase64 failed: %v", err)
	}

	for i, v := range seed {
		if v != expectedSeed[i] {
			t.Fatalf("Seed output mismatch at index %d: expected 0x%x, got 0x%x", i, expectedSeed[i], v)
		}
	}

	mt := MTFromSeed(seed)
	src := SrcFromMT(mt)

	for i, v := range src {
		if v != expectedSrc[i] {
			t.Fatalf("SRC output mismatch at index %d: expected 0x%x, got 0x%x", i, expectedSrc[i], v)
		}
	}

	rnd := RndFromSrc(&src)

	for i, v := range rnd {
		if v != expectedRnd[i] {
			t.Fatalf("RND output mismatch at index %d: expected 0x%x, got 0x%x", i, expectedRnd[i], v)
		}
	}

	wall136 := make([]byte, 136)
	for i := byte(0); i < 136; i++ {
		wall136[i] = i
	}

	ShuffleWithRnd(wall136, &rnd)
	if !bytes.Equal(wall136, expectedWall136) {
		t.Errorf("Shuffled Wall 136 does not match expected result")
	}
}
