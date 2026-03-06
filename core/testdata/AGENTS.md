# core/testdata/

> Deterministic seed files for reproducible game test replays.

## Overview

Contains binary seed data used by `game_test.go` to create deterministic wall shuffles via the Mersenne Twister PRNG. Each file represents a known initial state that produces a specific tile ordering, enabling predictable test scenarios.

## Key Files

- **seed_*.bin** — Binary seed data files, each producing a specific wall arrangement for testing different game scenarios (directed melds, dead wall draws, etc.)

## Architecture Notes

- Used exclusively by `core/game_test.go` via `os.ReadFile()`.
- Seeds pair with the MT19937 PRNG in `core/mt19937.go` to guarantee identical wall orderings across runs.
