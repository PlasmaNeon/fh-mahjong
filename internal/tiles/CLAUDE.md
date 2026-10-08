# internal/tiles/

> Canonical tile encodings shared across packages.

It imports only `proto`, so any package can use it without a cycle; that is also why the clone
helpers copy fields by hand instead of calling `proto.Clone`.

## tiles.go

- `KeyOf(suit, value)` / `Key(t)` — the face key `suit*100+value` (ignores the physical id; nil →
  0). Matches the hashing in shanten, scoring, and the bot.
- `Index34Of` / `Index34` — standard tile → 0–33; −1 for flowers, unknown suits, and out-of-range
  values. The range guards stop a bad value from colliding with another suit's band.
- `FromIndex34(idx)` — the inverse; anything else → `(SUIT_UNKNOWN, 0)`.
- `WildSet(wilds)`, `CountWilds(hand, wildSet)` — wild lookup by face.
- `CloneTile` / `CloneAction` — deep copies; nil → nil.

## Rules

- Never re-inline `suit*100+value` or add a local `cloneTile`/`cloneAction`.
- `internal/engine` does not import this package.
- Tile id `0` is a real tile (the first 1s), never a sentinel.
