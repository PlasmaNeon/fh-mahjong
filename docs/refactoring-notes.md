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

## 2026-08-16 — PR 1b: frontend CSS and copy de-duplication

Second half of the web pass. Net **-393 production lines**, -381 of them CSS.

| Change | Result |
|---|---|
| Deleted the orphaned legacy seat-layout CSS in `index.css` | 36 rules + 5 grouped-selector trims, -267 lines, -4.1KB built |
| Removed `theme/base.css`'s dead first-layer declarations | 121 declarations + 20 emptied rules, -124 lines, -2.9KB built |
| Moved the calc/shanten private dictionaries into `i18n/locales` | 97 entries now type-checked for EN/ZH parity |
| Extracted `theme/components/InputApplyRow.tsx` | replaced 5 hand-typed `.ldg-input-row` blocks |

### How the CSS changes were verified (there is no type checker for CSS)

- **Dead CSS:** a guard test (`table/deadCss.test.ts`) asserts each removed family has zero
  component references, with the live classes as a *control* proving the check can tell dead
  from live. The built stylesheet was then diffed rule-by-rule: 40 rules disappear, every one
  explained by a dead class, and the single altered selector group keeps byte-identical
  declarations.
- **base.css:** the transform deletes only declarations that a *later same-selector rule already
  overrides* — it never moves a rule. Merging rules (as first planned) would reorder the cascade,
  and a rule-set diff cannot detect that. Guards: a declaration is removed only when every
  selector in its rule's list is restated later with that property; `!important` is never removed
  and never counts as coverage; `@media`/`@keyframes` blocks are untouched. Verified by computing
  the effective last-wins declaration map for all 226 selectors before and after — zero differences.

### i18n scoping — do not merge these later

Only **9** of the tool-page keys are shared (`tools.*`); the rest stay `calc.*` / `shanten.*`.
Three pairs share English text but differ in Chinese, so merging would silently change the zh UI:

| key | calc | shanten |
|---|---|---|
| `apply` | 应用 | 确认 |
| `tilePalette` | 牌库 | 选牌 |
| `language` | English | EN |

`i18n/I18nContext.test.ts` asserts this split.

### Still outstanding from the design doc's web Tier 1

Task 11 — the three ad-hoc en/zh label mechanisms in `features/replay/`, the four hand-rolled
segmented controls that duplicate the `Toggle` primitive, the `東` compass mark in three places,
and the repeated tile-box size blocks (~200 lines). Not started.

## 2026-08-16 — PR 2: frontend renames

Pure motion, per §6.2 of the design doc. Every rename is `git mv` + exact-path import updates +
the matching `CLAUDE.md` edit, one commit each. **All 11 renamed files keep their history under
`git log --follow`** (verified; `PrivateRoom.tsx` traces 23 commits, `table-geometry.css` 33).

| Was | Now | Why |
|---|---|---|
| `src/index.css` (1,244 lines) | `table/table-geometry.css` + a 23-line `index.css` | It was the fixed-stage table geometry, not an app stylesheet |
| `table/TableScene.tsx` | `table/TableBoard.tsx` + `table/TableRoundResultOverlay.tsx` | There was no `TableScene` symbol; the file held two unrelated components |
| `features/game/Table.tsx` | `features/game/PrivateRoom.tsx` | It is the `/room/:roomId` waiting screen, one import from `TableScene`/`TableSample` |
| `hooks/{computeStageLayout,useGameStageLayout}` | `table/stage/` | `computeStageLayout` is not a hook |
| `features/replay/reviewTypes.ts` | `reviewClient.ts` | It exports `fetchReview`/`generateReview` |
| `features/auth/authModal.ts` | `authRouteState.ts` | It owns route state, not a modal |
| `features/lobby/navigation.ts` | `playIntent.ts` | A one-shot play-intent store, not routing |
| `utils/tileUtils.ts` | `utils/tileDisplay.ts` | Distinguishes it from `tileModel.ts`, the value model |
| `theme/components/ToolsRow.tsx` | `ButtonRow.tsx` | A generic button row, not tool-specific |
| `replayLibrary.test.ts`, `streamlinedNavigation.test.ts` | `replayReference.test.ts`, `Home.test.ts` | Named after what they test |

### Two things worth knowing

- **The `TableScene` split is two commits on purpose.** Done in one, git paired the rename with the
  *overlay* (65% similarity) and recorded `TableBoard.tsx` as a new file, so `--follow` needed a
  lowered threshold. Splitting into "pure rename" then "extract the overlay" gives both files clean
  history. Do the same for any future split.
- **`index.css` cannot preserve exact rule order.** CSS requires `@import` before other rules, so
  the geometry now precedes `body`/`#root`/`.app-root` instead of following them. Verified inert:
  same 851 rules and 91,770 bytes, identical rule set, and the geometry never styles those three
  selectors (nor they anything it styles), so nothing can win differently.

### Also fixed (stale docs the audit found)

- `table/CLAUDE.md` documented `SeatLane`/`DiscardLane` components inside `TableScene.tsx` — neither
  exists; those words live in CSS class names.
- `table/seat/CLAUDE.md` called `PlayerSeat` "the seat plaque: name, wind, score" — it is the
  seat-lane composition; wind and score render in `CenterHud.tsx`.
- `utils/CLAUDE.md` pointed at `Game.tsx` for `TileComponent` — it lives in `table/Tile.tsx`.
- `hooks/CLAUDE.md` described the directory as "focused on WASM integration" and now records what
  the audit found: **`useMahjongWasm.ts` has zero importers.**

### Deferred (endorsed, not done)

`public/Regular_shortnames/` → `public/tiles/` (needs a matching mount change in
`internal/api/server.go`); regrouping `features/game/{PrivateRoom,SeatCard,roomNavigation}` into
`features/room/`; deleting the dead `useMahjongWasm.ts` (a judgement call, not a rename).
