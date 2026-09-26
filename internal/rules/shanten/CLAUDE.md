# rules/shanten/

> Shanten and discard-analysis helpers for Fenghua mahjong.

## Overview

This package computes closed-hand progress metrics for Fenghua hands. It supports standard hands, seven pairs, and independence, including wild-tile handling. The package is shared by the server shanten API, in-game shanten display, and heuristic bot decision-making.

## Key Files

- **shanten.go** — Core table-based shanten algorithm with wild support. The seven-pairs and independence routes with wilds are closed forms, not a search over wild placements: seven pairs from the pair/kind/single counts, independence from the precomputed per-suit tables `suitMIS[mask]` and `suitMISWithWilds[mask][k]` (best MIS after adding up to k positions — not `min(3, mis+k)`: `{3,7}` cannot reach 3 with one wild) plus an exhaustive split of the wilds over the three suits and the honors. A route whose wilds cannot all be placed (`wildCapacity`) scores 14. This is the RL observation encoder's hot path (`AnalyzeHand` calls `Analyze` ~500x per observation).
- **analysis.go** — Higher-level helpers:
  - `Analyze()` / `AnalyzeFromTiles()` — route-by-route shanten breakdown
  - `AnalyzeHand()` — current-hand useful-tile count plus discard-option analysis
  - `FindUsefulTilesFromTiles()` — effective draws for the current hand state
  - `findUsefulTiles` takes the hand's own `RouteBreakdown` and prunes exactly: one added tile (natural or wild) lowers the seven-pairs or independence shanten by at most one, so a route already >= target+1 is not evaluated for any draw, and at tenpai (clamped target 0) no draw can count, so the loop is skipped. The standard route resumes `calcStandard`'s honor -> sou -> pin -> man chain from a per-hand `standardPrefix`, recomputing only from the group the draw lands in
  - Wild candidate draws are simulated as additional wilds, not as natural copies in the 34-count table
- **tables.go** — Suit/honor DP table generation (DFS). `generateTables()` loads the embedded precomputed tables and only falls back to the ~14s DFS build if the embed is missing/corrupt.
- **tables_embed.go** — Loads `shanten_tables.bin.gz` (gzip'd precomputed suit+honor tables, ~270KB) via `go:embed`, cutting first-use table build from ~14s to ~20ms per process (matters for every worker/eval/CLI startup).
- **shanten_tables.bin.gz** — Committed precomputed tables. Regenerate with `SHANTEN_REGEN=1 go test ./internal/rules/shanten -run TestRegenerateEmbeddedTables` after changing table generation, then commit the new file.
- **tables_embed_test.go** — `TestEmbeddedTablesMatchGeneratedExactly` guarantees the committed tables are byte-identical to the DFS generators (a mismatch would corrupt all hand evaluation); `TestRegenerateEmbeddedTables` (SHANTEN_REGEN=1) rewrites the file.
- **shanten_test.go** — Route, wild, edge-case, and benchmark coverage.
- **useful_tiles_equiv_test.go** — Keeps the unpruned `findUsefulTiles` (a full `Analyze` per draw) as an oracle over 40000 random hands with wilds and open melds, and checks `standardPrefix` against `calcStandard` for every draw position.
- **wild_routes_equiv_test.go** — Keeps the placement-enumeration implementation as an oracle and requires the closed forms to equal it on every suit mask (0-4 wilds) and on random 0-17-tile hands with 0-5 wilds. CI runs 3000 hands; `SHANTEN_EXHAUSTIVE=1` runs 60000 (~10 min). Any change to a wild route must keep this passing.

## Architecture Notes

- Flowers are excluded from shanten calculations; wild flowers are counted as wilds instead.
- `RouteUnavailable` marks routes that are invalid for the current hand shape (for example seven pairs after opening the hand).
- Discard analysis is keyed by tile type (`suit` + `value`) rather than unique tile ID so API consumers and bots get stable, deterministic options.
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/internal/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.
