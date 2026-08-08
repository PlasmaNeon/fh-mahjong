# Heuristic Benchmark Eval — absolute-strength stat sheet (`fh-mj-benchmark`)

**Date:** 2026-08-07
**Status:** Approved design, pre-implementation

## Purpose

Measure a trained checkpoint's **absolute strength** by playing it against 3
deterministic heuristic bots and reporting Tenhou/Majsoul-style per-hand
outcome statistics. This is a **yardstick, not a gate**: the paired
head-to-head protocol (`fh-mj-compare`) remains the only promotion gate. The
heuristic bots are far weaker than the champion, so gate use would saturate
(ceiling effect); the value here is a human-readable, longitudinally
comparable stat sheet per checkpoint.

## Decisions (settled during brainstorm)

- **Role:** absolute yardstick, run on demand / at campaign milestones. No
  training-loop integration.
- **Metrics:** core four — win rate (和了率), deal-in rate (放铳率), avg win
  value, avg deal-in loss — plus what `evaluate_policy_online` already
  reports (reward, placement, outcome counts, bust/truncation).
- **Match mode:** chongci (the campaign/deployment mode). Multi-hand matches
  yield many per-hand samples per episode.
- **Runner:** new `fh-mj-benchmark` CLI, run manually (typically on the 4090
  box). Approach A: thin layer over `evaluate_policy_online`, no Go changes.

## Feasibility (verified on main)

- `evaluate_policy_online` (`ai/src/fh_mahjong_ai/evaluate.py`) already runs
  one policy seat vs 3 Go `HeuristicPolicy` bots (`auto_play_heuristics`)
  and accepts `event_history_window` — B2b event-history champions are
  supported.
- The Go bridge decodes per-hand `round_outcome` into step/reset `info`
  (`bridge.py:_decode_round_outcome`): `is_draw`, `winner_seat`, `win_type`,
  `discarder_seat`, `total_score`, and per-seat `payouts`. Everything the
  core four need is already visible Python-side.
- The envpool wrapper drops `round_outcome` (known trap) — this design uses
  the direct single-env loop and does not touch envpool.

## Metric definitions

All per-hand, for learning seat `s`. A **hand** is one non-truncated round
(one `round_outcome` observed at a hand boundary). Truncated episodes keep
the hands recorded up to truncation.

| Stat | Definition |
|---|---|
| Win rate 和了率 | hands with `winner_seat == s` and `not is_draw` / hands played |
| Deal-in rate 放铳率 | hands won by discard (ron-type `win_type`) with `discarder_seat == s` and `winner_seat != s` / hands played |
| Avg win value | mean of seat `s`'s payout amount over its winning hands |
| Avg deal-in loss | mean of \|seat `s`'s payout\| over its deal-in hands |
| Draw rate | `is_draw` hands / hands played |
| Hands per match | context stat |

Values come from actual `payouts`, so Fenghua liability rules (e.g. payer
liability amplification) are reflected automatically rather than
re-derived.

## Components

### 1. `evaluate_policy_online` extension (`evaluate.py`)

At each hand boundary where `info["round_outcome"]` is already read for
outcome counts, additionally append a per-hand record:
`(match_seed, winner_seat, discarder_seat, win_type, is_draw, seat_s_payout)`.
The returned report gains a `hand_stats` block:

```json
{
  "hand_stats": {
    "hands_played": 0,
    "wins": 0, "deal_ins": 0, "draws": 0,
    "win_rate": 0.0, "deal_in_rate": 0.0, "draw_rate": 0.0,
    "avg_win_value": 0.0, "avg_deal_in_loss": 0.0,
    "per_match_hands": [[/* per-hand records grouped by match */]]
  }
}
```

`per_match_hands` keeps raw records grouped by match so the CLI can
bootstrap at match level. Missing `round_outcome` on a boundary is counted
as `unknown` and logged with a warning. **No behavior change for existing
callers** — the block is additive.

### 2. CLI: `fh-mj-benchmark` (`scripts/benchmark.py`)

- Entry point `fh-mj-benchmark = fh_mahjong_ai.scripts.benchmark:main` in
  `ai/pyproject.toml`.
- Loads the checkpoint the same way existing eval scripts do: model config +
  `event_history_window` from checkpoint metadata; greedy/argmax action
  selection.
- Runs `evaluate_policy_online` once per learning seat 0–3 with **disjoint
  seed ranges** (seat rotation removes dealer/seat bias).
- Key flags (with defaults): `--checkpoint` (required),
  `--episodes-per-seat 100`, `--seed-base 0`, `--match-mode chongci`,
  chongci params matching training defaults, `--bridge-library-path`,
  `--out` (default `<checkpoint>.benchmark.json`), `--bootstrap-iters 1000`.
- Merges the four seat reports into overall + per-seat stats.

### 3. Uncertainty

95% CIs on every rate/value stat via **match-level bootstrap** (resample
matches with replacement, default 1000 iterations). Hands within a match
are correlated, so hand-level binomial CIs would be overconfident.

### 4. Output

- **Stdout:** compact table — rows per seat + overall; columns win rate
  和了率, deal-in rate 放铳率, avg win value, avg deal-in loss, each ±95% CI
  (Implementation note: 95% CIs are computed for the pooled overall only — per-seat CIs were consciously dropped as too wide to be useful at 100 matches/seat.);
  plus match-level context (avg placement, bust rate, hands/match).
- **JSON report** at `--out`: checkpoint path, resolved config, seed
  ranges, per-seat and overall `hand_stats` + CIs, and the existing
  match-level metrics — stable schema so successive champions' sheets are
  directly comparable.

## Error handling

- Boundary without `round_outcome` → counted in a separate `unknown_hands`
  tally with a warning logged; such hands are excluded from all rate
  denominators (`hands_played` counts only hands with an outcome record).
- Truncated matches: keep recorded hands, count truncation separately
  (already reported).
- Checkpoint missing metadata needed to reconstruct the model → hard error
  naming the missing field (no silent defaults), consistent with
  checkpoint-metadata invariants from the GRP campaign.

## Testing

- **Unit:** feed synthetic `round_outcome` info sequences through the
  accumulator — win / deal-in / draw / truncation / missing-outcome cases;
  payout-sign edge cases; grouping by match.
- **Bootstrap:** deterministic-seed test that CI bounds bracket the point
  estimate and behave sanely on a degenerate all-same-outcome input.
- **Smoke:** Go-bridge end-to-end test running a few tiny chongci matches,
  asserting the `hand_stats` block exists and its counts are internally
  consistent (wins + non-wins == hands_played, rates in [0,1]).

## Non-goals

- No promotion-gate wiring, no selfplay-loop hook.
- No envpool parallelization (would require fixing its `round_outcome`
  drop).
- No player-facing rating surface.
- No Go-side changes.
