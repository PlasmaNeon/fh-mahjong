# Refactoring Notes — Duplication Removal (2026-06-27)

## Go: `tiles` package (`github.com/plasma/fh-mahjong/tiles`)

A leaf package (imports only `proto`) that owns:
- `Key` / `KeyOf` — canonical tile-type key `suit*100+value`.
- `Index34` / `Index34Of` / `FromIndex34` — 0-33 standard-tile index + inverse.
- `CloneTile` / `CloneAction` — lightweight proto deep-clones.

Replaced these previously-duplicated definitions:
| Removed | Was in |
|---------|--------|
| `tileToIndex`, inline `*100+value` | `rules/shanten/shanten.go` |
| `tileHash`, `indexToTile` | `rules/shanten/analysis.go` |
| 8 inline `*100+value` sites | `rules/fh.go` |
| `tileToShantenIndex`, `shantenIndexToTile`, inline keys | `api/shanten.go` |
| `tileTypeHash`, `cloneTile`, `cloneAction` | `bot/heuristic.go` |
| `cloneTile`, `cloneAction`, `tileTypeKey` | `rlenv/action.go`, `rlenv/observation.go` |
| 2 inline `*100+value` sites | `cmd/cli/main.go` |

Rule: never re-inline `suit*100+value` or re-add a local `cloneTile`/`cloneAction`; use `tiles`.
Note: the 42-plane index (`tileFaceIndex42`) stays in `rlenv` — it is observation-specific, not shared.
Note: `rules/fh.go` intentionally keeps its OWN `tileToIndex` (the row above removed the
`rules/shanten` one only). fh.go's version returns `0` (not `-1`) for flowers/unknown, and its
callers index `counts[tileToIndex(t)]` WITHOUT a `>= 0` guard — so do NOT replace it with
`tiles.Index34`, which returns `-1` and would index `counts[-1]` and panic.
`core/` deliberately does NOT depend on `tiles` (it has no tile-key needs and must stay ruleset-agnostic).

## Frontend: `web/src/utils/tileModel.ts`

Owns the shared tile value-model (`TileValue`/`TileDraft`), `TILE_LIBRARY`, suit
ordering, `formatTile`/`formatHand`, `parseHand`/`parseSingleTile`, and tile
counting. `pages/calcHelpers.ts` and `pages/shantenHelpers.ts` are now thin
adapters that preserve their exact public APIs and output strings (calc uses
space-separated/per-tile formatting and collects all parse errors; shanten uses
compact formatting and a single-error contract).

Rule: page helpers must not re-implement tile parsing/formatting/sorting — extend `tileModel.ts`.
