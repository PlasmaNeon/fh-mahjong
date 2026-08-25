# Reorg PR 2 — Python `scripts/` Bucketing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group the clean, independent script families (`train_*`, `evaluate_*`) into `scripts/train/` and `scripts/evaluate/`, leaving entangled modules flat — improving navigation without an import-web rewrite.

**Architecture:** `git mv` of leaf entry-point modules into subpackages, plus updates to their `pyproject.toml` console-script paths and test imports. Shared helpers stay at `scripts/` root so their dotted paths never change. Verified by `pytest`.

**Tech Stack:** Python 3, uv, pytest.

## ⚠️ Scope Decision (read before executing)

Investigation found the `scripts/` modules form an **import web**: `model_config_args` is imported by ~10 scripts; `generate_data`, `build_counterfactual_risk_data`, `generate_selfplay`, `generate_sampled_branch_counterfactuals`, and `branch_cf_calibration` are each imported by other scripts. The `generate_*` and `*_diagnostics`/`*_calibration` families are mutually coupled and do not fit clean buckets.

**Therefore this PR buckets ONLY the two clean leaf families** — `train_*` (9 modules) and `evaluate_*` (4 modules) — which are imported by no other script and depend only on root-level shared helpers (whose paths are unchanged). The `generate_*`, `diagnostics`, `serving`, and `pipeline` modules are **left flat on purpose**; bucketing them is high-churn for low gain and is explicitly out of scope.

This is the lowest-value of the four reorg PRs. **It is safe to drop entirely** if the import-web cost outweighs the navigation benefit.

## Global Constraints

- Use `git mv` for every move (preserve history).
- Shared/imported modules stay at `scripts/` root — do **not** move them.
- Every moved module needs its `pyproject.toml` entry-point path and any test import updated in the same commit.
- `cd ai && uv run pytest` must pass identically before and after.

---

### Task 1: Bucket the `train_*` family

**Files:**
- Move (9): `ai/src/fh_mahjong_ai/scripts/train_{bc,awbc,iql,global_ev,pairwise_delta,branch_preference_policy,action_risk,offline_q,ppo}.py` → `scripts/train/`
- Create: `ai/src/fh_mahjong_ai/scripts/train/__init__.py`
- Modify: `ai/pyproject.toml` (9 `[project.scripts]` lines)
- Modify: any `ai/tests/test_train_*.py` / `test_awbc.py` / `test_iql.py` / `test_offline_q.py` that import these modules

- [ ] **Step 1: Confirm the train modules are imported by no other script**

```bash
cd ai && grep -rn "scripts\.train_" src/fh_mahjong_ai/scripts | grep -v "^src/fh_mahjong_ai/scripts/train_"
```
Expected: no output (nothing imports `scripts.train_*` except possibly the file itself).

- [ ] **Step 2: Create the subpackage and move the 9 modules**

```bash
cd ai/src/fh_mahjong_ai/scripts
mkdir -p train && touch train/__init__.py
for m in train_bc train_awbc train_iql train_global_ev train_pairwise_delta \
         train_branch_preference_policy train_action_risk train_offline_q train_ppo; do
  git mv "$m.py" "train/$m.py"
done
git add train/__init__.py
```

- [ ] **Step 3: Update the 9 `pyproject.toml` entry-point paths**

In `ai/pyproject.toml`, rewrite each `fh_mahjong_ai.scripts.train_X` → `fh_mahjong_ai.scripts.train.train_X`:

```bash
cd ai && sed -i '' -E 's/fh_mahjong_ai\.scripts\.(train_[a-z_]+):/fh_mahjong_ai.scripts.train.\1:/' pyproject.toml
grep -n "scripts.train" pyproject.toml
```
Expected: all 9 train entries now read `...scripts.train.train_*:main`.

- [ ] **Step 4: Update test imports for moved train modules**

```bash
cd ai && grep -rln "from fh_mahjong_ai.scripts.train_\|import fh_mahjong_ai.scripts.train_" tests
```
For each hit, rewrite `fh_mahjong_ai.scripts.train_X` → `fh_mahjong_ai.scripts.train.train_X`:

```bash
cd ai && grep -rln "fh_mahjong_ai.scripts.train_" tests | xargs -I{} \
  sed -i '' -E 's/fh_mahjong_ai\.scripts\.(train_[a-z_]+)/fh_mahjong_ai.scripts.train.\1/g' {}
```

- [ ] **Step 5: Reinstall entry points and run the suite**

```bash
cd ai && uv sync && uv run pytest -q
```
Expected: PASS, same count as before the move.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(ai): group train_* scripts into scripts/train/"
```

---

### Task 2: Bucket the `evaluate_*` family

**Files:**
- Move (4): `ai/src/fh_mahjong_ai/scripts/evaluate.py`, `evaluate_guarded.py`, `evaluate_risk_guarded.py`, `evaluate_tail_constrained.py` → `scripts/evaluate/`
- Create: `ai/src/fh_mahjong_ai/scripts/evaluate/__init__.py`
- Modify: `ai/pyproject.toml` (2 entries: `fh-mj-evaluate`, `fh-mj-evaluate-risk-guarded`)
- Modify: any `ai/tests/test_evaluate.py` imports

- [ ] **Step 1: Confirm evaluate modules are imported by no other script**

```bash
cd ai && grep -rn "scripts\.evaluate" src/fh_mahjong_ai/scripts | grep -v "^src/fh_mahjong_ai/scripts/evaluate"
```
Expected: no output.

- [ ] **Step 2: Create subpackage and move the 4 modules**

```bash
cd ai/src/fh_mahjong_ai/scripts
mkdir -p evaluate && touch evaluate/__init__.py
for m in evaluate evaluate_guarded evaluate_risk_guarded evaluate_tail_constrained; do
  git mv "$m.py" "evaluate/$m.py"
done
git add evaluate/__init__.py
```

Note: this creates `scripts/evaluate/` as a package shadowing the old `scripts/evaluate.py` module name — intended. The package's `evaluate.py` is now `scripts.evaluate.evaluate`.

- [ ] **Step 3: Update the 2 `pyproject.toml` entries**

In `ai/pyproject.toml`:
- `fh-mj-evaluate = "fh_mahjong_ai.scripts.evaluate:main"` → `"fh_mahjong_ai.scripts.evaluate.evaluate:main"`
- `fh-mj-evaluate-risk-guarded = "fh_mahjong_ai.scripts.evaluate_risk_guarded:main"` → `"fh_mahjong_ai.scripts.evaluate.evaluate_risk_guarded:main"`

```bash
cd ai && grep -n "fh-mj-evaluate" pyproject.toml
```
Expected: both point under `scripts.evaluate.`.

- [ ] **Step 4: Update test imports**

```bash
cd ai && grep -rln "fh_mahjong_ai.scripts.evaluate" tests | xargs -I{} \
  sed -i '' -E 's/fh_mahjong_ai\.scripts\.evaluate(_[a-z_]+)?/fh_mahjong_ai.scripts.evaluate.evaluate\1/g' {}
```
Then manually verify the bare `evaluate` (no suffix) rewrote to `scripts.evaluate.evaluate`, not `scripts.evaluate.evaluate_`:

```bash
cd ai && grep -rn "scripts.evaluate" tests
```

- [ ] **Step 5: Reinstall and run the suite**

```bash
cd ai && uv sync && uv run pytest -q
```
Expected: PASS, same count.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(ai): group evaluate_* scripts into scripts/evaluate/"
```

---

### Task 3: Update `ai/AGENTS.md`

**Files:**
- Modify: `ai/AGENTS.md`

- [ ] **Step 1: Document the new layout**

Update `ai/AGENTS.md` to note `scripts/train/` and `scripts/evaluate/` subpackages, and that `generate_*`/diagnostics/serving scripts remain flat at `scripts/` root due to shared-helper coupling.

- [ ] **Step 2: Commit**

```bash
git add ai/AGENTS.md
git commit -m "docs(ai): document scripts subpackage layout"
```

---

## Self-Review Notes

- Spec coverage: implements the spec's "Python — group scripts only" intent, scoped down to the clean families per the import-web finding. The spec's `generate/` and `diagnostics/` buckets are deliberately deferred and documented as such.
- Type/path consistency: shared helpers (`model_config_args`, `generate_data`, `build_counterfactual_risk_data`, etc.) are never moved, so no inter-script import rewrites are needed.
- The `pytest` gate after each task is the real correctness check; the grep audits catch missed entry-point/test references before the gate runs.
