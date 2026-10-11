# web/src/utils/

> Shared frontend helpers: tile display, the tile value-model, wind labels, and API JSON parsing.

## Overview

Pages must not re-implement anything here — extend these modules instead.

## Key Files

- **tileDisplay.ts** — Tile display utilities:
  - `getTileSvgName(tile)` — Maps a Protobuf `Tile` (suit + value) to SVG filename (e.g., `1m.svg`, `chun.svg` for flowers)
  - `getTileSvgUrl(svgName)` — Builds the versioned face URL (`?v=hk-color-v3`); renderers and preloading share this helper because the Go server caches stable SVG filenames for 30 days. Bump its artwork version when replacing faces.
  - `getTileName(tile)` — Human-readable tile name (e.g., "1 Man", "East", "Spring")
  - Suit suffix mapping: MAN→`m`, PIN→`p`, SOU→`s`, JIHAI→`z`
  - Flower SVG mapping: values 1-8 → `chun.svg`, `xia.svg`, `qiu.svg`, `dong.svg`, `mei.svg`, `lan.svg`, `ju.svg`, `zhu.svg`
  - Flower name mapping: values 1-8 → Spring, Summer, Autumn, Winter, Plum, Orchid, Chrysanthemum, Bamboo

- **tileModel.ts** — shared tile value-model (`TileValue`/`TileDraft`), `TILE_LIBRARY`, `suitOrder`, format/parse/count helpers, and `makeWildTilePredicate` (the wild-tile 搭 test).
- **winds.ts** — `WIND_KANJI` (traditional 東南西北), `WIND_I18N_KEYS`, `windI18nKey`. Keep it
  separate from `features/replay/reviewUtils.ts`'s `JIHAI_EN`/`JIHAI_ZH`: those name all seven
  honor tiles with simplified 东, while table décor uses traditional 東 (`winds.test.ts` asserts
  the split).
- **apiJson.ts** — `readJsonBody` and `errorMessage` for the API's `{error}` response shape.

## Architecture Notes

- SVG assets are in `web/public/Regular_shortnames/` with names like `1m.svg`, `5p.svg`, `9s.svg`, `1z.svg` (East), `chun.svg` (Spring flower), etc.
- Used by `TileComponent` in `table/Tile.tsx`, by the theme's `LedgerTile`, and by the calc/shanten tool pages.
- `features/calc/calcHelpers.ts` and `features/shanten/shantenHelpers.ts` are thin adapters over it; do not re-implement `TILE_LIBRARY`, tile parsing, or suit ordering in feature helpers. `suitOrder(suit)` (man→pin→sou→jihai→flower) is the single suit-ordering function for the whole app — `table/handOrdering.ts` uses it too.
