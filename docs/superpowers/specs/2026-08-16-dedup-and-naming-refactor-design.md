# Repo-wide De-duplication and Naming Refactor — Design

**Date:** 2026-08-16
**Branch/worktree:** `worktree-refactor+dedup-2026-08` (`.claude/worktrees/refactor+dedup-2026-08`)
**Status:** design — awaiting approval before any code change

## 1. Goal and scope

Two related asks, one campaign:

1. **De-duplicate** code across the repo, working **frontend → backend → deep-learning** in that order.
2. **Rename** directories and files whose names no longer say what they hold.

**Non-goals.** No behaviour changes, no new features, no performance work, no dependency
changes, no proto changes. Every step is a refactor: the same inputs must produce the same
outputs, and the test suites are the proof.

## 2. How the candidates were found

| Stage | Method |
|---|---|
| Mechanical scan | `jscpd` (min 50 tokens / 6 lines) over `web/src`, `internal`, `cmd`, `ai/src`, `ai/tests`, excluding generated code |
| Semantic sweep | 12 independent finder agents (4 lenses x 3 subsystems) reading the code, seeded by the jscpd clone list |
| Naming sweep | 6 auditor agents (layout + file-name lenses x 3 subsystems), each reading every directory's `CLAUDE.md` |
| Verification | Adversarial verifier agents re-opened every cited site, corrected line ranges, counted referrers, and refuted candidates that only look alike |

### 2.1 How far each claim has been verified

Being explicit about this, because the plan's credibility rests on it:

| Claim class | Status |
|---|---|
| **Naming proposals** (all 99) | **Adversarially verified.** A second agent re-opened each file, confirmed the evidence, counted referrers across imports/docs/`Makefile`/`Dockerfile*`/CI/runbooks, and could reject. 25 endorsed as-is, 54 endorsed with a better name, **20 rejected** — the rejections are recorded in each section, including two that were in my own draft |
| **Ten headline de-duplication claims** | **Verified by hand** in this session — the three 42-face-index implementations, the three byte-identical stage-style blocks, the 26 `httptest` stubs across 9 files, the four identical `parse_seed_windows`, the nine dead CSS families (with live controls), `ai/tests` having no `conftest.py`, `oracle.py`'s 50 definitions, `InMemoryQueue`'s Redis method names, `useMahjongWasm`'s zero importers, and the Go import directions that make the proposed homes legal |
| **The other de-duplication candidates** | **Finder-reported, not yet adversarially verified.** Two or three independent lenses agreed on most of them, and the jscpd clone list seeds many, but their line counts are estimates. Each is verified at the moment it is implemented — that is what step 1 of §9.2 is for |

The de-duplication verification pass was cut short by session limits; the naming pass completed.
Rather than delay the plan, the Tier 1 items carry hand-verified evidence and everything else is
labelled as a candidate. No Tier 1 item rests on an unverified claim.

`jscpd` headline: **4.76% of lines are token-identical duplicates** (Python 6.54%, Go 4.44%,
TypeScript ~1.7%). Token-identical copies are the floor, not the ceiling — most of what follows
is semantic duplication that a clone detector cannot see.

## 3. Baseline (verified on this worktree)

```
gofmt -l .            clean
go vet ./...          clean
go test ./...         ok (all packages)
cd web && npx tsc     clean
cd web && npx vitest  28 files, 165 tests passed
uv run --project ai pytest ai/tests    915 passed, 2 skipped
```

One environment gotcha worth recording: a fresh worktree has no
`build/libfh_mahjong_bridge.dylib`, so `ai/tests` fails at `ctypes.CDLL` until you run
`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge`.

**CI covers Go and web only** (`.github/workflows/ci.yml`: gofmt/vet/test, then npm ci/tsc/vitest).
There is no Python job, so `ai/` changes are gated by local `pytest` — see §9.3.

## 4. Principles the refactor follows

1. **Behaviour-preserving, always.** If unifying two copies would change either one's behaviour,
   the shared version takes a parameter, or the candidate is dropped.
2. **Extract to the existing home.** Prefer the module that already owns the concept
   (`internal/tiles`, `web/src/utils/tileModel.ts`, `ai/.../storage.py`) over a new "utils" bucket.
3. **Respect the architecture invariants.** `internal/engine` must not import `internal/rules`;
   `ai/events.py` mirrors `internal/rl/eventcodec.go` (change both or neither); scoring entries
   only via `rules.NewScoreEntry`; Go stays the legality authority for RL actions.
4. **Renames are `git mv` + reference updates, in their own commits**, never mixed with logic
   changes — so a reviewer can read a rename commit as pure motion.
5. **One PR per subsystem**, in the user's order, each independently green and mergeable.
6. **Docs travel with the code.** Every touched directory's `CLAUDE.md` is updated in the same PR,
   and `docs/refactoring-notes.md` gains the new shared-module rules.
## 5. What this adds up to

| Subsystem | Candidates found | ~Lines removable | Clone rate (jscpd) | Where it concentrates |
|---|---:|---:|---:|---|
| Frontend `web/src` | 39 | ~1,340 | 1.7% | CSS (two layers + a dead layout system), the two tool pages, the three table-driving pages, the fetch layer, test scaffolding |
| Backend `internal/`, `cmd/` | 54 | ~2,750 | 4.4% | Test fixtures (~half), the policy-server HTTP layer, the self-play/paipu driver, tile-index helpers |
| Deep learning `ai/` | 39 | ~2,700 | 6.5% | Test fixtures (no `conftest.py` at all), script CLI plumbing, diagnostics statistics, model encoder trunks |
| **Total** | **132** | **~6,800** | **4.8%** | |

Roughly 40% of the total is test-only code, which is where the plan starts in each subsystem: it
is the lowest-risk work, and consolidating fixtures first makes the production extractions that
follow easier to verify.

These are *candidate* line counts from the discovery sweep. The plan commits to the Tier 1 items;
Tier 2 and Tier 3 are recorded so nothing is lost, not promised.
## 6. Frontend (`web/src`) — PR 1 and PR 2

TypeScript is the *least* duplicated subsystem by clone percentage (~1.7%), but its duplication is
concentrated where it hurts most: the two tool pages, the three pages that drive the shared table,
and the fetch layer.

### 6.1 De-duplication (PR 1)

**Tier 1 — do these**

| # | What is duplicated | Copies | Shared home |
|---|---|---|---|
| W1 | `CalcTile`/`ShantenTile`, `TileRow`/`HandRow`, and both `PaletteGrid`s — same `ldg-tile` button, same `TILE_LIBRARY` grid, drifted independently (Calc's tile never disables) | `features/calc/Calc.tsx:204-286`, `features/shanten/Shanten.tsx:106-197` | **new** `theme/components/LedgerTile.tsx` — `LedgerTile`, `LedgerTileRow`, `LedgerPaletteGrid` (optional `badge`, `usedCounts`) |
| W2 | The fixed-stage wrapper: identical `stageShellStyle`/`stageStyle` objects **and** the `stage-rotator › game-stage-shell › game-stage-frame › game-stage` JSX | `features/game/Game.tsx:321-333,537-562`, `features/replay/Replay.tsx:174-186,274-294`, `features/dev/TableSample.tsx:130-141,208-226` | `hooks/useGameStageLayout.ts` returns `shellStyle`/`stageStyle`; **new** `table/GameStage.tsx` owns the wrapper |
| W3 | JSON API boilerplate — POST body + `.json().catch(() => ({}))` + `data.error \|\| fallback` + `TypeError`→offline mapping, retyped in 6 files | `features/auth/{Account,AuthTicket}.tsx`, `features/game/Table.tsx` (x4), `features/lobby/{Lobby,CreateRoom}.tsx`, `features/replay/ReplayLibrary.tsx` | `features/auth/authClient.ts` (already the fetch module) — `postJson`, `readJsonBody`, `requireOk` |
| W4 | Tool-page chrome: the `ClubShell`+`ToolTabs`+header+language-toggle block, the input+apply row (x5), the chooser row (x3), plus **three private en/zh dictionaries** that bypass `useI18n()` — 17 overlapping keys, 12 EN and 10 ZH values byte-identical, and several that restate catalog entries that already exist (`language.switch`, `result.tsumo`, `nav.tools`) | `features/calc/Calc.tsx:51-178,643-797`, `features/shanten/Shanten.tsx:25-102,346-481`, `features/replay/ReviewPanel.tsx:45-83` | `theme/components/ToolWorkbench.tsx` + `InputApplyRow.tsx`; strings move to `i18n/locales/{en,zh-CN}.ts` under `tools.*` |
| W5 | Test scaffolding: `pixelVariable`/CSS-rule extraction copied across 3 layout tests; 4 files each define their own `renderToStaticMarkup(...)` wrapper; `ReviewPanel.test.ts` repeats an 11-prop object 5 times | `table/{compactHandLayout,desktopHandLayout,roundResultOverlay}.test.ts`, `features/auth/AuthDialog.test.ts`, `features/lobby/streamlinedNavigation.test.ts`, `theme/components/GameDialog.test.ts`, `features/replay/ReviewPanel.test.ts` | **new** `test/cssContract.ts` + `test/renderStatic.ts`; a local `renderPanel(overrides)` in `ReviewPanel.test.ts` |

**Tier 1 — CSS and i18n** (the largest web category, ~800 lines)

| # | What | Where | Action |
|---|---|---|---|
| W10 | **Dead CSS.** `index.css` carries two complete per-direction seat-layout implementations. The BEM one (`.seat-bundle*`, `.seat-hand__tiles--*`, `.discard-lane--*`) is what the components render; the older one (`.hand-container-*`, `.hand-main-block-*`, `.hand-inner-*`, `.melds-container-*`, `.melds-main-*`, `.flowers-container-*`, `.discard-pool*`, `.center-info-match`, `.center-info-status`) is referenced by **zero** components | `index.css:165-365,676-772,1178-1245` | Delete (~260 lines). **Verified by hand:** all nine families score 0 component references; the live controls (`seat-bundle`, `discard-lane`, `center-seat`, `seat-meld-group`) score 3-4 each |
| W11 | `theme/base.css` is **two full passes over the same design system** — a "legacy geometry" layer (1-757) and a "Rainy Club skin" layer (759-1293) re-declaring the same 55 selectors. 31 declarations are byte-identical no-ops; 90 are overridden and never reach the browser | `theme/base.css` | Merge selector-by-selector, skin value wins (~120 lines). Medium risk: some layer-1 declarations are *not* restated (`.ldg-input { flex: 1 }`, `.ldg-toggle { overflow: hidden }`) and must survive — so this is a per-selector merge, never a range delete, verified by diffing the built stylesheet |
| W12 | Three ad-hoc en/zh label mechanisms in the replay feature; four hand-rolled segmented controls that duplicate the `Toggle` primitive; the `東` compass mark in three places; duplicated tile-box size blocks | `features/replay/*`, `index.css`, `theme/` | Route through the existing primitives; ~200 lines |

Because W10 and W11 are pure CSS with no type checker behind them, both are verified by building
the stylesheet before and after and diffing the emitted CSS, not by eye.

**Tier 2 — small, safe, same PR**

| # | What | Where | Home |
|---|---|---|---|
| W6 | `tileIdsEqual` — a verbatim second copy | `table/tileFlightPlan.ts:47-50` vs `table/meldOrdering.ts:3-6` | `table/types.ts` (the leaf both already import); delete the copy |
| W7 | Re-inlined `` `${suit}-${value}` `` wild-tile keys instead of `tileModel.tileKey`, plus the wild predicate written three times | `features/game/Game.tsx:288-292`, `features/replay/Replay.tsx:169-172`, `features/shanten/Shanten.tsx:547,561`, `features/replay/replayEngine.ts:228-231` | `utils/tileModel.ts` — add `makeWildTilePredicate(wildTiles)` |
| W8 | Seat-wind labels in five spellings (kanji, i18n keys, en/zh literals) and the jihai/flower name arrays copied into `reviewUtils` | `table/TableScene.tsx:51`, `features/game/SeatCard.tsx:31,44`, `features/replay/{ReplayLibrary.tsx:38,reviewUtils.ts:143-148}`, `features/calc/{Calc.tsx:331-336,calcHelpers.ts:112-117}`, `utils/tileUtils.ts:28,45` | **new** `utils/winds.ts` (`WIND_KANJI`, `WIND_I18N_KEYS`, `windI18nKey`); export the name arrays from `utils/tileUtils.ts` |
| W9 | `replayEngine.getState` chii/pon and okan branches — identical steal-from-discard logic | `features/replay/replayEngine.ts:183-212` | merge the two branches in place |

W1 and W4 both rewrite the same two files, so they land as one sequence: extract the primitives,
then the chrome, then move the strings into i18n. W3 is marked medium risk only because the
error-message contract is user-visible — the shared helper must preserve each caller's fallback
string exactly, which the characterization tests pin first.

**Test coverage gap.** `Calc.tsx`, `Shanten.tsx`, `Game.tsx`, `Replay.tsx` and the page fetch
handlers have **no tests**. Per §9.2, W1–W4 each get a characterization test *before* extraction —
a `renderToStaticMarkup` snapshot of the tile row / palette / stage wrapper, and a fetch-mock test
per error contract. This is the one place the refactor adds test code, and it is the reason these
items are safe to do at all.

### 6.2 Naming (PR 2)

Every proposal below was re-opened by a verifier that counted its referrers across imports, docs,
`Makefile`, `Dockerfile*`, CI and runbooks. **20 of 25 web proposals survived**; the counts are the
real cost of each rename.

| # | Current | Proposed | Refs | Why |
|---|---|---|---:|---|
| N1 | `web/src/index.css` (1,501 lines) | move lines 20-1501 → `table/table-geometry.css`, leaving a ~19-line `index.css` (Tailwind import, `body`/`#root` reset) | 29 | It is not a global stylesheet — it is the fixed-stage table geometry. `theme/index.css` imports it while calling it "legacy geometry", and three tests `readFileSync` it by path. Pairs with the existing `table-theme.css` skin |
| N2 | `table/TableScene.tsx` | split → `TableBoard.tsx` + `TableRoundResultOverlay.tsx` | 26 | **There is no `TableScene` symbol** — verified. The file exports `TableBoard` plus an unrelated settlement dialog, and `tileFlight.tsx`/`CenterHud.tsx` import *types* through it instead of from `./types`, creating a circular type dependency. `roundResult.css` and `roundResultOverlay.test.ts` already exist as if the overlay had its own module |
| N3 | `features/game/Table.tsx` | `PrivateRoom.tsx`; `App.tsx`'s `TableRoute` → `PrivateRoomRoute` | 16 | It is the pre-match waiting room for `/room/:roomId`, sitting one import from `table/TableScene.tsx` and `features/dev/TableSample.tsx`. Its own siblings already say "room" |
| N4 | `hooks/computeStageLayout.ts` + `useGameStageLayout.ts` (+ test) | move all three to `table/stage/` | 10 | `computeStageLayout` is not a hook; `hooks/CLAUDE.md` still describes the directory as "focused on WASM integration" |
| N5 | `features/replay/reviewTypes.ts` | `reviewClient.ts` | 7 | It is a fetch client (`fetchReview`, `generateReview`) — verified — not a types module |
| N6 | `utils/tileUtils.ts` | `tileDisplay.ts` | 9 | Distinguishes it from `tileModel.ts` (the value model): this one is names and SVG mapping |
| N7 | `theme/components/ToolsRow.tsx` | `ButtonRow.tsx` | 9 | It is a generic button row, not tool-page-specific |
| N8 | `features/auth/authModal.ts` | `authRouteState.ts` | 8 | Names what both exports are actually about |
| N9 | `features/lobby/navigation.ts` | `playIntent.ts` | 4 | Describes the concept, not the category |

Also endorsed and folded in: `replayLibrary.test.ts` → `replayReference.test.ts`,
`streamlinedNavigation.test.ts` → `Home.test.ts`, and creating `table/tileId.ts` to host the single
`tileIdsEqual` (which pairs with W6).

**Endorsed but deferred:** moving `public/Regular_shortnames/` → `public/tiles/` (15 refs, and it
needs a matching mount change in `internal/api/server.go` — a frontend rename that reaches into the
Go server belongs in its own PR), and regrouping `features/game/{Table,SeatCard,roomNavigation}` into
a new `features/room/` folder (10 refs; worth doing, but only after N3 settles the vocabulary).

Stale docs fixed in the same PR: `table/CLAUDE.md:19-22` documents `SeatLane`/`DiscardLane` inside
`TableScene.tsx` (neither exists); `table/seat/CLAUDE.md:12` calls `PlayerSeat` "the seat plaque:
name, wind, score" (it is the seat-lane composition — wind and score are in `CenterHud.tsx`);
`utils/CLAUDE.md:22` points at `Game.tsx` for `TileComponent` (it is in `table/Tile.tsx`).

`hooks/useMahjongWasm.ts` has **zero importers** — verified dead. Deleting it is the user's call,
not a rename; the plan lists it and does nothing without a decision.
## 7. Backend (Go: `internal/`, `cmd/`) — PR 3 and PR 4

4.44% of Go lines are token-identical duplicates, and the semantic sweep found ~2,200 lines
across 42 candidates. Roughly half of that is **test scaffolding**, which is the cheapest and
safest half to fix.

### 7.1 De-duplication (PR 3)

**Tier 1 — production code**

| # | What is duplicated | Copies | Shared home |
|---|---|---|---|
| G1 | The 42-face tile index, written three times. `engine.FaceIndex42` and `rl.tileFaceIndex42` are semantically identical (same table, same `(int, bool)` contract, only the guard style differs); `review.faceIndex42FromTileID` is the same table keyed by tile id with a `-1` error contract | `engine/events.go:41`, `rl/action.go:42`, `review/replay.go:847` | `engine.FaceIndex42` stays; add `FaceIndex42FromID(id)`. Delete `rl.tileFaceIndex42`, make review delegate. **Verified by hand** — `rl` and `review` already import `engine` |
| G2 | The heuristic self-play driver: a ~55-line game loop plus `finalScores` and the ready-ack loop, in `cmd/rlpaipu` and twice in the review tests. The test copy has *drifted* — it derives seeds as `baseSeed*1000+nextHand` while `rl/env.go` uses a splitmix `deriveHandSeed` | `cmd/rlpaipu/main.go:60-162`, `review/replay_test.go:22-152`, `review/replay_v2_test.go:22-121`, mirrors `rl/env.go:434-469` | **new** `rl/selfplay.go` — `rl` already imports `engine` + `bot`, and both `review` and `cmd/rlpaipu` import `rl` |
| G3 | The paipu-v2 decision snapshot (sorted legal ids + chosen id) in four spellings, one of them production | `api/room_decisions.go:29-49`, `cmd/rlpaipu/main.go:132-151`, `review/replay_v2_test.go:102-121` | `rl/action.go` — `SortedLegalIDs`, `SnapshotDecision` |
| G4 | The policy-server HTTP layer: three separate `GET /healthz` probes with their own event-contract checks; client/timeout resolution and bearer-header setup retyped per call; `deriveHealthURL`/`deriveWarmupURL` byte-identical; `actionMaskJSON`/`actionMaskToInts` byte-identical | `bot/remote/{health,warmup,http_policy}.go`, `review/client.go`, `cmd/rlsmoke/main.go` | `bot/remote/healthz.go` — one `HealthzPayload` + probe; a sibling-route URL helper; one mask converter |
| G5 | `EnvPool` and `SearchPool` share command fan-out, response assembly and `slotResult` building | `rl/envpool.go:46-116`, `rl/searchpool.go:212-445` | `rl/envpool.go` — `runSlotCommands(...)` used by both |
| G6 | `Matchmaker.createMatch` and `StartPrivateTable` provision a room the same way; `BroadcastState`/`SendStateToClient` share state-prep; the private-table handlers repeat a prelude and a sentinel-error→HTTP-status mapping | `api/matchmaker.go:579-657,823-864`, `api/room.go:1135-1258`, `api/private_tables.go` (4 handlers) | in-package helpers in `api/` |
| G7 | Placement ranking + `MatchPlayer` row construction, once in the room persist path and once in the storage backfill | `api/room.go:534-595`, `storage/match_history.go:17-84` | `storage` — export `PlacementsFromScores` and one row builder |

**Tier 1 — test code** (same PR, lands first because it is lowest-risk)

| # | What | Scale | Shared home |
|---|---|---|---|
| G8 | The uniform-over-legal `/evaluate` policy-server stub: **26 `httptest` servers across 9 test files totalling 2,609 lines**, all decoding the same request shape and emitting `probs = 1/legal`, differing only in sha, blocking channel, counters and value constant | ~260 lines | **new** non-test package `review/reviewtest` — importable from both `api` and `review` tests (a `_test.go` helper cannot cross packages) |
| G9 | `rl` env config/reset scaffolds and first-legal-action mask scanners | ~140 lines | `rl/envtest_test.go` (package-local) |
| G10 | In-memory sqlite + `AutoMigrate` + `Server` construction, and `configureTable`/persist-and-load scaffolds, retyped across ~10 api tests | ~130 lines | `api` package-local test helpers |
| G11 | Static-JSON `httptest` helpers for `bot/remote` healthz/warmup tests | ~90 lines | `bot/remote/servers_test.go` |

**Tier 2 — deferred to a follow-up, with reasons**

- **G12, tile-notation parser for test hands (~450 lines, the single largest item).** `fh_test.go`
  alone hand-writes 413 `&pb.Tile{...}` literals; the notation is already spelled out in the test
  comments (`// 123m 456m 789m 123p 55p`), and the frontend already has `parseHand` in
  `tileModel.ts`. A Go `tiles.ParseHand` would delete ~450 lines. It is Tier 2 only because
  converting the scoring tests is exactly where a silent transcription error would be invisible —
  it deserves its own PR, converted one file at a time, each verified by an unchanged
  `go test ./internal/rules`.
- **G13, `engine/game.go` re-inlined round-end / turn-advance / dead-wall blocks** and
  **G14, `fh.go` pair-selection and chow-DFS triplication.** Real duplication in the two hottest,
  subtlest files. Explicitly out of scope — see §10.

### 7.2 Naming (PR 4)

**34 of 38 Go proposals survived verification.** Reference counts are low across the board, which
makes this the cheapest of the three rename PRs.

| # | Current | Proposed | Refs | Why |
|---|---|---|---:|---|
| M1 | `api/review_round21_test.go` … `review_round25_test.go` | regroup by subject: keep `review_test.go` as the fixture home, then `review_auth_test.go`, `review_build_admission_test.go`, `review_sha_cache_test.go`, `review_event_window_test.go` | 1 | Session-numbered names. Nothing says which file tests which behaviour, and "round21" means nothing to anyone who was not in that session. Both auditors ranked this the highest-value Go rename, and the blast radius is a single reference |
| M2 | `api/matchmaker.go` (978 lines) | split into `matchmaker.go`, `queue.go` (`InMemoryQueue`), and the seat-policy resolver | 8 | One file holds the queue data structure, matchmaking, the active-room registry, and seat-policy resolution |
| M3 | `InMemoryQueue.RPush` / `RPushUnique` / `LRange` / `LLen` / `LPopCount` | `Push` / `PushUnique` / `Range` / `Len` / `PopCount` | 3 | **Verified by hand.** Six methods on an in-process queue still speak Redis-list vocabulary. Redis was removed in PR #129 (2026-07-01) and was never wired up — these names are its last trace, and they actively mislead |
| M4 | `api/rl_agent_test.go`, `warmup_admission_test.go`, `seat_policy_leak_test.go` | `matchmaker_rl_seat_test.go`, `matchmaker_warmup_test.go`, `matchmaker_seat_policy_test.go` | 1 | Three tests of the matchmaker, named after the incident that motivated each |
| M5 | `rl/kan_dup_repro_test.go` | `wall_consumption_fuzz_test.go` (`TestFuzzDuplicateKanAction` → `TestFuzzNoDuplicateTileIDs`) | 3 | "repro" names a historical bug, not the invariant the test now guards |
| M6 | `review/client.go` | `policy_client.go` | 6 | `client.go` one package away from `api/client.go` meaning something else entirely |
| M7 | `api/client.go` + `client_test.go` | `ws_client.go` + `ws_client_test.go` | 1 | In a package of HTTP handlers, `client.go` reads as "HTTP client"; it is the WebSocket client connection. Rename both halves |
| M8 | `bot/context.go` | `policy.go`, absorbing the `Policy` interface from `heuristic.go:11` | 3 | The package's core interface lives in the file named after one implementation |
| M9 | `engine/rules.go` | `rule_engine.go` | 3 | snake_case matches every other multiword Go filename in the repo; also disambiguates from the `rules` package |
| M10 | `storage/db.go` (304 lines) | split → `models.go` + `migrate.go`; `db_test.go` → `models_test.go` | 2 | The file called `db.go` holds every GORM model |
| M11 | `bot/remote/identity.go` | `checkpoint_identity.go` | 1 | 14 lines about checkpoint identity, under a name that suggests auth |
| M12 | `review/context.go` | `chongci_context.go` | 2 | "context" collides with `context.Context` in a package that uses it |
| M13 | `bot/shadow_round24_test.go` | merge into `shadow_test.go` | 0 | Session-numbered, zero referrers |
| M14 | `cmd/cli` | `cmd/play` | 6 | It is an interactive terminal match (human seat 0 vs heuristic bots), not a general CLI. Its `CLAUDE.md` still advertises "offline hand evaluation" it no longer does |

**Endorsed, own follow-up PR:** splitting `api/room.go` (1,258 lines, 24 refs) into room lifecycle /
persistence / broadcast, `api/server.go` (9 refs), and `cmd/server/main.go` → `policy_wiring.go`
(14 refs). All three are real, but they are file surgery on the busiest files in the backend and
should not ride along with a rename PR.

**Rejected by verification** — worth recording so they are not re-proposed:

- `rules/fh.go` → `fenghua.go`. "fh" is not an opaque abbreviation here; it is the repo's own
  prefix, used at every level (`github.com/plasma/fh-mahjong`, `ai/src/fh_mahjong_ai`, the
  `fh-mj-*` console scripts). Renaming one file would make it the odd one out.
- `cmd/rlpaipu` → `cmd/paipugen` and `cmd/rlsmoke` → `cmd/paipusmoke` were endorsed only weakly
  (low value, medium cost, 9 refs including Makefile and runbooks). Default: drop, unless the user
  wants them.
## 8. Deep learning (`ai/`) — PR 5 and PR 6

Python is the most duplicated subsystem: **6.54% of lines are token-identical clones**, and the
semantic sweep found substantially more. The cause is structural — 45 library modules and 45 CLI
scripts in one flat package, grown campaign by campaign, with no shared CLI-argument module and
**no `conftest.py` at all**.

### 8.1 De-duplication (PR 5)

**Tier 1 — test fixtures.** `ai/tests` has 68 test files and no `conftest.py`. **33 of them build a
tiny `ModelConfig` inline and 26 build synthetic `Observation`s.** Both ai lenses independently
proposed the same fix, which is the largest and safest single win in the repo.

| # | What | Scale | Shared home |
|---|---|---|---|
| A1 | Tiny/small `ModelConfig` literals, synthetic `Observation`/`Transition` builders, anchor+champion checkpoint fixtures, the small-model argv fragment, the `__import__` mock-bridge monkeypatch idiom | ~400 lines across the suite | **new** `ai/tests/conftest.py` — `SMALL_MODEL_KWARGS`, `make_observation(...)`, `make_transitions(...)`, `mock_bridge` fixture, `SMALL_MODEL_ARGV` |
| A2 | The in-thread `serve_policy` HTTP harness, rebuilt per serving test | ~80 lines | `ai/tests/helpers/serving.py` — a `PolicyTestServer` context manager |

**Tier 1 — CLI plumbing.** ~45 scripts repeat the same argparse blocks and post-run boilerplate.

| # | What | Copies | Shared home |
|---|---|---|---|
| A3 | `parse_seed_windows` — **four byte-identical copies** (`evaluate.py`, `evaluate_guarded.py`, `evaluate_risk_guarded.py`, `evaluate_tail_constrained.py`) plus a fifth in `paired_trace.py` with a *different signature* (no `start_seed`) | 5 | `evaluate.py` (the library all five already import). **Verified by hand.** This one is a correctness matter, not tidiness: seed windows decide which seeds a promotion gate scores (screening 910000 vs confirmation 950000), and there are five parsers for them |
| A4 | The match-mode + chongci + max-steps argparse block, and three spellings of the bridge-library flag | ~155 lines | **new** `scripts/env_args.py` — `add_env_args`, `env_kwargs_from_args`, `add_bridge_args` |
| A5 | MLflow CLI flags + run setup | ~90 lines | `mlflow_tracking.py` — `add_mlflow_args`, `start_run_from_args` |
| A6 | The PPO argparse block + `PPOConfig`/`EnvConfig` construction across `train_ppo`/`train_oracle`/`train_selfplay_oracle`/`train_b2b` | ~70 lines | **new** `scripts/ppo_args.py` |
| A7 | 20+ hand-rolled JSON report writers (`json.dumps(..., indent=2, sort_keys=True)` + mkdir + write) | ~45 lines | `storage.py` — `write_json_report` (it already writes manifests this exact way) |
| A8 | checkpoint → eval-ready `PolicyValueNet` loader, retyped per script; `model_config_args.py` is not adopted everywhere it should be | ~45 lines | `storage.py` — `load_policy_net`; close the `model_config_args` adoption gap |

**Tier 1 — library code.**

| # | What | Copies | Shared home |
|---|---|---|---|
| A9 | The plane/scalar encoder trunk, built three times: `PolicyValueNet`, `GlobalEVNet`, `ActionGlobalEVNet` (plus the scalar-padding logic) | `model.py:25-62,145-152`, `global_ev.py:60-176` | `model.py` — `build_plane_scalar_encoders(...)` |
| A10 | `GoEnvPool` and `GoSearchPool` share Go-FFI pool lifecycle, and `envpool._config_message` re-encodes what `bridge.py` already encodes | `envpool.py`, `searchpool.py`, `bridge.py` | `_GoFFIPool` base in `envpool.py`; move the config encoder next to `build_bridge` |
| A11 | Diagnostics statistics — `weighted_rate`, `weighted_mean`, `rate`, `numeric_summary`, `reward_gap_buckets`, family-pair counters — copied across three diagnostics modules; likewise the paired-trace report row extractors | `global_ev_diagnostics.py`, `branch_cf_calibration.py`, `paired_trace_q_diagnostics.py`, `paired_trace_delta.py`, `paired_trace_action_ev.py` | **new** `diag_stats.py`; row extractors into `paired_trace.py` |
| A12 | `evaluate_duplicate_seats` is a near-copy of `evaluate_duplicate_seats_policy` | `evaluate.py:957-1258` | keep the `_policy` implementation; make the other a thin wrapper |
| A13 | Shard writers: `write_divergence_shard` is identical to `write_counterfactual_shard`; a third copy in `replay_policy_diagnostics.py` | 3 | `storage.py` — one `write_array_shard_dataset` |
| A14 | The four spawn-context rollout worker pools (`parallel_rollouts.py` x2, `oracle.py` x2) | ~210 lines | `parallel_rollouts.py` — one `SpawnRolloutPool` base |

**Tier 2 — production serving path, gated separately.** A15: single-observation → model-tensor
construction (including the event-history row) exists in `serving.py`, `policies.py` and
`scripts/serving_parity.py`. Consolidating it into one `tensorize` helper is correct, but it sits
on the path that serves the live RL agent. It runs last in PR 5, and `fh-mj-serving-parity` must
pass before and after — see §9.4.

**Not done:** merging the PPO/ACH minibatch update machinery and the per-iteration PPO driver
(~150 lines). Real duplication, live campaign code — see §10.

### 8.2 Naming (PR 6)

**18 of 26 ai proposals survived verification** — the lowest survival rate of the three subsystems,
because several apparent inconsistencies turned out to encode a real distinction (see the rejections).

| # | Current | Proposed | Refs | Why |
|---|---|---|---:|---|
| P1 | `oracle.py` — **3,229 lines, 50 top-level definitions** | split into `oracle.py` (Phase-1/2 oracle, lines 48-569 + `train_oracle`), `train_b2b.py` (B2b model surgery, collector, `train_b2b`), `train_state.py` (resume, atomic `train_state.pt`, history reconciliation, run-id lineage, checkpoint-dir lock, bridge pinning) | 34 | **Verified by hand.** The file's own docstring still says "Oracle-guiding helpers (Phase 1)" while lines 570-2454 are B2b and resume machinery; `MODULES.md:56` already concedes "(by accretion)". Nobody looking for "how does B2b training resume after a crash?" opens `oracle.py`. `train_b2b.py` (not `b2b.py`) because the repo's strongest convention is core `X.py` ↔ `scripts/X.py`, and `scripts/train_b2b.py` already exists |
| P2 | `ai/tests/test_deep16_rezero.py` — **3,220 lines, 135 tests** | split into `test_b2b_growth.py` (lines 64-540) + `test_b2b_resume.py` (541-end) | 4 | Named after a retired campaign; the growth tests are 15 of 135 while ~45 are resume tests. `test_b2b_*` is the existing family name, so these slot in beside `test_b2b_model.py` / `test_b2b_ppo.py` / `test_b2b_training.py` |
| P3 | `test_serve_policy_events.py`, `test_serving_evaluate.py`, `test_b2c_loading.py`, `test_oracle_phase2.py` | `test_serve_policy.py` (no split), `test_serve_policy_evaluate.py`, `test_checkpoint_loading.py`, `test_selfplay_oracle.py` (absorbing `test_ach_cli.py`) | 1-5 | Campaign labels ("b2c", "phase2") and suffixes that no longer match contents |
| P4 | `scripts/model_config_args.py` | move to package level beside `config.py` | 33 | Library plumbing imported by 33 sites, not a script |
| P5 | `trainer.py` | `offline_trainers.py` | 15 | "trainer" says nothing next to `ppo.py`, `ach.py`, `oracle.py`, which are also trainers; this one owns the *offline* trainers (BC/AWBC/IQL/offline-Q) |
| P6 | `streaming_data.py` | `streaming_buffer.py` | 6 | Distinguishes it from `data.py` and `storage.py`; it is a buffer |
| P7 | `scripts/evaluate_guarded.py` | `evaluate_q_guarded.py` | 5 | Three `evaluate_*guarded*` scripts guard on different things; only one says which |
| P8 | `ai/Dockerfile` | `Dockerfile.compose` | 5 | The unqualified name reads as "the" image; `Dockerfile.deploy` is the production one |
| P9 | `checkpoints/deploy/b2b-anchor075-restart-iter075.pt` | move to `checkpoints/anchors/` | 2 | It is a training anchor sitting in the directory that means "this ships to production" |

**Rejected by verification** — recorded so they are not re-proposed:

- `test_awbc.py` → `test_train_awbc.py` (and `test_iql`, `test_offline_q`). The two naming schemes
  are not arbitrary: `test_train_*.py` files import *only* their script, while `test_<module>.py`
  files test the library module. Renaming would erase a real distinction. A good catch — this was
  in my draft before verification.
- `paired_trace_delta.py` → `pairwise_delta.py`, `memprobe.py` → `memory_probe.py`,
  `test_gru_width.py` → `test_widen_event_gru.py`, `serving.py` → `checkpoint_policy.py`,
  `best-checkpoints.json` → `checkpoint-registry.json`. Each trades one ambiguity for another or
  fights an established convention.

**Two operational hazards the verifier surfaced for P1**, both of which the plan builds in:

1. **Monkeypatch targets do not move with the definition.** Tests patch by *lookup* location — e.g.
   `test_deep16_rezero.py:695` patches `fh_mahjong_ai.oracle._resolve_current_bridge_fingerprint`.
   After the split the correct target is the module that *calls* it (`train_b2b.py`), not the one
   that defines it (`train_state.py`). All ~40 patch strings get re-pointed deliberately, one at a
   time — never by `sed`.
2. **Three live runbooks carry copy-paste import snippets** (`deep16-rezero-runbook.md:56`,
   `gru-width-runbook.md:41`, `data-scale-960-runbook.md:147`, all
   `from fh_mahjong_ai.oracle import ...`) and must change in the same commit.

**Do not land PR 6 while a `--resume-from-state` training lap is mid-flight.** P1 moves the resume
machinery; a running lap that resumes across the change would fail to find its symbols. This is the
one item in the whole plan with a scheduling dependency on the user's own work.

**Still not proposed: reorganising `fh_mahjong_ai` into subpackages.** One auditor proposed
`bridge/`, `training/`, `data/`, `eval/`, `diagnostics/`, `serving/`; verification endorsed only a
narrow version (move the closed-graph, promotion-ineligible diagnostics modules into
`diagnostics/`, keeping every basename identical — 41 refs). Even that is medium cost for medium
value. Recommendation: **skip in this campaign.** Dozens of runbooks and `MODULES.md` reference the
flat module names, and that cost lands on the user's notes, not on the code.
## 9. Execution plan

### 9.1 PR sequencing — six PRs, in this order

| # | PR | Contents |
|---|---|---|
| 1 | `refactor(web): de-duplicate frontend` | Shared tool-page primitives, fixed-stage shell, API/fetch helpers, tile-model leftovers, test helpers |
| 2 | `refactor(web): clarify file and directory names` | Renames, moves, splits + `CLAUDE.md` updates |
| 3 | `refactor(go): de-duplicate backend` | Face-index unification, paipu decision snapshot, policy-client HTTP layer, api handler boilerplate, test fixtures |
| 4 | `refactor(go): clarify file and directory names` | Test-file regrouping, file splits + `CLAUDE.md` updates |
| 5 | `refactor(ai): de-duplicate RL stack` | Script CLI helpers, encoder trunk, diagnostics stats, storage/shard helpers, test fixtures |
| 6 | `refactor(ai): clarify module and script names` | Renames + `CLAUDE.md` / `MODULES.md` updates |

**Why de-dup before renames, per subsystem.** De-duplication deletes and merges files; renaming
first would move files that are about to disappear and double the diff. New shared modules created
in the de-dup PR are named correctly at birth, using the conventions the naming audit identified.

**Why renames get their own PR.** A rename PR is pure motion — a reviewer can verify it with
`git log --follow` and a green build. Mixed into a logic PR, a hundred renamed files hide the ten
lines that actually changed behaviour.

Each PR is independently green and independently mergeable. Merge with `gh pr merge N --merge`.

### 9.2 The loop for every individual change

1. **Cover first.** If the verifier reported `tests_covering: none found`, write a characterization
   test that pins the *current* behaviour of each copy, and watch it pass, before touching anything.
   This is the only new test code the refactor adds.
2. **Extract** the shared implementation into its target home.
3. **Rewrite call sites** one at a time.
4. **Delete** the copies.
5. **Run the subsystem gate** (below). Never batch more than one extraction between gate runs.

### 9.3 Gates

| Subsystem | Gate |
|---|---|
| web | `cd web && npx tsc && npx vitest run` |
| Go | `gofmt -l .` (must print nothing), `go vet ./...`, `go test ./...` |
| ai | `uv run --project ai pytest ai/tests` (915 passed, 2 skipped is the baseline) |
| all, before each PR | all three of the above |

`ai/` has **no CI job** — the Python gate is local-only. This plan does not add one (out of scope),
but it is worth knowing that a green GitHub check does not mean `ai/` is green.

### 9.4 Differential harness — proof beyond the unit tests

Unit tests do not cover every path the refactor touches, so two cheap deterministic diffs run
before each of PRs 3 and 5:

- **Go / engine + rl:** generate seeded replays at baseline and after the refactor —
  `go run ./cmd/rlpaipu` over a fixed seed set — and require byte-identical paipu JSON.
  A refactor that changes engine, rules, rl or review behaviour will move a tile somewhere.
- **ai / serving:** `fh-mj-serving-parity` (already a hard promotion gate, vacuity-proof) plus a
  fixed-seed rollout whose action-id sequence must match baseline exactly.

Both harnesses are recorded in the plan as commands with their expected output, so any later
session can re-run them.

## 10. Risks and what is deliberately left alone

| Risk | Mitigation |
|---|---|
| A "duplicate" is actually two intentionally different behaviours | Every candidate was adversarially verified against the real files; anything with unresolved behaviour differences is dropped, not parameterised into a flag |
| Refactor lands while an RL campaign is mid-flight | `ai/` is the last PR; the differential harness plus `fh-mj-serving-parity` gate it; no checkpoint, manifest, or wire format changes |
| A rename breaks a runbook, Dockerfile, or CI reference | Verifiers counted referrers per proposal, including `docs/superpowers/*`, `Makefile`, `Dockerfile*`, `.github/workflows`, and `ai/pyproject.toml` scripts; every referrer is updated in the same PR |
| Renaming a Python module breaks a console entry point | `[project.scripts]` names are user-facing and stay fixed; only module paths move, with the entry point re-pointed |
| Big-bang risk | Six independently-green PRs, each reversible on its own |

**Deliberately not done:**

- **No `ai/` package reorganisation into subpackages.** The flat `fh_mahjong_ai` layout is awkward,
  but dozens of runbooks, specs, memories, and in-flight campaign notes reference module paths
  directly. The cost lands on the user, not the code. File-level renames only.
- **No changes to `internal/rules/fh.go` scoring internals.** The hot path with the most subtle
  behaviour and the highest cost of a silent error. The duplication there is real; it is not worth
  the risk in a refactor whose whole premise is "nothing changes".
- **No merge of the PPO / ACH training loops.** Same reasoning: live campaign code.
- **No proto changes, no dependency changes, no CI changes.**
