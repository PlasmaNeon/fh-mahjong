# PR 2 — Frontend Renames Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this
> plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the frontend files and directories whose names no longer describe their contents,
per §6.2 of the design doc. Pure motion — no behaviour, no logic, no rendered output changes.

**Architecture:** Every rename is `git mv` (so `git log --follow` keeps working) plus an exact-path
import update plus the matching `CLAUDE.md` edit, in one commit per rename.

**Tech Stack:** React 19, TypeScript, Vite 7, vitest.

**Spec:** `docs/superpowers/specs/2026-08-16-dedup-and-naming-refactor-design.md` §6.2

## Global Constraints

- **Pure motion.** A reviewer must be able to read each commit as a move. If a rename tempts a
  logic change, the logic change does not happen in this PR.
- **`git mv`, never delete-and-create** — history must follow the file.
- **Update imports by exact path.** `Table` is a substring of `TableScene`, `TableSample` and
  `TableBoard`; a substring replace corrupts all three. Match `from '.../Table'` with the quote.
- **Gate after every task:** `cd web && npx tsc && npx vitest run`. Baseline **35 files, 222 tests**.
- Every directory whose contents move gets its `CLAUDE.md` updated in the same commit. Never
  replace an `AGENTS.md` symlink with a regular file.
- Stacked on PR 1b (`refactor/web-css-dedup`), because `index.css` changed there.

---

### Task 1: `utils/tileUtils.ts` → `utils/tileDisplay.ts`

Distinguishes it from `utils/tileModel.ts` (the value model). This one is names and SVG mapping.

- [ ] **Step 1:** `cd web && git mv src/utils/tileUtils.ts src/utils/tileDisplay.ts`
- [ ] **Step 2:** Update importers — `grep -rln "utils/tileUtils\|'\./tileUtils'\|'\.\./tileUtils'" src` then rewrite each import path.
- [ ] **Step 3:** Update `src/utils/CLAUDE.md`, and fix its stale line 21 ("Used by TileComponent in Game.tsx" — `TileComponent` lives in `table/Tile.tsx`).
- [ ] **Step 4:** Gate — `npx tsc && npx vitest run`. Expected: clean, 222 tests.
- [ ] **Step 5:** Commit — `refactor(web): rename tileUtils to tileDisplay`

### Task 2: `theme/components/ToolsRow.tsx` → `ButtonRow.tsx`

It is a generic button row, not tool-page-specific. The CSS class `.ldg-tools-row` stays in this
commit — renaming a class is a stylesheet change, not a file rename.

- [ ] **Step 1:** `git mv src/theme/components/ToolsRow.tsx src/theme/components/ButtonRow.tsx`
- [ ] **Step 2:** Rename the component `ToolsRow` → `ButtonRow` and its default export.
- [ ] **Step 3:** Update `src/theme/index.ts` (`export { default as ToolsRow }` → `ButtonRow`) and every `<ToolsRow>` usage.
- [ ] **Step 4:** Update `src/theme/CLAUDE.md` and `src/theme/components/CLAUDE.md`.
- [ ] **Step 5:** Gate, then commit — `refactor(web): rename ToolsRow to ButtonRow`

### Task 3: `features/auth/authModal.ts` → `authRouteState.ts`

Names what both exports are about: the route state carried through the login flow.

- [ ] **Step 1:** `git mv src/features/auth/authModal.ts src/features/auth/authRouteState.ts` (and its `.test.ts` if one exists)
- [ ] **Step 2:** Update importers by exact path; update `src/features/auth/CLAUDE.md`.
- [ ] **Step 3:** Gate, then commit — `refactor(web): rename authModal to authRouteState`

### Task 4: `features/lobby/navigation.ts` → `playIntent.ts`

Describes the concept (a remembered play intent) rather than the category.

- [ ] **Step 1:** `git mv src/features/lobby/navigation.ts src/features/lobby/playIntent.ts` and `navigation.test.ts` → `playIntent.test.ts`
- [ ] **Step 2:** Update importers and `src/features/lobby/CLAUDE.md`.
- [ ] **Step 3:** Gate, then commit — `refactor(web): rename lobby navigation to playIntent`

### Task 5: `features/replay/reviewTypes.ts` → `reviewClient.ts`

Verified: it exports `fetchReview` and `generateReview` — a fetch client, not a types module.

- [ ] **Step 1:** `git mv src/features/replay/reviewTypes.ts src/features/replay/reviewClient.ts`
- [ ] **Step 2:** Update importers and `src/features/replay/CLAUDE.md`.
- [ ] **Step 3:** Gate, then commit — `refactor(web): rename reviewTypes to reviewClient`

### Task 6: move the stage layout out of `hooks/`

`computeStageLayout.ts` is not a hook, and `hooks/CLAUDE.md` still describes the directory as
"focused on WASM integration". All three files move to `table/stage/`.

- [ ] **Step 1:** `mkdir -p src/table/stage && git mv src/hooks/computeStageLayout.ts src/hooks/computeStageLayout.test.ts src/hooks/useGameStageLayout.ts src/table/stage/` and move `src/hooks/stageStyles.test.ts` too.
- [ ] **Step 2:** Update importers by exact path.
- [ ] **Step 3:** Create `src/table/stage/CLAUDE.md` (+ `ln -s CLAUDE.md AGENTS.md`) describing the fixed-stage geometry; rewrite `src/hooks/CLAUDE.md` for what remains (`useMahjongWasm.ts`).
- [ ] **Step 4:** Gate, then commit — `refactor(web): move the fixed-stage layout into table/stage`

### Task 7: `features/game/Table.tsx` → `PrivateRoom.tsx`

It is the pre-match waiting room for `/room/:roomId`, sitting one import from `table/TableScene.tsx`
and `features/dev/TableSample.tsx`.

- [ ] **Step 1:** `git mv src/features/game/Table.tsx src/features/game/PrivateRoom.tsx`
- [ ] **Step 2:** Rename the component `Table` → `PrivateRoom`; in `App.tsx` rename the wrapper `TableRoute` → `PrivateRoomRoute`. **Match import paths with the closing quote** (`from './Table'`) so `TableScene`/`TableSample` are untouched.
- [ ] **Step 3:** Update `src/features/game/CLAUDE.md`, `src/features/CLAUDE.md`, `src/CLAUDE.md`.
- [ ] **Step 4:** Gate, then commit — `refactor(web): rename the waiting-room page to PrivateRoom`

### Task 8: split `table/TableScene.tsx`

Verified: **there is no `TableScene` symbol.** The file exports `TableBoard` plus the unrelated
settlement dialog `TableRoundResultOverlay`, and `tileFlight.tsx`/`CenterHud.tsx` import *types*
through it instead of from `./types`, creating a circular type dependency.

- [ ] **Step 1:** `git mv src/table/TableScene.tsx src/table/TableBoard.tsx`
- [ ] **Step 2:** Move `TableRoundResultOverlay` (and its `RoundResultView` type) into a new `src/table/TableRoundResultOverlay.tsx`, pairing with the existing `roundResult.css` and `roundResultOverlay.test.ts`.
- [ ] **Step 3:** Re-point `tileFlight.tsx` and `CenterHud.tsx` to import types from `./types` directly, breaking the type cycle.
- [ ] **Step 4:** Update the five importers and `src/table/CLAUDE.md` — including its stale lines 19-22, which document `SeatLane`/`DiscardLane` inside this file (neither exists).
- [ ] **Step 5:** Gate, then commit — `refactor(web): split TableScene into TableBoard and the round-result overlay`

### Task 9: `src/index.css` → `table/table-geometry.css`

It is the fixed-stage table geometry, not a global stylesheet. `theme/index.css` imports it while
calling it "legacy geometry"; three tests `readFileSync` it by path.

- [ ] **Step 1:** `git mv src/index.css src/table/table-geometry.css`
- [ ] **Step 2:** Create a new `src/index.css` holding only the global lines — the Tailwind import, the `roundResult.css` import, and the `body` / `#root` / `.app-root` reset — plus an `@import './table/table-geometry.css'`.
- [ ] **Step 3:** Update `theme/index.css`'s `@import '../index.css'` if its target changed, and the three tests that read `src/index.css` (`readSourceCss('src/index.css')` → the new path).
- [ ] **Step 4:** **Verify the built stylesheet is unchanged** — build before and after, diff the emitted CSS rule-by-rule. Expected: identical.
- [ ] **Step 5:** Update `src/CLAUDE.md` (its ~15 bullets describing table geometry under "index.css"), `src/table/CLAUDE.md`, `src/hooks/CLAUDE.md`, `web/CLAUDE.md`.
- [ ] **Step 6:** Gate, then commit — `refactor(web): move the table geometry out of index.css`

### Task 10: subject-named test files

- [ ] **Step 1:** `git mv src/features/replay/replayLibrary.test.ts src/features/replay/replayReference.test.ts`
- [ ] **Step 2:** `git mv src/features/lobby/streamlinedNavigation.test.ts src/features/lobby/Home.test.ts`
- [ ] **Step 3:** Gate, then commit — `refactor(web): name two test files after their subject`

### Task 11: wrap-up

- [ ] **Step 1:** Full gate — `npx tsc && npx vitest run`, then `gofmt -l . && go vet ./... && go test ./...`
- [ ] **Step 2:** Confirm history followed every file — `git log --follow --oneline <new-path> | tail -3` for each rename.
- [ ] **Step 3:** Append a PR 2 section to `docs/refactoring-notes.md`.
- [ ] **Step 4:** Push and open the PR against `refactor/web-css-dedup`.

## Deferred (endorsed but out of scope)

- `public/Regular_shortnames/` → `public/tiles/` (15 refs, and it needs a matching mount change in
  `internal/api/server.go` — a frontend rename reaching into the Go server belongs in its own PR).
- Regrouping `features/game/{PrivateRoom,SeatCard,roomNavigation}` into `features/room/` (10 refs;
  worth doing once Task 7 settles the vocabulary).
- `hooks/useMahjongWasm.ts` has **zero importers** — verified dead. Deleting it is a judgement
  call for the user, not a rename.
