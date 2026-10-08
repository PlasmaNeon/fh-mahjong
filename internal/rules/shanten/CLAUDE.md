# internal/rules/shanten/

> Shanten and discard analysis with wild support, for standard, Seven Pairs, and Independence
> routes. Used by the shanten API, the in-game display, the heuristic bot, and the RL encoder.

## Key files

- **shanten.go** — table-based shanten. Seven Pairs and Independence with wilds are closed forms:
  Seven Pairs from pair/kind/single counts, Independence from precomputed per-suit tables
  (`suitMIS`, `suitMISWithWilds`) plus an exhaustive split of wilds across suits and honors. A
  route whose wilds cannot all be placed scores 14. This is the RL encoder's hot path (~500 calls
  per observation).
- **analysis.go** — `Analyze` / `AnalyzeFromTiles` (route breakdown), `AnalyzeHand` (useful-tile
  count plus per-discard options), `FindUsefulTilesFromTiles`, and `WinningTiles` (the draws that
  complete a tenpai hand; used by the look-ahead planes). `findUsefulTiles` prunes routes that one
  tile cannot improve and reuses a per-hand standard-route prefix. Wild candidate draws are
  simulated as extra wilds.
- **tables.go**, **tables_embed.go**, **shanten_tables.bin.gz** — DFS-generated suit and honor
  tables, embedded precomputed (~270 KB; ~20 ms load instead of ~14 s). Regenerate with
  `SHANTEN_REGEN=1 go test ./internal/rules/shanten -run TestRegenerateEmbeddedTables` and commit
  the file.

## Invariants

- `TestEmbeddedTablesMatchGeneratedExactly` keeps the committed tables identical to the
  generator.
- `useful_tiles_equiv_test.go` and `wild_routes_equiv_test.go` keep the unpruned and
  placement-enumeration implementations as oracles; any change to a route must pass them
  (`SHANTEN_EXHAUSTIVE=1` runs the ~10-minute version).
- Flowers are excluded; wild flowers count as wilds. `RouteUnavailable` marks impossible routes
  (e.g. Seven Pairs with an open meld).
- Discard options are keyed by tile face, not physical id.
- Use the shared `tiles` package for face keys and the 0–33 index.
