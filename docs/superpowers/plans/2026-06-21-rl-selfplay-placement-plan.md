# RL Self-Play Scale + Placement-Aware Reward Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **UPDATE 2026-06-21 (post-merge of PR #82 "chongci rl tooling"):** main now ships a
> `GlobalEVNet` visible-state final-match-EV predictor (`ai/src/fh_mahjong_ai/global_ev.py`,
> `fh-mj-train-global-ev`) plus IQL integration via `--target-mode global_ev_td` (bootstrap Q
> targets from a frozen global-EV value function) and a `policy_kl_weight` config field. This is
> the real implementation of the "visible global reward/value prediction" idea from the design
> discussion. This branch was rebased onto that main. **Synergy added (committed):**
> `global_ev_targets()` and `fh-mj-train-global-ev` now accept `--reward-shaping placement`, so the
> global EV value function can be trained on rank-based placement EV; IQL `--target-mode
> global_ev_td` then bootstraps *placement-aware* Q targets. Net effect: placement shaping is now
> available in BOTH the MC return path (`fh-mj-train-iql --reward-shaping placement`) and the
> learned-value-bootstrap path (`fh-mj-train-global-ev --reward-shaping placement` →
> `fh-mj-train-iql --target-mode global_ev_td --global-ev-checkpoint ...`).
>
> The recommended Phase-3 training recipe is now: (a) train a raw GlobalEV and a placement
> GlobalEV on the Phase-2 data; (b) run three IQL variants on identical data — raw MC baseline,
> `--reward-shaping placement` MC, and `--target-mode global_ev_td` with the placement GlobalEV;
> (c) compare all three against the current promoted checkpoint on the fixed CI gate. The
> `global_ev_td` + placement-GlobalEV variant is the most promising because it combines a learned
> value function with placement-aware credit assignment.

**Goal:** Improve the Chongci RL agent by (1) hardening evaluation with confidence intervals, (2) scaling mixed self-play data to establish a clean stronger baseline, and (3) adding placement-aware (rank-based) reward shaping as an isolated, toggleable ablation on top of that baseline.

**Architecture:** Three sequenced phases. Phase 1 adds standard-error/CI reporting to the existing duplicate-seat evaluation so every later comparison is trustworthy. Phase 2 is an operational data-scaling runbook that produces a larger mixed self-play dataset and a re-trained IQL checkpoint using the *current* (raw net-score) return target — this is the new baseline. Phase 3 adds placement-aware reward shaping as a read-time transform on the already-stored per-seat `terminal_rewards` vector (no Go changes, no data regeneration), wired behind a `--reward-shaping placement` flag, then trained and compared against the Phase-2 baseline. Conservative Q/value learning (discrete IQL with expectile value + BC regularization) is already the default and is unchanged.

**Tech Stack:** Python 3.12 (uv-managed), PyTorch, NumPy, the existing `fh_mahjong_ai` package, Go `rlenv` simulator (read-only here), `unittest` test suite.

**Out of scope (deliberate):** Oracle / privileged-information auxiliary heads, the action-risk / paired-trace tail-risk critic line (rejected for structural data-scale reasons), and any architecture change (transformer/hierarchical). Do not touch `paired_trace*`, `risk_filter`, `train_action_risk`, or `evaluate_*guarded` in this plan.

**Key seams discovered:**
- Return target is read from the per-seat terminal-reward vector in two places: `ai/src/fh_mahjong_ai/buffer.py:42-47` (`ObjectReplayBuffer._return_for`) and `ai/src/fh_mahjong_ai/buffer.py:127` (`ArrayReplayBuffer.sample`). Stored arrays keep the full per-seat vector as `terminal_rewards` shape `(N, num_seats)` (`ai/src/fh_mahjong_ai/storage.py:417`). Placement rank can therefore be computed per row entirely in Python.
- Every online/duplicate report routes reward stats through `reward_summary()` (`ai/src/fh_mahjong_ai/evaluate.py:19`), then exposes `"mean_reward"` in the duplicate-seat reports (`evaluate.py:723`, `evaluate.py:842`). This is the single place to add CI fields.

---

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `ai/src/fh_mahjong_ai/evaluate.py` | reward summary + duplicate-seat reports | Add `sem`/`ci95` to `reward_summary`; surface `mean_reward_sem`/`mean_reward_ci95` in duplicate reports |
| `ai/tests/test_evaluate.py` | eval tests | Add CI-field assertions |
| `ai/src/fh_mahjong_ai/data.py` | trajectory post-processing | Add `placement_shaped_returns()` helper |
| `ai/tests/test_data.py` | data tests | Add placement-shaping tests |
| `ai/src/fh_mahjong_ai/buffer.py` | replay buffers | Add `reward_shaping`/`placement_values` to both buffers; apply in `sample()` |
| `ai/tests/test_buffer.py` | buffer tests | Add placement-shaping sampling tests |
| `ai/src/fh_mahjong_ai/config.py` | configs | Add `reward_shaping`/`placement_values` to `DiscreteIQLConfig` |
| `ai/src/fh_mahjong_ai/scripts/train_iql.py` | IQL CLI | Add `--reward-shaping`/`--placement-values`; thread into `load_iql_replay_buffer` and onto buffers |
| `ai/tests/test_iql.py` | IQL CLI tests | Add placement-shaping CLI smoke |
| `docs/rl-papers/chongci-rl-experiment-progress.md` | experiment log | Append Phase-2 and Phase-3 experiment entries |
| `ai/checkpoints/best-checkpoints.json` | checkpoint registry | Update on promotion only |

---

## Phase 1: Evaluation Confidence Intervals

Rationale: later phases must be compared on a fixed, larger duplicate-seat budget with confidence intervals, or we repeat the "failure moved between sources" noise problem. Establish this first.

### Task 1: Standard error and 95% CI in `reward_summary`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py:19-55`
- Test: `ai/tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_evaluate.py`:

```python
def test_reward_summary_reports_sem_and_ci95(self):
    from fh_mahjong_ai.evaluate import reward_summary

    summary = reward_summary([1.0, 1.0, 1.0, 1.0])
    self.assertEqual(summary["sem"], 0.0)
    self.assertEqual(summary["ci95"], 0.0)

    summary = reward_summary([0.0, 2.0])
    # sample std (ddof=1) of [0,2] is sqrt(2); sem = sqrt(2)/sqrt(2) = 1.0
    self.assertAlmostEqual(summary["sem"], 1.0, places=6)
    self.assertAlmostEqual(summary["ci95"], 1.96, places=6)

def test_reward_summary_empty_has_ci_fields(self):
    from fh_mahjong_ai.evaluate import reward_summary

    summary = reward_summary([])
    self.assertEqual(summary["sem"], 0.0)
    self.assertEqual(summary["ci95"], 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_evaluate -k sem -v`
Expected: FAIL with `KeyError: 'sem'`.

(If the test module path differs, use: `uv run --project ai python -m unittest ai.tests.test_evaluate` — match the project's existing test invocation; confirm with `uv run --project ai python -m unittest discover -s ai/tests -v` if unsure.)

- [ ] **Step 3: Add CI fields to the empty branch**

In `ai/src/fh_mahjong_ai/evaluate.py`, inside the `if not values:` return dict (currently lines 22-35), add two keys before the closing brace:

```python
            "negative_rate": 0.0,
            "sem": 0.0,
            "ci95": 0.0,
        }
```

- [ ] **Step 4: Add CI fields to the populated branch**

In the same function, replace the populated `return {` block (currently lines 42-55) so it ends with the new keys. Insert immediately before `return {`:

```python
    sem = float(np.std(array, ddof=1) / np.sqrt(count)) if count > 1 else 0.0
```

Then add these two keys to the returned dict (after `"negative_rate"`):

```python
        "negative_rate": negative_count / count,
        "sem": sem,
        "ci95": 1.96 * sem,
    }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_evaluate -k sem -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(eval): add SEM and 95% CI to reward_summary"
```

### Task 2: Surface `mean_reward_ci95` in duplicate-seat reports

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (the `evaluate_duplicate_seats_policy` report dict near line 723 and the `evaluate_duplicate_seats` report dict near line 842)
- Test: `ai/tests/test_evaluate.py`

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_evaluate.py` (reuse the existing duplicate-seat test setup pattern already in this file; if a helper builds an env+policy for `evaluate_duplicate_seats`, copy that setup):

```python
def test_duplicate_seats_report_includes_ci(self):
    from fh_mahjong_ai.evaluate import evaluate_duplicate_seats

    report = self._run_small_duplicate_seats()  # existing helper or inline setup
    self.assertIn("mean_reward_sem", report)
    self.assertIn("mean_reward_ci95", report)
    self.assertGreaterEqual(report["mean_reward_ci95"], 0.0)
```

If no `_run_small_duplicate_seats` helper exists, inline the same construction the nearest existing duplicate-seat test in this file uses, then assert the two new keys.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_evaluate -k duplicate_seats_report_includes_ci -v`
Expected: FAIL with `KeyError` / `assertIn` failure.

- [ ] **Step 3: Add CI keys to both duplicate-seat report dicts**

In `evaluate_duplicate_seats_policy` (report dict starting near line 712) and `evaluate_duplicate_seats` (report dict starting near line 831), both already compute `rewards = reward_summary(...)` and set `"mean_reward": rewards["mean"]`. Add immediately after that line in each dict:

```python
        "mean_reward": rewards["mean"],
        "mean_reward_sem": rewards["sem"],
        "mean_reward_ci95": rewards["ci95"],
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_evaluate -k duplicate_seats_report_includes_ci -v`
Expected: PASS.

- [ ] **Step 5: Run the full evaluate test module**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_evaluate -v`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(eval): surface mean_reward CI in duplicate-seat reports"
```

---

## Phase 2: Scale Mixed Self-Play and Establish the Baseline

Rationale: this is the highest-confidence lever. Only one Chongci checkpoint has ever been promoted. We grow the frozen opponent pool and dataset, retrain IQL with the **current raw return target** (no shaping yet), and lock in a stronger baseline measured under Phase-1 CIs. This phase is operational (no new code) — it produces artifacts and a recorded experiment entry. Run on the training box per `ai/README.md` (WSL/4090 flow).

### Task 3: Generate scaled mixed self-play dataset

**Files:**
- Artifacts only: new shard directory under the runs path (e.g. `/root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards/`)
- Modify (append): `docs/rl-papers/chongci-rl-experiment-progress.md`

- [ ] **Step 1: Confirm the frozen opponent pool**

The pool must be: heuristic, BC, the current promoted Chongci IQL checkpoint (`current_chongci` from `ai/checkpoints/best-checkpoints.json`), and at least one older checkpoint. Resolve paths:

```bash
uv run --project ai python -c "from fh_mahjong_ai.checkpoint_manifest import load_manifest; m=load_manifest(); print(m)"
```

- [ ] **Step 2: Generate self-play shards across multiple seed windows**

Use distinct, non-overlapping seed windows from any evaluation seeds. Repeat per opponent-pool composition so the learning seat (seat 0) sees a mix of opponents. Example (adjust seat policies to cover the pool):

```bash
uv run --project ai fh-mj-generate-selfplay \
  --match-mode chongci \
  --episodes 4000 --seed 600000 \
  --seat-policy "1=checkpoint:/root/.../current_chongci.pt" \
  --seat-policy "2=heuristic" \
  --seat-policy "3=random" \
  --format npz-shards \
  --output /root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards-a
```

Target an order-of-magnitude more transitions than prior Chongci runs (aim for hundreds of thousands of operation-level transitions across windows). Generate ≥3 windows with rotated seat policies into sibling shard dirs (`-a`, `-b`, `-c`).

- [ ] **Step 3: Verify dataset manifests**

Run:
```bash
uv run --project ai python -c "import json,glob; [print(p, json.load(open(p)).get('transitions') or json.load(open(p)).get('action_count')) for p in glob.glob('/root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards-*/manifest.json')]"
```
Expected: each manifest reports seed range, policy source, bridge kind=go, commit SHA, and a transition count consistent with `--episodes`.

- [ ] **Step 4: Record the data-generation entry**

Append a `### Experiment: Scaled Mixed Self-Play Data Generation` block to `docs/rl-papers/chongci-rl-experiment-progress.md` using the file's Maintenance Protocol template (Run / Question / Data / Training=n/a / Evaluation=n/a / Result=row counts / Decision=inconclusive / Interpretation).

- [ ] **Step 5: Commit the log update**

```bash
git add docs/rl-papers/chongci-rl-experiment-progress.md
git commit -m "docs(rl): record scaled Chongci self-play data generation"
```

### Task 4: Train baseline IQL on scaled data (raw returns)

**Files:**
- Artifacts only: `/root/fh-mahjong-runs/chongci-scale-<date>/iql-baseline/`
- Modify (append): `docs/rl-papers/chongci-rl-experiment-progress.md`

- [ ] **Step 1: Train IQL across all scaled shards plus retained heuristic data**

Pass repeated `--data` (do not merge/discard older datasets), warm-start from the current promoted checkpoint, keep conservative defaults (expectile value, BC regularization). NOTE: `fh-mj-train-iql` has **no** `--match-mode` flag — Chongci-ness is already baked into the stored transitions, so the trainer just reads the shards:

```bash
uv run --project ai fh-mj-train-iql \
  --data /root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards-a \
  --data /root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards-b \
  --data /root/fh-mahjong-runs/chongci-scale-<date>/selfplay-shards-c \
  --data /root/.../existing-heuristic-shards \
  --epochs 6 --batch-size 256 --lr 1e-4 \
  --checkpoint-dir /root/fh-mahjong-runs/chongci-scale-<date>/iql-baseline \
  --mlflow
```

(Do NOT pass `--reward-shaping` here — Phase 3 introduces it. This run is the raw-return baseline.)

- [ ] **Step 2: Confirm checkpoints were written**

Run: `ls /root/fh-mahjong-runs/chongci-scale-<date>/iql-baseline/`
Expected: per-epoch `.pt` checkpoints plus the training report JSON.

- [ ] **Step 3: Record the training entry** in `chongci-rl-experiment-progress.md` (Question = "does scaled data + raw-return IQL beat the current promoted checkpoint", Training = hyperparameters + MLflow run id, Decision = still running).

### Task 5: Evaluate baseline under fixed CI gate and decide

**Files:**
- Artifacts only: evaluation report JSON
- Modify (append): `docs/rl-papers/chongci-rl-experiment-progress.md`; possibly `ai/checkpoints/best-checkpoints.json`

- [ ] **Step 1: Define and run the fixed large duplicate-seat gate**

Use a fixed, large, pre-registered seed budget (e.g. ≥1500 seeds across ≥3 windows), duplicate seats on, Chongci mode, comparing each candidate epoch against the current promoted anchor:

```bash
uv run --project ai fh-mj-evaluate \
  --match-mode chongci \
  --checkpoint /root/fh-mahjong-runs/chongci-scale-<date>/iql-baseline/epoch_6.pt \
  --duplicate-seats --eval-seeds 534000:600,544001:600,554001:600 \
  --report-output /root/fh-mahjong-runs/chongci-scale-<date>/eval-baseline.json
```

Repeat for the anchor (`current_chongci`) over the identical seeds.

- [ ] **Step 2: Apply the CI-aware promotion rule**

A candidate epoch is the new baseline only if, on the identical seed budget:
- `mean_reward` ≥ anchor `mean_reward`, **and** the candidate's `mean_reward_ci95` does not overlap downward into a worse region than the anchor mean (i.e. `candidate.mean_reward - candidate.mean_reward_ci95 ≥ anchor.mean_reward - anchor.mean_reward_ci95`), **and**
- `large_loss_rate` ≤ anchor `large_loss_rate`, **and**
- `positive_reward_rate` does not regress materially.

- [ ] **Step 3: Record the decision** in `chongci-rl-experiment-progress.md` with the full metrics table including `mean_reward_ci95`. If promoted, update `ai/checkpoints/best-checkpoints.json` `current_chongci` (metadata only; do not commit the `.pt`).

- [ ] **Step 4: Commit log + manifest**

```bash
git add docs/rl-papers/chongci-rl-experiment-progress.md ai/checkpoints/best-checkpoints.json
git commit -m "docs(rl): scaled-data IQL baseline duplicate-seat gate result"
```

**STOP / CHECKPOINT:** Do not start Phase 3 until Phase 2 has produced a recorded baseline (promoted or not). Phase 3 is measured *against this baseline on the same seed budget*, so attribution stays clean.

---

## Phase 3: Placement-Aware Reward Shaping

Rationale: convert the per-seat terminal net-score vector into rank-based placement value (Mortal/Suphx-style), so credit assignment optimizes final standing rather than raw net magnitude. Implemented as a read-time transform on existing stored `terminal_rewards` — no Go changes, no data regeneration, fully toggleable, and trained on the *same* Phase-2 data so the only variable is the return target.

### Task 6: `placement_shaped_returns` helper

**Files:**
- Modify: `ai/src/fh_mahjong_ai/data.py`
- Test: `ai/tests/test_data.py`

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_data.py`:

```python
def test_placement_shaped_returns_basic_ranking(self):
    import numpy as np
    from fh_mahjong_ai.data import placement_shaped_returns

    rewards = np.array([[0.5, -0.2, 1.1, -1.4]], dtype=np.float32)
    shaped = placement_shaped_returns(rewards)
    # seat2 best -> 1.0, seat0 second -> 1/3, seat1 third -> -1/3, seat3 last -> -1.0
    np.testing.assert_allclose(
        shaped[0], [1.0 / 3.0, -1.0 / 3.0, 1.0, -1.0], rtol=1e-6
    )

def test_placement_shaped_returns_averages_ties(self):
    import numpy as np
    from fh_mahjong_ai.data import placement_shaped_returns

    rewards = np.array([[1.0, 1.0, -1.0, -1.0]], dtype=np.float32)
    shaped = placement_shaped_returns(rewards)
    # top two tie -> average(1.0, 1/3); bottom two tie -> average(-1/3, -1.0)
    np.testing.assert_allclose(
        shaped[0],
        [2.0 / 3.0, 2.0 / 3.0, -2.0 / 3.0, -2.0 / 3.0],
        rtol=1e-6,
    )

def test_placement_shaped_returns_preserves_shape(self):
    import numpy as np
    from fh_mahjong_ai.data import placement_shaped_returns

    rewards = np.zeros((5, 4), dtype=np.float32)
    self.assertEqual(placement_shaped_returns(rewards).shape, (5, 4))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_data -k placement -v`
Expected: FAIL with `ImportError`/`AttributeError: placement_shaped_returns`.

- [ ] **Step 3: Implement the helper**

Add to `ai/src/fh_mahjong_ai/data.py` (top imports already include `numpy as np`; add `from typing import Sequence` to the existing typing import):

```python
def placement_shaped_returns(
    terminal_rewards: np.ndarray,
    placement_values: Sequence[float] = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0),
) -> np.ndarray:
    """Convert per-seat terminal rewards into rank-based placement values.

    The last axis is the seat axis. Each row is ranked by descending reward
    (rank 0 = highest reward -> placement_values[0]). Tied rewards receive the
    average of their tied placement values. Output keeps the input shape.
    """
    rewards = np.asarray(terminal_rewards, dtype=np.float32)
    table = np.asarray(placement_values, dtype=np.float32)
    if rewards.shape[-1] != table.shape[0]:
        raise ValueError("placement_values length must match the seat axis")

    flat = rewards.reshape(-1, rewards.shape[-1])
    shaped = np.empty_like(flat)
    for row_index in range(flat.shape[0]):
        row = flat[row_index]
        order = np.argsort(-row, kind="stable")
        ranks = np.empty(row.shape[0], dtype=np.int64)
        ranks[order] = np.arange(row.shape[0])
        seat_values = table[ranks]
        for value in np.unique(row):
            tie_mask = row == value
            if int(np.count_nonzero(tie_mask)) > 1:
                seat_values[tie_mask] = float(seat_values[tie_mask].mean())
        shaped[row_index] = seat_values
    return shaped.reshape(rewards.shape)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_data -k placement -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/data.py ai/tests/test_data.py
git commit -m "feat(data): add placement_shaped_returns rank-based reward helper"
```

### Task 7: Apply placement shaping in both replay buffers

**Files:**
- Modify: `ai/src/fh_mahjong_ai/buffer.py` (`ObjectReplayBuffer` near lines 42-52, `ArrayReplayBuffer` near line 127)
- Test: `ai/tests/test_buffer.py`

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_buffer.py`:

```python
def test_array_buffer_placement_shaping(self):
    import numpy as np
    from fh_mahjong_ai.buffer import ArrayReplayBuffer

    # two transitions, both seat 0; full per-seat terminal rewards differ in rank
    arrays = {
        "seats": np.array([0, 0], dtype=np.int64),
        "planes": np.zeros((2, 39, 42, 1), dtype=np.float32),
        "scalars": np.zeros((2, 58), dtype=np.float32),
        "action_mask": np.ones((2, 204), dtype=np.int8),
        "action_ids": np.array([0, 0], dtype=np.int64),
        "terminal_rewards": np.array(
            [[1.1, 0.5, -0.2, -1.4], [-1.4, 0.5, -0.2, 1.1]], dtype=np.float32
        ),
        "terminated": np.array([True, True], dtype=np.bool_),
        "truncated": np.array([False, False], dtype=np.bool_),
        "steps_to_done": np.array([0, 0], dtype=np.int32),
    }
    buf = ArrayReplayBuffer(
        arrays=arrays,
        indices=np.array([0, 1]),
        reward_shaping="placement",
    )
    batch = buf.sample(2, seed=0)
    # both rows sampled; seat 0 is 1st in row0 (-> 1.0) and last in row1 (-> -1.0)
    returns_by_index = dict(zip(batch.action_ids.tolist(), batch.returns.tolist()))
    self.assertIn(1.0, [round(v, 6) for v in batch.returns.tolist()])
    self.assertIn(-1.0, [round(v, 6) for v in batch.returns.tolist()])
```

(If `ArrayReplayBuffer` requires more array keys to construct, copy the exact key set from the nearest existing `test_buffer.py` ArrayReplayBuffer test and add `reward_shaping="placement"`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_buffer -k placement -v`
Expected: FAIL with `TypeError: unexpected keyword argument 'reward_shaping'`.

- [ ] **Step 3: Add fields and shaping to `ArrayReplayBuffer`**

In `ai/src/fh_mahjong_ai/buffer.py`, add to the `ArrayReplayBuffer` dataclass fields:

```python
    reward_shaping: str = "raw"
    placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
```

Add the import at the top of the file:

```python
from .data import placement_shaped_returns
```

Replace the returns line (currently `returns = self.arrays["terminal_rewards"][indices, seats]...` near line 127) with:

```python
        if self.reward_shaping == "placement":
            full_terminal = self.arrays["terminal_rewards"][indices].astype(np.float32, copy=False)
            shaped = placement_shaped_returns(full_terminal, self.placement_values)
            returns = shaped[np.arange(indices.shape[0]), seats].astype(np.float32, copy=False)
        else:
            returns = self.arrays["terminal_rewards"][indices, seats].astype(np.float32, copy=False)
```

- [ ] **Step 4: Add fields and shaping to `ObjectReplayBuffer`**

Add the same two fields to the `ObjectReplayBuffer` dataclass. Replace its `_return_for` (lines 42-47) with:

```python
        def _return_for(item: Transition) -> float:
            seat = item.observation.seat
            tr = item.info.get("terminal_rewards")
            if tr is None:
                return float(item.rewards[seat])
            tr = np.asarray(tr, dtype=np.float32)
            if self.reward_shaping == "placement":
                tr = placement_shaped_returns(tr, self.placement_values)
            return float(tr[seat])
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_buffer -k placement -v`
Expected: PASS.

- [ ] **Step 6: Run the full buffer test module**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_buffer -v`
Expected: PASS (raw path unchanged).

- [ ] **Step 7: Commit**

```bash
git add ai/src/fh_mahjong_ai/buffer.py ai/tests/test_buffer.py
git commit -m "feat(buffer): optional placement reward shaping in replay buffers"
```

### Task 8: Config + IQL CLI wiring

**Files:**
- Modify: `ai/src/fh_mahjong_ai/config.py:61-92` (`DiscreteIQLConfig`)
- Modify: `ai/src/fh_mahjong_ai/scripts/train_iql.py` (`main` arg parsing near line 569; `load_iql_replay_buffer` near line 405; `DiscreteIQLConfig` build near line 198)
- Test: `ai/tests/test_iql.py`

- [ ] **Step 1: Write the failing test**

Add to `ai/tests/test_iql.py` (follow the existing CLI smoke-test pattern in that file — it already builds a tiny mock/sharded dataset and runs `train_iql.main` with argv; copy that fixture and add the flag):

```python
def test_train_iql_cli_placement_shaping_runs(self):
    import sys
    from fh_mahjong_ai.scripts import train_iql

    data_dir = self._make_tiny_chongci_shards()   # existing helper or inline
    out_dir = self._tmp_path("iql-placement")
    argv = [
        "fh-mj-train-iql",
        "--match-mode", "chongci",
        "--data", str(data_dir),
        "--epochs", "1", "--batch-size", "8",
        "--reward-shaping", "placement",
        "--checkpoint-dir", str(out_dir),
    ]
    old = sys.argv
    try:
        sys.argv = argv
        train_iql.main()
    finally:
        sys.argv = old
    self.assertTrue(any(out_dir.glob("*.pt")))
```

If no helper produces tiny Chongci shards, reuse whatever the nearest existing `test_iql.py` CLI test uses to create `--data`, and just add `--reward-shaping placement` to its argv plus the assertion.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_iql -k placement -v`
Expected: FAIL with `error: unrecognized arguments: --reward-shaping`.

- [ ] **Step 3: Add config fields**

In `ai/src/fh_mahjong_ai/config.py`, add to `DiscreteIQLConfig`:

```python
    reward_shaping: str = "raw"
    placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)
```

- [ ] **Step 4: Add CLI arguments**

In `train_iql.py` `main()` argument section (near line 581), add:

```python
    parser.add_argument(
        "--reward-shaping",
        choices=("raw", "placement"),
        default="raw",
        help="raw terminal net-score return (default) or rank-based placement value",
    )
    parser.add_argument(
        "--placement-values",
        type=float,
        nargs=4,
        default=(1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0),
        help="placement values for ranks 1..4 when --reward-shaping placement",
    )
```

- [ ] **Step 5: Thread into config and buffer construction**

Where `DiscreteIQLConfig(...)` is built (near line 198), pass:

```python
        reward_shaping=args.reward_shaping,
        placement_values=tuple(args.placement_values),
```

In `load_iql_replay_buffer` (signature near line 405), add parameters `reward_shaping: str = "raw"` and `placement_values: tuple = (1.0, 1.0 / 3.0, -1.0 / 3.0, -1.0)`, and set them on each value-bearing buffer at construction. For every `ArrayReplayBuffer(arrays=arrays, indices=...)` and `ReplayBuffer(...)` built in the **main/auxiliary value path** (the `--data` sources, NOT the `--pairwise-data` zero-weight buffer near line 524), pass `reward_shaping=reward_shaping, placement_values=placement_values`. For `ReplayBuffer.extend` path, set the two attributes on the instance before `extend` (e.g. `buffer.reward_shaping = reward_shaping`). Then update the call site (near line 139) to forward `reward_shaping=args.reward_shaping, placement_values=tuple(args.placement_values)`.

Leave the `--pairwise-data` buffer at default `raw` (its returns carry zero IQL sample weight, so shaping is irrelevant there; keep it untouched to avoid confusion).

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_iql -k placement -v`
Expected: PASS.

- [ ] **Step 7: Run the full IQL test module**

Run: `uv run --project ai python -m unittest fh_mahjong_ai.tests.test_iql -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add ai/src/fh_mahjong_ai/config.py ai/src/fh_mahjong_ai/scripts/train_iql.py ai/tests/test_iql.py
git commit -m "feat(iql): --reward-shaping placement flag wired through config and buffers"
```

### Task 9: Full test suite gate

**Files:** none (verification only)

- [ ] **Step 1: Run the whole Python suite**

Run: `uv run --project ai python -m unittest discover -s ai/tests -v`
Expected: all PASS.

- [ ] **Step 2: Run Go tests (no Go code changed, but confirm no accidental breakage)**

Run: `go test ./...`
Expected: all PASS.

### Task 10: Train + evaluate placement-shaped IQL against the Phase-2 baseline

**Files:**
- Artifacts only
- Modify (append): `docs/rl-papers/chongci-rl-experiment-progress.md`; possibly `ai/checkpoints/best-checkpoints.json`
- Modify: `docs/rl-papers/implementation-takeaways.md` and `docs/rl-papers/roadmap-and-development-plan.md` if the result affects general guidance

- [ ] **Step 1: Train the shaped variant on identical Phase-2 data**

Same `--data` inputs, same hyperparameters as Task 4, adding only the shaping flag:

```bash
uv run --project ai fh-mj-train-iql \
  --match-mode chongci \
  --data .../selfplay-shards-a --data .../selfplay-shards-b --data .../selfplay-shards-c \
  --data .../existing-heuristic-shards \
  --epochs 6 --batch-size 256 --lr 1e-4 \
  --reward-shaping placement \
  --checkpoint-dir /root/fh-mahjong-runs/chongci-scale-<date>/iql-placement \
  --mlflow
```

- [ ] **Step 2: Evaluate on the identical fixed CI gate from Task 5**

Same seeds, duplicate seats, Chongci mode. Produce `eval-placement.json`.

- [ ] **Step 3: Compare placement vs Phase-2 baseline using the CI rule**

Promote the placement variant only if, on identical seeds: `mean_reward` improves with non-overlapping/CI-separated margin (`candidate.mean_reward - candidate.mean_reward_ci95 ≥ baseline.mean_reward`), `large_loss_rate` does not regress, and `positive_reward_rate` does not regress materially. Placement shaping is expected to trade a little raw mean for better tail/rank behavior — judge on all three metrics, not mean alone.

- [ ] **Step 4: Record the experiment** in `chongci-rl-experiment-progress.md` with the full metrics table (including `mean_reward_ci95` and `large_loss_rate` for baseline vs placement). Decision: promoted / rejected / inconclusive.

- [ ] **Step 5: Update registry and roadmap if promoted**

If promoted, update `ai/checkpoints/best-checkpoints.json` `current_chongci` metadata, and add a one-line note to `docs/rl-papers/implementation-takeaways.md` (reward design section) recording that placement-aware shaping is now the Chongci default. Do not commit `.pt` binaries.

- [ ] **Step 6: Commit**

```bash
git add docs/rl-papers/chongci-rl-experiment-progress.md ai/checkpoints/best-checkpoints.json docs/rl-papers/implementation-takeaways.md docs/rl-papers/roadmap-and-development-plan.md
git commit -m "docs(rl): placement-aware reward shaping experiment result"
```

---

## Self-Review Notes

- **Spec coverage:** larger self-play data (Phase 2), placement-aware reward/value prediction (Phase 3, strong rank-based version), conservative Q/value updates (unchanged default — explicitly noted, no task needed), eval rigor with CIs (Phase 1, prerequisite), sequenced attribution (STOP checkpoint between phases). All covered.
- **No Go changes:** placement shaping reuses stored per-seat `terminal_rewards`; verified ranking by net delta equals ranking by final Chongci score (all seats share the same starting score).
- **Type consistency:** `placement_shaped_returns(terminal_rewards, placement_values)` is the single helper, called identically in both buffers; config/CLI field names `reward_shaping` and `placement_values` match across `config.py`, `buffer.py`, and `train_iql.py`.
- **Eval keys:** `sem`/`ci95` added in `reward_summary`; `mean_reward_sem`/`mean_reward_ci95` exposed in both duplicate-seat report dicts; the promotion rules in Tasks 5 and 10 consume exactly those keys.
