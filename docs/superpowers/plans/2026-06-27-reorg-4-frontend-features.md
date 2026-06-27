# Reorg PR 4 — Frontend `features/` Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dissolve `web/src/pages/` into feature folders (`features/{auth,lobby,calc,shanten,replay,game}/`), each owning its routes + components + helpers, matching the existing `table/` module pattern.

**Architecture:** `git mv` route files and their co-located helpers/components into feature folders. Files move from `src/pages/` (1 level under `src`) to `src/features/<name>/` (2 levels), so imports of `src`-level dirs rewrite `'../` → `'../../`; intra-feature `'./` imports are unchanged because co-located files move together. `App.tsx` route imports update per feature. Verified by `tsc --noEmit`, `vitest`, and a production build.

**Tech Stack:** React 19, TypeScript, Vite 7, Vitest.

## Global Constraints

- Use `git mv`; never delete+recreate.
- No path aliases exist for `pages/` (confirmed) — all imports are relative.
- `table/`, `theme/`, `contexts/`, `hooks/`, `proto/`, `utils/`, `config.ts` stay put.
- After each task: `cd web && npx tsc --noEmit` must pass (catches broken imports).
- Final task gates on `npm run build` + `npx vitest run`.

## Move Map (reference)

| Feature folder | Files moved from `pages/` |
|---|---|
| `features/auth/` | `Login.tsx` |
| `features/lobby/` | `Lobby.tsx`, `CreateRoom.tsx`, `Home.tsx` |
| `features/calc/` | `Calc.tsx`, `calcHelpers.ts` |
| `features/shanten/` | `Shanten.tsx`, `shantenHelpers.ts` |
| `features/replay/` | `Replay.tsx`, `replayEngine.ts`, `replayTypes.ts` |
| `features/game/` | `Game.tsx`, `Table.tsx`, `SeatCard.tsx`, `MatchEndOverlay.tsx`, `ExitMatchButton.tsx`, `privateRoomSession.ts`, `rejoinMatch.ts`, `rejoinMatch.test.ts` |

Confirmed: no cross-feature imports among these (each file's `'./'` imports resolve within its own target feature).

---

### Task 0: Pre-flight — confirm only `App.tsx` imports from `pages/`

**Files:** none (verification only)

- [ ] **Step 1: List every importer of `pages/`**

```bash
cd web && grep -rnE "from '(\.\./)*pages/" src
```
Expected: only `src/App.tsx` lines. If any other file imports from `pages/`, add it to the relevant feature task's modify list before proceeding.

- [ ] **Step 2: Confirm no `pages/` path alias in config**

```bash
cd web && grep -nE "pages|alias" vite.config.ts tsconfig.json
```
Expected: no alias mapping `pages` → anything.

---

### Task 1: `features/auth/` — Login

**Files:**
- Move: `src/pages/Login.tsx` → `src/features/auth/Login.tsx`
- Modify: `src/App.tsx` (Login import)

- [ ] **Step 1: Move**

```bash
cd web/src && mkdir -p features/auth && git mv pages/Login.tsx features/auth/Login.tsx
```

- [ ] **Step 2: Fix `src`-level relative imports inside the moved file**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" features/auth/Login.tsx
```

- [ ] **Step 3: Update `App.tsx` import**

Change `import Login from './pages/Login'` → `import Login from './features/auth/Login'`.

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Login into features/auth/"
```

---

### Task 2: `features/lobby/` — Lobby, CreateRoom, Home

**Files:**
- Move: `src/pages/{Lobby,CreateRoom,Home}.tsx` → `src/features/lobby/`
- Modify: `src/App.tsx` (Lobby, CreateRoom, Home imports)

- [ ] **Step 1: Move**

```bash
cd web/src && mkdir -p features/lobby
git mv pages/Lobby.tsx features/lobby/Lobby.tsx
git mv pages/CreateRoom.tsx features/lobby/CreateRoom.tsx
git mv pages/Home.tsx features/lobby/Home.tsx
```

- [ ] **Step 2: Fix `src`-level relative imports**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" features/lobby/Lobby.tsx features/lobby/CreateRoom.tsx features/lobby/Home.tsx
```

- [ ] **Step 3: Update `App.tsx` imports**

- `import Home from './pages/Home'` → `'./features/lobby/Home'`
- `import Lobby from './pages/Lobby'` → `'./features/lobby/Lobby'`
- `import CreateRoom from './pages/CreateRoom'` → `'./features/lobby/CreateRoom'`

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Lobby/CreateRoom/Home into features/lobby/"
```

---

### Task 3: `features/calc/` — Calc + calcHelpers

**Files:**
- Move: `src/pages/Calc.tsx`, `src/pages/calcHelpers.ts` → `src/features/calc/`
- Modify: `src/App.tsx` (Calc import)

**Interfaces:** `Calc.tsx` imports `'./calcHelpers'` (intra — unchanged).

- [ ] **Step 1: Move both**

```bash
cd web/src && mkdir -p features/calc
git mv pages/Calc.tsx features/calc/Calc.tsx
git mv pages/calcHelpers.ts features/calc/calcHelpers.ts
```

- [ ] **Step 2: Fix `src`-level relative imports (leaves `./calcHelpers` intact)**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" features/calc/Calc.tsx features/calc/calcHelpers.ts
```

- [ ] **Step 3: Update `App.tsx` import**

`import Calc from './pages/Calc'` → `'./features/calc/Calc'`.

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Calc + calcHelpers into features/calc/"
```

---

### Task 4: `features/shanten/` — Shanten + shantenHelpers

**Files:**
- Move: `src/pages/Shanten.tsx`, `src/pages/shantenHelpers.ts` → `src/features/shanten/`
- Modify: `src/App.tsx` (Shanten import)

- [ ] **Step 1: Move both**

```bash
cd web/src && mkdir -p features/shanten
git mv pages/Shanten.tsx features/shanten/Shanten.tsx
git mv pages/shantenHelpers.ts features/shanten/shantenHelpers.ts
```

- [ ] **Step 2: Fix `src`-level relative imports**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" features/shanten/Shanten.tsx features/shanten/shantenHelpers.ts
```

- [ ] **Step 3: Update `App.tsx` import**

`import Shanten from './pages/Shanten'` → `'./features/shanten/Shanten'`.

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Shanten + shantenHelpers into features/shanten/"
```

---

### Task 5: `features/replay/` — Replay + engine + types

**Files:**
- Move: `src/pages/{Replay.tsx,replayEngine.ts,replayTypes.ts}` → `src/features/replay/`
- Modify: `src/App.tsx` (Replay import)

**Interfaces:** `Replay.tsx` imports `'./replayTypes'`, `'./replayEngine'`; `replayEngine.ts` imports `'./replayTypes'` (all intra — unchanged).

- [ ] **Step 1: Move the three**

```bash
cd web/src && mkdir -p features/replay
git mv pages/Replay.tsx features/replay/Replay.tsx
git mv pages/replayEngine.ts features/replay/replayEngine.ts
git mv pages/replayTypes.ts features/replay/replayTypes.ts
```

- [ ] **Step 2: Fix `src`-level relative imports**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" features/replay/Replay.tsx features/replay/replayEngine.ts features/replay/replayTypes.ts
```

- [ ] **Step 3: Update `App.tsx` import**

`import Replay from './pages/Replay'` → `'./features/replay/Replay'`.

- [ ] **Step 4: Typecheck**

```bash
cd web && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Replay + engine into features/replay/"
```

---

### Task 6: `features/game/` — Game, Table, and co-located modules

**Files:**
- Move: `src/pages/{Game.tsx,Table.tsx,SeatCard.tsx,MatchEndOverlay.tsx,ExitMatchButton.tsx,privateRoomSession.ts,rejoinMatch.ts,rejoinMatch.test.ts}` → `src/features/game/`
- Modify: `src/App.tsx` (Table, Game imports)

**Interfaces (intra — unchanged `'./'`):** `Game.tsx`→`./privateRoomSession`,`./rejoinMatch`,`./ExitMatchButton`,`./MatchEndOverlay`; `Table.tsx`→`./privateRoomSession`,`./rejoinMatch`,`./SeatCard`; `ExitMatchButton.tsx`→`./privateRoomSession`,`./rejoinMatch`; `rejoinMatch.test.ts`→`./rejoinMatch`.

- [ ] **Step 1: Move all eight**

```bash
cd web/src && mkdir -p features/game
for f in Game.tsx Table.tsx SeatCard.tsx MatchEndOverlay.tsx ExitMatchButton.tsx \
         privateRoomSession.ts rejoinMatch.ts rejoinMatch.test.ts; do
  git mv "pages/$f" "features/game/$f"
done
```

- [ ] **Step 2: Fix `src`-level relative imports (leaves all `'./'` intra-imports intact)**

```bash
cd web/src && perl -i -pe "s{'\.\./}{'../../}g" \
  features/game/Game.tsx features/game/Table.tsx features/game/SeatCard.tsx \
  features/game/MatchEndOverlay.tsx features/game/ExitMatchButton.tsx \
  features/game/privateRoomSession.ts features/game/rejoinMatch.ts features/game/rejoinMatch.test.ts
```

- [ ] **Step 3: Update `App.tsx` imports**

- `import Table from './pages/Table'` → `'./features/game/Table'`
- `import Game from './pages/Game'` → `'./features/game/Game'`

- [ ] **Step 4: Typecheck + run the moved test**

```bash
cd web && npx tsc --noEmit && npx vitest run src/features/game/rejoinMatch.test.ts
```
Expected: typecheck clean; test PASS.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor(web): move Game/Table + session modules into features/game/"
```

---

### Task 7: Remove empty `pages/`, update docs, final gate

**Files:**
- Delete: `src/pages/` (now contains only `AGENTS.md`)
- Move: `src/pages/AGENTS.md` content → `src/features/AGENTS.md`
- Modify: `src/AGENTS.md` (module map)

- [ ] **Step 1: Confirm `pages/` holds only AGENTS.md**

```bash
cd web/src && ls pages
```
Expected: `AGENTS.md` only.

- [ ] **Step 2: Replace pages AGENTS.md with features AGENTS.md**

```bash
cd web/src && git mv pages/AGENTS.md features/AGENTS.md && rmdir pages
```
Then rewrite `features/AGENTS.md` to document the feature-folder layout (auth, lobby, calc, shanten, replay, game) instead of the old pages list.

- [ ] **Step 3: Update `src/AGENTS.md`**

Update its directory map: `pages/` → `features/{auth,lobby,calc,shanten,replay,game}/`, each owning its routes + helpers.

- [ ] **Step 4: Final audit — no surviving `pages/` references**

```bash
cd web && grep -rnE "pages/" src
```
Expected: no output.

- [ ] **Step 5: Full build + test gate**

```bash
cd web && npx tsc --noEmit && npm run build && npx vitest run
```
Expected: typecheck clean, build succeeds, all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "refactor(web): drop empty pages/, document features/ layout"
```

---

## Self-Review Notes

- Spec coverage: implements the entire "Frontend Reorg Detail" — feature folders, the `'../`→`'../../` depth fix, `App.tsx` route updates, and the build+vitest gate.
- Type/path consistency: every moved file's intra-feature `'./'` imports are preserved because co-located files move together; only `src`-level `'../'` imports change depth. Task 0 verifies `App.tsx` is the sole external importer before any move.
- The `proto/` dual-binding consolidation is explicitly NOT part of this PR (per spec non-goal).
- `tsc --noEmit` after each task is the fast correctness gate; the final task adds the full production build + complete vitest run.
