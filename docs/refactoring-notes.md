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

## 2026-08-16 — PR 3: Go de-duplication

Behaviour-preserving, per §7.1 of the design doc. Every commit gated on
`gofmt -l . && go vet ./... && go test ./...`, and the engine-touching ones additionally on a
**seeded-paipu differential harness**: `cmd/rlpaipu` over 7 fixed seeds must stay byte-identical
to `main`. It did, at every step.

| Shared home | Owns | Copies removed from |
|---|---|---|
| `engine.FaceIndex42` / `FaceIndex34` / `FaceIndex42FromID` | the 42-face tile space | `rl.tileFaceIndex42/34`, `review.faceIndex42FromTileID/34` |
| `rl.SortedLegalIDs` | the paipu-v2 legal-id snapshot | `api/room_decisions.go`, `cmd/rlpaipu` |
| `rl.ReadyAllPlayersForNextRound` / `IsFinalReadyBeforeNextRound` / `FinalScores` | the ROUND_END ready-ack loop | `rl/env.go`, `review/replay_test.go`, `cmd/rlpaipu` |
| `rl.runSlotCommands` | pool command validation + fan-out + slot ordering | `EnvPool.ApplyCommands`, `SearchPool.Step` |
| `remote.fetchHealthzBody` / `siblingRoute` | the healthz round-trip and /act→sibling-route mapping | `HealthChecker.probe`, `HTTPPolicy.ValidateServer`, `deriveWarmupURL` |
| `storage.PlacementsFromScores` | competition ranking | `api/room.go`, `storage/match_history.go` |
| `internal/review/reviewtest` | the `/evaluate` policy stub | 5 of 26 `httptest` stubs across `api` + `review` |
| `api.newTestDB` / `newTestServer` | in-memory sqlite + AutoMigrate | 5 api test files |

### Divergences made explicit rather than unified

Two "duplicates" were really two behaviours wearing the same shape. Both now take the difference
as a parameter, so it is visible instead of hidden in look-alike functions:

- **Hand-seed derivation.** `internal/rl` uses a splitmix `deriveHandSeed`; the review fixtures were
  generated with `baseSeed*1000+handNum`. `ReadyAllPlayersForNextRound` takes the seed rule as an
  argument. Unifying them would change every recorded paipu.
- **First-legal-action fallback.** `env_test` returns `-1` when nothing is legal; the pool and bench
  copies return `0` because they feed the value straight into a step request.

### Deliberately NOT merged

- **`review.HTTPPolicyClient.CurrentCheckpointSha256`** is a third `/healthz` caller, but returns
  `(string, error)`, reads `checkpoint_sha256` rather than the event-contract fields, and lives in a
  package that does not import `internal/bot/remote`. Sharing would mean a new package dependency
  and a union payload more complex than the three callers.
- **`remote.actionMaskJSON` vs `review.actionMaskToInts`** — identical six-line `[]byte`→`[]int`
  converters spanning those same two packages. Coupling them for six obvious lines costs more than
  it saves.
- **The five remaining `httptest` stubs** are genuinely bespoke (fixed `[1,0]` probability vectors,
  a sha that changes between chunks to drive the mismatch path).

### Still outstanding from the design doc's Go Tier 1

- **Task 7, api handler/room boilerplate** (~65 lines): the private-table handler prelude, the
  sentinel-error → HTTP-status mapping, and the `BroadcastState`/`SendStateToClient` state-prep.
  The broadcast half is the risky one — the two paths differ in per-seat redaction, and leaking an
  opponent's concealed hand is exactly what `state_redaction_test.go` guards. Left for its own PR.
- **G12, a tile-notation parser for test hands** (~450 lines, the single largest item), and
  **G13/G14** (`engine/game.go`, `rules/fh.go`) which §10 of the design doc excludes.

## 2026-08-16 — PR 4: Go renames

Pure motion, per §7.2 of the design doc. Stacked on PR 3 (same files). Every rename is `git mv` +
exact-path reference updates + the matching `CLAUDE.md` edit.

| Was | Now | Why |
|---|---|---|
| `review_round21..25_test.go` (5 files) | `review_auth_test.go`, `review_build_concurrency_test.go`, `review_build_checkpoint_test.go`, `review_get_live_sha_test.go`, `review_ratelimit_test.go` | Named after the review *session* that produced them; they were four unrelated subjects spread across five sessions |
| `api/matchmaker.go` | + `api/queue.go` | One file held the queue structure, matchmaking, the active-room registry and seat policy |
| `InMemoryQueue.RPush/RPushUnique/LRange/LLen/LPopCount` | `Push/PushUnique/Items/Len/PopN` | Redis-list vocabulary on an in-process queue; Redis went in PR #129 and was never wired up |
| `storage/db.go` | `models.go` + `migrate.go` | The file called `db.go` held every GORM model |
| `bot/context.go` | `bot/policy.go` (+ `Policy` moved here from `heuristic.go`) | The package's core interface lived in the file named after one implementation |
| `review/client.go`, `api/client.go` | `policy_client.go`, `ws_client.go` | Same word, two meanings, one package apart |
| `review/context.go` | `chongci_context.go` | Collides with `context.Context` in a package that uses it |
| `engine/rules.go` | `rule_engine.go` | Holds only `RuleEngine`; disambiguates from the `rules` package |
| `bot/remote/identity.go` | `checkpoint_identity.go` | 14 lines about checkpoint identity under a name suggesting auth |
| `cross_room_repro_test.go`, `seat_policy_leak_test.go`, `rl/kan_dup_repro_test.go`, `bot/shadow_round24_test.go` | `private_room_scope_test.go`, `seat_policy_lifecycle_test.go`, `rl/env_fuzz_test.go`, merged into `shadow_test.go` | "repro"/"leak"/session numbers name incidents, not invariants |
| `cmd/cli` | `cmd/play` | An interactive terminal match, not a general CLI; its doc still advertised "offline hand evaluation" |

### How the review-test regroup was verified

The five files' 28 `Test` functions were **diffed by name** against the five new files: identical
set, nothing lost or duplicated. The four cross-file helpers moved into `review_test.go` (already
the shared helper home) rather than into a subject file, which would have stranded them for four
other callers.

### Two design-doc proposals rejected on the evidence

- `rl_agent_test.go` and `warmup_admission_test.go` → the doc proposed `matchmaker_*_test.go`.
  Reading them, both names already describe their subject. Left alone.
- `rl/kan_dup_repro_test.go` → the doc guessed `wall_consumption_fuzz_test.go`. The test actually
  fuzzes the **action-mask builder** for duplicate action ids, so it is `env_fuzz_test.go`, and its
  test function is now `TestFuzzActionMaskHasNoDuplicateIDs` — an invariant, not a bug reproduction.

### Deferred (endorsed, not done)

Splitting `api/room.go` (1,258 lines), `api/server.go`, and `cmd/server/main.go` → `policy_wiring.go`.
All real, all file surgery on the busiest files in the backend; they should not ride along with a
rename PR. `cmd/rlpaipu` → `cmd/paipugen` and `cmd/rlsmoke` → `cmd/paipusmoke` were endorsed only
weakly (low value, 9 refs including Makefile and runbooks) and are dropped.

## 2026-08-16 — PR 5: ai de-duplication (partial)

Behaviour-preserving, per §8.1 of the design doc. Gated on
`uv run --project ai pytest ai/tests` (**915 → 921 passed**, 2 skipped) and, for anything touching
the model or serving path, on `fh-mj-serving-parity --in-process` against the committed champion
(189/189 decisions, max logit diff 0.000e+00).

| Shared home | Owns | Copies removed from |
|---|---|---|
| `evaluate.parse_seed_windows` | seed-window expansion | 5 CLIs (4 identical + 1 variant) |
| `storage.write_json_report` | the report JSON encoding | 3 eval CLIs |
| `storage.write_single_shard_dataset` | one-shard npz + manifest | `build_counterfactual_risk_data`, `replay_policy_diagnostics` |
| `model.build_plane_scalar_encoders` | the plane/scalar observation trunk | `PolicyValueNet`, `GlobalEVNet`, `ActionGlobalEVNet` |
| `ai/tests/conftest.py` | `SMALL_MODEL`, `small_model_config`, `make_observation`, `save_checkpoint` | 8 test files (there was no conftest at all) |

### The encoder trunk is the one to be careful with

`build_plane_scalar_encoders` returns the modules **loose**, as a NamedTuple, for the caller to
assign under their historical attribute names. It deliberately does **not** wrap them in a container
`Module`: those attribute names *are* the `state_dict` keys in every committed checkpoint, so
nesting them would prefix every key (`trunk.plane_stem.*`) and stop the deployed champion loading.

Verified by capturing the key sets before and after (36 keys for `PolicyValueNet`, 18 for
`GlobalEVNet` — identical), loading the champion, and running serving-parity.
`test_model.py` now pins the shape so a future "tidy-up" into a sub-Module fails loudly.

### Two traps worth remembering

- **`test_storage.py`'s `_SMALL` was function-local**, not module-level. An unanchored regex removed
  its text and left the indentation behind, which surfaced as an `IndentationError` two lines later.
  Every touched file is now `ast.parse`-checked.
- **`write_divergence_shard` emits a manifest block named `"counterfactual"`**, not `"divergence"`.
  Parameterising it by function name looked like an improvement and was an on-disk format change;
  the test suite caught it. Both callers keep the historical key.

### Still outstanding from the design doc's ai Tier 1

`scripts/env_args.py` and `ppo_args.py` (the argparse blocks, ~225 lines), MLflow arg/run setup
(~90), the checkpoint→net loader (~45), the diagnostics statistics helpers (~70), the
`evaluate_duplicate_seats` near-copy (~135), the four spawn rollout pools (~210), the serving-test
HTTP harness (~80), and A15 `tensorize` (the serving path — gate with `fh-mj-serving-parity`).
