# Route study: when the AI goes Independence

Measure when the policy pursues Independence (十三不搭/大大胡) versus the standard 4 sets + pair,
as charts a human can learn from. Two outputs:

1. **Deal chart** — route shanten at the deal → which route the hand ended on, how it won, payout.
2. **Fork statistics** — at discards where Independence and standard want different tiles, which
   side the policy takes; at chii/pon offers that would end Independence, whether it calls.

Raw per-decision records are kept so a later rule-card fit (decision tree) needs no rerun.

Base: PR #266 (`RoundOutcome.breakdown`, strong-table benchmark). Branch `feat/route-study`.

## Run

`fh-mj-benchmark --route-study`, same table and seeds as the 2026-10-01 anchor075 entry:
`ckpt/saug-ext-iter150.pt` with `--symmetry-average suits` vs 3× `ckpt/anchor075.pt` (greedy),
chongci, 400 matches per seat, `--seed-base 1000`, `--workers 10` (~50 min CPU).

All four seats are recorded, split into the benchmark's existing sides: `learner` (current best)
and `opponents` (anchor075). Against heuristic bots (no `--opponent-checkpoint`) the bots play
inside the Go env, so only the learner is recorded.

## Definitions

| Term | Definition |
|---|---|
| Routes | `standard`, `seven_pairs`, `independence`. Shanten from `shanten.AnalyzeHand` on the seat's closed hand, wilds included. `99` = unavailable (seat has an open meld). |
| Decision shanten | Route shanten of the seat's closed hand at a decision. At a discard decision (14 tiles) it equals the best shanten one discard can reach on that route. |
| After shanten | For one legal discard: route shanten of the 13 tiles left (`DiscardOption.After`). |
| Deal | The seat's first discard decision of the hand. |
| Turn | 1 + the number of the seat's discard decisions the recorder saw earlier in the hand. |
| `win_route` | From the winning `RoundOutcome.breakdown`: `independence` if `independence` is present (seven stars and missing-suit always ride on it); else `seven_pairs` if `straight_seven_pairs` or `wild_seven_pairs`; else `special` if any all-honors or eight-flowers pattern; else `standard`. `none` when the seat did not win. |
| `end_route` | At the seat's last decision of the hand: the unique route with the lowest decision shanten, `tie` if the lowest is shared, `standard` once the seat has an open meld. |
| Fork | A discard decision with no open melds where the discards minimizing after-Independence shanten and the discards minimizing after-standard shanten are disjoint sets. |
| Fork side | `independence` if the chosen discard is in the Independence-best set, `standard` if in the standard-best set, else `neither`. The raw record also flags whether it minimizes after-seven-pairs shanten. |
| Call offer | A decision whose legal actions include chii or pon and not ron, with no open melds. `called` = the chosen action is chii, pon or kan. |

## Components

1. **Proto** (`proto/game.proto`): `RouteShanten {overall, standard, seven_pairs, independence}`,
   `DiscardRoute {action_id, after: RouteShanten, is_wild}`, `RouteProbeRequest {seat}`,
   `RouteProbe {seat, routes, discards[], wild_count, open_meld_count}`. Regenerate Go, TS and
   Python bindings.
2. **`internal/rl`**: `(*Env).RouteProbe(seat) (*pb.RouteProbe, error)`. Runs
   `shanten.AnalyzeHand` on the seat's closed hand (same call as the observation encoder). Emits one
   `DiscardRoute` per legal discard action of that seat (`DiscardBase + FaceIndex42`), mapped from
   `DiscardOptions` by tile key; empty when the seat has no discard action. Read-only: never
   mutates the game.
3. **`cmd/rlbridge`**: export `FHEnvRouteProbe(handle, request)`.
4. **`ai/.../bridge.py`**: `CtypesGoBridge.route_probe(seat) -> dict`. The mock bridge does not
   implement it; route study requires the Go bridge.
5. **`ai/.../route_study.py`** (new):
   - `RouteStudyRecorder(learning_seat, probe_fn, shard_path)` with
     `on_decision(observation, action_id)` (probes before the action is applied),
     `on_hand_end(round_outcome)`, `on_match_end(truncated)`, `summary()`.
   - Per seat it keeps the open hand's deal shanten, turn count and last decision shanten; at hand
     end it emits one hand record per seat and folds it into the aggregates.
   - A match that truncates drops its open hand and counts it in `truncated_hands`.
   - `merge_route_study(summaries)` sums aggregates; `format_route_study(summary)` prints charts.
   - Raw records (`kind`: `hand` / `fork` / `call`, with seed, seat, side, hand index) stream to a
     gzip JSONL shard.
6. **`evaluate.py`**: `evaluate_policy_online(..., route_study_shard=None)`. When set, builds the
   recorder with `bridge.route_probe`, calls it for every seat's decision, and adds
   `route_study` to the report. When unset the loop and report are unchanged.
7. **`scripts/benchmark.py`**: `--route-study` flag. Each chunk writes
   `<out stem>.route-study/seat{S}-seeds{a}-{b}.jsonl.gz`; `overall.route_study` is the merged
   summary; charts print after the win-pattern table.

## Aggregates (`overall.route_study.<side>`)

Shanten buckets clip to `0..6` (`6` = 6+, `-1` → `0`); `-` = unavailable.

- `deal[std][indep]`, and `deal_by_wilds[0|1|2+][std][indep]`: `hands`, `end_<route>` (incl.
  `end_tie`), `win_<route>` (incl. `win_special`), `deal_ins`, `payout_sum`.
- `fork[gap][turn]`: gap = Independence − standard decision shanten, clipped `-3..+3`; turn
  buckets `1-3`, `4-6`, `7-9`, `10+`. Counts `forks`, `independence`, `standard`, `neither`.
- `call[indep]`: `offers`, `called`.
- `hands_recorded`, `hands_without_deal` (hand ended before the seat's first discard),
  `truncated_hands`.

Printed per side: deal pivots of "% won by Independence (n)", "% ended on Independence", and
"mean payout"; fork pivot of "% Independence side (n)"; call row of "% called (n)".

## Testing

- Go: `RouteProbe` on a fixed state with an Independence-shaped 14-tile hand — routes equal
  `AnalyzeHand`, one entry per legal discard with the right action ids, the env's next observation
  is byte-identical before and after the probe.
- Python: bridge decode test; recorder unit tests on synthetic probes — fork disjoint vs
  overlapping sets, `end_route` tie and open-meld cases, `win_route` mapping (seven stars →
  `independence`), turn counting, truncation drop, merge sums.
- Benchmark: report without the flag unchanged (existing golden tests); a 4-match run with the
  flag writes shards and `route_study`.
- CI gates per root `CLAUDE.md`.

## Out of scope

Rule-card / decision-tree fit, paired current-vs-anchor divergence examples, review-UI route
labels, value or EV comparison between routes, the batched pool evaluator.

## Reading the result

Descriptive only: shows what the policy chooses, not by how much one route beats the other, and
the table is all bots. Results go to `worklog/rl-experiment/chongci-rl-experiment-progress.md`.
