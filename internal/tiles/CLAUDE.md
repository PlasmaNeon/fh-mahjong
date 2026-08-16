# internal/tiles/

> Canonical tile encodings shared across the engine — the de-duplication target of the 2026-06-27 refactor.

## Overview

This package holds the three things every tile-touching package used to re-implement locally: the per-tile-type face key, the 0-33 standard-tile index, and deep-clone helpers for proto `Tile`/`PlayerAction` values on the bot and RL hot paths.

**It imports only the proto package**, so every other package can depend on it without creating an import cycle. That constraint is why the clone helpers enumerate fields by hand instead of calling `proto.Clone` — pulling in the protobuf runtime here would widen the dependency.

## Key Files

- **tiles.go** — the whole package:
  - `KeyOf(suit, value)` / `Key(t)` — the canonical per-tile-type key, `suit*100+value`. Identifies a tile **face**, ignoring the physical tile id, and matches the hashing used by shanten, scoring, and bot code. A nil tile yields `0`.
  - `Index34Of(suit, value)` / `Index34(t)` — maps a standard man/pin/sou/jihai tile to its 0-33 index; returns `-1` for flowers, unknown suits, and out-of-range values (value < 1, or above the suit maximum: 9 for man/pin/sou, 7 for jihai). **The range guards matter**: a bad value would otherwise silently collide with another suit's index band.
  - `FromIndex34(idx)` — inverse of `Index34Of` for 0-33; any other index yields `(SUIT_UNKNOWN, 0)`.
  - `WildSet(wilds)` — builds a face-key lookup for a round's wild tiles. Nil tiles are skipped; a nil or empty slice yields an empty but non-nil map.
  - `CountWilds(hand, wildSet)` — how many tiles in a hand match the wild set **by face**.
  - `CloneTile(t)` / `CloneAction(a)` — deep copies; nil yields nil.
- **tiles_test.go** — covers the index range guards, the nil-tile contracts, and clone independence.

## Architecture Notes

- **Do not re-inline `suit*100+value` or re-add a local `cloneTile`/`cloneAction`.** That duplication is exactly what this package exists to remove; the same note appears in `internal/bot/CLAUDE.md` and `internal/rules/shanten/CLAUDE.md`.
- Imported by `cmd/cli`, `internal/api`, `internal/bot`, `internal/bot/remote`, `internal/review`, `internal/rl`, `internal/rules`, and `internal/rules/shanten`.
- The face key deliberately discards tile id. Tile id `0` is a real tile (the first 1s) and must never be used as a sentinel — see the root `CLAUDE.md`.
