# Reorg PR 1 — Docs + Root Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move loose root docs into `docs/` (kebab-renamed), delete stray build artifacts, and fix every reference — leaving a clean top level.

**Architecture:** Pure file moves via `git mv` plus reference updates. No code changes. Verified by a grep audit that no stale paths survive in tracked files.

**Tech Stack:** git, ripgrep/grep.

## Global Constraints

- Use `git mv` for every move (preserve history); never delete+recreate.
- `README.md` and `AGENTS.md` stay at repo root.
- No behavioral/code changes in this PR.
- After every move, the corresponding references must be updated in the same commit.

---

### Task 1: Move rules docs into `docs/rules/`

**Files:**
- Move: `official_rules.md` → `docs/rules/official-rules.md`
- Move: `rules.md` → `docs/rules/rules.md`

- [ ] **Step 1: Create target dir and move**

```bash
mkdir -p docs/rules
git mv official_rules.md docs/rules/official-rules.md
git mv rules.md docs/rules/rules.md
```

- [ ] **Step 2: Fix the internal cross-reference inside rules.md**

`docs/rules/rules.md:69` references `official_rules.md`. Update it:

```bash
sed -i '' 's/from official_rules\.md/from official-rules.md/' docs/rules/rules.md
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs: move Fenghua rules docs into docs/rules/"
```

---

### Task 2: Move remaining root docs into `docs/`

> **Superseded during rebase:** `main` independently removed `technical_design.md`,
> `user_guide.md`, and `tasks.md` as stale inception docs (commit `20c43d7`)
> before this PR landed. This task is therefore a no-op — those files no longer
> exist to move. PR 1 relocates only `official_rules.md` + `rules.md` (Task 1).

**Files:**
- Move: `technical_design.md` → `docs/technical-design.md`
- Move: `user_guide.md` → `docs/user-guide.md`
- Move: `tasks.md` → `docs/tasks.md`

- [ ] **Step 1: Move the three files**

```bash
git mv technical_design.md docs/technical-design.md
git mv user_guide.md docs/user-guide.md
git mv tasks.md docs/tasks.md
```

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "docs: move design/user-guide/tasks docs into docs/"
```

---

### Task 3: Update all references to the moved docs

**Files:**
- Modify: `AGENTS.md` (lines ~63, 65, 135)
- Modify: `README.md` (lines ~29, 31, 88, 90)
- Modify: user memory index `/Users/plasma/.claude/projects/-Users-plasma-fh-mahjong/memory/MEMORY.md` and any memory file naming these paths

- [ ] **Step 1: Update root `AGENTS.md`**

Replace the Key Files paths and scoring reference:
- `` `official_rules.md` `` → `` `docs/rules/official-rules.md` ``
- `` `technical_design.md` `` → `` `docs/technical-design.md` ``
- `` `tasks.md` `` → `` `docs/tasks.md` ``
- `` `rules.md` `` → `` `docs/rules/rules.md` ``
- the line "Full scoring reference: `official_rules.md` and `rules.md`" → "...`docs/rules/official-rules.md` and `docs/rules/rules.md`"

- [ ] **Step 2: Update `README.md`**

Update the tree diagram and the doc links:
- `official_rules.md` → `docs/rules/official-rules.md`
- `technical_design.md` → `docs/technical-design.md`
- the markdown links `[official_rules.md](official_rules.md)` → `[official-rules.md](docs/rules/official-rules.md)` and `[technical_design.md](technical_design.md)` → `[technical-design.md](docs/technical-design.md)`

- [ ] **Step 3: Update the user memory index**

In `/Users/plasma/.claude/projects/-Users-plasma-fh-mahjong/memory/MEMORY.md`, update the Key Files bullets that name `official_rules.md`, `rules.md`, `technical_design.md`, `tasks.md` to their new `docs/...` paths.

- [ ] **Step 4: Grep audit — no stale references remain**

```bash
git grep -nE "(^|[^-/])official_rules\.md|technical_design\.md|user_guide\.md" -- ':!worklog/specs/2026-06-27*'
```
Expected: no output (the spec file is excluded as it documents the old→new mapping).

```bash
git grep -nE "\]\(rules\.md\)|\]\(tasks\.md\)|\(technical_design\.md\)"
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: update references to relocated root docs"
```

---

### Task 4: Remove stray root artifacts

**Files:**
- Delete: `server` (root build artifact, ~49 MB, untracked)
- Delete: root `node_modules/` (untracked, no package.json)
- Modify: `.gitignore` (add `/server`)

- [ ] **Step 1: Confirm both are untracked before deleting**

```bash
git ls-files --error-unmatch server 2>/dev/null && echo "TRACKED — stop" || echo "untracked, safe"
git ls-files node_modules | head -1
```
Expected: `server` → "untracked, safe"; `node_modules` → no output (already gitignored/untracked).

- [ ] **Step 2: Delete the artifacts**

```bash
rm -f server
rm -rf node_modules
```

- [ ] **Step 3: Add explicit gitignore for the root binary**

Add a line `/server` under the "Build output and vendor" section of `.gitignore`.

- [ ] **Step 4: Verify clean status**

```bash
git status --porcelain
```
Expected: only the `.gitignore` modification shows; no `server`/`node_modules` entries.

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: drop stray root server binary and node_modules; gitignore /server"
```

---

## Self-Review Notes

- Spec coverage: covers the spec's "Deletions" and "Docs" rows. `killer_mortal_gui/` and root `testdata/` are intentionally untouched per spec.
- `mkdir` lines are kept because `git mv` will not create intermediate dirs on all platforms; harmless if the dir already exists.
- All `sed -i ''` use the BSD/macOS empty-suffix form (this is a darwin host).
