# Refactoring Notes — Duplication Removal (2026-06-27)

## Go: `tiles` package (`github.com/plasma/fh-mahjong/internal/tiles`)

A leaf package (imports only `proto`) that owns:
- `Key` / `KeyOf` — canonical tile-type key `suit*100+value`.
- `Index34` / `Index34Of` / `FromIndex34` — 0-33 standard-tile index + inverse.
- `CloneTile` / `CloneAction` — lightweight proto deep-clones.

Replaced these previously-duplicated definitions:
| Removed | Was in |
|---------|--------|
| `tileToIndex`, inline `*100+value` | `internal/rules/shanten/shanten.go` |
| `tileHash`, `indexToTile` | `internal/rules/shanten/analysis.go` |
| 8 inline `*100+value` sites | `internal/rules/fh.go` |
| `tileToShantenIndex`, `shantenIndexToTile`, inline keys | `internal/api/shanten.go` |
| `tileTypeHash`, `cloneTile`, `cloneAction` | `internal/bot/heuristic.go` |
| `cloneTile`, `cloneAction`, `tileTypeKey` | `internal/rl/action.go`, `internal/rl/observation.go` |
| 2 inline `*100+value` sites | `cmd/cli/main.go` |

Rule: never re-inline `suit*100+value` or re-add a local `cloneTile`/`cloneAction`; use `tiles`.
Note: the 42-plane index (`tileFaceIndex42`) stays in `internal/rl` — it is observation-specific, not shared.
Note: `internal/rules/fh.go` intentionally keeps its OWN `tileToIndex` (the row above removed the
`internal/rules/shanten` one only). fh.go's version returns `0` (not `-1`) for flowers/unknown, and its
callers index `counts[tileToIndex(t)]` WITHOUT a `>= 0` guard — so do NOT replace it with
`tiles.Index34`, which returns `-1` and would index `counts[-1]` and panic.
`internal/engine/` deliberately does NOT depend on `tiles` (it has no tile-key needs and must stay ruleset-agnostic).

## Frontend: `web/src/utils/tileModel.ts`

Owns the shared tile value-model (`TileValue`/`TileDraft`), `TILE_LIBRARY`, suit
ordering, `formatTile`/`formatHand`, `parseHand`/`parseSingleTile`, and tile
counting. `pages/calcHelpers.ts` and `pages/shantenHelpers.ts` are now thin
adapters that preserve their exact public APIs and output strings (calc uses
space-separated/per-tile formatting and collects all parse errors; shanten uses
compact formatting and a single-error contract).

Rule: page helpers must not re-implement tile parsing/formatting/sorting — extend `tileModel.ts`.

## 2026-08-16 — PR 1a: frontend de-duplication

Second de-duplication pass, from
`docs/superpowers/specs/2026-08-16-dedup-and-naming-refactor-design.md` §6.1.
Behaviour-preserving: no rendered output, copy, or API changed.

New shared homes — pages must not re-implement these:

| Module | Owns | Replaced copies in |
|---|---|---|
| `table/tileId.ts` | `tileIdsEqual` | `table/meldOrdering.ts`, `table/tileFlightPlan.ts` (both re-export it) |
| `theme/components/LedgerTile.tsx` | `LedgerTile`, `LedgerTileRow`, `LedgerPaletteGrid` | `features/calc/Calc.tsx`, `features/shanten/Shanten.tsx` |
| `hooks/computeStageLayout.ts` → `stageStyles()` | the fixed-stage `shellStyle`/`stageStyle` | `features/game/Game.tsx`, `features/replay/Replay.tsx`, `features/dev/TableSample.tsx` |
| `utils/tileModel.ts` → `makeWildTilePredicate()` | the wild-tile (搭) test | `Game.tsx`, `Replay.tsx` |
| `utils/winds.ts` | `WIND_KANJI`, `WIND_I18N_KEYS`, `windI18nKey` | `table/TableScene.tsx`, `features/game/SeatCard.tsx`, `features/replay/ReplayLibrary.tsx` |
| `utils/apiJson.ts` | `readJsonBody`, `errorMessage` | 6 feature files, 10 parse sites, 13 fallback sites |
| `test/` | `cssContract.ts`, `renderStatic.tsx`, `memoryStorage.ts` | 8 test files |

### Deliberately NOT merged (do not "fix" these later)

- **`features/replay/reviewUtils.ts` `JIHAI_EN`/`JIHAI_ZH` vs `utils/winds.ts`.** Jihai *tile*
  names cover seven faces (incl. Haku/Hatsu/Chun) and use **simplified** 东; the table décor and
  seat plaques use **traditional** 東. Merging would change rendered characters.
  `utils/winds.test.ts` asserts the split.
- **`features/calc/calcHelpers.ts` `WIND_OPTIONS`.** An English-only `{value,label}` form-option
  list — a different shape for a different job.
- **`features/shanten/Shanten.tsx`'s response parse.** It falls back to
  `{ error: 'Request failed' }` rather than `{}`, so `readJsonBody` would change what the user
  sees when a body is not JSON.
- **`theme/components/GameDialog.test.ts`.** Renders without `I18nProvider`; using `renderStatic`
  would add a provider rather than remove a duplicate.

### Notes

- `LedgerTile`'s `disabled` is an explicit prop, not derived from `dimmed`: shanten disables
  exhausted palette tiles, calc's palette stays clickable. Passing `usedCounts` to
  `LedgerPaletteGrid` switches on the shanten badge/disable behaviour.
- `replayEngine.ts` had no tests; its chii/pon and okan steal branches were merged only after
  four characterization tests were written against the duplicated code and seen to pass.
- The design doc listed `replayEngine.ts:228-231` as a third wild-tile-key site. It has no such
  code; nothing was changed there.
