# web/src/utils/

> Utility functions for tile display and data conversion.

## Overview

Shared helper functions used across frontend components for mapping tile data to display names and SVG asset paths.

## Key Files

- **tileUtils.ts** — Tile display utilities:
  - `getTileSvgName(tile)` — Maps a Protobuf `Tile` (suit + value) to SVG filename (e.g., `1m.svg`, `chun.svg` for flowers)
  - `getTileName(tile)` — Human-readable tile name (e.g., "1 Man", "East", "Spring")
  - `getSuitOrder(suit)` — Sort order for suits: MAN=1, PIN=2, SOU=3, JIHAI=4, FLOWER=5
  - Suit suffix mapping: MAN→`m`, PIN→`p`, SOU→`s`, JIHAI→`z`
  - Flower SVG mapping: values 1-8 → `chun.svg`, `xia.svg`, `qiu.svg`, `dong.svg`, `mei.svg`, `lan.svg`, `ju.svg`, `zhu.svg`
  - Flower name mapping: values 1-8 → Spring, Summer, Autumn, Winter, Plum, Orchid, Chrysanthemum, Bamboo

## Architecture Notes

- SVG assets are in `web/public/Regular_shortnames/` with names like `1m.svg`, `5p.svg`, `9s.svg`, `1z.svg` (East), `chun.svg` (Spring flower), etc.
- Used by `TileComponent` in `Game.tsx` and by `Calc.tsx`.
- **tileModel.ts** — shared tile value-model + format/sort/parse primitives. `features/calc/calcHelpers.ts` and `features/shanten/shantenHelpers.ts` are thin adapters over it; do not re-implement `TILE_LIBRARY`, tile parsing, or suit ordering in feature helpers.
