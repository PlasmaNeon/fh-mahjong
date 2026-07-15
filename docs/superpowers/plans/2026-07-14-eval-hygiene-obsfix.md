# Eval Hygiene + Observation Double-Count Fix (Spec A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the interrupt-window double-count of the active discard from the RL observation encoder, and upgrade the evaluator with wall-seed-clustered confidence intervals plus a paired-comparison CLI.

**Architecture:** One-line Go fix in `publicSeenCounts` guarded by two regression tests (unit + encoder-level invariant). Python side adds a pure clustered-statistics helper in `evaluate.py`, wires three new backward-compatible fields into both duplicate-seat report builders, and adds a standalone `fh-mj-compare` CLI that computes the seed-clustered paired difference between two report JSONs. Docs record the new seed-window policy.

**Tech Stack:** Go 1.25 (`internal/rl`, `internal/engine`), Python 3.12 + numpy (`ai/src/fh_mahjong_ai`), pytest.

**Spec:** `docs/superpowers/specs/2026-07-14-eval-hygiene-obsfix-design.md` (approved). Branch: `claude/eval-hygiene` (exists, off main @ 97a84c9).

## Global Constraints

- Existing report fields must remain byte-compatible: only ADD fields (`per_seed_mean_placements`, `mean_placement_ci95_clustered`, `cluster_design_effect`); never rename, remove, or change the value of an existing field.
- Do NOT build a `--compat-double-count` serving flag. The spec's decision rule creates it only if the post-merge measurement demands it.
- No new Python dependencies (numpy only — no scipy; the t critical value is computed locally).
- After Go changes: `go vet ./...` and `go test ./...` must pass. After Python changes: `uv run --project ai pytest` must pass.
- Commits end with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- The post-merge champion fixed-vs-buggy paired eval on the 4090 is Task 5 (runbook, not code) — it happens AFTER the PR gauntlet and merge, not on this branch.

---

### Task 1: Go — remove the ActiveDiscard double-count from publicSeenCounts

**Files:**
- Modify: `internal/rl/observation.go:502` (the `addCounts(&counts, faceCountsFromTile(state.ActiveDiscard))` line inside `publicSeenCounts`)
- Create: `internal/rl/observation_test.go`

**Interfaces:**
- Consumes: `publicSeenCounts(state *pb.GameState) [42]int` (unexported, same package), `EncodeObservation(state, seat, decisionIndex)`, `tileFaceIndex42`, `channelOffset`, `engine.NewGame`, `engine.SeedFromUint64`, `rules.FenghuaRuleset`, `env.game.Rules.GetValidInterrupts` — all existing.
- Produces: nothing new — behavior change only. Plane 37 (public seen counts) and `publicDangerScore` (scalar 39) stop double-counting the claimable discard.

**Background for the implementer:** `handleDiscard` (internal/engine/game.go:813-821) appends the discarded tile to `player.Discards` and THEN sets `state.ActiveDiscard` to the same tile. So whenever `ActiveDiscard != nil`, that tile is already inside the discarder's `Discards` — `publicSeenCounts` summing both counts it twice. Encoder layout facts you need: plane channel 37 is `setRawCountPlane(planes, 37, publicSeenCounts(state), 4)` — value at `channelOffset(37)+faceIndex` is `count/4`. Plane 28 is a presence plane for `ActiveDiscard` and legitimately changes with it; compare ONLY plane 37.

- [ ] **Step 1: Write the failing tests**

Create `internal/rl/observation_test.go`:

```go
package rl

import (
	"testing"

	"github.com/plasma/fh-mahjong/internal/engine"
	"github.com/plasma/fh-mahjong/internal/rules"
	pb "github.com/plasma/fh-mahjong/proto"
)

// countFaceInPublicZones counts physical copies of a face visible in public
// zones, iterating the state directly — an implementation independent of
// publicSeenCounts, so the test cannot share a bug with the code under test.
// ActiveDiscard is deliberately NOT a zone: during a claim window the tile
// already sits in the discarder's Discards.
func countFaceInPublicZones(state *pb.GameState, faceIndex int) int {
	total := 0
	countTiles := func(ts []*pb.Tile) {
		for _, tile := range ts {
			if idx, ok := tileFaceIndex42(tile); ok && idx == faceIndex {
				total++
			}
		}
	}
	for _, p := range state.Players {
		countTiles(p.Discards)
		for _, meld := range p.OpenMelds {
			countTiles(meld.Tiles)
		}
		countTiles(p.FlowerMelds)
	}
	countTiles(state.WildTiles)
	return total
}

// TestPublicSeenCounts_ActiveDiscardNotDoubleCounted: a tile that sits in a
// player's Discards AND is the ActiveDiscard (the invariant state during every
// WAIT_DISCARDS window) must be counted exactly once.
func TestPublicSeenCounts_ActiveDiscardNotDoubleCounted(t *testing.T) {
	discard := &pb.Tile{Id: 9001, Suit: pb.Suit_SUIT_MAN, Value: 5}
	state := &pb.GameState{
		Players: []*pb.PlayerState{{}, {}, {}, {}},
	}
	state.Players[0].Discards = []*pb.Tile{discard}
	state.ActiveDiscard = discard

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	counts := publicSeenCounts(state)
	if counts[faceIndex] != 1 {
		t.Fatalf("claimable discard counted %d times in publicSeenCounts, want exactly 1", counts[faceIndex])
	}
}

// TestEncodeObservation_SeenPlaneCountsClaimedTileOnce builds a real
// WAIT_DISCARDS interrupt window (mirroring handleDiscard's append-then-set
// sequence) and asserts plane 37's value for the claimed face equals the
// number of PHYSICAL copies visible in public zones — counted independently.
// Before the fix this fails: the encoder reports one extra copy.
func TestEncodeObservation_SeenPlaneCountsClaimedTileOnce(t *testing.T) {
	config := &pb.EnvConfig{
		LearningSeats:      []uint32{0, 1, 2, 3},
		AutoPlayHeuristics: false,
		MaxDecisions:       512,
	}
	env := New(config)
	env.game = engine.NewGame("obs-double-count", &rules.FenghuaRuleset{}, engine.MatchOptions{})
	env.game.SetWallSeed(engine.SeedFromUint64(7))
	if err := env.game.Start(); err != nil {
		t.Fatalf("start: %v", err)
	}
	state := env.game.State

	const discarder = uint32(0)
	const observer = uint32(2)

	// Mirror handleDiscard: append to Discards, THEN set ActiveDiscard.
	discard := &pb.Tile{Id: 9001, Suit: pb.Suit_SUIT_MAN, Value: 5}
	state.Players[discarder].Discards = append(state.Players[discarder].Discards, discard)
	state.ActivePlayer = discarder
	state.Phase = pb.GamePhase_PHASE_WAIT_DISCARDS
	state.ActiveDiscard = discard
	state.IsHaitei = false

	// Observer holds a matching pair -> PON eligible: a REAL interrupt decision.
	r1 := &pb.Tile{Id: 9101, Suit: discard.Suit, Value: discard.Value}
	r2 := &pb.Tile{Id: 9102, Suit: discard.Suit, Value: discard.Value}
	state.Players[observer].ClosedHand = append(state.Players[observer].ClosedHand, r1, r2)
	state.Players[observer].ValidActions = env.game.Rules.GetValidInterrupts(state, discard, observer)
	if len(state.Players[observer].ValidActions) == 0 {
		t.Fatalf("premise broken: observer has no interrupt actions — not a claim window")
	}

	obs, err := EncodeObservation(state, observer, 0)
	if err != nil {
		t.Fatalf("encode: %v", err)
	}

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	// r1/r2 are in the observer's CLOSED hand — not public. Public copies of
	// this face = the discard itself + whatever Start() dealt into public
	// zones (normally zero, but count independently rather than assume).
	wantCopies := countFaceInPublicZones(state, faceIndex)
	got := obs.Planes[channelOffset(37)+faceIndex]
	want := float32(wantCopies) / 4.0
	if got != want {
		t.Fatalf("plane 37 seen count for claimed face = %v (%.0f copies), want %v (%d copies)",
			got, got*4, want, wantCopies)
	}
}

// TestPublicSeenCounts_NonWindowStateUnchanged: with no ActiveDiscard (the
// normal PLAYER_TURN state), counts come from the piles alone — the fix must
// not change this path.
func TestPublicSeenCounts_NonWindowStateUnchanged(t *testing.T) {
	discard := &pb.Tile{Id: 9002, Suit: pb.Suit_SUIT_SOU, Value: 3}
	state := &pb.GameState{
		Players: []*pb.PlayerState{{}, {}, {}, {}},
	}
	state.Players[1].Discards = []*pb.Tile{discard}
	state.ActiveDiscard = nil

	faceIndex, ok := tileFaceIndex42(discard)
	if !ok {
		t.Fatalf("no face index for test tile")
	}
	counts := publicSeenCounts(state)
	if counts[faceIndex] != 1 {
		t.Fatalf("discard counted %d times with nil ActiveDiscard, want 1", counts[faceIndex])
	}
}
```

- [ ] **Step 2: Run tests to verify the double-count tests fail**

Run: `go test ./internal/rl/ -run 'TestPublicSeenCounts|TestEncodeObservation_SeenPlane' -v`
Expected: `TestPublicSeenCounts_ActiveDiscardNotDoubleCounted` FAILS (`counted 2 times ... want exactly 1`); `TestEncodeObservation_SeenPlaneCountsClaimedTileOnce` FAILS (one extra copy on plane 37); `TestPublicSeenCounts_NonWindowStateUnchanged` PASSES.

- [ ] **Step 3: Apply the fix**

In `internal/rl/observation.go`, `publicSeenCounts` (line ~495), delete the ActiveDiscard line:

```go
func publicSeenCounts(state *pb.GameState) [42]int {
	var counts [42]int
	for _, player := range state.Players {
		addCounts(&counts, faceCountsFromTiles(player.Discards))
		addCounts(&counts, faceCountsFromMelds(player.OpenMelds))
		addCounts(&counts, faceCountsFromTiles(player.FlowerMelds))
	}
	// ActiveDiscard is intentionally NOT summed: handleDiscard appends the
	// tile to the discarder's Discards before setting ActiveDiscard, so during
	// every claim window the tile is already in the pile above — adding it
	// again double-counted the claimable tile at every interrupt decision.
	addCounts(&counts, faceCountsFromTiles(state.WildTiles))
	return counts
}
```

- [ ] **Step 4: Run the full Go suite**

Run: `go vet ./... && go test ./...`
Expected: vet clean; all packages PASS (the three new tests included). If any EXISTING test fails, it was asserting the buggy count — inspect it: a test that hardcodes a double-counted expectation gets its expectation corrected (with a comment citing this fix), never the production code re-broken.

- [ ] **Step 5: Commit**

```bash
git add internal/rl/observation.go internal/rl/observation_test.go
git commit -m "fix(rl): stop double-counting the claimable discard in publicSeenCounts

During every WAIT_DISCARDS window the active discard already sits in the
discarder's Discards pile (handleDiscard appends before setting
ActiveDiscard), so summing both counted the claimable tile twice in plane 37
and in publicDangerScore at every interrupt decision.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Python — clustered placement statistics in duplicate-seat reports

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (add `_t_critical_975`, `clustered_placement_stats`, `_clustered_report_fields` near `reward_summary` at line ~61; wire into `evaluate_duplicate_seats_policy` return dict at ~848 and `evaluate_duplicate_seats` return dict at ~1000)
- Create: `ai/tests/test_evaluate_clustered.py`

**Interfaces:**
- Consumes: `reward_summary` (existing; its `ci95` = `1.96 * sem` is the naive baseline), `seat_reports` lists in both duplicate functions where each report carries `per_episode_placements` ordered by the shared seed list.
- Produces (Task 3 and Task 4 rely on these exact names):
  - `_t_critical_975(df: int) -> float` — two-sided 95% Student-t critical value.
  - `clustered_placement_stats(per_seat_placements: Sequence[Sequence[float]]) -> Dict[str, Any]` with keys `per_seed_mean_placements: list[float]`, `mean_placement_clustered: float`, `mean_placement_sem_clustered: float`, `mean_placement_ci95_clustered: float`, `cluster_design_effect: float`, `num_seeds: int`. Raises `ValueError` on unequal per-seat lengths.
  - Report fields added to BOTH duplicate-seat report dicts: `per_seed_mean_placements`, `mean_placement_ci95_clustered`, `cluster_design_effect`.

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_evaluate_clustered.py`:

```python
import numpy as np
import pytest

from fh_mahjong_ai.evaluate import (
    _t_critical_975,
    clustered_placement_stats,
)


def test_t_critical_matches_tables():
    # Known two-sided 95% Student-t critical values.
    assert _t_critical_975(1) == pytest.approx(12.706, abs=0.01)
    assert _t_critical_975(2) == pytest.approx(4.303, abs=0.01)
    assert _t_critical_975(4) == pytest.approx(2.776, abs=0.01)
    assert _t_critical_975(10) == pytest.approx(2.228, abs=0.01)
    assert _t_critical_975(119) == pytest.approx(1.980, abs=0.005)
    assert _t_critical_975(10_000) == pytest.approx(1.960, abs=0.002)


def test_per_seed_means_and_count():
    # 2 seats x 3 seeds; per-seed mean = column mean.
    stats = clustered_placement_stats([[1.0, 0.0, -1.0], [0.0, 1.0, -1.0]])
    assert stats["per_seed_mean_placements"] == pytest.approx([0.5, 0.5, -1.0])
    assert stats["num_seeds"] == 3
    assert stats["mean_placement_clustered"] == pytest.approx(0.0)


def test_seat_order_invariance():
    # Reordering seats (rows) must not change any statistic: the seed is the
    # cluster, and a per-seed mean is order-free.
    a = [[1.0, 0.2, -0.5, 0.9], [0.0, 0.4, -1.0, 0.3], [0.5, -0.2, 0.0, 0.1]]
    s1 = clustered_placement_stats(a)
    s2 = clustered_placement_stats([a[2], a[0], a[1]])
    assert s1["per_seed_mean_placements"] == pytest.approx(s2["per_seed_mean_placements"])
    assert s1["mean_placement_ci95_clustered"] == pytest.approx(s2["mean_placement_ci95_clustered"])
    assert s1["cluster_design_effect"] == pytest.approx(s2["cluster_design_effect"])


def test_unequal_lengths_rejected():
    with pytest.raises(ValueError):
        clustered_placement_stats([[1.0, 2.0], [1.0]])


def test_correlated_seeds_widen_ci():
    # Strong within-seed correlation: all 4 rotations of a seed share its
    # value. Clustered CI must exceed the naive iid CI (design effect > 1).
    rng = np.random.default_rng(0)
    seed_values = rng.normal(size=200)
    per_seat = [list(seed_values) for _ in range(4)]  # identical rotations
    stats = clustered_placement_stats(per_seat)
    flat = np.repeat(seed_values, 1)  # any one seat row IS the seed values
    naive_sem = float(np.std(np.concatenate([flat] * 4), ddof=1) / np.sqrt(800))
    naive_ci = 1.96 * naive_sem
    assert stats["mean_placement_ci95_clustered"] > naive_ci
    assert stats["cluster_design_effect"] == pytest.approx(4.0, rel=0.05)


def test_independent_data_design_effect_near_one():
    rng = np.random.default_rng(1)
    per_seat = [list(rng.normal(size=500)) for _ in range(4)]
    stats = clustered_placement_stats(per_seat)
    assert 0.7 < stats["cluster_design_effect"] < 1.3


def test_degenerate_inputs():
    empty = clustered_placement_stats([])
    assert empty["num_seeds"] == 0
    assert empty["per_seed_mean_placements"] == []
    assert empty["mean_placement_ci95_clustered"] == 0.0
    one = clustered_placement_stats([[0.5], [0.7]])
    assert one["num_seeds"] == 1
    assert one["mean_placement_ci95_clustered"] == 0.0  # no df -> no interval
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_evaluate_clustered.py -v`
Expected: FAIL with `ImportError: cannot import name '_t_critical_975'`.

- [ ] **Step 3: Implement the helpers**

In `ai/src/fh_mahjong_ai/evaluate.py`, directly below `reward_summary` (after line ~103), add:

```python
# Small-df lookup for the two-sided 95% Student-t critical value; the
# Cornish-Fisher series below is accurate to ~1e-3 only for df >= 5.
_T_CRITICAL_975_SMALL_DF = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776}


def _t_critical_975(df: int) -> float:
    """Two-sided 95% Student-t critical value (numpy-only, no scipy)."""
    if df <= 0:
        return float("inf")
    if df in _T_CRITICAL_975_SMALL_DF:
        return _T_CRITICAL_975_SMALL_DF[df]
    z = 1.959963984540054
    g1 = (z**3 + z) / 4.0
    g2 = (5 * z**5 + 16 * z**3 + 3 * z) / 96.0
    g3 = (3 * z**7 + 19 * z**5 + 17 * z**3 - 15 * z) / 384.0
    return float(z + g1 / df + g2 / df**2 + g3 / df**3)


def clustered_placement_stats(per_seat_placements: Sequence[Sequence[float]]) -> Dict[str, Any]:
    """Wall-seed-clustered placement statistics for duplicate-seat evals.

    ``per_seat_placements`` holds one sequence per rotated seat, each ordered
    by the SHARED seed list. The wall seed is the independent sampling unit;
    the seat rotations of one seed are correlated replicates, so the interval
    is a t-interval over per-seed means, not over the flattened placements.
    ``cluster_design_effect`` is the ratio of the clustered to the naive
    variance of the mean (>1 = positive within-seed correlation).
    """
    empty = {
        "per_seed_mean_placements": [],
        "mean_placement_clustered": 0.0,
        "mean_placement_sem_clustered": 0.0,
        "mean_placement_ci95_clustered": 0.0,
        "cluster_design_effect": 0.0,
        "num_seeds": 0,
    }
    rows = [list(map(float, seat)) for seat in per_seat_placements]
    if not rows:
        return empty
    lengths = {len(row) for row in rows}
    if len(lengths) != 1:
        raise ValueError(
            f"per-seat placement lists must share one length (one entry per seed); got lengths {sorted(lengths)}"
        )
    num_seeds = lengths.pop()
    if num_seeds == 0:
        return empty

    matrix = np.asarray(rows, dtype=np.float64)  # (seats, seeds)
    seed_means = matrix.mean(axis=0)
    mean = float(seed_means.mean())
    if num_seeds < 2:
        return {
            "per_seed_mean_placements": [float(v) for v in seed_means],
            "mean_placement_clustered": mean,
            "mean_placement_sem_clustered": 0.0,
            "mean_placement_ci95_clustered": 0.0,
            "cluster_design_effect": 0.0,
            "num_seeds": num_seeds,
        }

    clustered_sem = float(np.std(seed_means, ddof=1) / np.sqrt(num_seeds))
    flat = matrix.reshape(-1)
    naive_var_of_mean = float(np.var(flat, ddof=1) / flat.size) if flat.size > 1 else 0.0
    design_effect = (clustered_sem**2 / naive_var_of_mean) if naive_var_of_mean > 0 else 0.0
    return {
        "per_seed_mean_placements": [float(v) for v in seed_means],
        "mean_placement_clustered": mean,
        "mean_placement_sem_clustered": clustered_sem,
        "mean_placement_ci95_clustered": _t_critical_975(num_seeds - 1) * clustered_sem,
        "cluster_design_effect": design_effect,
        "num_seeds": num_seeds,
    }


def _clustered_report_fields(seat_reports: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """The three clustered fields added to duplicate-seat reports.

    Falls back to empty stats (instead of raising) when seat reports are
    ragged — a defensive path only; duplicate-seat runs always evaluate the
    identical seed list on every seat.
    """
    per_seat = [
        [float(p) for p in report.get("per_episode_placements", [])]
        for report in seat_reports
    ]
    try:
        stats = clustered_placement_stats(per_seat)
    except ValueError:
        stats = clustered_placement_stats([])
    return {
        "per_seed_mean_placements": stats["per_seed_mean_placements"],
        "mean_placement_ci95_clustered": stats["mean_placement_ci95_clustered"],
        "cluster_design_effect": stats["cluster_design_effect"],
    }
```

(`Sequence`, `Dict`, `Any`, and `np` are already imported at the top of `evaluate.py`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_evaluate_clustered.py -v`
Expected: all PASS.

- [ ] **Step 5: Wire the fields into both duplicate-seat reports**

In `evaluate_duplicate_seats_policy`, in the returned dict (line ~848), immediately after the three existing placement lines:

```python
        "per_episode_placements": all_placements,
        "mean_placement": placements["mean"],
        "mean_placement_ci95": placements["ci95"],
        "placement_count": len(all_placements),
        **_clustered_report_fields(seat_reports),
```

Apply the identical `**_clustered_report_fields(seat_reports),` insertion in `evaluate_duplicate_seats`'s returned dict (after its `"placement_count": len(all_placements),` line, ~1020).

- [ ] **Step 6: Add the report-integration test**

Append to `ai/tests/test_evaluate_clustered.py`:

```python
def test_clustered_report_fields_from_seat_reports():
    from fh_mahjong_ai.evaluate import _clustered_report_fields

    seat_reports = [
        {"per_episode_placements": [1.0, -1.0]},
        {"per_episode_placements": [1.0 / 3.0, -1.0 / 3.0]},
        {"per_episode_placements": [-1.0 / 3.0, 1.0 / 3.0]},
        {"per_episode_placements": [-1.0, 1.0]},
    ]
    fields = _clustered_report_fields(seat_reports)
    # Duplicate seats of one seed cover all four ranks -> per-seed mean 0.
    assert fields["per_seed_mean_placements"] == pytest.approx([0.0, 0.0])
    assert fields["mean_placement_ci95_clustered"] == pytest.approx(0.0)

    # Ragged seat reports (defensive path) degrade to empty stats, not a crash.
    ragged = _clustered_report_fields([{"per_episode_placements": [1.0]}, {"per_episode_placements": []}])
    assert ragged["per_seed_mean_placements"] == []
```

- [ ] **Step 7: Run the full Python suite**

Run: `uv run --project ai pytest`
Expected: all PASS (existing duplicate-seat tests unaffected — fields were only added).

- [ ] **Step 8: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate_clustered.py
git commit -m "feat(eval): wall-seed-clustered placement CI in duplicate-seat reports

The naive CI treats 4 rotations of one wall seed as independent samples.
Adds per_seed_mean_placements, mean_placement_ci95_clustered (t-interval
over per-seed means), and cluster_design_effect to both duplicate-seat
report builders; existing fields unchanged.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: fh-mj-compare — seed-clustered paired comparison CLI

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/compare_reports.py`
- Modify: `ai/pyproject.toml` (`[project.scripts]`: add `fh-mj-compare = "fh_mahjong_ai.scripts.compare_reports:main"` after the `fh-mj-evaluate` line)
- Create: `ai/tests/test_compare_reports.py`

**Interfaces:**
- Consumes: `_t_critical_975` and `clustered_placement_stats` from `fh_mahjong_ai.evaluate` (Task 2 signatures).
- Produces: `paired_comparison(report_a: dict, report_b: dict) -> dict` and CLI `fh-mj-compare REPORT_A REPORT_B [--json]`. Comparison dict keys: `num_seeds`, `per_seed_deltas`, `mean_delta`, `delta_sem_clustered`, `delta_ci95_clustered`, `mean_placement_a`, `mean_placement_b`, `large_loss_rate_a`, `large_loss_rate_b`, `significant` (bool: 0 outside the CI).

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_compare_reports.py`:

```python
import json

import numpy as np
import pytest

from fh_mahjong_ai.scripts.compare_reports import main, paired_comparison


def make_report(seeds, per_seed_means, large_loss_rate=0.05, with_field=True):
    """Minimal duplicate-seat report. with_field=False mimics an OLD report
    that predates per_seed_mean_placements (reconstruction fallback)."""
    report = {
        "seeds": list(seeds),
        "mean_placement": float(np.mean(per_seed_means)),
        "large_loss_rate": large_loss_rate,
        "seat_reports": [
            {"per_episode_placements": [float(m) for m in per_seed_means]}
            for _ in range(4)
        ],
    }
    if with_field:
        report["per_seed_mean_placements"] = [float(m) for m in per_seed_means]
    return report


def test_identical_reports_zero_delta():
    seeds = list(range(910000, 910010))
    means = list(np.linspace(-1, 1, 10))
    result = paired_comparison(make_report(seeds, means), make_report(seeds, means))
    assert result["num_seeds"] == 10
    assert result["mean_delta"] == pytest.approx(0.0)
    assert result["per_seed_deltas"] == pytest.approx([0.0] * 10)
    assert result["significant"] is False


def test_constant_shift_detected():
    seeds = list(range(910000, 910200))
    rng = np.random.default_rng(2)
    base = rng.normal(scale=0.1, size=200)
    result = paired_comparison(
        make_report(seeds, list(base + 0.5)),
        make_report(seeds, list(base)),
    )
    assert result["mean_delta"] == pytest.approx(0.5, abs=1e-6)
    assert result["delta_ci95_clustered"] < 0.1
    assert result["significant"] is True


def test_seed_mismatch_refused():
    a = make_report([1, 2, 3], [0.0, 0.0, 0.0])
    b = make_report([1, 2, 4], [0.0, 0.0, 0.0])
    with pytest.raises(ValueError, match="seed"):
        paired_comparison(a, b)
    with pytest.raises(ValueError, match="seed"):
        paired_comparison(make_report([], []), make_report([], []))


def test_old_report_reconstruction_fallback():
    seeds = list(range(5))
    means = [0.1, -0.2, 0.3, 0.0, -0.1]
    old = make_report(seeds, means, with_field=False)
    assert "per_seed_mean_placements" not in old
    result = paired_comparison(old, make_report(seeds, means))
    assert result["mean_delta"] == pytest.approx(0.0)


def test_cli_json_mode(tmp_path, capsys):
    seeds = list(range(910000, 910020))
    means = list(np.linspace(-0.5, 0.5, 20))
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(make_report(seeds, [m + 0.1 for m in means])))
    path_b.write_text(json.dumps(make_report(seeds, means)))

    main([str(path_a), str(path_b), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["num_seeds"] == 20
    assert payload["mean_delta"] == pytest.approx(0.1, abs=1e-6)


def test_cli_text_mode(tmp_path, capsys):
    seeds = [1, 2, 3, 4]
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(make_report(seeds, [0.5, 0.5, 0.5, 0.5])))
    path_b.write_text(json.dumps(make_report(seeds, [0.0, 0.0, 0.0, 0.0])))

    main([str(path_a), str(path_b)])
    out = capsys.readouterr().out
    assert "mean delta" in out
    assert "0.5" in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_compare_reports.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'fh_mahjong_ai.scripts.compare_reports'`.

- [ ] **Step 3: Implement the tool**

Create `ai/src/fh_mahjong_ai/scripts/compare_reports.py`:

```python
"""fh-mj-compare: seed-clustered paired comparison of two duplicate-seat reports.

Every promotion or lever-verdict claim must come from this tool run on two
reports produced on the SAME seed window (see the seed-window policy in
docs/rl-papers/chongci-rl-experiment-progress.md).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, Optional, Sequence

import numpy as np

from fh_mahjong_ai.evaluate import _t_critical_975, clustered_placement_stats


def _per_seed_means(report: Dict[str, Any], num_seeds: int) -> list[float]:
    """Per-seed mean placements: the report field when present, otherwise
    reconstructed from seat_reports (reports that predate the field)."""
    means = report.get("per_seed_mean_placements")
    if isinstance(means, list) and len(means) == num_seeds:
        return [float(m) for m in means]
    per_seat = [
        [float(p) for p in seat.get("per_episode_placements", [])]
        for seat in report.get("seat_reports", [])
    ]
    stats = clustered_placement_stats(per_seat)
    if stats["num_seeds"] != num_seeds:
        raise ValueError(
            f"cannot recover per-seed means: report has {stats['num_seeds']} seeds of placements "
            f"but a seed list of {num_seeds}"
        )
    return stats["per_seed_mean_placements"]


def paired_comparison(report_a: Dict[str, Any], report_b: Dict[str, Any]) -> Dict[str, Any]:
    seeds_a = list(report_a.get("seeds", []))
    seeds_b = list(report_b.get("seeds", []))
    if not seeds_a or not seeds_b:
        raise ValueError("both reports must carry a non-empty seed list")
    if seeds_a != seeds_b:
        raise ValueError(
            f"seed lists differ ({len(seeds_a)} vs {len(seeds_b)} seeds; "
            "first mismatch at index "
            f"{next((i for i, (a, b) in enumerate(zip(seeds_a, seeds_b)) if a != b), min(len(seeds_a), len(seeds_b)))}) "
            "— paired comparison requires reports from the SAME seed window"
        )

    num_seeds = len(seeds_a)
    means_a = np.asarray(_per_seed_means(report_a, num_seeds), dtype=np.float64)
    means_b = np.asarray(_per_seed_means(report_b, num_seeds), dtype=np.float64)
    deltas = means_a - means_b

    mean_delta = float(deltas.mean())
    if num_seeds > 1:
        sem = float(np.std(deltas, ddof=1) / np.sqrt(num_seeds))
        ci95 = _t_critical_975(num_seeds - 1) * sem
    else:
        sem = 0.0
        ci95 = 0.0

    return {
        "num_seeds": num_seeds,
        "per_seed_deltas": [float(d) for d in deltas],
        "mean_delta": mean_delta,
        "delta_sem_clustered": sem,
        "delta_ci95_clustered": ci95,
        "mean_placement_a": float(report_a.get("mean_placement", means_a.mean())),
        "mean_placement_b": float(report_b.get("mean_placement", means_b.mean())),
        "large_loss_rate_a": report_a.get("large_loss_rate"),
        "large_loss_rate_b": report_b.get("large_loss_rate"),
        "significant": bool(ci95 > 0.0 and abs(mean_delta) > ci95),
    }


def _format_text(result: Dict[str, Any], label_a: str, label_b: str) -> str:
    lines = [
        f"paired comparison over {result['num_seeds']} wall seeds (A - B)",
        f"  A: {label_a}",
        f"  B: {label_b}",
        f"  mean placement A: {result['mean_placement_a']:+.4f}   large_loss A: {result['large_loss_rate_a']}",
        f"  mean placement B: {result['mean_placement_b']:+.4f}   large_loss B: {result['large_loss_rate_b']}",
        f"  mean delta: {result['mean_delta']:+.4f} ± {result['delta_ci95_clustered']:.4f} (seed-clustered CI95)",
        f"  significant at 95%: {'YES' if result['significant'] else 'no'}",
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_a", help="duplicate-seat report JSON (candidate)")
    parser.add_argument("report_b", help="duplicate-seat report JSON (baseline)")
    parser.add_argument("--json", action="store_true", help="emit the comparison dict as JSON")
    args = parser.parse_args(argv)

    with open(args.report_a) as fh:
        report_a = json.load(fh)
    with open(args.report_b) as fh:
        report_b = json.load(fh)

    result = paired_comparison(report_a, report_b)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(_format_text(result, args.report_a, args.report_b))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Register the CLI**

In `ai/pyproject.toml` under `[project.scripts]`, after the `fh-mj-evaluate = ...` line, add:

```toml
fh-mj-compare = "fh_mahjong_ai.scripts.compare_reports:main"
```

- [ ] **Step 5: Run tests to verify they pass, then the full suite**

Run: `uv run --project ai pytest ai/tests/test_compare_reports.py -v`
Expected: all PASS.
Run: `uv run --project ai pytest`
Expected: all PASS.
Run: `uv run --project ai fh-mj-compare --help`
Expected: usage text with `report_a report_b [--json]`.

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/compare_reports.py ai/tests/test_compare_reports.py ai/pyproject.toml
git commit -m "feat(eval): fh-mj-compare seed-clustered paired comparison CLI

Single source of gate verdicts: validates identical seed lists, computes
the per-seed paired placement delta with a t-interval CI95, reconstructs
per-seed means from seat_reports for pre-field reports, --json mode.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Docs — seed-window policy + AGENTS.md updates

**Files:**
- Modify: `docs/rl-papers/chongci-rl-experiment-progress.md` (append a subsection to the maintenance/protocol section at the top of the file, after the existing protocol rules)
- Modify: `internal/rl/AGENTS.md` (observation encoder notes)
- Modify: `ai/AGENTS.md` (evaluator + new CLI notes; if evaluator docs live in a deeper `AGENTS.md`, update that one instead — check `ls ai/AGENTS.md ai/src/fh_mahjong_ai/AGENTS.md`)

**Interfaces:**
- Consumes: field/CLI names exactly as produced by Tasks 2-3 (`per_seed_mean_placements`, `mean_placement_ci95_clustered`, `cluster_design_effect`, `fh-mj-compare`).
- Produces: nothing code-facing.

- [ ] **Step 1: Append the seed-window policy to the progress note protocol section**

Read the protocol/maintenance section at the top of `docs/rl-papers/chongci-rl-experiment-progress.md` and append this subsection to it (adjust the heading level to match neighbors):

```markdown
### Seed-window policy (2026-07-14, binding)

The `870000+` window is RETIRED for promotion decisions: it selected
iter_200/240/275 AND scored every later gate, so any number measured on it
carries winner's-curse bias (~+0.035 expected on the champion's margin).

- **Screening** — `--start-seed 910000 --online-episodes 120` (480
  placements): cheap looks, checkpoint selection, curiosity. Unlimited use;
  never cite for promotion.
- **Confirmation** — `--start-seed 950000 --online-episodes 1500` (6000
  placements, ~6h on the 4090): final gates ONLY. Every promotion or
  lever-verdict claim must cite a confirmation run compared via
  `fh-mj-compare` (seed-clustered paired CI95). The windows cannot collide:
  screening consumes seeds far below 950000 at these episode counts.
- CIs: duplicate-seat rotations of one wall seed are correlated — use the
  clustered fields (`mean_placement_ci95_clustered`, `cluster_design_effect`)
  added 2026-07-14, not the naive iid `mean_placement_ci95`. Power reference
  (iid-optimistic; scale by the measured design effect): 1500 seeds ≈ ±0.03
  half-width; 80% power needs ~550 seeds for a true +0.05, ~1530 for +0.03.
```

- [ ] **Step 2: Update AGENTS.md for touched directories**

`internal/rl/AGENTS.md` — in the observation/encoder section, note: `publicSeenCounts` intentionally excludes `ActiveDiscard` (already present in the discarder's `Discards` during claim windows; summing both double-counted the claimable tile — fixed 2026-07-14, regression-tested in `observation_test.go`).

`ai/AGENTS.md` (or the deeper evaluator AGENTS.md if that is where evaluate.py is documented) — note the three new duplicate-seat report fields, the seed-cluster rationale (one line), the `fh-mj-compare` CLI as the required gate-verdict tool, and the screening/confirmation seed-window split with the exact `--start-seed` values.

- [ ] **Step 3: Commit**

```bash
git add docs/rl-papers/chongci-rl-experiment-progress.md internal/rl/AGENTS.md ai/AGENTS.md
git commit -m "docs(rl): binding seed-window policy + clustered-CI eval protocol

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(If a deeper AGENTS.md was updated instead of `ai/AGENTS.md`, stage that path.)

---

### Task 5: Runbook — champion re-measurement (POST-MERGE, on the 4090; not part of this branch's code)

Executed after the PR gauntlet and merge. Recorded here so the operational close-out is not lost.

**Prereqs on the box (`ssh wsl`, repo `/root/fh-mahjong`):** pull merged main; rebuild the bridge: `go build -buildmode=c-shared -o build/libfh_mahjong_bridge.so ./cmd/rlbridge`. Champion checkpoint: `/root/fh-mahjong-runs/deploy/selfplay-deep4-student-iter275-39ch.pt`.

- [ ] **Step 1: FIXED-encoder screening eval** — champion vs anchor on the screening window (`--start-seed 910000 --online-episodes 120`, chongci flags as in prior gate runs), report → `/root/fh-mahjong-runs/spec-a/champion-fixed.json`.
- [ ] **Step 2: BUGGY-encoder paired run** — same command, same seeds, with the bridge built from the pre-fix commit (`git worktree add /root/fh-mahjong-prefix <pre-fix SHA>` and build its bridge; point `--bridge-library-path` at it), report → `/root/fh-mahjong-runs/spec-a/champion-buggy.json`.
- [ ] **Step 3: Verdict** — `uv run --project ai fh-mj-compare /root/fh-mahjong-runs/spec-a/champion-fixed.json /root/fh-mahjong-runs/spec-a/champion-buggy.json`. Apply the spec's decision rule: fixed ≥ buggy within the clustered CI → fix ships unconditionally (nothing more to build); fixed CI-worse → build the `--compat-double-count` serving flag (new task, spec §1) pinned to the current champion.
- [ ] **Step 4: Record** — append the paired result AND the measured `cluster_design_effect` of the screening window to `docs/rl-papers/chongci-rl-experiment-progress.md` (it calibrates Spec B's run sizes); commit the note to main per the progress-note convention.

---

## Verification (whole branch, before the PR gauntlet)

1. `go vet ./... && go test ./...` — clean.
2. `uv run --project ai pytest` — clean.
3. `uv run --project ai fh-mj-compare --help` — works.
4. `git diff origin/main --stat` — touches only: `internal/rl/observation.go`, `internal/rl/observation_test.go`, `internal/rl/AGENTS.md`, `ai/src/fh_mahjong_ai/evaluate.py`, `ai/src/fh_mahjong_ai/scripts/compare_reports.py`, `ai/tests/test_evaluate_clustered.py`, `ai/tests/test_compare_reports.py`, `ai/pyproject.toml`, `ai/AGENTS.md` (or deeper), `docs/rl-papers/chongci-rl-experiment-progress.md`, plus the spec and this plan.
