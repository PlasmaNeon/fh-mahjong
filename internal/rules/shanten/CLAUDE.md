# rules/shanten/

> Shanten and discard-analysis helpers for Fenghua mahjong.

## Overview

This package computes closed-hand progress metrics for Fenghua hands. It supports standard hands, seven pairs, and independence, including wild-tile handling. The package is shared by the server shanten API, in-game shanten display, and heuristic bot decision-making.

## Key Files

- **shanten.go** — Core table-based shanten algorithm with wild support.
- **analysis.go** — Higher-level helpers:
  - `Analyze()` / `AnalyzeFromTiles()` — route-by-route shanten breakdown
  - `AnalyzeHand()` — current-hand useful-tile count plus discard-option analysis
  - `FindUsefulTilesFromTiles()` — effective draws for the current hand state
  - Wild candidate draws are simulated as additional wilds, not as natural copies in the 34-count table
- **tables.go** — Suit/honor DP table generation (DFS). `generateTables()` loads the embedded precomputed tables and only falls back to the ~14s DFS build if the embed is missing/corrupt.
- **tables_embed.go** — Loads `shanten_tables.bin.gz` (gzip'd precomputed suit+honor tables, ~270KB) via `go:embed`, cutting first-use table build from ~14s to ~20ms per process (matters for every worker/eval/CLI startup).
- **shanten_tables.bin.gz** — Committed precomputed tables. Regenerate with `SHANTEN_REGEN=1 go test ./internal/rules/shanten -run TestRegenerateEmbeddedTables` after changing table generation, then commit the new file.
- **tables_embed_test.go** — `TestEmbeddedTablesMatchGeneratedExactly` guarantees the committed tables are byte-identical to the DFS generators (a mismatch would corrupt all hand evaluation); `TestRegenerateEmbeddedTables` (SHANTEN_REGEN=1) rewrites the file.
- **shanten_test.go** — Route, wild, edge-case, and benchmark coverage.

## Architecture Notes

- Flowers are excluded from shanten calculations; wild flowers are counted as wilds instead.
- `RouteUnavailable` marks routes that are invalid for the current hand shape (for example seven pairs after opening the hand).
- Discard analysis is keyed by tile type (`suit` + `value`) rather than unique tile ID so API consumers and bots get stable, deterministic options.
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/internal/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.
