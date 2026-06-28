# Reorg PR 3 — Go `internal/` Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Go library packages under `internal/` (enforcing module-private boundaries), grouping/renaming them into clear domains: `core→engine`, `models→storage`, `rlenv→rl`; `api`, `rules`, and `bot` keep their names.

**Architecture:** Each package is moved with `git mv` (history preserved), then every import path and — for renamed packages — every `package` clause and qualified reference is rewritten across the module. `proto/` and `cmd/` stay at root. Each task ends green: `go build ./... && go vet ./... && go test ./...`.

**Tech Stack:** Go 1.25, perl (for word-boundary rewrites), git.

## Global Constraints

- Module path is unchanged: `github.com/plasma/fh-mahjong`.
- Use `git mv`; never delete+recreate.
- `core/game.go` (→ `internal/engine/game.go`) must still never import the rules package — the ruleset-agnostic rule survives unchanged.
- After EVERY task: `go build ./... && go vet ./... && go test ./...` must pass, AND `git diff --stat` reviewed for accidental edits (e.g. a `score.` mangled by a `core` rename — guarded by `\b` but verify).
- Use **perl** for qualifier renames (`\b` word boundaries); BSD `sed` lacks `\b`.

## Import-Path Map (reference)

| Old | New |
|---|---|
| `…/core` | `…/internal/engine` |
| `…/rules`, `…/rules/shanten` | `…/internal/rules`, `…/internal/rules/shanten` |
| `…/models` | `…/internal/storage` |
| `…/bot`, `…/bot/remote` | `…/internal/bot`, `…/internal/bot/remote` |
| `…/rlenv` | `…/internal/rl` |
| `…/api` | `…/internal/api` |

(`…` = `github.com/plasma/fh-mahjong`.) Package renames: `core→engine`, `models→storage`, `rlenv→rl`. `api`, `rules`, `shanten`, `bot`, `remote` keep their package names (path-only move).

**Collision guardrails (why these names):** `core` is renamed to `engine`, NOT `game` — proto's Go package is already `package game` (aliased `pb`) and 344 local vars are named `game`. `api` keeps its name, NOT renamed to `server` — `cmd/server/main.go` has a local `server` variable. `engine.`, `storage.`, and `rl.` are confirmed unused as qualifiers (0 collisions).

---

### Task 1: Move `rules/` (+`shanten/`) → `internal/rules/` (path-only)

**Files:**
- Move: `rules/` → `internal/rules/` (carries `rules/shanten/` and both `AGENTS.md`)
- Modify: all importers — `api/calc.go`, `api/room.go`, `api/shanten.go`, `cmd/cli/main.go`, `cmd/rlpaipu/main.go`, `cmd/wasm/main.go`, `rlenv/env.go`, plus test files

**Interfaces:** Produces import path `…/internal/rules` and `…/internal/rules/shanten`. Package names `rules` and `shanten` unchanged — no qualifier edits.

- [ ] **Step 1: Move the tree**

```bash
mkdir -p internal
git mv rules internal/rules
```

- [ ] **Step 2: Rewrite import paths module-wide**

```bash
git grep -l 'fh-mahjong/rules' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/rules}{fh-mahjong/internal/rules}g'
```

- [ ] **Step 3: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: all PASS. If a path was missed, the build error names the file — fix and rerun.

- [ ] **Step 4: Review the diff for surprises**

```bash
git diff --stat
```
Expected: only import-line changes + the rename moves.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor(go): move rules package under internal/"
```

---

### Task 2: Move `core/` → `internal/engine/` (rename package `core`→`engine`)

**Files:**
- Move: `core/` → `internal/engine/` (carries `core/testdata/`, `core/AGENTS.md`)
- Modify: importers `api/matchmaker.go`, `api/room.go`, `api/room_bot_test.go`, `cmd/cli/main.go`, `cmd/rlpaipu/main.go`, `rlenv/env.go`, `rlenv/env_test.go` (rlenv moves later), and the package's own `*_test.go` (`package core_test`)

**Interfaces:** Produces import path `…/internal/engine`, package `engine`. Qualifier `core.` → `engine.`. (Do NOT use `game` — it collides with proto's `package game` and 344 local `game` vars.)

- [ ] **Step 1: Move the tree**

```bash
git mv core internal/engine
```

- [ ] **Step 2: Rewrite import paths**

```bash
git grep -l 'fh-mahjong/core' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/core}{fh-mahjong/internal/engine}g'
```

- [ ] **Step 3: Rename the package clause (incl. external test package)**

```bash
perl -i -pe 's/^package core$/package engine/; s/^package core_test$/package engine_test/' internal/engine/*.go
```

- [ ] **Step 4: Rename qualified references `core.` → `engine.` (word-boundary safe)**

```bash
git grep -l '\bcore\.' -- '*.go' | xargs perl -i -pe 's/\bcore\./engine./g'
```
Note: `\bcore` does not match inside `score` (the `s` is a word char, so there is no boundary before `core`), so `score.` is safe.

- [ ] **Step 5: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 6: Review diff — confirm nothing was mangled**

```bash
git diff | grep -nE 'sengine\.' | head    # expect: no output (no score. mangling)
git diff --stat
```
Expected: every `engine.` change is a real package-qualifier swap; no `sengine.` artifacts.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor(go): move core -> internal/engine and rename package to engine"
```

---

### Task 3: Move `models/` → `internal/storage/` (rename package `models`→`storage`)

**Files:**
- Move: `models/` → `internal/storage/` (carries `models/AGENTS.md`)
- Modify: importers `api/auth.go`, `api/matchmaker.go`, `api/paipu.go`, `api/room.go`, `api/server.go`, `cmd/server/main.go`

**Interfaces:** Produces import path `…/internal/storage`, package `storage`. Qualifier `models.` → `storage.`.

- [ ] **Step 1: Move the tree**

```bash
git mv models internal/storage
```

- [ ] **Step 2: Rewrite import paths**

```bash
git grep -l 'fh-mahjong/models' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/models}{fh-mahjong/internal/storage}g'
```

- [ ] **Step 3: Rename the package clause**

```bash
perl -i -pe 's/^package models$/package storage/; s/^package models_test$/package storage_test/' internal/storage/*.go
```

- [ ] **Step 4: Rename qualified references `models.` → `storage.`**

```bash
git grep -l '\bmodels\.' -- '*.go' | xargs perl -i -pe 's/\bmodels\./storage./g'
```

- [ ] **Step 5: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(go): move models -> internal/storage and rename package to storage"
```

---

### Task 4: Move `bot/` (+`remote/`) → `internal/bot/` (path-only)

**Files:**
- Move: `bot/` → `internal/bot/` (carries `bot/remote/`, all `AGENTS.md`)
- Modify: importers `api/matchmaker.go`, `api/rl_agent_test.go`, `api/room.go`, `api/room_bot_test.go`, `cmd/cli/main.go`, `cmd/rlpaipu/main.go`, `cmd/server/main.go`, and `rlenv/env.go` (still at old path here)

**Interfaces:** Produces import path `…/internal/bot` and `…/internal/bot/remote`. Packages `bot`, `remote` unchanged — no qualifier edits.

- [ ] **Step 1: Move the tree**

```bash
git mv bot internal/bot
```

- [ ] **Step 2: Rewrite import paths**

```bash
git grep -l 'fh-mahjong/bot' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/bot}{fh-mahjong/internal/bot}g'
```

- [ ] **Step 3: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(go): move bot package under internal/"
```

---

### Task 5: Move `rlenv/` → `internal/rl/` (rename package `rlenv`→`rl`)

**Files:**
- Move: `rlenv/` → `internal/rl/` (carries `rlenv/AGENTS.md`)
- Modify: importers `internal/bot/remote/http_policy.go`, `cmd/rlbridge/main.go`

**Interfaces:** Produces import path `…/internal/rl`, package `rl`. Qualifier `rlenv.` → `rl.`.

- [ ] **Step 1: Move the tree**

```bash
git mv rlenv internal/rl
```

- [ ] **Step 2: Rewrite import paths**

```bash
git grep -l 'fh-mahjong/rlenv' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/rlenv}{fh-mahjong/internal/rl}g'
```

- [ ] **Step 3: Rename the package clause**

```bash
perl -i -pe 's/^package rlenv$/package rl/; s/^package rlenv_test$/package rl_test/' internal/rl/*.go
```

- [ ] **Step 4: Rename qualified references `rlenv.` → `rl.`**

```bash
git grep -l '\brlenv\.' -- '*.go' | xargs perl -i -pe 's/\brlenv\./rl./g'
```

- [ ] **Step 5: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(go): move rlenv -> internal/rl and rename package to rl"
```

---

### Task 6: Move `api/` → `internal/api/` (path-only)

**Files:**
- Move: `api/` → `internal/api/` (carries `api/AGENTS.md`)
- Modify: importer `cmd/server/main.go`

**Interfaces:** Produces import path `…/internal/api`. Package `api` is unchanged — no `package` clause or qualifier edits. (Do NOT rename to `server`: `cmd/server/main.go` holds a local `server` variable and the binary dir is already `cmd/server`; keep the clean `cmd/server` → `internal/api` split.)

Note: `internal/api/server.go` imports the `web` embed package (`…/web`) and `…/proto`; both paths are unchanged by this move.

- [ ] **Step 1: Move the tree**

```bash
git mv api internal/api
```

- [ ] **Step 2: Rewrite import paths**

```bash
git grep -l 'fh-mahjong/api' -- '*.go' | xargs perl -i -pe 's{fh-mahjong/api}{fh-mahjong/internal/api}g'
```
(No other package path begins with `api`, and route strings like `"/api/v1"` are not `fh-mahjong/api`, so this is safe.)

- [ ] **Step 3: Build, vet, test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(go): move api package under internal/"
```

---

### Task 7: Update docs, AGENTS.md, and memory; final audit

**Files:**
- Modify: root `AGENTS.md` (Module Map block, Key Files table, Architecture Principles)
- Create: `internal/AGENTS.md` (one-paragraph map of the internal packages)
- Modify: `README.md` (any module tree diagram)
- Modify: user memory index `/Users/plasma/.claude/projects/-Users-plasma-fh-mahjong/memory/MEMORY.md` (Key Files paths)

- [ ] **Step 1: Update root `AGENTS.md`**

In the Module Map and Key Files table, rewrite paths:
- `core/` → `internal/engine/`, `core/game.go` → `internal/engine/game.go`, `core/rules.go` → `internal/engine/rules.go`
- `rules/` → `internal/rules/`, `rules/fh.go` → `internal/rules/fh.go`
- `api/` → `internal/api/`
- `models/` → `internal/storage/`
- `bot/` → `internal/bot/`, `bot/heuristic.go` → `internal/bot/heuristic.go`
- `rlenv/` → `internal/rl/`, `rlenv/env.go` → `internal/rl/env.go`, `rlenv/action.go` → `internal/rl/action.go`
- Architecture Principle 1: "Rulesets implement `RuleEngine` in `rules/`" → "in `internal/rules/`"; the `core.Game`/`internal/engine` no-import-rules rule wording.

- [ ] **Step 2: Create `internal/AGENTS.md`**

A short doc mapping: `engine` (state machine), `rules` (+`shanten`), `api` (REST+WS), `storage` (GORM), `bot` (+`remote`), `rl` (RL env). Note the `internal/` boundary intent.

- [ ] **Step 3: Update memory index**

In `MEMORY.md`, update Key Files: `core/game.go`→`internal/engine/game.go`, `core/rules.go`→`internal/engine/rules.go`, `rules/fh.go`→`internal/rules/fh.go`. Note the `core/game.go must never import rules/` rule now reads `internal/engine` / `internal/rules`.

- [ ] **Step 4: Final grep audit — no stale Go paths in tracked files**

```bash
git grep -nE 'fh-mahjong/(core|api|models|rlenv|bot|rules)("|/)' -- '*.go'
```
Expected: no output (all now under `internal/`).

```bash
git grep -nE '`(core|rlenv|models|api)/' -- '*.md' ':!docs/superpowers/'
```
Expected: no output (docs updated; spec/plan files under docs/superpowers excluded as they record the mapping).

- [ ] **Step 5: Final full build + test**

```bash
go build ./... && go vet ./... && go test ./...
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "docs(go): update AGENTS.md, README, and memory for internal/ layout"
```

---

## Self-Review Notes

- Spec coverage: implements the entire "Go Reorg Detail" section — import-path map, package renames, `git mv`, build/test gate, and the no-import-rules invariant.
- Type/path consistency: every renamed package's qualifier (`core→engine`, `models→storage`, `rlenv→rl`) is rewritten in the same task that moves it, so the tree is green at each commit. `api`, `rules`, `bot` are path-only moves (no qualifier edits).
- Renames were chosen to avoid collisions: `core→engine` (not `game` — clashes with proto's `package game` and 344 local `game` vars); `api` kept (not `server` — clashes with a local `server` var in `cmd/server/main.go`). `core.`→`engine.` is guarded against `score.` by `\b` plus a Step-6 diff check.
- `proto/` stays at root (cross-language schema source); its generated Go package import path is unchanged, so no proto edits are needed.
