package core

import (
	"crypto/sha512"
	"encoding/base64"
	"encoding/binary"
	"errors"
)

// MT19937 implementation exactly matching the C (and Rust) reference implementation
// used by Tenhou for reproducible wall shuffling.

const (
	n         = 624
	m         = 397
	matrixA   = 0x9908b0df
	upperMask = 0x80000000
	lowerMask = 0x7fffffff
)

type MT19937 struct {
	mt  [n]uint32
	mti int
}

func NewMT19937() *MT19937 {
	return &MT19937{
		mti: n + 1,
	}
}

func (rng *MT19937) seed(s uint32) {
	rng.mt[0] = s
	rng.mti = 1
	for rng.mti < n {
		rng.mt[rng.mti] = 1812433253*(rng.mt[rng.mti-1]^(rng.mt[rng.mti-1]>>30)) + uint32(rng.mti)
		rng.mti++
	}
}

// SeedSlice initializes the generator with a given array of uint32 keys.
func (rng *MT19937) SeedSlice(initKey []uint32) {
	rng.seed(19650218)
	i := 1
	j := 0
	keyLen := len(initKey)
	k := n
	if keyLen > n {
		k = keyLen
	}

	for ; k != 0; k-- {
		rng.mt[i] = (rng.mt[i] ^ ((rng.mt[i-1] ^ (rng.mt[i-1] >> 30)) * 1664525)) + initKey[j] + uint32(j)
		i++
		j++
		if i >= n {
			rng.mt[0] = rng.mt[n-1]
			i = 1
		}
		if j >= keyLen {
			j = 0
		}
	}

	for k = n - 1; k != 0; k-- {
		rng.mt[i] = (rng.mt[i] ^ ((rng.mt[i-1] ^ (rng.mt[i-1] >> 30)) * 1566083941)) - uint32(i)
		i++
		if i >= n {
			rng.mt[0] = rng.mt[n-1]
			i = 1
		}
	}

	rng.mt[0] = 0x80000000 // MSB is 1; assuring non-zero initial array
}

// GenU32 generates a random number on [0, 0xffffffff] interval
func (rng *MT19937) GenU32() uint32 {
	var y uint32
	mag01 := [2]uint32{0x0, matrixA}

	if rng.mti >= n {
		if rng.mti == n+1 {
			rng.seed(5489)
		}

		var kk int
		for kk = 0; kk < n-m; kk++ {
			y = (rng.mt[kk] & upperMask) | (rng.mt[kk+1] & lowerMask)
			rng.mt[kk] = rng.mt[kk+m] ^ (y >> 1) ^ mag01[y&0x1]
		}
		for ; kk < n-1; kk++ {
			y = (rng.mt[kk] & upperMask) | (rng.mt[kk+1] & lowerMask)
			rng.mt[kk] = rng.mt[kk+(m-n)] ^ (y >> 1) ^ mag01[y&0x1]
		}
		y = (rng.mt[n-1] & upperMask) | (rng.mt[0] & lowerMask)
		rng.mt[n-1] = rng.mt[m-1] ^ (y >> 1) ^ mag01[y&0x1]

		rng.mti = 0
	}

	y = rng.mt[rng.mti]
	rng.mti++

	/* Tempering */
	y ^= y >> 11
	y ^= (y << 7) & 0x9d2c5680
	y ^= (y << 15) & 0xefc60000
	y ^= y >> 18

	return y
}

// --------------------------------------------------------------------------
// Tenhou Shuffle Algorithm Details
// --------------------------------------------------------------------------

const (
	MT19937SeedSize = 624
	NumChunks       = 9
	SrcLen          = 1024 / 32 * NumChunks // 288 uint32s
	RndLen          = 512 / 32 * NumChunks  // 144 uint32s
)

// SeedFromBase64 decodes MT19937 seed from a little-endian base-64 encoded string.
func SeedFromBase64(b64 string) ([MT19937SeedSize]uint32, error) {
	var seed [MT19937SeedSize]uint32
	bytes, err := base64.StdEncoding.DecodeString(b64)
	if err != nil {
		return seed, err
	}
	if len(bytes) != MT19937SeedSize*4 {
		return seed, errors.New("invalid seed size")
	}

	for i := 0; i < MT19937SeedSize; i++ {
		seed[i] = binary.LittleEndian.Uint32(bytes[i*4 : (i+1)*4])
	}
	return seed, nil
}

func MTFromSeed(seed [MT19937SeedSize]uint32) *MT19937 {
	mt := NewMT19937()
	mt.SeedSlice(seed[:])
	return mt
}

// SeedFromUint64 expands a single uint64 into a full MT19937 seed array using
// SplitMix64 so tests and RL environments can request deterministic walls
// without having to manage the full 624-word seed payload themselves.
func SeedFromUint64(value uint64) [MT19937SeedSize]uint32 {
	var seed [MT19937SeedSize]uint32
	state := value
	for i := 0; i < MT19937SeedSize; i += 2 {
		word := splitMix64(&state)
		seed[i] = uint32(word)
		if i+1 < MT19937SeedSize {
			seed[i+1] = uint32(word >> 32)
		}
	}
	return seed
}

func splitMix64(state *uint64) uint64 {
	*state += 0x9e3779b97f4a7c15
	z := *state
	z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9
	z = (z ^ (z >> 27)) * 0x94d049bb133111eb
	return z ^ (z >> 31)
}

func SrcFromMT(mt *MT19937) [SrcLen]uint32 {
	var src [SrcLen]uint32
	for i := 0; i < SrcLen; i++ {
		src[i] = mt.GenU32()
	}
	return src
}

func RndFromSrc(src *[SrcLen]uint32) [RndLen]uint32 {
	var rnd [RndLen]uint32
	hasher := sha512.New()

	for i := 0; i < NumChunks; i++ {
		hasher.Reset()

		// Convert block to 128 bytes (32 uint32s)
		blockBytes := make([]byte, 128)
		for j := 0; j < 32; j++ {
			binary.LittleEndian.PutUint32(blockBytes[j*4:(j+1)*4], src[i*32+j])
		}

		hasher.Write(blockBytes)
		hashBlock := hasher.Sum(nil) // 64 bytes

		// Convert the 64 byte hash into 16 uint32s
		for j := 0; j < 16; j++ {
			rnd[i*16+j] = binary.LittleEndian.Uint32(hashBlock[j*4 : (j+1)*4])
		}
	}
	return rnd
}

func RndFromMT(mt *MT19937) [RndLen]uint32 {
	src := SrcFromMT(mt)
	return RndFromSrc(&src)
}

// ShuffleWithRnd shuffles a byte array representing wall tiles using randomness
// derived from MT19937+SHA512. The `wall` should contain values 0..135 sequentially.
func ShuffleWithRnd(wall []byte, rnd *[RndLen]uint32) {
	n := len(wall)
	if n != 144 && n != 136 && n != 108 {
		panic("invalid wall length")
	}
	for i := 0; i < n-1; i++ {
		swapIdx := i + int(rnd[i])%(n-i)
		wall[i], wall[swapIdx] = wall[swapIdx], wall[i]
	}
}

// ShuffleWithMT shuffles the game wall using an active MT19937 generator.
func ShuffleWithMT(wall []byte, mt *MT19937) {
	rnd := RndFromMT(mt)
	ShuffleWithRnd(wall, &rnd)
}
