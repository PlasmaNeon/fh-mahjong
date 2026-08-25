# Placement-Reshape Stage 0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land every gauntleted code change and measurement that the spec's Stage 0 (as amended by Amendment 1) requires before the placement-reshape training lap may start.

**Architecture:** A new pure module `placement_bonus.py` owns the registered utility vector, exact-standings reconstruction, tie-averaged utilities, and the λ-calibration / return-scale-gate arithmetic. `train_b2b.collect_b2b_rollouts` gains an optional terminal bonus (attached to each seat's own last row, fail-closed on any incomplete match) plus seed-keyed match telemetry on `RolloutBatch`; the trainer, resume echo, checkpoint metadata, and collect-bench digest learn the new fields. `evaluate.py` gains match-level rank shares, 4th-place rate, the asymmetric secondary utility, per-episode large-loss arrays and clustered versions of all three; `fh-mj-compare` pairs them. Box-side tasks (archive read, calibration run, positive-λ digest parity) close Stage 0 and produce Amendment 2.

**Tech Stack:** Python 3.12 via `uv run --project ai`, numpy, PyTorch, pytest; Go c-shared bridge (`go build -buildmode=c-shared -o build/libfh_mahjong_bridge.dylib ./cmd/rlbridge`) for integration tests.

**Spec:** `../specs/2026-08-21-placement-reshape-design.md` (read "Design", "Stage 0", and "Amendment 1" in full before starting any task).

## Global Constraints

- `v = (0.8601670494, 0.3541864321, -0.0505980617, -1.1637554197)` — registered to full precision, never rescaled.
- `λ = 0.5 · σ_R / σ_V`, `ddof=0`, over exactly 320 matches / 1280 seat-match records; `R` = dense rewards credited to the seat's PPO trajectory (NOT `match_net`); `V` = `v(rank)` on full reset-inclusive standings with averaged ties. λ is frozen once; never lowered post hoc.
- Scale gates on the identical frozen batch + cloned anchor: shaped/raw return RMS ≤ 1.35; shaped/raw |return| p99 ≤ 1.50; shaped/raw initial critic MSE ≤ 2.00; everything finite.
- Bonus attaches to **each seat's own last recorded row**; `dones` unchanged; per-match bonus sum = 0 within 1e-6 incl. ties; reward tensors otherwise byte-identical; λ=0 reproduces the champion digest.
- Fail closed **before GAE/update** on: truncation, zero-decision seat, reset-terminal match, non-four-seat match. No "2% truncation" tolerance.
- Utilities rank exact **integer** final scores including busted seats; never use `rank_labels`.
- Eval: 4th-share is match-level from final scores, ties fractional, truncation = full 4th occupancy. Deal-in = all-hand `hand_stats.deal_in_rate`. Ragged/missing clustered arrays are errors.
- Resume echo: new `PPOConfig` fields are **rejected on change** (default behavior) and whitelisted as legacy additions.
- All Python via `uv run --project ai ...`. Run `uv run --project ai python -m pytest ai/tests -q` before every commit in this plan; `gofmt -l . && go vet ./... && go test ./...` are untouched (no Go changes) but run once at the end.
- New markdown docs are named `yyyymmdd-<summary>.md`.

---

## File map

| File | Responsibility |
|---|---|
| Create `ai/src/fh_mahjong_ai/placement_bonus.py` | Registered vector, `exact_final_scores`, `placement_utilities` (tie-averaged), `rank_occupancy` (fractional shares), `calibrate_lambda`, `apply_terminal_bonus`, `return_scale_gates` |
| Create `ai/tests/test_placement_bonus.py` | Pure-function tests incl. the busted-tie matrix |
| Modify `ai/src/fh_mahjong_ai/ppo.py` | `PPOConfig` bonus fields; `RolloutBatch.match_telemetry`; concat merges telemetry |
| Modify `ai/src/fh_mahjong_ai/train_b2b.py` | Bonus attach + fail-closed in `collect_b2b_rollouts`; pre-update guard in the train loop; checkpoint metadata |
| Modify `ai/src/fh_mahjong_ai/train_state.py` | Legacy-echo whitelist for the new fields |
| Modify `ai/src/fh_mahjong_ai/scripts/train_b2b.py`, `scripts/collect_bench.py` | Shared CLI args; digest covers telemetry |
| Create `ai/src/fh_mahjong_ai/scripts/placement_calibrate.py` | `fh-mj-placement-calibrate`: 320-match collection → λ, σ, corr, scale gates, JSON report |
| Modify `ai/src/fh_mahjong_ai/evaluate.py` | Per-episode tail arrays, rank shares, clustered tail stats, fail-closed ragged check, rank-parity check |
| Modify `ai/src/fh_mahjong_ai/scripts/compare_reports.py` | Pair 4th-share / large-loss / training-utility; deal-in from hand_stats |
| Modify tests `test_b2b_training.py`, `test_b2b_resume.py`, `test_collect_bench.py`, `test_evaluate.py`, `test_evaluate_clustered.py`, `test_compare_reports.py` | As listed per task |
| Modify `ai/CLAUDE.md`, `ai/pyproject.toml` | Docs + entry point |

---

### Task 1: `placement_bonus.py` — utilities, exact standings, rank occupancy

**Files:**
- Create: `ai/src/fh_mahjong_ai/placement_bonus.py`
- Test: `ai/tests/test_placement_bonus.py`

**Interfaces:**
- Produces:
  - `PLACEMENT_RESHAPE_VALUES: tuple[float, float, float, float]`
  - `exact_final_scores(match_net: Sequence[float], starting_score: float) -> list[int]` — `starting_score + round(net*1000)` per seat, matching `train_b2b.py:621`.
  - `placement_utilities(final_scores: Sequence[float], values=PLACEMENT_RESHAPE_VALUES) -> np.ndarray[4]` — descending rank, tied scores average the utilities of the slots they jointly occupy.
  - `rank_occupancy(final_scores: Sequence[float]) -> np.ndarray[(4,4)]` — row = seat, col = rank slot 0..3, fractional for ties, rows sum to 1.

- [ ] **Step 1: Write the failing tests**

```python
# ai/tests/test_placement_bonus.py
import numpy as np
import pytest

from fh_mahjong_ai.placement_bonus import (
    PLACEMENT_RESHAPE_VALUES, exact_final_scores, placement_utilities, rank_occupancy,
)

V = PLACEMENT_RESHAPE_VALUES


def test_registered_vector_is_centered_and_rms_matched():
    v = np.asarray(V, dtype=np.float64)
    assert abs(v.mean()) < 1e-9
    canonical_rms = np.sqrt(np.mean(np.square([1.0, 1/3, -1/3, -1.0])))
    assert abs(np.sqrt(np.mean(v**2)) - canonical_rms) < 1e-9
    # shape of (10,5,1,-10) after centering: differences preserved up to one scale
    raw = np.asarray([10.0, 5.0, 1.0, -10.0]); raw = raw - raw.mean()
    assert np.allclose(v / raw, (v / raw)[0])


def test_exact_final_scores_rounds_reward_scale_to_points():
    assert exact_final_scores([1.5, 1.0, -2.5, 0.0], 2000.0) == [3500, 3000, -500, 2000]
    # float32 drift well below half a point must not flip
    assert exact_final_scores([1.4999996, 0, 0, 0], 2000.0)[0] == 3500


def test_utilities_distinct_scores_follow_rank():
    u = placement_utilities([3500, 3000, 2000, -500])
    assert np.allclose(u, V)
    assert abs(u.sum()) < 1e-9


@pytest.mark.parametrize("scores,expected", [
    # two tied leaders share slots 0,1
    ([3000, 3000, 2000, 1000], [(V[0]+V[1])/2, (V[0]+V[1])/2, V[2], V[3]]),
    # two distinct busted seats: still ranked by exact score
    ([3000, 2000, -100, -500], [V[0], V[1], V[2], V[3]]),
    # two tied busted seats share slots 2,3
    ([3000, 2000, -500, -500], [V[0], V[1], (V[2]+V[3])/2, (V[2]+V[3])/2]),
    # three busted with a tie among two of them
    ([4000, -200, -200, -900], [V[0], (V[1]+V[2])/2, (V[1]+V[2])/2, V[3]]),
    # all four tied
    ([2000, 2000, 2000, 2000], [0.0, 0.0, 0.0, 0.0]),
    # three-way tie at the bottom
    ([5000, 1000, 1000, 1000], [V[0]] + [(V[1]+V[2]+V[3])/3]*3),
])
def test_utilities_tie_matrix(scores, expected):
    u = placement_utilities(scores)
    assert np.allclose(u, expected)
    assert abs(u.sum()) < 1e-9


def test_rank_occupancy_fractional_ties():
    occ = rank_occupancy([3000, 3000, 2000, 1000])
    assert np.allclose(occ[0], [0.5, 0.5, 0, 0])
    assert np.allclose(occ[1], [0.5, 0.5, 0, 0])
    assert np.allclose(occ[2], [0, 0, 1, 0])
    assert np.allclose(occ[3], [0, 0, 0, 1])
    assert np.allclose(occ.sum(axis=1), 1.0)
    assert np.allclose(occ.sum(axis=0), 1.0)


def test_rank_occupancy_all_tied():
    assert np.allclose(rank_occupancy([1, 1, 1, 1]), 0.25)


def test_utilities_reject_wrong_seat_count():
    with pytest.raises(ValueError):
        placement_utilities([1, 2, 3])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_placement_bonus.py -q`
Expected: FAIL with `ModuleNotFoundError: fh_mahjong_ai.placement_bonus`

- [ ] **Step 3: Implement**

```python
# ai/src/fh_mahjong_ai/placement_bonus.py
"""Placement-reshape experiment (spec 2026-08-21): the registered asymmetric
terminal placement utility and the exact-standings helpers shared by the B2b
collector (training bonus), the calibration script, and the evaluator.

Everything here is pure numpy on final scores — no bridge, no model — so the
tie/bust semantics are testable exhaustively and identical on both sides.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .data import placement_shaped_returns

# (10, 5, 1, -10) mean-subtracted and RMS-matched to the canonical eval vector
# (1, 1/3, -1/3, -1). Registered to full precision; never rescale this — any
# rescaling is cancelled by an inverse rescaling of lambda (spec, Design).
PLACEMENT_RESHAPE_VALUES: tuple[float, float, float, float] = (
    0.8601670494, 0.3541864321, -0.0505980617, -1.1637554197,
)

NUM_SEATS = 4


def exact_final_scores(match_net: Sequence[float], starting_score: float) -> list[int]:
    """Integer final scores from reward-scale (score/1000) per-seat nets — the
    same ×1000-and-round reconstruction train_b2b uses for hindsight labels,
    so utilities and labels can never disagree on a tie or a bust."""
    net = np.asarray(match_net, dtype=np.float64)
    if net.shape != (NUM_SEATS,):
        raise ValueError(f"match_net must have {NUM_SEATS} seats, got shape {net.shape}")
    return [int(round(starting_score + round(float(n) * 1000.0))) for n in net]


def placement_utilities(final_scores: Sequence[float],
                        values: Sequence[float] = PLACEMENT_RESHAPE_VALUES) -> np.ndarray:
    """Per-seat utility from final standings: descending score → values[rank];
    tied seats (busted or not) average the utilities of the slots they share.
    Busted seats are ranked by their exact score like everyone else (the aux
    `rank_labels` class 4 is NOT a 4th-place utility)."""
    scores = np.asarray(final_scores, dtype=np.float64)
    if scores.shape != (NUM_SEATS,):
        raise ValueError(f"final_scores must have {NUM_SEATS} seats, got shape {scores.shape}")
    return placement_shaped_returns(scores[None, :].astype(np.float32),
                                    tuple(float(v) for v in values))[0].astype(np.float64)


def rank_occupancy(final_scores: Sequence[float]) -> np.ndarray:
    """[seat, rank-slot] fractional occupancy: a seat tied with k-1 others over
    slots s..s+k-1 occupies each of them 1/k. Rows and columns sum to 1."""
    scores = np.asarray(final_scores, dtype=np.float64)
    if scores.shape != (NUM_SEATS,):
        raise ValueError(f"final_scores must have {NUM_SEATS} seats, got shape {scores.shape}")
    occ = np.zeros((NUM_SEATS, NUM_SEATS), dtype=np.float64)
    order = np.argsort(-scores, kind="stable")
    slot = 0
    while slot < NUM_SEATS:
        tied = [order[slot]]
        j = slot + 1
        while j < NUM_SEATS and scores[order[j]] == scores[order[slot]]:
            tied.append(order[j]); j += 1
        share = 1.0 / len(tied)
        for seat in tied:
            occ[seat, slot:j] = share
        slot = j
    return occ
```

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_placement_bonus.py -q`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/placement_bonus.py ai/tests/test_placement_bonus.py
git commit -m "feat(ai): placement_bonus — registered asymmetric utility, exact standings, rank occupancy"
```

---

### Task 2: Config, telemetry field, concat, and digest

**Files:**
- Modify: `ai/src/fh_mahjong_ai/ppo.py` (`PPOConfig` ~line 156; `RolloutBatch` ~line 165; `concat_rollout_batches` ~line 210–245)
- Modify: `ai/src/fh_mahjong_ai/scripts/collect_bench.py` (`_ROLLOUT_DIGEST_ARRAY_FIELDS` ~line 73; `_digest_batch` ~line 111)
- Test: `ai/tests/test_b2b_ppo.py`, `ai/tests/test_collect_bench.py`

**Interfaces:**
- Produces: `PPOConfig.placement_bonus_values: Optional[tuple] = None`, `PPOConfig.placement_bonus_lambda: float = 0.0`, `PPOConfig.placement_bonus_calibration_digest: str = ""`; `RolloutBatch.match_telemetry: list[dict] | None = None` where each dict is `{"seed": int, "final_scores": [4 ints], "trajectory_returns": [4 floats], "utilities": [4 floats], "bonus": [4 floats], "tie_groups": int, "busts": int}`.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_b2b_ppo.py
def test_concat_merges_match_telemetry_in_order():
    a = _batch(3); b = _batch(2)
    a.match_telemetry = [{"seed": 1}, {"seed": 2}]
    b.match_telemetry = [{"seed": 3}]
    out = concat_rollout_batches([a, b])
    assert [t["seed"] for t in out.match_telemetry] == [1, 2, 3]


def test_concat_rejects_mixed_telemetry_presence():
    a = _batch(3); b = _batch(2)
    a.match_telemetry = [{"seed": 1}]
    with pytest.raises(ValueError, match="match_telemetry"):
        concat_rollout_batches([a, b])


def test_ppo_config_bonus_defaults_off():
    cfg = PPOConfig()
    assert cfg.placement_bonus_values is None
    assert cfg.placement_bonus_lambda == 0.0
    assert cfg.placement_bonus_calibration_digest == ""
```

```python
# append to ai/tests/test_collect_bench.py
def test_digest_covers_match_telemetry():
    from fh_mahjong_ai.scripts.collect_bench import _digest_batch
    from fh_mahjong_ai.ppo import RolloutBatch
    import numpy as np
    def mk(tel):
        z = np.zeros((2, 1), dtype=np.float32)
        return RolloutBatch(planes=z, scalars=z, action_mask=z.astype(np.int8),
                            actions=np.zeros(2, dtype=np.int64), old_logprobs=z[:, 0],
                            values=z[:, 0], rewards=z[:, 0], dones=np.array([0, 1], np.float32),
                            match_telemetry=tel)
    d0 = _digest_batch(0, 1, mk(None))
    d1 = _digest_batch(0, 1, mk([{"seed": 0, "bonus": [0.1, 0, 0, -0.1]}]))
    d2 = _digest_batch(0, 1, mk([{"seed": 0, "bonus": [0.2, 0, 0, -0.2]}]))
    assert len({d0, d1, d2}) == 3
```

(`concat_rollout_batches`, `PPOConfig` and `pytest` are already imported at the top of `test_b2b_ppo.py`; add `from fh_mahjong_ai.ppo import PPOConfig` if not.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_ppo.py ai/tests/test_collect_bench.py -q -k "telemetry or bonus_defaults"`
Expected: FAIL (`TypeError: unexpected keyword 'match_telemetry'` / AttributeError / stale-digest RuntimeError)

- [ ] **Step 3: Implement**

In `PPOConfig`, after `grp_placement_values`:
```python
    # Placement-reshape experiment (spec 2026-08-21, Option A): additive
    # terminal utility lambda * values[rank] on each seat's final recorded
    # row in collect_b2b_rollouts. values=None disables it entirely (the
    # champion recipe). When enabled, collection fails CLOSED on any match
    # without a complete four-seat terminal standing. The calibration digest
    # pins which Stage-0 collection produced lambda. All three are recipe
    # fields: the resume echo rejects any change.
    placement_bonus_values: Optional[tuple] = None
    placement_bonus_lambda: float = 0.0
    placement_bonus_calibration_digest: str = ""
```

In `RolloutBatch`, after `rank_labels`:
```python
    # Seed-keyed match-level telemetry (NOT row-aligned; one dict per match,
    # in collection order). Carried separately from the row arrays so it can
    # never misalign them; covered by the collect-bench digest.
    match_telemetry: list | None = None
```

In `concat_rollout_batches`, after the optional-field loop and before `result = RolloutBatch(...)`:
```python
    present = [b.match_telemetry is not None for b in nonempty]
    if all(present):
        fields["match_telemetry"] = [t for b in nonempty for t in b.match_telemetry]
    elif any(present):
        raise ValueError("concat_rollout_batches: 'match_telemetry' is present in some batches but not others")
    else:
        fields["match_telemetry"] = None
```

In `collect_bench.py`, `_digest_batch`: change `expected_fields = set(_ROLLOUT_DIGEST_ARRAY_FIELDS) | {"truncated_matches"}` to `| {"truncated_matches", "match_telemetry"}` and, after hashing `truncated_matches`, add:
```python
    tel = batch.match_telemetry
    payload = json.dumps({"field": "match_telemetry", "present": tel is not None,
                          "value": tel}, sort_keys=True, separators=(",", ":")).encode()
    _update_length_prefixed(h, payload)
```

- [ ] **Step 4: Run the two test files fully**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_ppo.py ai/tests/test_collect_bench.py ai/tests/test_collect_profile.py -q`
Expected: PASS (existing digest-parity tests still pass because telemetry is None for both sides).

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/ppo.py ai/src/fh_mahjong_ai/scripts/collect_bench.py ai/tests/test_b2b_ppo.py ai/tests/test_collect_bench.py
git commit -m "feat(ppo): placement-bonus config fields, seed-keyed match telemetry, digest coverage"
```

---

### Task 3: Terminal bonus + fail-closed collection in `collect_b2b_rollouts`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py:536–645` (the per-match loop)
- Test: `ai/tests/test_b2b_training.py`

**Interfaces:**
- Consumes: Task 1 (`exact_final_scores`, `placement_utilities`, `rank_occupancy`), Task 2 (config fields, `match_telemetry`).
- Produces: `collect_b2b_rollouts` always fills `match_telemetry` (bonus on or off); when `config.placement_bonus_values is not None` it adds `lambda*utility[k]` to `seat_rewards[k][-1]` and raises `RuntimeError` on truncation / reset-terminal / any seat with zero decisions.

- [ ] **Step 1: Write failing tests** (Go bridge; these run against `build/libfh_mahjong_bridge.dylib`)

```python
# append to ai/tests/test_b2b_training.py
import numpy as np
import pytest
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.ppo import PPOConfig
from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES, placement_utilities
from fh_mahjong_ai.train_b2b import collect_b2b_rollouts

_GO_ENV = dict(bridge_kind="go", event_history_window=8, oracle_observation=True,
               max_steps_per_episode=4000)


def _go_collect(lam, values, matches=2, seed=4242):
    env = EnvConfig(**_GO_ENV)
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=matches, max_steps_per_episode=4000,
                    match_mode="chongci", placement_bonus_values=values,
                    placement_bonus_lambda=lam)
    return collect_b2b_rollouts(env, model, cfg, base_seed=seed)


def _segments(batch):
    """Row index of each done=1, i.e. each seat-block's last row, in order."""
    return np.flatnonzero(batch.dones == 1.0)


def test_bonus_off_is_byte_identical_and_has_telemetry():
    a = _go_collect(0.0, None)
    b = _go_collect(0.0, None)
    assert np.array_equal(a.rewards, b.rewards)
    assert a.match_telemetry is not None and len(a.match_telemetry) == 2
    t = a.match_telemetry[0]
    assert set(t) >= {"seed", "final_scores", "trajectory_returns", "utilities", "bonus", "tie_groups", "busts"}
    assert t["seed"] == 4242 and np.allclose(t["bonus"], 0.0)


def test_bonus_attaches_once_per_seat_on_own_last_row_and_sums_to_zero():
    off = _go_collect(0.0, None)
    on = _go_collect(0.7, PLACEMENT_RESHAPE_VALUES)
    assert off.rewards.shape == on.rewards.shape
    assert np.array_equal(off.dones, on.dones)
    diff = on.rewards - off.rewards
    ends = _segments(off)
    # every non-terminal row untouched
    mask = np.ones_like(diff, dtype=bool); mask[ends] = False
    assert np.array_equal(diff[mask], np.zeros(mask.sum(), np.float32))
    # terminal rows carry exactly lambda*utility, in seat order per match
    expected = np.concatenate([0.7 * placement_utilities(t["final_scores"]) for t in on.match_telemetry])
    assert np.allclose(diff[ends], expected.astype(np.float32), atol=1e-6)
    for t in on.match_telemetry:
        assert abs(sum(t["bonus"])) < 1e-6
        assert np.allclose(t["bonus"], 0.7 * np.asarray(t["utilities"]))
    # everything else byte-identical
    for name in ("planes", "scalars", "action_mask", "actions", "old_logprobs", "values",
                 "events", "event_lengths", "dealin_labels", "rank_labels"):
        assert np.array_equal(getattr(off, name), getattr(on, name)), name


def test_bonus_fails_closed_on_truncation():
    env = EnvConfig(**{**_GO_ENV, "max_steps_per_episode": 8})
    model = PolicyValueNet(EnvConfig(bridge_kind="go"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=8,
                    match_mode="chongci", placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                    placement_bonus_lambda=0.5)
    with pytest.raises(RuntimeError, match="placement bonus.*truncat"):
        collect_b2b_rollouts(env, model, cfg, base_seed=1)
```

Also a pure test of the zero-decision guard via the mock bridge in classic mode (mock never truncates, but a seat may have zero decisions at tiny step caps — assert the guard message when it does, otherwise skip):

```python
def test_bonus_fails_closed_on_zero_decision_seat_or_passes():
    env = EnvConfig(bridge_kind="mock", event_history_window=8, oracle_observation=True,
                    max_steps_per_episode=3)
    model = PolicyValueNet(EnvConfig(bridge_kind="mock"),
                           ModelConfig(**SMALL_MODEL, event_window=8,
                                       privileged_critic=True, aux_heads=True))
    cfg = PPOConfig(device="cpu", matches_per_iter=1, max_steps_per_episode=3,
                    match_mode="classic", placement_bonus_values=PLACEMENT_RESHAPE_VALUES,
                    placement_bonus_lambda=0.5)
    try:
        batch = collect_b2b_rollouts(env, model, cfg, base_seed=0)
    except RuntimeError as e:
        assert "placement bonus" in str(e)
        return
    assert int((batch.dones == 1).sum()) == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_training.py -q -k bonus`
Expected: FAIL (`match_telemetry` is None / no RuntimeError / diff nonzero)

- [ ] **Step 3: Implement** in `collect_b2b_rollouts`

Add imports at top of `train_b2b.py`:
```python
from .placement_bonus import exact_final_scores, placement_utilities, rank_occupancy
```

Before the `try:` (after `outcomes_seen = 0`):
```python
    bonus_values = config.placement_bonus_values
    bonus_on = bonus_values is not None
    bonus_lambda = float(config.placement_bonus_lambda) if bonus_on else 0.0
    match_telemetry: list[dict] = []
```

Replace the reset-terminal `continue` (line ~541):
```python
            if reset_result is not None and (reset_result.terminated or reset_result.truncated):
                if bonus_on:
                    raise RuntimeError(
                        f"placement bonus: match seed {base_seed + m} ended at reset "
                        "(no four-seat terminal standing) — fail closed")
                continue
```

After `final_scores = {...}` (line ~621) and before `rows`, insert:
```python
            int_scores = exact_final_scores(match_net, starting_score)
            assert [starting_score + round(float(match_net[k]) * 1000.0) for k in range(4)] == int_scores
            if bonus_on:
                if is_truncated:
                    raise RuntimeError(
                        f"placement bonus: match seed {base_seed + m} was truncated — no "
                        "terminal rank exists; fail closed (spec Amendment 1 item 4)")
                empty = [k for k in range(4) if not seat_rewards[k]]
                if empty:
                    raise RuntimeError(
                        f"placement bonus: match seed {base_seed + m} has zero-decision "
                        f"seat(s) {empty}; fail closed")
            utilities = placement_utilities(int_scores, bonus_values) if bonus_on \
                else placement_utilities(int_scores)
            bonus = bonus_lambda * utilities if bonus_on else np.zeros(4)
            if bonus_on:
                if abs(float(bonus.sum())) > 1e-6:
                    raise RuntimeError(f"placement bonus: per-match bonus sum {bonus.sum()} != 0")
                for k in range(4):
                    seat_rewards[k][-1] += float(bonus[k])
            occ = rank_occupancy(int_scores)
            match_telemetry.append({
                "seed": int(base_seed + m),
                "truncated": bool(is_truncated),
                "final_scores": [int(s) for s in int_scores],
                "trajectory_returns": [float(sum(seat_rewards[k])) - float(bonus[k]) for k in range(4)],
                "utilities": [float(u) for u in utilities],
                "bonus": [float(b) for b in bonus],
                "rank_occupancy": occ.tolist(),
                "tie_groups": int(4 - len(set(int_scores))),
                "busts": int(sum(1 for s in int_scores if s <= bust_threshold)),
            })
```
(The `assert` pins the new helper to the existing reconstruction; keep `final_scores` as-is for `_assemble_hindsight_labels`. `trajectory_returns` is the PPO-credited dense return *excluding* the bonus — this is Amendment 1's `R`.)

In the `return RolloutBatch(...)`, add `match_telemetry=match_telemetry,`.

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_training.py ai/tests/test_b2b_resume.py ai/tests/test_collect_profile.py -q`
Expected: PASS. (If `test_bonus_fails_closed_on_truncation` passes without truncating at 8 steps, lower `max_steps_per_episode` to 4; a chongci match cannot complete in 4 env steps.)

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/train_b2b.py ai/tests/test_b2b_training.py
git commit -m "feat(b2b): additive terminal placement bonus on each seat's last row, fail-closed collection, match telemetry"
```

---

### Task 4: Trainer guard, checkpoint metadata, resume whitelist, CLI args

**Files:**
- Modify: `ai/src/fh_mahjong_ai/train_b2b.py:1425–1435` (before `compute_gae`) and the checkpoint `metadata={...}` block (~line 1503)
- Modify: `ai/src/fh_mahjong_ai/train_state.py:418` (`_LEGACY_ECHO_ADDITIONS["ppo_config"]`)
- Create: `ai/src/fh_mahjong_ai/placement_bonus_args.py`
- Modify: `ai/src/fh_mahjong_ai/scripts/train_b2b.py` (parser + `PPOConfig(...)` at line 168), `ai/src/fh_mahjong_ai/scripts/collect_bench.py` (its parser + PPOConfig construction)
- Test: `ai/tests/test_b2b_resume.py`, `ai/tests/test_b2b_training.py`

**Interfaces:**
- Produces: `add_placement_bonus_args(parser)`, `placement_bonus_kwargs(args) -> dict` (keys = the three PPOConfig field names). Checkpoint metadata gains `"objective": {"placement_bonus_values": list|None, "placement_bonus_lambda": float, "placement_bonus_calibration_digest": str}`.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_b2b_resume.py (same shape as test_resume_from_state_raises_on_different_lr)
def test_resume_rejects_changed_placement_bonus(tmp_path) -> None:
    from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
    env, model_config, champion_path, config_first = b2b_run_configs(tmp_path, iterations=2)
    checkpoint_dir = tmp_path / "ckpt"
    train_b2b(env, model_config, champion_path, checkpoint_dir, config_first,
             base_seed=5, train_state_every=2)
    state_path = checkpoint_dir / "train_state.pt"
    # The bonus fields are RECIPE, not operational: any change must be rejected.
    changed = replace(config_first, iterations=4,
                      placement_bonus_values=PLACEMENT_RESHAPE_VALUES, placement_bonus_lambda=0.3)
    with pytest.raises(ValueError, match="placement_bonus"):
        train_b2b(env, model_config, champion_path, checkpoint_dir, changed,
                 base_seed=5, resume_from_state=state_path)


def test_legacy_state_without_bonus_fields_normalizes() -> None:
    from fh_mahjong_ai.train_state import _LEGACY_ECHO_ADDITIONS
    assert {"placement_bonus_values", "placement_bonus_lambda",
            "placement_bonus_calibration_digest"} <= _LEGACY_ECHO_ADDITIONS["ppo_config"]
```
```python
# append to ai/tests/test_b2b_training.py
def test_checkpoint_metadata_records_objective(tmp_path):
    # Identical setup to test_train_b2b_two_iters_mock (copy its env/model/config
    # construction and train_b2b call verbatim, checkpoint_dir = tmp_path / "ckpt"), then:
    import torch
    payload = torch.load(tmp_path / "ckpt" / "iter_001.pt", map_location="cpu")
    obj = payload["metadata"]["objective"]
    assert obj == {"placement_bonus_values": None, "placement_bonus_lambda": 0.0,
                   "placement_bonus_calibration_digest": ""}


def test_cli_placement_bonus_args_roundtrip():
    import argparse
    from fh_mahjong_ai.placement_bonus_args import add_placement_bonus_args, placement_bonus_kwargs
    p = argparse.ArgumentParser(); add_placement_bonus_args(p)
    a = p.parse_args(["--placement-bonus-values", "0.86", "0.35", "-0.05", "-1.16",
                      "--placement-bonus-lambda", "0.42", "--placement-bonus-calibration-digest", "abc"])
    assert placement_bonus_kwargs(a) == {"placement_bonus_values": (0.86, 0.35, -0.05, -1.16),
                                         "placement_bonus_lambda": 0.42,
                                         "placement_bonus_calibration_digest": "abc"}
    assert placement_bonus_kwargs(p.parse_args([])) == {"placement_bonus_values": None,
                                                        "placement_bonus_lambda": 0.0,
                                                        "placement_bonus_calibration_digest": ""}
    with pytest.raises(SystemExit):
        p.parse_args(["--placement-bonus-lambda", "0.5"])  # lambda without values is an error
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_resume.py ai/tests/test_b2b_training.py -q -k "bonus or objective or legacy_state"`
Expected: FAIL

- [ ] **Step 3: Implement**

`ai/src/fh_mahjong_ai/placement_bonus_args.py`:
```python
"""Shared CLI surface for the placement-reshape terminal bonus (train_b2b,
collect_bench, placement_calibrate) so every tool builds the identical
PPOConfig fields."""
from __future__ import annotations
import argparse


def add_placement_bonus_args(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("placement bonus (spec 2026-08-21)")
    g.add_argument("--placement-bonus-values", type=float, nargs=4, default=None,
                   metavar="V", help="utility for ranks 1..4; omit to disable the bonus")
    g.add_argument("--placement-bonus-lambda", type=float, default=0.0,
                   help="frozen lambda from fh-mj-placement-calibrate (requires --placement-bonus-values)")
    g.add_argument("--placement-bonus-calibration-digest", type=str, default="",
                   help="digest of the Stage-0 calibration collection that produced lambda")


def placement_bonus_kwargs(args: argparse.Namespace) -> dict:
    values = args.placement_bonus_values
    lam = float(args.placement_bonus_lambda)
    if values is None and (lam != 0.0 or args.placement_bonus_calibration_digest):
        raise SystemExit("--placement-bonus-lambda/--placement-bonus-calibration-digest require --placement-bonus-values")
    return {
        "placement_bonus_values": tuple(float(v) for v in values) if values is not None else None,
        "placement_bonus_lambda": lam,
        "placement_bonus_calibration_digest": str(args.placement_bonus_calibration_digest),
    }
```

`scripts/train_b2b.py`: call `add_placement_bonus_args(p)` after the last `add_argument`; add `**placement_bonus_kwargs(args)` to the `PPOConfig(...)` call at line 168. Same two edits in `scripts/collect_bench.py` wherever it builds its `PPOConfig`.

`train_state.py` `_LEGACY_ECHO_ADDITIONS["ppo_config"]`: add
```python
        "placement_bonus_values",             # absent before placement-reshape Stage 0 (2026-08-22)
        "placement_bonus_lambda",             # idem
        "placement_bonus_calibration_digest", # idem
```
(Do NOT add them to `_RESUME_LOGGED_FIELDS` — they are recipe and must be rejected on change. Check that the echo serializer handles a `tuple`/`None` value; it already round-trips `grp_placement_values`, so it does.)

`train_b2b.py` train loop, immediately after the batch is collected and before `compute_gae` (line ~1431):
```python
                if config.placement_bonus_values is not None:
                    # Spec Amendment 1 item 4: the collector already raises on
                    # an incomplete match, but never let a truncated batch
                    # reach GAE/optimizer under this objective.
                    if int(batch.truncated_matches) != 0:
                        raise RuntimeError(
                            f"iter {iteration}: {batch.truncated_matches} truncated match(es) "
                            "with the placement bonus enabled — fail closed before update")
                    if batch.match_telemetry is None or len(batch.match_telemetry) != config.matches_per_iter:
                        raise RuntimeError(f"iter {iteration}: match telemetry missing or incomplete")
```
And add to `metrics` after the existing `rank_label_coverage` block:
```python
                if batch.match_telemetry:
                    bonus = np.asarray([t["bonus"] for t in batch.match_telemetry], dtype=np.float64)
                    occ = np.asarray([t["rank_occupancy"] for t in batch.match_telemetry], dtype=np.float64)
                    metrics["bonus_mean"] = float(bonus.mean())
                    metrics["bonus_rms"] = float(np.sqrt(np.mean(bonus**2)))
                    metrics["bonus_abs_p99"] = float(np.percentile(np.abs(bonus), 99))
                    metrics["tie_groups_total"] = int(sum(t["tie_groups"] for t in batch.match_telemetry))
                    metrics["busts_total"] = int(sum(t["busts"] for t in batch.match_telemetry))
                    # per-seat 4th-slot occupancy: seat-bias detector (self-play
                    # aggregate is mechanically ~0.25; only the SPREAD is informative)
                    for k in range(4):
                        metrics[f"seat{k}_fourth_occupancy"] = float(occ[:, k, 3].mean())
```
Checkpoint `metadata={...}` (line ~1503): add
```python
                        "objective": {
                            "placement_bonus_values": (list(config.placement_bonus_values)
                                                       if config.placement_bonus_values is not None else None),
                            "placement_bonus_lambda": float(config.placement_bonus_lambda),
                            "placement_bonus_calibration_digest": str(config.placement_bonus_calibration_digest),
                        },
```

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_b2b_resume.py ai/tests/test_b2b_training.py ai/tests/test_collect_bench.py ai/tests/test_train_state.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/placement_bonus_args.py ai/src/fh_mahjong_ai/train_b2b.py ai/src/fh_mahjong_ai/train_state.py ai/src/fh_mahjong_ai/scripts/train_b2b.py ai/src/fh_mahjong_ai/scripts/collect_bench.py ai/tests/test_b2b_resume.py ai/tests/test_b2b_training.py
git commit -m "feat(b2b): placement-bonus CLI, pre-update fail-closed guard, objective metadata, resume whitelist, telemetry metrics"
```

---

### Task 5: λ calibration and return-scale gates (`fh-mj-placement-calibrate`)

**Files:**
- Modify: `ai/src/fh_mahjong_ai/placement_bonus.py` (add `calibrate_lambda`, `apply_terminal_bonus`, `return_scale_gates`)
- Create: `ai/src/fh_mahjong_ai/scripts/placement_calibrate.py`
- Modify: `ai/pyproject.toml` (`fh-mj-placement-calibrate = "fh_mahjong_ai.scripts.placement_calibrate:main"`)
- Test: `ai/tests/test_placement_bonus.py`, `ai/tests/test_placement_calibrate.py`

**Interfaces:**
- `calibrate_lambda(telemetry: list[dict], values, k=0.5) -> dict` → `{"lambda", "sigma_R", "sigma_V", "corr_RV", "k", "num_matches", "num_records"}`; raises unless `num_matches == 320` unless `require_matches` is overridden (tests pass `require_matches=2`).
- `apply_terminal_bonus(rewards, dones, telemetry, values, lam) -> np.ndarray` — clone of `rewards` with `lam*utility` added at each seat's last row, using the `dones` segmentation and telemetry order (4 segments per match in seat order).
- `return_scale_gates(raw_returns, shaped_returns, values_pred) -> dict` with the three ratios, the per-gate pass flags, and `"all_pass"`.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_placement_bonus.py
from fh_mahjong_ai.placement_bonus import apply_terminal_bonus, calibrate_lambda, return_scale_gates


def _tel(seed, scores, rets):
    u = placement_utilities(scores)
    return {"seed": seed, "final_scores": scores, "trajectory_returns": rets,
            "utilities": u.tolist(), "bonus": [0.0]*4, "truncated": False,
            "rank_occupancy": rank_occupancy(scores).tolist(), "tie_groups": 0, "busts": 0}


def test_calibrate_lambda_matches_closed_form():
    tel = [_tel(0, [3500, 3000, 2000, -500], [1.5, 1.0, 0.0, -2.5]),
           _tel(1, [2100, 2000, 1900, 2000], [0.1, 0.0, -0.1, 0.0])]
    out = calibrate_lambda(tel, V, k=0.5, require_matches=2)
    R = np.asarray([t["trajectory_returns"] for t in tel]).ravel()
    Vv = np.asarray([t["utilities"] for t in tel]).ravel()
    assert out["lambda"] == pytest.approx(0.5 * R.std() / Vv.std())
    assert out["corr_RV"] == pytest.approx(np.corrcoef(R, Vv)[0, 1])
    assert out["num_records"] == 8


def test_calibrate_lambda_requires_exact_match_count():
    with pytest.raises(ValueError, match="320"):
        calibrate_lambda([_tel(0, [1, 2, 3, 4], [0, 0, 0, 1])], V)


def test_apply_terminal_bonus_hits_each_segment_end():
    rewards = np.zeros(10, np.float32)
    dones = np.zeros(10, np.float32); dones[[1, 4, 6, 9]] = 1.0   # 4 segments = 1 match
    tel = [_tel(0, [3500, 3000, 2000, -500], [0, 0, 0, 0])]
    out = apply_terminal_bonus(rewards, dones, tel, V, 2.0)
    assert np.allclose(out[[1, 4, 6, 9]], 2.0 * np.asarray(V))
    assert np.count_nonzero(out) == 4
    with pytest.raises(ValueError):
        apply_terminal_bonus(rewards, dones[:9], tel, V, 1.0)  # segment/telemetry mismatch


def test_return_scale_gates():
    raw = np.array([1.0, -1.0, 0.5, -0.5]); shaped = raw * 1.2; pred = np.zeros(4)
    g = return_scale_gates(raw, shaped, pred)
    assert g["rms_ratio"] == pytest.approx(1.2) and g["rms_pass"]
    assert g["p99_ratio"] == pytest.approx(1.2) and g["p99_pass"]
    assert g["critic_mse_ratio"] == pytest.approx(1.44) and g["critic_mse_pass"]
    assert g["all_pass"]
    assert not return_scale_gates(raw, raw * 1.5, pred)["all_pass"]
```

```python
# ai/tests/test_placement_calibrate.py
import json
from fh_mahjong_ai.config import EnvConfig, ModelConfig
from fh_mahjong_ai.model import PolicyValueNet
from fh_mahjong_ai.storage import save_checkpoint
from fh_mahjong_ai.placement_bonus import PLACEMENT_RESHAPE_VALUES
from fh_mahjong_ai.scripts.placement_calibrate import run_calibration
from tests.test_b2b_training import SMALL_MODEL   # same tiny net the b2b tests use


def test_run_calibration_mock_classic(tmp_path):
    # Raw 39ch champion exactly as test_b2b_training._champion builds it.
    env39 = EnvConfig(bridge_kind="mock")
    save_checkpoint(tmp_path / "champion.pt", PolicyValueNet(env39, ModelConfig(**SMALL_MODEL)))
    env = EnvConfig(bridge_kind="mock", match_mode="classic", event_history_window=8,
                    oracle_observation=True, max_steps_per_episode=64)
    mcfg = ModelConfig(**SMALL_MODEL, event_window=8, privileged_critic=True, aux_heads=True)
    out = tmp_path / "calib.json"
    report = run_calibration(env, mcfg, tmp_path / "champion.pt", output=out, matches=2,
                             require_matches=2, base_seed=720000, num_workers=1,
                             collect_dispatch_chunk=0, k=0.5, gamma=0.99, gae_lambda=0.95,
                             device="cpu")
    assert report["calibration"]["num_matches"] == 2 and report["calibration"]["num_records"] == 8
    assert report["gates"]["all_pass"] in (True, False)
    assert report["collection_digest"] and report["values"] == list(PLACEMENT_RESHAPE_VALUES)
    assert json.loads(out.read_text())["calibration"]["lambda"] == report["calibration"]["lambda"]
```
(If `tests` is not importable as a package, copy the `SMALL_MODEL` dict literal from `test_b2b_training.py` into this file instead.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_placement_bonus.py ai/tests/test_placement_calibrate.py -q`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement**

Append to `placement_bonus.py`:
```python
CALIBRATION_MATCHES = 320
K_REGISTERED = 0.5
GATE_RMS_MAX, GATE_P99_MAX, GATE_CRITIC_MSE_MAX = 1.35, 1.50, 2.00


def calibrate_lambda(telemetry: Sequence[dict], values: Sequence[float] = PLACEMENT_RESHAPE_VALUES,
                     k: float = K_REGISTERED, require_matches: int = CALIBRATION_MATCHES) -> dict:
    """lambda = k * sigma_R / sigma_V over all seat-match records (ddof=0).
    R = dense PPO-credited trajectory return (telemetry["trajectory_returns"]),
    V = registered utility on the full final standings."""
    if len(telemetry) != require_matches:
        raise ValueError(f"calibration requires exactly {require_matches} matches (got {len(telemetry)}); "
                         "spec registers 320")
    if any(t.get("truncated") for t in telemetry):
        raise ValueError("calibration collection contains a truncated match — fail closed")
    R = np.asarray([t["trajectory_returns"] for t in telemetry], dtype=np.float64).ravel()
    Vv = np.asarray([placement_utilities(t["final_scores"], values) for t in telemetry],
                    dtype=np.float64).ravel()
    sR, sV = float(R.std(ddof=0)), float(Vv.std(ddof=0))
    if not (np.isfinite(sR) and np.isfinite(sV)) or sR == 0.0 or sV == 0.0:
        raise ValueError(f"degenerate calibration: sigma_R={sR} sigma_V={sV}")
    return {"lambda": float(k * sR / sV), "sigma_R": sR, "sigma_V": sV,
            "corr_RV": float(np.corrcoef(R, Vv)[0, 1]), "k": float(k),
            "num_matches": len(telemetry), "num_records": int(R.size)}


def apply_terminal_bonus(rewards: np.ndarray, dones: np.ndarray, telemetry: Sequence[dict],
                         values: Sequence[float], lam: float) -> np.ndarray:
    """Return a copy of `rewards` with lam*utility added at every seat's last
    row. Segments (done=1) come 4 per match in seat order 0..3, matches in
    telemetry order — exactly collect_b2b_rollouts' layout."""
    ends = np.flatnonzero(np.asarray(dones) == 1.0)
    if ends.size != 4 * len(telemetry):
        raise ValueError(f"{ends.size} done rows but {len(telemetry)} matches (expected 4 per match)")
    out = np.array(rewards, dtype=np.float32, copy=True)
    for i, t in enumerate(telemetry):
        u = placement_utilities(t["final_scores"], values)
        for k in range(4):
            out[ends[4 * i + k]] += np.float32(lam * u[k])
    return out


def return_scale_gates(raw_returns: np.ndarray, shaped_returns: np.ndarray,
                       values_pred: np.ndarray) -> dict:
    raw = np.asarray(raw_returns, np.float64); shp = np.asarray(shaped_returns, np.float64)
    pred = np.asarray(values_pred, np.float64)
    rms = lambda x: float(np.sqrt(np.mean(x**2)))
    p99 = lambda x: float(np.percentile(np.abs(x), 99))
    mse = lambda x: float(np.mean((pred - x) ** 2))
    finite = bool(np.isfinite(raw).all() and np.isfinite(shp).all())
    g = {
        "rms_ratio": rms(shp) / rms(raw), "p99_ratio": p99(shp) / p99(raw),
        "critic_mse_ratio": mse(shp) / mse(raw), "finite": finite,
        "raw_return_rms": rms(raw), "shaped_return_rms": rms(shp),
        "raw_return_abs_p99": p99(raw), "shaped_return_abs_p99": p99(shp),
        "raw_critic_mse": mse(raw), "shaped_critic_mse": mse(shp),
    }
    g["rms_pass"] = g["rms_ratio"] <= GATE_RMS_MAX
    g["p99_pass"] = g["p99_ratio"] <= GATE_P99_MAX
    g["critic_mse_pass"] = g["critic_mse_ratio"] <= GATE_CRITIC_MSE_MAX
    g["all_pass"] = bool(finite and g["rms_pass"] and g["p99_pass"] and g["critic_mse_pass"])
    return g
```

`scripts/placement_calibrate.py` (mirror `collect_bench.py`'s model build and collector usage — reuse `_build_model`, `ParallelB2bCollector`, `_digest_batch` from it):
```python
"""fh-mj-placement-calibrate: Stage-0 lambda calibration + return-scale gates
for the placement-reshape experiment (spec 2026-08-21, Amendment 1 item 2).

Collects the registered calibration matches from the champion with the bonus
OFF, computes lambda = k*sigma_R/sigma_V from the match telemetry, then on the
IDENTICAL batch compares raw vs bonus-shaped GAE returns against the anchor's
own value predictions. Never adjusts lambda; prints/records pass/fail only.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
from ..config import EnvConfig
from ..model_config_args import add_model_config_args, model_config_from_args
from ..ppo import PPOConfig, compute_gae
from ..placement_bonus import (PLACEMENT_RESHAPE_VALUES, apply_terminal_bonus, calibrate_lambda,
                               return_scale_gates, CALIBRATION_MATCHES)
from ..train_b2b import ParallelB2bCollector, _b2b_model_env_config
from .collect_bench import _build_model, _digest_batch


def run_calibration(env_config: EnvConfig, model_config, champion: Path, *, output: Path,
                    matches: int, require_matches: int, base_seed: int, num_workers: int,
                    collect_dispatch_chunk: int, k: float, gamma: float, gae_lambda: float,
                    device: str) -> dict:
    model, model_config = _build_model(env_config, model_config, champion, 0, device)
    cfg = PPOConfig(device=device, matches_per_iter=matches, match_mode=env_config.match_mode,
                    max_steps_per_episode=env_config.max_steps_per_episode, num_workers=num_workers,
                    collect_dispatch_chunk=collect_dispatch_chunk, gamma=gamma,
                    gae_lambda=gae_lambda)   # bonus OFF: values=None
    collector = ParallelB2bCollector(env_config, model_config, cfg, num_workers)
    try:
        state = {k_: v.detach().cpu() for k_, v in model.state_dict().items()}
        batch = collector.collect(state, base_seed, matches)
    finally:
        collector.close()
    if int(batch.truncated_matches) != 0:
        raise SystemExit(f"calibration collection truncated {batch.truncated_matches} match(es) — fail closed")
    digest = _digest_batch(base_seed, matches, batch)
    calib = calibrate_lambda(batch.match_telemetry, PLACEMENT_RESHAPE_VALUES, k=k,
                             require_matches=require_matches)
    shaped_rewards = apply_terminal_bonus(batch.rewards, batch.dones, batch.match_telemetry,
                                          PLACEMENT_RESHAPE_VALUES, calib["lambda"])
    _, raw_ret = compute_gae(batch.rewards, batch.values, batch.dones, gamma, gae_lambda)
    _, shp_ret = compute_gae(shaped_rewards, batch.values, batch.dones, gamma, gae_lambda)
    gates = return_scale_gates(raw_ret, shp_ret, batch.values)
    bonus = np.asarray([t["utilities"] for t in batch.match_telemetry]) * calib["lambda"]
    report = {
        "values": list(PLACEMENT_RESHAPE_VALUES), "calibration": calib, "gates": gates,
        "collection_digest": digest, "base_seed": base_seed, "matches": matches,
        "gamma": gamma, "gae_lambda": gae_lambda, "champion": str(champion),
        "bonus_mean": float(bonus.mean()), "bonus_rms": float(np.sqrt(np.mean(bonus**2))),
        "bonus_abs_p99": float(np.percentile(np.abs(bonus), 99)),
        "fourth_place_bonus_over_sigma_R": float(calib["lambda"] * PLACEMENT_RESHAPE_VALUES[3] / calib["sigma_R"]),
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True))
    return report


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--champion", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--matches", type=int, default=CALIBRATION_MATCHES)
    p.add_argument("--require-matches", type=int, default=CALIBRATION_MATCHES)
    p.add_argument("--base-seed", type=int, default=720000)
    p.add_argument("--num-workers", type=int, default=1)
    p.add_argument("--collect-dispatch-chunk", type=int, default=0)
    p.add_argument("--k", type=float, default=0.5)
    p.add_argument("--gamma", type=float, default=0.99)
    p.add_argument("--gae-lambda", type=float, default=0.95)
    p.add_argument("--match-mode", choices=("classic", "chongci"), default="chongci")
    p.add_argument("--bridge-kind", choices=("go", "mock"), default="go")
    p.add_argument("--bridge-lib", type=str, default=None)
    p.add_argument("--device", type=str, default="cpu")
    p.add_argument("--event-window", type=int, default=128)
    p.add_argument("--max-steps-per-episode", type=int, default=4000)
    add_model_config_args(p)
    args = p.parse_args(argv)
    env_config = EnvConfig(bridge_kind=args.bridge_kind, bridge_library_path=args.bridge_lib,
                           match_mode=args.match_mode, max_steps_per_episode=args.max_steps_per_episode,
                           event_history_window=args.event_window, oracle_observation=True)
    model_config = model_config_from_args(args, event_window=args.event_window)
    report = run_calibration(env_config, model_config, args.champion, output=args.output,
                             matches=args.matches, require_matches=args.require_matches,
                             base_seed=args.base_seed, num_workers=args.num_workers,
                             collect_dispatch_chunk=args.collect_dispatch_chunk, k=args.k,
                             gamma=args.gamma, gae_lambda=args.gae_lambda, device=args.device)
    gates = report["gates"]
    print(json.dumps({k: report[k] for k in ("calibration", "gates")}, indent=2))
    if not gates["all_pass"]:
        raise SystemExit("return-scale gates FAILED — return to consultation; do not lower lambda")
```
(`ParallelB2bCollector.close()` exists at `train_b2b.py:834`. `_build_model(env, mcfg, champion, growth_blocks=0, device)` routes through `build_b2b_model`, i.e. the champion is a raw 39ch checkpoint.)

Add the entry point to `ai/pyproject.toml` under `[project.scripts]`.

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_placement_bonus.py ai/tests/test_placement_calibrate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/placement_bonus.py ai/src/fh_mahjong_ai/scripts/placement_calibrate.py ai/pyproject.toml ai/tests/test_placement_bonus.py ai/tests/test_placement_calibrate.py
git commit -m "feat(ai): fh-mj-placement-calibrate — lambda = k*sigma_R/sigma_V and return-scale gates on the frozen batch"
```

---

### Task 6: Evaluator tail metrics — rank shares, 4th-place rate, secondary utility, per-episode arrays, rank parity

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (`record_episode` ~line 730–790; per-seat report dict ~line 880–925)
- Test: `ai/tests/test_evaluate.py`

**Interfaces:**
- Produces per-seat report keys: `per_episode_fourth_share: list[float]`, `per_episode_large_loss: list[float]` (0/1), `per_episode_training_utility: list[float]`, `placement_rank_shares: [4 floats]` (learning seat's mean occupancy per slot), `fourth_place_rate: float`, `training_utility_mean: float`, `rank_parity_mismatches: int`.
- Helper in `placement_bonus.py`: `eval_episode_tail(net: np.ndarray[4], learning_seat: int, starting_score: float, truncated: bool) -> dict` with keys `fourth_share`, `utility`, `occupancy` (4,), `parity_ok`.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_placement_bonus.py
from fh_mahjong_ai.placement_bonus import eval_episode_tail


def test_eval_episode_tail_truncation_is_full_fourth():
    t = eval_episode_tail(np.array([1.0, 0, 0, -1.0]), 0, 2000.0, truncated=True)
    assert t["fourth_share"] == 1.0 and t["utility"] == V[3]
    assert np.allclose(t["occupancy"], [0, 0, 0, 1])


def test_eval_episode_tail_ties_fractional():
    t = eval_episode_tail(np.array([0.0, 0.0, 1.0, -1.0]), 0, 2000.0, truncated=False)
    assert t["fourth_share"] == 0.0 and np.allclose(t["occupancy"], [0, 0.5, 0.5, 0])
    assert t["utility"] == pytest.approx((V[1] + V[2]) / 2)
    assert t["parity_ok"]
```

```python
# append to ai/tests/test_evaluate.py — real Go bridge (build/libfh_mahjong_bridge.dylib must exist;
# several existing tests in this file already require it)
def test_seat_report_carries_tail_arrays():
    from fh_mahjong_ai.evaluate import evaluate_online
    model = PolicyValueNet(EnvConfig(), ModelConfig())
    report = evaluate_online(model=model, episodes=3, seeds=[910000, 910001, 910002],
                             bridge_kind="go", device="cpu", learning_seat=0, match_mode="chongci")
    n = report["episodes"]
    for key in ("per_episode_fourth_share", "per_episode_large_loss", "per_episode_training_utility"):
        assert len(report[key]) == n
    assert len(report["placement_rank_shares"]) == 4
    assert abs(sum(report["placement_rank_shares"]) - 1.0) < 1e-9
    assert 0.0 <= report["fourth_place_rate"] <= 1.0
    assert report["rank_parity_mismatches"] == 0
    assert report["fourth_place_rate"] == pytest.approx(np.mean(report["per_episode_fourth_share"]))
    assert report["large_loss_rate"] == pytest.approx(np.mean(report["per_episode_large_loss"]))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_placement_bonus.py ai/tests/test_evaluate.py -q -k "tail"`
Expected: FAIL

- [ ] **Step 3: Implement**

Append to `placement_bonus.py`:
```python
def eval_episode_tail(net: np.ndarray, learning_seat: int, starting_score: float,
                      truncated: bool, values: Sequence[float] = PLACEMENT_RESHAPE_VALUES) -> dict:
    """Evaluator-side tail metrics for one episode. Truncation = full 4th-place
    occupancy and the worst utility (the objective's terminal rank does not
    exist; omitting it would censor). `parity_ok` checks that ranking the
    float accumulated net agrees with ranking the exact integer standings."""
    if truncated:
        return {"fourth_share": 1.0, "utility": float(values[3]),
                "occupancy": np.array([0.0, 0.0, 0.0, 1.0]), "parity_ok": True}
    ints = exact_final_scores(net, starting_score)
    occ = rank_occupancy(ints)
    u = placement_utilities(ints, values)
    float_occ = rank_occupancy(np.asarray(net, dtype=np.float64))
    return {"fourth_share": float(occ[learning_seat, 3]), "utility": float(u[learning_seat]),
            "occupancy": occ[learning_seat], "parity_ok": bool(np.allclose(occ, float_occ))}
```

In `evaluate.py` `evaluate_policy_online`: add lists `seat_fourth: list[float] = []`, `seat_large_loss: list[float] = []`, `seat_utility: list[float] = []`, `occupancy_sum = np.zeros(4)`, `rank_parity_mismatches = 0` next to `seat_placements`; in `record_episode`, after `seat_placements.append(placement)`:
```python
        net_vec = episode_reward_vector(episode, rewards, num_seats=4, reset_rewards=reset_rewards)
        tail = eval_episode_tail(net_vec, learning_seat,
                                 float(chongci_starting_score) if normalized_match_mode == "chongci" else 0.0,
                                 truncated)
        seat_fourth.append(tail["fourth_share"])
        seat_utility.append(tail["utility"])
        seat_large_loss.append(1.0 if reward <= resolved_large_loss_threshold else 0.0)
        occupancy_sum += tail["occupancy"]
        if not tail["parity_ok"]:
            rank_parity_mismatches += 1
```
(`nonlocal` the counter and array as the function already does for `wins` etc.; `chongci_starting_score` is a parameter of `evaluate_policy_online` — check its exact name at the signature ~line 660.)

In the returned dict, after `"placement_count"`:
```python
        "per_episode_fourth_share": seat_fourth,
        "per_episode_large_loss": seat_large_loss,
        "per_episode_training_utility": seat_utility,
        "placement_rank_shares": (occupancy_sum / completed).tolist() if completed else [0.0] * 4,
        "fourth_place_rate": float(np.mean(seat_fourth)) if seat_fourth else 0.0,
        "training_utility_mean": float(np.mean(seat_utility)) if seat_utility else 0.0,
        "rank_parity_mismatches": int(rank_parity_mismatches),
```
Import `eval_episode_tail` from `.placement_bonus` at the top of `evaluate.py`.

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_evaluate.py ai/tests/test_placement_bonus.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/placement_bonus.py ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py ai/tests/test_placement_bonus.py
git commit -m "feat(evaluate): per-episode 4th-share, large-loss and training-utility arrays, rank shares, rank parity check"
```

---

### Task 7: Duplicate-seat clustered tail fields, fail-closed ragged check, aggregated hand-stats deal-in

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (`clustered_placement_stats` ~line 165; `_clustered_report_fields` ~line 264; duplicate-seat return dict ~line 1085–1150)
- Test: `ai/tests/test_evaluate_clustered.py`

**Interfaces:**
- Produces: `clustered_metric_stats(per_seat: Sequence[Sequence[float]], prefix: str) -> dict` (generalization of `clustered_placement_stats`, keys `per_seed_mean_<prefix>`, `mean_<prefix>_clustered`, `mean_<prefix>_sem_clustered`, `mean_<prefix>_ci95_clustered`, `num_seeds`); duplicate-seat report gains `per_seed_mean_fourth_share`, `per_seed_mean_large_loss`, `per_seed_mean_training_utility`, `fourth_place_rate`, `training_utility_mean`, `hand_stats` (aggregated over seats), `deal_in_rate` (= aggregated `hand_stats["deal_in_rate"]`), `rank_parity_mismatches` (sum). `_clustered_report_fields` raises `ValueError` on ragged or missing arrays.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_evaluate_clustered.py
import pytest
from fh_mahjong_ai.evaluate import _clustered_report_fields, clustered_metric_stats


def test_clustered_metric_stats_generic_prefix():
    s = clustered_metric_stats([[1, 0, 1], [0, 0, 1]], "fourth_share")
    assert s["per_seed_mean_fourth_share"] == [0.5, 0.0, 1.0]
    assert s["mean_fourth_share_clustered"] == pytest.approx(0.5)
    assert s["num_seeds"] == 3


def test_clustered_report_fields_reject_ragged_and_missing():
    good = {"per_episode_placements": [0.0, 1.0], "per_episode_fourth_share": [0.0, 1.0],
            "per_episode_large_loss": [0.0, 0.0], "per_episode_training_utility": [0.1, -0.1]}
    ragged = {**good, "per_episode_placements": [0.0]}
    with pytest.raises(ValueError, match="ragged|length"):
        _clustered_report_fields([good, ragged])
    missing = {k: v for k, v in good.items() if k != "per_episode_fourth_share"}
    with pytest.raises(ValueError, match="per_episode_fourth_share"):
        _clustered_report_fields([good, missing])
    out = _clustered_report_fields([good, good])
    assert out["per_seed_mean_fourth_share"] == [0.0, 1.0]
    assert out["per_seed_mean_large_loss"] == [0.0, 0.0]
    assert "mean_fourth_share_ci95_clustered" in out
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_evaluate_clustered.py -q`
Expected: FAIL

- [ ] **Step 3: Implement**

Refactor: rename the body of `clustered_placement_stats` into `clustered_metric_stats(per_seat, prefix)` that builds its keys with `prefix`, and keep `clustered_placement_stats(per_seat)` as `return clustered_metric_stats(per_seat, "placement")` plus `cluster_design_effect` (only placement keeps that key — leave it in the generic function under `cluster_design_effect_<prefix>`? No: keep the generic function returning `cluster_design_effect` too, and have the placement wrapper rename nothing; the existing key names `per_seed_mean_placements` (plural!) and `mean_placement_clustered` must stay byte-identical for old reports, so the wrapper post-renames `per_seed_mean_placement` → `per_seed_mean_placements`).

`_clustered_report_fields`:
```python
_TAIL_ARRAYS = ("per_episode_placements", "per_episode_fourth_share",
                "per_episode_large_loss", "per_episode_training_utility")


def _clustered_report_fields(seat_reports):
    """Clustered placement AND tail fields for duplicate-seat reports. Fails
    closed: ragged or missing per-episode arrays are a protocol error, never
    empty stats (spec 2026-08-21 Amendment 1 item 9)."""
    for key in _TAIL_ARRAYS:
        for i, r in enumerate(seat_reports):
            if not isinstance(r.get(key), list):
                raise ValueError(f"seat report {i} lacks {key}; regenerate the report")
    per = {key: [[float(x) for x in r[key]] for r in seat_reports] for key in _TAIL_ARRAYS}
    placement = clustered_placement_stats(per["per_episode_placements"])   # raises on ragged
    fourth = clustered_metric_stats(per["per_episode_fourth_share"], "fourth_share")
    ll = clustered_metric_stats(per["per_episode_large_loss"], "large_loss")
    util = clustered_metric_stats(per["per_episode_training_utility"], "training_utility")
    return {
        "per_seed_mean_placements": placement["per_seed_mean_placements"],
        "mean_placement_ci95_clustered": placement["mean_placement_ci95_clustered"],
        "cluster_design_effect": placement["cluster_design_effect"],
        **{k: v for k, v in fourth.items() if k != "num_seeds"},
        **{k: v for k, v in ll.items() if k != "num_seeds"},
        **{k: v for k, v in util.items() if k != "num_seeds"},
    }
```
(Tests that construct seat reports with only `per_episode_placements` — grep `_clustered_report_fields\|seat_reports` in `ai/tests` — must be updated to supply all four arrays.)

Duplicate-seat return dict: add
```python
        "fourth_place_rate": float(np.mean([r["fourth_place_rate"] for r in seat_reports])) if seat_reports else 0.0,
        "training_utility_mean": float(np.mean([r["training_utility_mean"] for r in seat_reports])) if seat_reports else 0.0,
        "rank_parity_mismatches": int(sum(r.get("rank_parity_mismatches", 0) for r in seat_reports)),
        "hand_stats": agg_hand_stats,
        "deal_in_rate": agg_hand_stats["deal_in_rate"],
```
where, before the `return {`, you compute once:
```python
    agg_hand_stats = summarize_hand_stats(
        [m for r in seat_reports for m in r.get("per_match_hand_records", [])],
        sum(int(r.get("hand_stats", {}).get("unknown_hands", 0)) for r in seat_reports))
```

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_evaluate_clustered.py ai/tests/test_evaluate.py ai/tests/test_serve_policy_evaluate.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate_clustered.py ai/tests/test_evaluate.py
git commit -m "feat(evaluate): clustered 4th-share/large-loss/utility fields, fail-closed ragged check, all-hand deal-in on duplicate-seat reports"
```

---

### Task 8: `fh-mj-compare` pairs the tail metrics

**Files:**
- Modify: `ai/src/fh_mahjong_ai/scripts/compare_reports.py` (`paired_comparison` ~line 158–232; `_format_text`)
- Test: `ai/tests/test_compare_reports.py`

**Interfaces:**
- Produces in the comparison dict: `tail_metrics: dict | None` with, for each of `fourth_share`, `large_loss`, `training_utility`: `{"mean_delta", "delta_sem_clustered", "delta_ci95_clustered", "ci95_lower", "ci95_upper", "a", "b"}`; plus `deal_in_rate_a/b`, `rank_parity_mismatches_a/b`; and `tail_gate: dict` evaluating the spec's three registered conditions (`fourth_primary_pass`, `canonical_noninferiority_pass`, `large_loss_safety_pass`, `all_pass`) — **reported, never changes `significant`**. Missing tail arrays in exactly one report → `ValueError`; in both → `tail_metrics=None`, `tail_gate=None` with a text WARNING.

- [ ] **Step 1: Write failing tests**

```python
# append to ai/tests/test_compare_reports.py
def make_tail_report(seeds, placements, fourth, ll, util, deal_in=0.12):
    r = make_report(seeds, placements)
    r["per_seed_mean_fourth_share"] = list(map(float, fourth))
    r["per_seed_mean_large_loss"] = list(map(float, ll))
    r["per_seed_mean_training_utility"] = list(map(float, util))
    r["deal_in_rate"] = deal_in
    r["rank_parity_mismatches"] = 0
    return r


def test_tail_metrics_paired_and_gated():
    seeds = list(range(1300000, 1300040))
    n = len(seeds)
    a = make_tail_report(seeds, [0.0]*n, [0.20]*n, [0.04]*n, [0.1]*n)
    b = make_tail_report(seeds, [0.0]*n, [0.25]*n, [0.05]*n, [0.0]*n)
    # add tiny seed-varying noise so SEM is finite and nonzero
    a["per_seed_mean_fourth_share"] = [0.20 + 0.001*((i % 3) - 1) for i in range(n)]
    res = paired_comparison(a, b)
    t = res["tail_metrics"]["fourth_share"]
    assert t["mean_delta"] == pytest.approx(-0.05, abs=1e-3)
    assert t["ci95_upper"] < 0
    assert res["tail_metrics"]["large_loss"]["mean_delta"] == pytest.approx(-0.01)
    assert res["deal_in_rate_a"] == 0.12
    g = res["tail_gate"]
    assert g["fourth_primary_pass"] and g["canonical_noninferiority_pass"] and g["large_loss_safety_pass"] and g["all_pass"]
    assert res["significant"] is False  # canonical metric untouched


def test_tail_metrics_missing_in_one_report_is_error():
    seeds = list(range(10)); n = 10
    a = make_tail_report(seeds, [0.0]*n, [0.2]*n, [0.0]*n, [0.0]*n)
    b = make_report(seeds, [0.0]*n)
    with pytest.raises(ValueError, match="tail"):
        paired_comparison(a, b)


def test_tail_metrics_absent_in_both_is_none():
    seeds = list(range(10))
    res = paired_comparison(make_report(seeds, [0.0]*10), make_report(seeds, [0.0]*10))
    assert res["tail_metrics"] is None and res["tail_gate"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --project ai python -m pytest ai/tests/test_compare_reports.py -q`
Expected: FAIL (`KeyError: 'tail_metrics'`)

- [ ] **Step 3: Implement**

In `compare_reports.py` add:
```python
_TAIL_FIELDS = {
    "fourth_share": "per_seed_mean_fourth_share",
    "large_loss": "per_seed_mean_large_loss",
    "training_utility": "per_seed_mean_training_utility",
}
# Spec 2026-08-21 confirmation gate (tail-primary). Reported only; never
# feeds `significant`, which stays the canonical placement test.
FOURTH_PRIMARY_MAX_DELTA = -0.010
CANONICAL_NONINFERIORITY_CI_LOWER = -0.030
LARGE_LOSS_SAFETY_CI_UPPER = 0.005


def _paired_delta(a: np.ndarray, b: np.ndarray) -> Dict[str, Any]:
    d = a - b; n = d.size
    mean = float(d.mean())
    sem = float(np.std(d, ddof=1) / np.sqrt(n)) if n > 1 else 0.0
    ci = _t_critical_975(n - 1) * sem if n > 1 else 0.0
    return {"mean_delta": mean, "delta_sem_clustered": sem, "delta_ci95_clustered": ci,
            "ci95_lower": mean - ci, "ci95_upper": mean + ci,
            "a": float(a.mean()), "b": float(b.mean())}


def _tail_metrics(report_a, report_b, num_seeds):
    have_a = all(isinstance(report_a.get(f), list) for f in _TAIL_FIELDS.values())
    have_b = all(isinstance(report_b.get(f), list) for f in _TAIL_FIELDS.values())
    if have_a != have_b:
        raise ValueError("tail-metric arrays present in only one report — regenerate both reports "
                         "with the tail-aware evaluator before a placement-reshape comparison")
    if not have_a:
        return None
    out = {}
    for name, field in _TAIL_FIELDS.items():
        a = np.asarray(report_a[field], dtype=np.float64); b = np.asarray(report_b[field], dtype=np.float64)
        if a.size != num_seeds or b.size != num_seeds:
            raise ValueError(f"{field} length != seed count — ragged tail arrays (fail closed)")
        out[name] = _paired_delta(a, b)
    return out
```
In `paired_comparison`, before the `return`:
```python
    tail = _tail_metrics(report_a, report_b, num_seeds)
    tail_gate = None
    if tail is not None:
        f, ll = tail["fourth_share"], tail["large_loss"]
        tail_gate = {
            "fourth_primary_pass": bool(f["mean_delta"] <= FOURTH_PRIMARY_MAX_DELTA and f["ci95_upper"] < 0.0),
            "canonical_noninferiority_pass": bool(mean_delta - ci95 > CANONICAL_NONINFERIORITY_CI_LOWER),
            "large_loss_safety_pass": bool(ll["ci95_upper"] <= LARGE_LOSS_SAFETY_CI_UPPER),
        }
        tail_gate["all_pass"] = all(tail_gate.values())
```
and add to the returned dict:
```python
        "tail_metrics": tail,
        "tail_gate": tail_gate,
        "deal_in_rate_a": report_a.get("deal_in_rate"),
        "deal_in_rate_b": report_b.get("deal_in_rate"),
        "rank_parity_mismatches_a": report_a.get("rank_parity_mismatches"),
        "rank_parity_mismatches_b": report_b.get("rank_parity_mismatches"),
```
`_format_text`: append lines for each tail metric (`4th-share delta: {mean:+.4f} [{lo:+.4f}, {hi:+.4f}]`, etc.), the deal-in rates, and `tail gate: PASS/FAIL (primary …, non-inferiority …, safety …)`; when `tail_metrics is None` append `  NOTE: no tail metrics — reports predate the tail-aware evaluator`.

- [ ] **Step 4: Run tests**

Run: `uv run --project ai python -m pytest ai/tests/test_compare_reports.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/compare_reports.py ai/tests/test_compare_reports.py
git commit -m "feat(compare): paired seed-clustered 4th-share/large-loss/utility deltas and the registered tail gate"
```

---

### Task 9: Docs + full local gauntlet

**Files:**
- Modify: `ai/CLAUDE.md` (tools table: add `fh-mj-placement-calibrate`; a short "Placement-reshape terminal bonus" note near the `fh-mj-compare` paragraph at line ~172 listing the new report keys and that `significant` remains canonical)
- Modify: `worklog/specs/2026-08-21-placement-reshape-design.md` — no protocol change; add under Amendments: "Stage 0 code landed (commits …); λ pending box calibration."

- [ ] **Step 1: Update `ai/CLAUDE.md`** with the two additions above (keep the AGENTS.md symlink untouched).

- [ ] **Step 2: Run the full gauntlet**

Run:
```bash
uv run --project ai python -m pytest ai/tests -q
gofmt -l . ; go vet ./... && go test ./...
```
Expected: all PASS, `gofmt` prints nothing.

- [ ] **Step 3: Commit**

```bash
git add ai/CLAUDE.md worklog/specs/2026-08-21-placement-reshape-design.md
git commit -m "docs(ai): placement-reshape Stage 0 tooling and report keys"
```

---

### Task 10 (box): read the archived champion discounting

**Files:** none in repo; append to spec Amendment 2.

- [ ] **Step 1:** On the 4090/WSL box (read-only), print `gamma`, `gae_lambda`, `ppo_epochs`, `lr`, `entropy_coef`, `minibatch_size`, `matches_per_iter`, `max_grad_norm` from the ds960 archived frozen config / `train_state.pt` echo under `/root/fh-mahjong-runs/data-scale-960/` (`CLOSEOUT-MANIFEST.json` names the files). Label every line with the source path (ssh may double-execute; never `sort -u`).
- [ ] **Step 2:** Record the values verbatim in the spec under "Amendment 2 — Stage 0 measurements", and pass the recorded `--gamma/--gae-lambda` to Task 11 and Task 12.

---

### Task 11 (box): λ calibration + scale gates

- [ ] **Step 1:** Build the bridge on the box and run, with the archived γ/λ_GAE:
```bash
uv run --project ai fh-mj-placement-calibrate --champion <anchor075.pt> \
  --output /root/fh-mahjong-runs/placement-reshape/stage0/calibration.json \
  --matches 320 --base-seed 720000 --num-workers 10 --collect-dispatch-chunk 320 \
  --device cuda --gamma <archived> --gae-lambda <archived> \
  --event-window 128 <model-config flags identical to the ds960 launch command>
```
- [ ] **Step 2:** Verify `calibration.num_matches == 320`, `num_records == 1280`, `gates.all_pass == true`, zero truncation, and copy `lambda`, `sigma_R`, `sigma_V`, `corr_RV`, `collection_digest`, the three ratios, `bonus_mean/rms/abs_p99`, and `fourth_place_bonus_over_sigma_R` into Amendment 2. If any gate fails: STOP, return to consult; do not rerun with a smaller λ.

---

### Task 12 (box): positive-λ digest parity

- [ ] **Step 1:** With the frozen λ, run `fh-mj-collect-bench` (collection-only digest mode) three times at `--num-workers 1 / 10 / 20`, `--collect-dispatch-chunk 320`, 320 matches, seeds 720320+, passing `--placement-bonus-values <v> --placement-bonus-lambda <λ> --placement-bonus-calibration-digest <digest>`; and once at `--num-workers 10` with `--collect-dispatch-chunk 0`.
- [ ] **Step 2:** All four digests must be identical, and must differ from the same run without the bonus flags. Record all five digests in Amendment 2.
- [ ] **Step 3:** Run the registered 120-seed screening evaluator on anchor075 (seeds 910000–910119) and confirm the report carries `deal_in_rate` from `hand_stats` with `unknown_hands == 0` and `rank_parity_mismatches == 0`. Record in Amendment 2. Stage 0 is complete only when Tasks 10–12 are all recorded; then return to consult before Stage 1.
