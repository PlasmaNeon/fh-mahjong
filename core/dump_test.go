package core

import (
"encoding/binary"
"fmt"
"os"
"strings"
"testing"
)

func TestDump(t *testing.T) {
	seedB64, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.seed_str")
	expectedSeedBin, _ := os.ReadFile("testdata/2016022509gm-0009-0000-b327da61.seed_u32")
	
	cleanB64 := strings.Trim(string(seedB64), "\"\n\r\t ")
	seed, _ := SeedFromBase64(cleanB64)
	
	fmt.Printf("Expected first 16 bytes: %x\n", expectedSeedBin[:16])
	
	actual := make([]byte, 16)
	for i := 0; i < 4; i++ {
		binary.LittleEndian.PutUint32(actual[i*4:(i+1)*4], seed[i])
	}
	fmt.Printf("Actual first 16 bytes:   %x\n", actual)
}
