# Repository Structure Reorganization — Design

**Date:** 2026-06-27
**Status:** Approved (pending spec review)
**Topic:** Folder/directory naming + placement reorg across Go, frontend, Python, and docs

## Problem

The repo layout has drifted into a state that is hard to navigate and does not
enforce architectural boundaries:

- **Go module is flat** at the root (`api/ bot/ core/ models/ proto/ rlenv/
  rules/ cmd/`) with no `internal/`, so any future external module could import
  internals, and the boundary between "engine" / "server" / "RL" is implicit.
- **Some folder names are vague or overlap** (`rlenv`, `models`, `core`).
- **Frontend `web/src/pages/`** mixes real route pages with shared components,
  helpers, and engine logic.
- **Root clutter:** loose design/rules `.md` files at the top level, a 49 MB
  `server` build artifact, and a stray `node_modules/` with no `package.json`.

## Goals

1. **Clear mental model** — the layout should make the system's domains obvious
   at a glance (pain point #1).
2. **Enforced boundaries** — adopt Go's `internal/` so engine/server/rules/RL
   packages cannot be imported from outside the module, and group related
   packages into domains (pain point #3).

## Non-Goals

- **No module-path rename.** `github.com/plasma/fh-mahjong` stays.
- **No code-symbol renames** beyond Go package identifiers that must change to
  match a renamed folder (e.g. `HometownRuleset` keeps its name).
- **No proto-binding consolidation.** The dual `web/src/proto/` binding styles
  are a separate code migration, noted below but out of scope here.
- **No behavioral changes.** This is a pure move/rename; `go test ./...` and the
  frontend test suite must pass identically before and after.

## Target Structure

```
fh-mahjong/
├── AGENTS.md  README.md  go.mod  go.sum         (root: unchanged)
├── Dockerfile  docker-compose.yml  .env.example (root: unchanged)
├── proto/                          stays — cross-language schema source of truth
├── cmd/                            stays — server, cli, wasm, rlbridge, rlpaipu
├── internal/                       NEW — enforced module-private boundary
│   ├── engine/    ← core/          (package core → engine)
│   ├── rules/     ← rules/         (package rules — unchanged)
│   │   └── shanten/                (package shanten — unchanged)
│   ├── api/       ← api/           (package api — unchanged; moves under internal/)
│   ├── storage/   ← models/        (package models → storage)
│   ├── bot/       ← bot/           (package bot — unchanged)
│   │   └── remote/                 (package remote — unchanged)
│   └── rl/        ← rlenv/         (package rlenv → rl)
├── ai/                             Python — scripts/ bucketed only
│   └── src/fh_mahjong_ai/
│       ├── (flat modules unchanged — high-churn, left alone)
│       └── scripts/
│           ├── train/      (train_*.py)
│           ├── generate/   (generate_*.py)
│           ├── evaluate/   (evaluate_*.py)
│           └── diagnostics/(*_diagnostics.py, calibration, paired_trace, etc.)
├── web/src/
│   ├── features/                   NEW — feature-first grouping
│   │   ├── game/    (Game, Table, SeatCard, MatchEndOverlay,
│   │   │            ExitMatchButton, rejoinMatch[.test], privateRoomSession)
│   │   ├── replay/  (Replay, replayEngine, replayTypes)
│   │   ├── calc/    (Calc, calcHelpers)
│   │   ├── shanten/ (Shanten, shantenHelpers)
│   │   ├── lobby/   (Lobby, CreateRoom, Home)
│   │   └── auth/    (Login)
│   ├── table/  theme/  contexts/  hooks/  proto/   (stay)
│   └── (pages/ dissolved into features/)
├── docs/
│   ├── rules/
│   │   ├── official-rules.md   ← official_rules.md
│   │   └── rules.md            ← rules.md
│   ├── technical-design.md     ← technical_design.md
│   ├── user-guide.md           ← user_guide.md
│   ├── tasks.md                ← tasks.md
│   └── rl-papers/  superpowers/   (stay)
└── testdata/                       left in place (referenced by tests via path)
```

### Deletions (root hygiene)

- `server` — 49 MB build artifact at root. Delete; add `/server` to
  `.gitignore`. (Builds should target `bin/`, already gitignored.)
- root `node_modules/` — stray, no `package.json`, already gitignored. Delete.

### Left untouched

- `killer_mortal_gui/` — external Mortal GUI client, gitignored, referenced by
  nothing in the repo. Not a repo concern; left in the working tree as-is.
- `testdata/` (root paipu fixtures) — referenced by tests via relative path;
  moving risks breakage for no navigation gain.

## Go Reorg Detail

### Import-path map

| Old import path | New import path |
|---|---|
| `…/core` | `…/internal/engine` |
| `…/api` | `…/internal/api` |
| `…/models` | `…/internal/storage` |
| `…/rlenv` | `…/internal/rl` |
| `…/bot` | `…/internal/bot` |
| `…/bot/remote` | `…/internal/bot/remote` |
| `…/rules` | `…/internal/rules` |
| `…/rules/shanten` | `…/internal/rules/shanten` |
| `…/proto` | unchanged |

(`…` = `github.com/plasma/fh-mahjong`.)

### Package-identifier renames

`core → engine`, `models → storage`, `rlenv → rl`. The `api` package keeps its
name (it moves to `internal/api`; the `cmd/server` binary imports it). Packages
whose folder name is unchanged (`api`, `rules`, `shanten`, `bot`, `remote`) keep
their identifiers. Every renamed package requires updating its `package`
declaration and every qualified reference (e.g. `core.Game` → `engine.Game`).

**Naming note — why not `game`/`server`:** `core` is *not* renamed to `game`
because proto's generated Go package is already `package game` (imported
aliased as `pb`) and 344 local variables are named `game` (instances of
`core.Game`); `engine` avoids both clashes. `api` is *not* renamed to `server`
because the binary already lives in `cmd/server` and `cmd/server/main.go` holds
a local `server` variable — keeping `api` gives the clean split `cmd/server`
(binary) → `internal/api` (handlers).

### Mechanical procedure

1. `git mv` each folder to its new location (preserves history).
2. Module-wide find/replace of import paths (table above).
3. Rename `package` declarations and qualified call sites for the four renamed
   packages.
4. `go build ./...` then `go test ./...` — must pass with zero diff in results.
5. `gofmt`/`goimports` the touched files.

`core/game.go` must still never import `rules/` (now `internal/rules`) — the
ruleset-agnostic rule survives the move unchanged.

## Frontend Reorg Detail

- Create `web/src/features/{game,replay,calc,shanten,lobby,auth}/`.
- Move route pages and their co-located helpers/components per the tree above.
- Update all relative imports (the moved files reference `../proto`, `../theme`,
  `../contexts`, `../hooks`, `../table`, `../utils`; depth changes from
  `src/pages/` (1 level) to `src/features/<name>/` (2 levels), so `../` →
  `../../`).
- Update `App.tsx` route imports to the new `features/` paths.
- `table/`, `theme/`, `contexts/`, `hooks/`, `proto/`, `utils/` stay put.
- Verify with `npm run build` and the vitest suite (several `.test.ts` files move
  with their subjects: `rejoinMatch.test.ts`, plus `table/`'s existing tests are
  untouched).

## Python Reorg Detail

- Only `ai/src/fh_mahjong_ai/scripts/` is regrouped, into `train/`, `generate/`,
  `evaluate/`, `diagnostics/` subpackages (each with `__init__.py`).
- Flat modules under `src/fh_mahjong_ai/` are **left alone** — their import
  paths are referenced across tests and scripts; regrouping them is high-churn
  for low navigational gain.
- Any console-script entry points / `pyproject.toml` references to moved script
  modules must be updated to the new dotted paths.
- Verify with the existing `pytest` suite.

## Reference Updates

Moving folders and docs invalidates path references that must be updated in the
same change:

- **Root `AGENTS.md`** — Module Map, Key Files table, regen commands, doc paths.
- **Per-directory `AGENTS.md`** — each moved Go package has one; relocate and
  update. Add `internal/AGENTS.md` if helpful.
- **Doc cross-links** — references to `official_rules.md`, `rules.md`,
  `technical_design.md`, `tasks.md`, `user_guide.md` in README, AGENTS.md files,
  and other docs.
- **User memory index** (`MEMORY.md` and any memory files naming these paths) —
  update Key Files paths (`core/game.go` → `internal/engine/game.go`, etc.).
- **Dockerfile / docker-compose / build scripts** — verify no hardcoded package
  paths break (cmd paths are unchanged, so build targets should be stable).

## Implementation Staging

Four independent PRs, each self-contained and verifiable. They have no
ordering dependency on each other, but the suggested order runs lowest-risk
first:

1. **Docs + root hygiene** — move root `.md` → `docs/`, delete `server` binary
   and stray `node_modules/`, update references. Lowest risk.
2. **Python `scripts/` bucketing** — isolated to `ai/`.
3. **Go `internal/` reorg** — the import-path + package-rename change. Highest
   blast radius within Go; verified by `go build`/`go test`.
4. **Frontend `features/` reorg** — isolated to `web/`; verified by build + vitest.

Each PR updates the AGENTS.md files it touches.

## Out-of-Scope Follow-up (noted, not executed)

`web/src/proto/` ships two incompatible binding styles both in active use:
`game.ts` (ts_proto, flat exports like `ActionType`, used by Calc/shanten) and
`game.js` + `game.d.ts` (pbjs namespace `game.*`, used by Game/Table/contexts),
plus `game_cjs.js`. Consolidating to one is a code migration (different APIs),
not a folder move — tracked separately.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Broken Go imports after move | `go build ./...` + `go test ./...` gate each step |
| Lost git history on moves | Use `git mv`, never delete+recreate |
| Frontend relative-import breakage | Build + vitest gate; systematic `../` → `../../` audit |
| Stale path references in docs/memory/AGENTS | Explicit reference-update checklist above |
| `internal/` blocks a legitimate external importer | None today — all importers are `cmd/` within the module |

## Verification

- Go: `go build ./... && go test ./...` — identical pass set before/after.
- Frontend: `cd web && npm run build && npx vitest run` — green.
- Python: `cd ai && pytest` — green.
- Grep audit: no surviving references to old paths in tracked files.
