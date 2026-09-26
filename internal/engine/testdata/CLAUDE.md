# internal/engine/testdata/

> Tenhou wall-shuffle fixtures for the MT19937 exact-match test.

## Key Files

- **2016022509gm-0009-0000-b327da61.\*** — one Tenhou game's shuffle, stage by stage: `seed_str` (base64 seed), `seed_u32` (decoded seed words), `src_u32` / `rnd_u32` (MT19937 output and derived random words), `wall136` (the resulting 136-tile wall).

## Architecture Notes

- Read only by `TestTenhouShuffleExactMatch` in `internal/engine/mt19937_test.go`, which requires `mt19937.go` to reproduce Tenhou's wall exactly.
