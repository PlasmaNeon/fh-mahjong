# web/src/utils/

> Utility functions for tile display and data conversion.

## Overview

Shared helper functions used across frontend components for mapping tile data to display names and SVG asset paths.

## Key Files

- **tileUtils.ts** — Tile display utilities:
  - `getTileSvgName(tile)` — Maps a Protobuf `Tile` (suit + value) to SVG filename (e.g., `Man1.svg`)
  - `getTileName(tile)` — Human-readable tile name (e.g., "1m", "East")
  - `getSuitOrder(suit)` — Sort order for suits: MAN=1, PIN=2, SOU=3, JIHAI=4
  - Suit suffix mapping: MAN→`m`, PIN→`p`, SOU→`s`, JIHAI→`z`

## Architecture Notes

- SVG assets are in `web/public/Regular_shortnames/` with names like `Man1.svg`, `Pin5.svg`, `Sou9.svg`, `Ton.svg` (East), etc.
- Used by `TileComponent` in `Game.tsx` and by `Calc.tsx`.
