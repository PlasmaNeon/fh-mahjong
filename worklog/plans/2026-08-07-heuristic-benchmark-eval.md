# Heuristic Benchmark Eval (`fh-mj-benchmark`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `fh-mj-benchmark` CLI that plays a checkpoint greedily against 3 heuristic bots with seat rotation and reports Tenhou/Majsoul-style per-hand stats (win rate 和了率, deal-in rate 放铳率, avg win value, avg deal-in loss) with match-level bootstrap CIs, printed as a table and saved as JSON.

**Architecture:** A new pure-function module `hand_stats.py` classifies per-hand `round_outcome` dicts and computes summaries/bootstrap CIs. `evaluate_policy_online` (in `ai/src/fh_mahjong_ai/evaluate.py`) is extended additively to collect per-hand records from transition infos and return a `hand_stats` block. A new CLI script `scripts/benchmark.py` loads the checkpoint via serving's metadata-driven loader, runs the evaluator once per seat 0–3 with disjoint seeds, merges, bootstraps, prints, and writes JSON.

**Tech Stack:** Python 3 (`ai/` package, run via `uv run --project ai`), numpy, torch, pytest (unittest-style classes are also used in this suite), existing Go c-shared bridge (NO Go changes).

**Spec:** `worklog/specs/2026-08-07-heuristic-benchmark-eval-design.md`

## Global Constraints

- **No Go-side changes.** Everything reads the already-decoded `info["round_outcome"]` dicts (shape produced by `CtypesGoBridge._decode_round_outcome`: keys `is_draw`, `winner_seat`, `win_type`, `win_type_name`, `discarder_seat`, `total_score`, `payouts=[{seat, amount}]`).
- **`evaluate_policy_online` changes must be additive** — no existing report key changes, no behavior change for existing callers.
- This is a **yardstick, not a gate** — no selfplay-loop or promotion wiring.
- Run all Python tests from the repo root: `uv run --project ai pytest ai/tests/... -v`.
- Work on branch `feat/heuristic-benchmark` cut from current local `main` (which already carries the spec commit `7b061ae`).
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## Domain background (read once)

- One **episode** = one match. In chongci mode a match is many hands. The Go env delivers each finished hand's `RoundOutcome` on the next step response that reaches a learning-seat decision (`internal/rl/env.go` pending-outcome mechanism), so in Python each hand's outcome appears exactly once as `step_result.info["round_outcome"]` — and each `step_result.info` is stored on the `Transition` appended to `episode`. The match-ending hand's outcome rides on the terminal step. Consequently, **scanning `t.info.get("round_outcome")` over an episode's transitions yields exactly one record per delivered hand, terminal hand included.**
- Edge: a match can terminate directly at reset (`reset_result.terminated`); then `episode` is empty and the outcome is in `reset_result.info` (already passed to `record_episode` as the `outcome` parameter).
- Edge: the Go env *discards* a pending prior-hand outcome if no learning-seat decision occurs between that hand's end and MATCH_END (comment in `internal/rl/env.go:344-349`). Such hands are silently unobservable — this is why rates use *observed* hands as denominator.
- Win types: `win_type_name` is `"ACTION_TSUMO"` (self-draw) or `"ACTION_RON"` (win by discard). A **deal-in** is: not a draw, `win_type_name == "ACTION_RON"`, `discarder_seat == learning_seat`, `winner_seat != learning_seat`. This matches the existing `update_outcome_counts` classification in `evaluate.py:414-443`.
- Payouts are actual net amounts per seat (Fenghua liability rules already applied Go-side). The learning seat's win value / deal-in loss is its own entry in `payouts`.

---

### Task 1: `hand_stats.py` — per-hand classification, summary, bootstrap CI

**Files:**
- Create: `ai/src/fh_mahjong_ai/hand_stats.py`
- Test: `ai/tests/test_hand_stats.py`

**Interfaces:**
- Consumes: `round_outcome` dicts as decoded by the bridge (shape above).
- Produces (used by Tasks 2 and 3):
  - `hand_record(outcome: dict, learning_seat: int) -> dict` with keys `is_draw: bool, win: bool, deal_in: bool, win_type_name: str, payout: int`
  - `summarize_hand_stats(per_match_records: list[list[dict]], unknown_hands: int = 0) -> dict` with keys `matches, hands_played, unknown_hands, wins, deal_ins, draws, win_rate, deal_in_rate, draw_rate, avg_win_value, avg_deal_in_loss, hands_per_match` (`avg_win_value` / `avg_deal_in_loss` are `None` when there are no wins / deal-ins)
  - `bootstrap_hand_stats_ci(per_match_records: list[list[dict]], iters: int = 1000, seed: int = 0) -> dict[str, list[float] | None]` — 95% percentile CIs `[lo, hi]` for `win_rate, deal_in_rate, draw_rate, avg_win_value, avg_deal_in_loss`; `None` per-stat when undefined (e.g. <2 matches, or a stat with no samples)

- [ ] **Step 0: Create the branch**

```bash
git checkout main && git checkout -b feat/heuristic-benchmark
```

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_hand_stats.py`:

```python
import unittest

from fh_mahjong_ai.hand_stats import (
    bootstrap_hand_stats_ci,
    hand_record,
    summarize_hand_stats,
)


def _outcome(is_draw=False, winner=-1, discarder=-1, win_type="ACTION_TSUMO", payouts=()):
    return {
        "is_draw": is_draw,
        "winner_seat": winner,
        "win_type_name": win_type,
        "discarder_seat": discarder,
        "total_score": sum(abs(p["amount"]) for p in payouts),
        "payouts": list(payouts),
    }


class HandRecordTest(unittest.TestCase):
    def test_tsumo_win_for_learning_seat(self) -> None:
        rec = hand_record(
            _outcome(winner=0, win_type="ACTION_TSUMO",
                     payouts=[{"seat": 0, "amount": 24}, {"seat": 1, "amount": -8},
                              {"seat": 2, "amount": -8}, {"seat": 3, "amount": -8}]),
            learning_seat=0,
        )
        self.assertTrue(rec["win"])
        self.assertFalse(rec["deal_in"])
        self.assertFalse(rec["is_draw"])
        self.assertEqual(rec["payout"], 24)

    def test_deal_in_requires_ron_by_learning_seat_discard(self) -> None:
        rec = hand_record(
            _outcome(winner=2, discarder=0, win_type="ACTION_RON",
                     payouts=[{"seat": 2, "amount": 16}, {"seat": 0, "amount": -16}]),
            learning_seat=0,
        )
        self.assertTrue(rec["deal_in"])
        self.assertFalse(rec["win"])
        self.assertEqual(rec["payout"], -16)

    def test_other_seat_ron_is_not_deal_in(self) -> None:
        rec = hand_record(
            _outcome(winner=2, discarder=1, win_type="ACTION_RON",
                     payouts=[{"seat": 2, "amount": 16}, {"seat": 1, "amount": -16}]),
            learning_seat=0,
        )
        self.assertFalse(rec["deal_in"])
        self.assertFalse(rec["win"])
        self.assertEqual(rec["payout"], 0)  # seat 0 not in payouts

    def test_learning_seat_ron_win_is_win_not_deal_in(self) -> None:
        rec = hand_record(
            _outcome(winner=0, discarder=3, win_type="ACTION_RON",
                     payouts=[{"seat": 0, "amount": 16}, {"seat": 3, "amount": -16}]),
            learning_seat=0,
        )
        self.assertTrue(rec["win"])
        self.assertFalse(rec["deal_in"])

    def test_draw_hand(self) -> None:
        rec = hand_record(_outcome(is_draw=True), learning_seat=0)
        self.assertTrue(rec["is_draw"])
        self.assertFalse(rec["win"])
        self.assertFalse(rec["deal_in"])


class SummarizeHandStatsTest(unittest.TestCase):
    def _match(self):
        # One match: tsumo win (+24), deal-in (-16), draw.
        return [
            hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                 payouts=[{"seat": 0, "amount": 24}]), 0),
            hand_record(_outcome(winner=1, discarder=0, win_type="ACTION_RON",
                                 payouts=[{"seat": 1, "amount": 16},
                                          {"seat": 0, "amount": -16}]), 0),
            hand_record(_outcome(is_draw=True), 0),
        ]

    def test_summary_counts_and_rates(self) -> None:
        stats = summarize_hand_stats([self._match(), self._match()], unknown_hands=1)
        self.assertEqual(stats["matches"], 2)
        self.assertEqual(stats["hands_played"], 6)
        self.assertEqual(stats["unknown_hands"], 1)
        self.assertEqual(stats["wins"], 2)
        self.assertEqual(stats["deal_ins"], 2)
        self.assertEqual(stats["draws"], 2)
        self.assertAlmostEqual(stats["win_rate"], 2 / 6)
        self.assertAlmostEqual(stats["deal_in_rate"], 2 / 6)
        self.assertAlmostEqual(stats["draw_rate"], 2 / 6)
        self.assertAlmostEqual(stats["avg_win_value"], 24.0)
        self.assertAlmostEqual(stats["avg_deal_in_loss"], 16.0)
        self.assertAlmostEqual(stats["hands_per_match"], 3.0)

    def test_empty_input(self) -> None:
        stats = summarize_hand_stats([])
        self.assertEqual(stats["matches"], 0)
        self.assertEqual(stats["hands_played"], 0)
        self.assertEqual(stats["win_rate"], 0.0)
        self.assertIsNone(stats["avg_win_value"])
        self.assertIsNone(stats["avg_deal_in_loss"])

    def test_no_wins_yields_none_avg_win_value(self) -> None:
        match = [hand_record(_outcome(is_draw=True), 0)]
        stats = summarize_hand_stats([match])
        self.assertIsNone(stats["avg_win_value"])
        self.assertIsNone(stats["avg_deal_in_loss"])


class BootstrapCITest(unittest.TestCase):
    def test_ci_brackets_point_estimate_and_is_deterministic(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        loss = hand_record(_outcome(winner=1, discarder=0, win_type="ACTION_RON",
                                    payouts=[{"seat": 0, "amount": -10}]), 0)
        matches = [[win, loss], [win, win], [loss, loss], [win, loss], [win, win]]
        cis_a = bootstrap_hand_stats_ci(matches, iters=200, seed=7)
        cis_b = bootstrap_hand_stats_ci(matches, iters=200, seed=7)
        self.assertEqual(cis_a, cis_b)  # deterministic under a fixed seed
        point = summarize_hand_stats(matches)["win_rate"]
        lo, hi = cis_a["win_rate"]
        self.assertLessEqual(lo, point)
        self.assertGreaterEqual(hi, point)
        self.assertLessEqual(0.0, lo)
        self.assertLessEqual(hi, 1.0)

    def test_degenerate_all_same_outcome(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        cis = bootstrap_hand_stats_ci([[win], [win], [win]], iters=100, seed=1)
        self.assertEqual(cis["win_rate"], [1.0, 1.0])
        self.assertIsNone(cis["avg_deal_in_loss"])  # no deal-ins ever

    def test_fewer_than_two_matches_returns_none(self) -> None:
        win = hand_record(_outcome(winner=0, win_type="ACTION_TSUMO",
                                   payouts=[{"seat": 0, "amount": 20}]), 0)
        cis = bootstrap_hand_stats_ci([[win]], iters=100, seed=1)
        self.assertIsNone(cis["win_rate"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_hand_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'fh_mahjong_ai.hand_stats'`

- [ ] **Step 3: Implement `hand_stats.py`**

Create `ai/src/fh_mahjong_ai/hand_stats.py`:

```python
"""Per-hand Tenhou/Majsoul-style outcome statistics for heuristic benchmarking.

Consumes the ``round_outcome`` dicts decoded by ``CtypesGoBridge._decode_round_outcome``
(keys: ``is_draw``, ``winner_seat``, ``win_type``, ``win_type_name``,
``discarder_seat``, ``total_score``, ``payouts=[{seat, amount}]``). Payout amounts
are actual per-seat nets, so Fenghua liability rules are already reflected.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

_RON = "ACTION_RON"

_RATE_STATS = ("win_rate", "deal_in_rate", "draw_rate")
_VALUE_STATS = ("avg_win_value", "avg_deal_in_loss")
CI_STATS = _RATE_STATS + _VALUE_STATS


def hand_record(outcome: dict[str, Any], learning_seat: int) -> dict[str, Any]:
    """Classify one hand's outcome from the learning seat's perspective."""
    payout = 0
    for entry in outcome.get("payouts") or []:
        if int(entry.get("seat", -1)) == int(learning_seat):
            payout = int(entry.get("amount", 0))
            break
    is_draw = bool(outcome.get("is_draw", False))
    winner = int(outcome.get("winner_seat", -1))
    discarder = int(outcome.get("discarder_seat", -1))
    win_type_name = str(outcome.get("win_type_name", ""))
    win = (not is_draw) and winner == int(learning_seat)
    deal_in = (
        (not is_draw)
        and win_type_name == _RON
        and discarder == int(learning_seat)
        and winner != int(learning_seat)
    )
    return {
        "is_draw": is_draw,
        "win": win,
        "deal_in": deal_in,
        "win_type_name": win_type_name,
        "payout": payout,
    }


def summarize_hand_stats(
    per_match_records: list[list[dict[str, Any]]],
    unknown_hands: int = 0,
) -> dict[str, Any]:
    """Aggregate per-hand records (grouped by match) into the core stat sheet."""
    records = [rec for match in per_match_records for rec in match]
    hands = len(records)
    wins = sum(1 for r in records if r["win"])
    deal_ins = sum(1 for r in records if r["deal_in"])
    draws = sum(1 for r in records if r["is_draw"])
    win_values = [r["payout"] for r in records if r["win"]]
    deal_in_losses = [abs(r["payout"]) for r in records if r["deal_in"]]
    matches = len(per_match_records)
    return {
        "matches": matches,
        "hands_played": hands,
        "unknown_hands": int(unknown_hands),
        "wins": wins,
        "deal_ins": deal_ins,
        "draws": draws,
        "win_rate": wins / hands if hands else 0.0,
        "deal_in_rate": deal_ins / hands if hands else 0.0,
        "draw_rate": draws / hands if hands else 0.0,
        "avg_win_value": float(np.mean(win_values)) if win_values else None,
        "avg_deal_in_loss": float(np.mean(deal_in_losses)) if deal_in_losses else None,
        "hands_per_match": hands / matches if matches else 0.0,
    }


def bootstrap_hand_stats_ci(
    per_match_records: list[list[dict[str, Any]]],
    iters: int = 1000,
    seed: int = 0,
) -> dict[str, Optional[list[float]]]:
    """95% percentile CIs via match-level bootstrap.

    Matches (not hands) are resampled with replacement because hands within a
    match are correlated; hand-level binomial CIs would be overconfident.
    A stat with no defined value in the ORIGINAL sample (e.g. no deal-ins
    anywhere) gets ``None``; bootstrap iterations where a value stat has no
    samples are skipped for that stat.
    """
    matches = len(per_match_records)
    if matches < 2:
        return {stat: None for stat in CI_STATS}
    point = summarize_hand_stats(per_match_records)
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {stat: [] for stat in CI_STATS}
    for _ in range(int(iters)):
        indices = rng.integers(0, matches, size=matches)
        resampled = [per_match_records[i] for i in indices]
        stats = summarize_hand_stats(resampled)
        for stat in CI_STATS:
            value = stats[stat]
            if value is not None:
                samples[stat].append(float(value))
    cis: dict[str, Optional[list[float]]] = {}
    for stat in CI_STATS:
        if point[stat] is None or not samples[stat]:
            cis[stat] = None
        else:
            lo, hi = np.percentile(samples[stat], [2.5, 97.5])
            cis[stat] = [float(lo), float(hi)]
    return cis
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_hand_stats.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/hand_stats.py ai/tests/test_hand_stats.py
git commit -m "feat(ai): per-hand Tenhou-style stat accumulator with match-level bootstrap CIs

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: collect per-hand records in `evaluate_policy_online`

**Files:**
- Modify: `ai/src/fh_mahjong_ai/evaluate.py` (function `evaluate_policy_online`, currently lines 600–849; edits inside `record_episode` at ~667 and the return dict at ~794)
- Test: `ai/tests/test_evaluate.py` (append a new test class)

**Interfaces:**
- Consumes: `hand_record`, `summarize_hand_stats` from `fh_mahjong_ai.hand_stats` (Task 1).
- Produces (relied on by Task 3): the report returned by `evaluate_policy_online` gains two additive keys:
  - `"hand_stats"`: the `summarize_hand_stats(...)` dict
  - `"per_match_hand_records"`: `list[list[dict]]` — raw `hand_record` dicts grouped by match, for CLI-side merging and bootstrap
- No existing keys change. Existing callers are unaffected.

**How outcomes are extracted (from the domain background):** every delivered hand outcome sits in some transition's `info["round_outcome"]` (the terminal hand rides the terminal transition, which IS appended to `episode` before `record_episode` runs). Only the terminate-at-reset path has an empty `episode` with the outcome in the `outcome` parameter. Do NOT add the `outcome` parameter's record when `episode` is non-empty — that would double-count the terminal hand.

- [ ] **Step 1: Write the failing test**

Append to `ai/tests/test_evaluate.py` (imports at top of file already include `evaluate_policy_online`, `ActionChoice`, `Observation`; no new imports needed):

```python
class HandStatsCollectionTest(unittest.TestCase):
    def test_mock_bridge_episodes_report_empty_hand_stats_with_unknowns(self) -> None:
        # The mock bridge never emits round_outcome: every completed,
        # non-truncated episode is one unknown hand boundary.
        class FirstLegalPolicy:
            def choose(self, observation: Observation) -> ActionChoice:
                return ActionChoice(action_id=observation.legal_actions[0])

        report = evaluate_policy_online(
            policy=FirstLegalPolicy(),
            episodes=3,
            seeds=[1, 2, 3],
            bridge_kind="mock",
        )

        self.assertIn("hand_stats", report)
        self.assertIn("per_match_hand_records", report)
        stats = report["hand_stats"]
        self.assertEqual(stats["hands_played"], 0)
        self.assertEqual(stats["matches"], report["episodes"])
        self.assertEqual(stats["unknown_hands"], report["episodes"])
        self.assertEqual(len(report["per_match_hand_records"]), report["episodes"])
        self.assertTrue(all(m == [] for m in report["per_match_hand_records"]))
```

Also add a direct unit test of the extraction rule (same class), driving `record_episode` indirectly is awkward — instead test via synthetic transitions through the real loop is not possible on the mock bridge, so test the extraction helper directly. To make that possible, the implementation step factors extraction into a module-level function `_episode_round_outcomes(episode, outcome)` in `evaluate.py`:

```python
    def test_episode_round_outcomes_extraction_rules(self) -> None:
        from fh_mahjong_ai.evaluate import _episode_round_outcomes

        ro_a = {"is_draw": False, "winner_seat": 1, "win_type_name": "ACTION_RON",
                "discarder_seat": 0, "payouts": [{"seat": 0, "amount": -10}]}
        ro_b = {"is_draw": True, "winner_seat": -1, "win_type_name": "ACTION_UNKNOWN",
                "discarder_seat": -1, "payouts": []}

        def _t(info):
            o = _obs()
            return Transition(observation=o, action_id=5, rewards=np.zeros(4, np.float32),
                              next_observation=o, terminated=False, truncated=False,
                              info=info)

        # Mid-match + terminal outcomes come from transition infos; the
        # `outcome` param duplicates the terminal transition's info and must
        # NOT be re-added.
        episode = [_t({}), _t({"round_outcome": ro_a}), _t({}), _t({"round_outcome": ro_b})]
        self.assertEqual(_episode_round_outcomes(episode, ro_b), [ro_a, ro_b])
        # Terminate-at-reset: empty episode, outcome param is the only record.
        self.assertEqual(_episode_round_outcomes([], ro_a), [ro_a])
        # Nothing anywhere.
        self.assertEqual(_episode_round_outcomes([], None), [])
        self.assertEqual(_episode_round_outcomes([_t({})], None), [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -k "HandStats" -v`
Expected: FAIL — `KeyError: 'hand_stats'` and `ImportError`/`AttributeError` for `_episode_round_outcomes`

- [ ] **Step 3: Implement the collection**

In `ai/src/fh_mahjong_ai/evaluate.py`:

3a. Add to the existing import block near the top:

```python
from .hand_stats import hand_record, summarize_hand_stats
```

3b. Add a module-level helper (place it next to `update_outcome_counts`, ~line 414):

```python
def _episode_round_outcomes(
    episode: list[Transition],
    outcome: Optional[dict[str, Any]],
) -> list[dict[str, Any]]:
    """All hand outcomes delivered during one match, in order.

    Every delivered outcome sits in some transition's ``info["round_outcome"]``
    (the match-ending hand rides the terminal transition, which the caller
    appends before recording). The ``outcome`` parameter duplicates the
    terminal transition's info, so it is used ONLY when the episode has no
    transitions (terminate-at-reset) — adding it otherwise would double-count
    the final hand.
    """
    outcomes = [
        ro for t in episode
        if (ro := (t.info or {}).get("round_outcome")) is not None
    ]
    if not episode and outcome is not None:
        outcomes = [outcome]
    return outcomes
```

3c. Inside `evaluate_policy_online`, add accumulators next to the existing ones (~line 663, near `wins = 0`):

```python
    per_match_hand_records: list[list[dict[str, Any]]] = []
    unknown_hands = 0
```

3d. Inside `record_episode` (declare `nonlocal wins, large_losses, truncations, unknown_hands` — extend the existing `nonlocal` line), append after the `episode_summaries.append(...)` block:

```python
        hand_outcomes = _episode_round_outcomes(episode, outcome)
        per_match_hand_records.append(
            [hand_record(ro, learning_seat) for ro in hand_outcomes]
        )
        if not truncated and not hand_outcomes:
            # A completed match that delivered no outcome at all: count the
            # terminal boundary as unknown rather than silently shrinking
            # the denominator. (Truncations are already tallied separately.)
            unknown_hands += 1
```

3e. Add to the return dict (anywhere alongside the other keys, e.g. after `"round_outcome_rates"`):

```python
        "hand_stats": summarize_hand_stats(per_match_hand_records, unknown_hands),
        "per_match_hand_records": per_match_hand_records,
```

- [ ] **Step 4: Run the new tests, then the whole evaluate suite for regressions**

Run: `uv run --project ai pytest ai/tests/test_evaluate.py -v`
Expected: all PASS (new tests plus every pre-existing test untouched)

- [ ] **Step 5: Commit**

```bash
git add ai/src/fh_mahjong_ai/evaluate.py ai/tests/test_evaluate.py
git commit -m "feat(ai): evaluate_policy_online reports per-hand stat records (additive)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `fh-mj-benchmark` CLI

**Files:**
- Create: `ai/src/fh_mahjong_ai/scripts/benchmark.py`
- Modify: `ai/pyproject.toml` (add one line to `[project.scripts]`)
- Modify: `ai/AGENTS.md` (document the new command — follow the existing entry style for `fh-mj-evaluate`)
- Test: `ai/tests/test_benchmark.py`

**Interfaces:**
- Consumes:
  - `evaluate_policy_online(policy=..., episodes=..., seeds=..., learning_seat=..., match_mode=..., chongci_*=..., bridge_library_path=..., event_history_window=...)` from Task 2 (reads its `"hand_stats"` and `"per_match_hand_records"` keys plus existing `"mean_placement"`, `"truncation_rate"`, `"round_outcome_counts"`)
  - `summarize_hand_stats`, `bootstrap_hand_stats_ci` from Task 1
  - `CheckpointPolicy.from_checkpoint(path, device=...)` from `fh_mahjong_ai.serving` (metadata-driven architecture recovery; `.model` attribute; `.model.model_config.event_window`)
  - `TorchGreedyPolicy(model, device=...)` from `fh_mahjong_ai.policies` (greedy argmax; threads event histories when `model.wants_events`)
- Produces:
  - console entry point `fh-mj-benchmark`
  - `merge_seat_reports(seat_reports: dict[int, dict], bootstrap_iters: int, bootstrap_seed: int) -> dict` (module-level, unit-testable)
  - `format_stat_table(merged: dict) -> str` (module-level, unit-testable)
  - JSON report file (default `<checkpoint>.benchmark.json`)

- [ ] **Step 1: Write the failing tests**

Create `ai/tests/test_benchmark.py`:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from fh_mahjong_ai.hand_stats import hand_record
from fh_mahjong_ai.scripts import benchmark as benchmark_cli


def _win(seat=0, amount=20):
    return hand_record(
        {"is_draw": False, "winner_seat": seat, "win_type_name": "ACTION_TSUMO",
         "discarder_seat": -1, "payouts": [{"seat": seat, "amount": amount}]},
        learning_seat=seat,
    )


def _deal_in(seat=0, amount=-10):
    return hand_record(
        {"is_draw": False, "winner_seat": (seat + 1) % 4, "win_type_name": "ACTION_RON",
         "discarder_seat": seat, "payouts": [{"seat": seat, "amount": amount}]},
        learning_seat=seat,
    )


def _seat_report(seat, matches):
    from fh_mahjong_ai.hand_stats import summarize_hand_stats
    return {
        "seat": seat,
        "episodes": len(matches),
        "hand_stats": summarize_hand_stats(matches),
        "per_match_hand_records": matches,
        "mean_placement": 2.5,
        "truncation_rate": 0.0,
        "round_outcome_counts": {},
    }


class MergeSeatReportsTest(unittest.TestCase):
    def test_overall_pools_all_seats_matches(self) -> None:
        reports = {
            0: _seat_report(0, [[_win(0)], [_deal_in(0)]]),
            1: _seat_report(1, [[_win(1)], [_win(1)]]),
            2: _seat_report(2, [[_deal_in(2)], [_deal_in(2)]]),
            3: _seat_report(3, [[_win(3)], [_deal_in(3)]]),
        }
        merged = benchmark_cli.merge_seat_reports(reports, bootstrap_iters=50, bootstrap_seed=3)
        self.assertEqual(merged["overall"]["hand_stats"]["matches"], 8)
        self.assertEqual(merged["overall"]["hand_stats"]["hands_played"], 8)
        self.assertAlmostEqual(merged["overall"]["hand_stats"]["win_rate"], 4 / 8)
        self.assertAlmostEqual(merged["overall"]["hand_stats"]["deal_in_rate"], 4 / 8)
        self.assertIn("ci95", merged["overall"])
        self.assertIsNotNone(merged["overall"]["ci95"]["win_rate"])
        self.assertEqual(set(merged["per_seat"].keys()), {0, 1, 2, 3})
        self.assertAlmostEqual(merged["per_seat"][1]["hand_stats"]["win_rate"], 1.0)

    def test_table_renders_core_four_and_seats(self) -> None:
        reports = {s: _seat_report(s, [[_win(s)], [_deal_in(s)]]) for s in range(4)}
        merged = benchmark_cli.merge_seat_reports(reports, bootstrap_iters=50, bootstrap_seed=3)
        table = benchmark_cli.format_stat_table(merged)
        self.assertIn("win rate", table)
        self.assertIn("deal-in rate", table)
        self.assertIn("overall", table)
        self.assertIn("seat 0", table)
        self.assertIn("seat 3", table)


class MainTest(unittest.TestCase):
    def test_main_runs_four_seats_and_writes_json(self) -> None:
        matches_by_seat = {s: [[_win(s)], [_deal_in(s)]] for s in range(4)}
        calls = []

        def fake_eval(**kwargs):
            calls.append(kwargs)
            return _seat_report(kwargs["learning_seat"], matches_by_seat[kwargs["learning_seat"]])

        fake_model = mock.Mock()
        fake_model.model_config.event_window = 32
        fake_model.wants_events = True
        fake_policy = mock.Mock(model=fake_model)

        with TemporaryDirectory() as tmp:
            ckpt = Path(tmp) / "champion.pt"
            ckpt.write_bytes(b"fake")
            with mock.patch.object(
                benchmark_cli.CheckpointPolicy, "from_checkpoint", return_value=fake_policy,
            ) as load, mock.patch.object(
                benchmark_cli, "evaluate_policy_online", side_effect=fake_eval,
            ), mock.patch.object(
                benchmark_cli, "TorchGreedyPolicy", return_value=mock.Mock(),
            ):
                benchmark_cli.main([
                    "--checkpoint", str(ckpt),
                    "--episodes-per-seat", "2",
                    "--seed-base", "100",
                    "--bootstrap-iters", "50",
                ])

            load.assert_called_once()
            self.assertEqual([c["learning_seat"] for c in calls], [0, 1, 2, 3])
            # Disjoint seed ranges: 2 episodes/seat from base 100.
            self.assertEqual(calls[0]["seeds"], [100, 101])
            self.assertEqual(calls[1]["seeds"], [102, 103])
            self.assertEqual(calls[3]["seeds"], [106, 107])
            # Event window flows from checkpoint metadata, chongci is default.
            self.assertTrue(all(c["event_history_window"] == 32 for c in calls))
            self.assertTrue(all(c["match_mode"] == "chongci" for c in calls))

            out = Path(str(ckpt) + ".benchmark.json")
            self.assertTrue(out.exists())
            payload = json.loads(out.read_text())
            self.assertEqual(payload["checkpoint"], str(ckpt))
            self.assertEqual(payload["episodes_per_seat"], 2)
            self.assertIn("overall", payload)
            self.assertIn("per_seat", payload)
            self.assertIn("ci95", payload["overall"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --project ai pytest ai/tests/test_benchmark.py -v`
Expected: FAIL — `ImportError: cannot import name 'benchmark'`

- [ ] **Step 3: Implement the CLI**

Create `ai/src/fh_mahjong_ai/scripts/benchmark.py`:

```python
"""Absolute-strength benchmark: a checkpoint vs 3 heuristic bots, Tenhou-style stats.

A YARDSTICK, not a gate (the heuristic bots are far weaker than the champion,
so gate use would saturate). The paired protocol (fh-mj-compare /
fh-mj-evaluate --duplicate-seats) remains the promotion gate.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Optional, Sequence

from fh_mahjong_ai.evaluate import evaluate_policy_online
from fh_mahjong_ai.hand_stats import CI_STATS, bootstrap_hand_stats_ci, summarize_hand_stats
from fh_mahjong_ai.policies import TorchGreedyPolicy
from fh_mahjong_ai.serving import CheckpointPolicy

_SEATS = (0, 1, 2, 3)


def merge_seat_reports(
    seat_reports: dict[int, dict[str, Any]],
    bootstrap_iters: int,
    bootstrap_seed: int,
) -> dict[str, Any]:
    """Pool all seats' matches into overall stats + CIs; keep per-seat sheets."""
    pooled: list[list[dict[str, Any]]] = []
    unknown = 0
    per_seat: dict[int, dict[str, Any]] = {}
    for seat, report in sorted(seat_reports.items()):
        pooled.extend(report["per_match_hand_records"])
        unknown += int(report["hand_stats"]["unknown_hands"])
        per_seat[seat] = {
            "hand_stats": report["hand_stats"],
            "mean_placement": report.get("mean_placement"),
            "truncation_rate": report.get("truncation_rate"),
            "round_outcome_counts": report.get("round_outcome_counts", {}),
        }
    overall_stats = summarize_hand_stats(pooled, unknown)
    ci95 = bootstrap_hand_stats_ci(pooled, iters=bootstrap_iters, seed=bootstrap_seed)
    return {
        "overall": {"hand_stats": overall_stats, "ci95": ci95},
        "per_seat": per_seat,
    }


def _fmt_rate(value: Optional[float], ci: Optional[list[float]] = None) -> str:
    if value is None:
        return "n/a"
    text = f"{value * 100:.1f}%"
    if ci is not None:
        text += f" [{ci[0] * 100:.1f}, {ci[1] * 100:.1f}]"
    return text


def _fmt_value(value: Optional[float], ci: Optional[list[float]] = None) -> str:
    if value is None:
        return "n/a"
    text = f"{value:.1f}"
    if ci is not None:
        text += f" [{ci[0]:.1f}, {ci[1]:.1f}]"
    return text


def format_stat_table(merged: dict[str, Any]) -> str:
    """Human-readable stat sheet: one row per seat plus pooled overall."""
    header = (
        f"{'':<10}{'win rate 和了率':<28}{'deal-in rate 放铳率':<28}"
        f"{'avg win value':<22}{'avg deal-in loss':<22}{'hands':>7}"
    )
    lines = [header, "-" * len(header)]
    for seat, entry in sorted(merged["per_seat"].items()):
        stats = entry["hand_stats"]
        lines.append(
            f"{f'seat {seat}':<10}"
            f"{_fmt_rate(stats['win_rate']):<28}"
            f"{_fmt_rate(stats['deal_in_rate']):<28}"
            f"{_fmt_value(stats['avg_win_value']):<22}"
            f"{_fmt_value(stats['avg_deal_in_loss']):<22}"
            f"{stats['hands_played']:>7}"
        )
    overall = merged["overall"]["hand_stats"]
    ci = merged["overall"]["ci95"]
    lines.append("-" * len(header))
    lines.append(
        f"{'overall':<10}"
        f"{_fmt_rate(overall['win_rate'], ci['win_rate']):<28}"
        f"{_fmt_rate(overall['deal_in_rate'], ci['deal_in_rate']):<28}"
        f"{_fmt_value(overall['avg_win_value'], ci['avg_win_value']):<22}"
        f"{_fmt_value(overall['avg_deal_in_loss'], ci['avg_deal_in_loss']):<22}"
        f"{overall['hands_played']:>7}"
    )
    lines.append(
        f"matches={overall['matches']}  hands/match={overall['hands_per_match']:.1f}  "
        f"draw rate={_fmt_rate(overall['draw_rate'], ci['draw_rate'])}  "
        f"unknown hands={overall['unknown_hands']}"
    )
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark a checkpoint vs 3 heuristic bots (absolute-strength "
                    "yardstick; NOT a promotion gate)")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--episodes-per-seat", type=int, default=100,
                        help="matches per seat; the policy plays every seat 0-3")
    parser.add_argument("--seed-base", type=int, default=1000,
                        help="first seed; seats use disjoint consecutive ranges")
    parser.add_argument("--match-mode", type=str, default="chongci",
                        choices=("chongci", "classic"))
    parser.add_argument("--chongci-starting-score", type=int, default=2000)
    parser.add_argument("--chongci-bust-threshold", type=int, default=0)
    parser.add_argument("--chongci-max-hands", type=int, default=50)
    parser.add_argument("--bridge-library-path", type=Path, default=None)
    parser.add_argument("--device", type=str, default="cpu")
    parser.add_argument("--bootstrap-iters", type=int, default=1000)
    parser.add_argument("--bootstrap-seed", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None,
                        help="JSON report path (default: <checkpoint>.benchmark.json)")
    args = parser.parse_args(argv)

    if args.episodes_per_seat < 1:
        parser.error("--episodes-per-seat must be >= 1")
    if args.bootstrap_iters < 1:
        parser.error("--bootstrap-iters must be >= 1")

    # Metadata-driven load: architecture (incl. event window) is recovered from
    # the checkpoint itself — no model flags to get wrong. Missing/odd payloads
    # fail loudly inside the loader (checkpoint-metadata invariants).
    checkpoint_policy = CheckpointPolicy.from_checkpoint(args.checkpoint, device=args.device)
    model = checkpoint_policy.model
    event_window = int(model.model_config.event_window)
    policy = TorchGreedyPolicy(model, device=args.device)

    seat_reports: dict[int, dict[str, Any]] = {}
    for seat in _SEATS:
        start = args.seed_base + seat * args.episodes_per_seat
        seeds = list(range(start, start + args.episodes_per_seat))
        print(f"[benchmark] seat {seat}: {args.episodes_per_seat} {args.match_mode} "
              f"matches, seeds {seeds[0]}..{seeds[-1]}", flush=True)
        seat_reports[seat] = evaluate_policy_online(
            policy=policy,
            episodes=args.episodes_per_seat,
            seeds=seeds,
            bridge_library_path=args.bridge_library_path,
            learning_seat=seat,
            match_mode=args.match_mode,
            chongci_starting_score=args.chongci_starting_score,
            chongci_bust_threshold=args.chongci_bust_threshold,
            chongci_max_hands=args.chongci_max_hands,
            event_history_window=event_window,
        )

    merged = merge_seat_reports(seat_reports, args.bootstrap_iters, args.bootstrap_seed)

    out_path = args.out if args.out is not None else Path(str(args.checkpoint) + ".benchmark.json")
    payload = {
        "checkpoint": str(args.checkpoint),
        "match_mode": args.match_mode,
        "chongci_config": {
            "starting_score": args.chongci_starting_score,
            "bust_threshold": args.chongci_bust_threshold,
            "max_hands": args.chongci_max_hands,
        },
        "episodes_per_seat": args.episodes_per_seat,
        "seed_base": args.seed_base,
        "event_history_window": event_window,
        "bootstrap": {"iters": args.bootstrap_iters, "seed": args.bootstrap_seed},
        "overall": merged["overall"],
        "per_seat": {str(seat): entry for seat, entry in merged["per_seat"].items()},
    }
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print()
    print(format_stat_table(merged))
    print(f"\nreport written to {out_path}")


if __name__ == "__main__":
    main()
```

3b. Add the entry point to `ai/pyproject.toml` under `[project.scripts]` (after the `fh-mj-evaluate` line):

```toml
fh-mj-benchmark = "fh_mahjong_ai.scripts.benchmark:main"
```

3c. Update `ai/AGENTS.md`: add `fh-mj-benchmark` to whatever list documents the console commands, one entry in the same style as its neighbors, stating: benchmark a checkpoint vs 3 heuristic bots with seat rotation; Tenhou-style per-hand stats + match-level bootstrap CIs; yardstick not a gate; writes `<checkpoint>.benchmark.json`. Also check `ai/src/fh_mahjong_ai/scripts/AGENTS.md` (if it exists) and add the script there in matching style.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --project ai pytest ai/tests/test_benchmark.py -v`
Expected: all PASS. (If the `mock.patch.object(benchmark_cli.CheckpointPolicy, ...)` patch fails because of import style, patch `benchmark_cli.CheckpointPolicy.from_checkpoint` via `mock.patch("fh_mahjong_ai.scripts.benchmark.CheckpointPolicy.from_checkpoint", ...)` instead — same effect.)

- [ ] **Step 5: Reinstall entry points and smoke the console script wiring**

Run: `uv run --project ai fh-mj-benchmark --help`
Expected: argparse help text listing `--checkpoint`, `--episodes-per-seat`, `--bootstrap-iters` (uv re-syncs the editable install automatically; if the command is not found, run `uv sync --project ai` once and retry).

- [ ] **Step 6: Commit**

```bash
git add ai/src/fh_mahjong_ai/scripts/benchmark.py ai/tests/test_benchmark.py ai/pyproject.toml ai/AGENTS.md
git commit -m "feat(ai): fh-mj-benchmark CLI — absolute-strength stat sheet vs heuristic bots

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(Include `ai/src/fh_mahjong_ai/scripts/AGENTS.md` in the `git add` if it exists and was edited.)

---

### Task 4: full-suite verification and real-bridge smoke run

**Files:**
- No new files. This task verifies the branch end-to-end.

**Interfaces:**
- Consumes: everything above.
- Produces: a green test suite and (if a bridge library + checkpoint are available locally) one real benchmark run demonstrating non-zero `hands_played`.

- [ ] **Step 1: Run the entire ai test suite**

Run: `uv run --project ai pytest ai/tests/ -x -q`
Expected: all PASS, no regressions.

- [ ] **Step 2: Run Go tests (sanity — no Go code changed)**

Run: `go test ./...` (from repo root)
Expected: all PASS.

- [ ] **Step 3: Real-bridge smoke run (best-effort)**

If a built bridge library and a champion checkpoint are available on this machine (champion checkpoints live in `/Users/plasma/fh-mahjong-models/`; the bridge library is wherever `resolve_bridge_library` finds it — check how other local runs pass `--bridge-library-path`), run a tiny benchmark:

```bash
uv run --project ai fh-mj-benchmark \
  --checkpoint /Users/plasma/fh-mahjong-models/<champion>.pt \
  --episodes-per-seat 2 --chongci-max-hands 8 --bootstrap-iters 100
```

Expected: a printed table with `hands_played > 0`, `unknown hands` near 0, and a `<checkpoint>.benchmark.json` file. If no library/checkpoint is available locally, note that the smoke run is deferred to the 4090 box and move on — the mocked tests still gate the merge.

**Delete the smoke-run JSON afterwards** (it sits next to the real checkpoint): `rm /Users/plasma/fh-mahjong-models/<champion>.pt.benchmark.json`

- [ ] **Step 4: Commit any AGENTS.md stragglers and stop**

The branch is complete. Integration (PR creation and merge) happens via superpowers:finishing-a-development-branch — per user preference, a PR merged with `gh pr merge N --merge` (never squash/rebase).

---

## Self-review notes (already applied)

- **Spec coverage:** metric definitions → Task 1; `hand_stats` block in `evaluate_policy_online` → Task 2; CLI, seat rotation, disjoint seeds, metadata-driven load, JSON + table, bootstrap CIs → Task 3; smoke/regression → Task 4. Non-goals (no gate wiring, no envpool, no Go changes) respected throughout.
- **Deviation from spec, intentional:** the spec's `hand_stats.per_match_hands` field is implemented as the sibling report key `per_match_hand_records` (cleaner: `hand_stats` stays a pure summary; raw records live next to the other raw per-episode report keys like `per_episode_rewards`). The JSON report nests per-seat entries under string keys for JSON compatibility.
- **Type consistency:** `hand_record` dict keys (`is_draw`, `win`, `deal_in`, `win_type_name`, `payout`) match between Tasks 1–3; `summarize_hand_stats` key set matches its uses in `format_stat_table` and tests; `CI_STATS` covers exactly the five stats formatted with CIs.
