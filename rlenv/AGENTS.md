# rlenv/

> Deterministic RL environment wrapper around the Go game engine.

## Overview

This package keeps the authoritative simulator in Go while exposing a training-oriented interface: fixed action ids, seat-relative observations, deterministic seeded resets, step-to-next-decision flow control, and heuristic trajectory export.

## Key Files

- **action.go** — 204-action catalog plus action-mask generation and action encode/decode helpers. `DecodeActionID` is exported so serving clients can validate remote policy ids through the same legality map used by the RL bridge.
- **observation.go** — Seat-relative observation encoder (`39 x 42 x 1` planes, 58 scalars) with no hidden-opponent tile leakage. `EncodeObservation` is exported for remote-policy clients that need the same visible input format as Python training.
- **env.go** — `Env` wrapper with deterministic `Reset`, `Step`, `EvaluateBranches`, and `GenerateHeuristicTrajectory`.
  - Terminal responses include `RoundOutcome` metadata for winner, win type, discarder, draw flag, score, and payouts.
  - In Chongci mode, `Env.Step` / `advanceToDecision` returns a dense per-step reward from `scoreDeltaReward`: the acting seat's running-score delta since the previous decision, which telescopes exactly to the match net-change.
  - `EvaluateBranches` clones the live `core.Game`, applies each candidate action from the current learning-seat decision, then lets deterministic heuristics finish the branch to create same-state counterfactual labels without mutating the live environment.
  - Branch requests can stop at the next round end for multi-hand modes, returning hand payout labels from the current visible match context instead of rolling every candidate to full Chongci match end.
- **action_test.go** — Fixed action/tile-index mapping tests; tile faces follow the backend shanten order `man, pin, sou, jihai, flower`.
- **env_test.go** — Determinism, action round-trip, hidden-information, and trajectory-export tests.

## Architecture Notes

- `rlenv/` wraps `core.Game`; it must not fork rules or state-transition logic.
- Non-learning seats are automated through the shared Go heuristic bot when `auto_play_heuristics` is enabled.
- `EnvConfig.match_mode = MATCH_MODE_CHONGCI` starts the core engine with Chongci options and treats `PHASE_MATCH_END` as the terminal RL state.
- During Chongci generation/evaluation, `advanceToDecision()` auto-acks `ROUND_END` ready gates so an episode can span multiple hands until bust or hand cap.
- Chongci `Reset(seed)` derives a deterministic wall seed for each later hand before the final ready ack starts the next round; same episode seed plus same policy must replay the same multi-hand match.
- Chongci terminal rewards are final score net change divided by 1000, matching the scale of classic single-hand payout rewards.
- Classic mode rewards are unchanged: intermediate `Score` stays 0 and round end still returns `roundRewards`.
- `advanceToDecision()` only resolves WAIT_DISCARDS automatically after verifying every pending interrupt seat has already queued a response; otherwise it returns an error instead of silently skipping input.
- `advanceToDecision()` must resolve an already-ready WAIT_DISCARDS window even when `AutoPlayHeuristics` is disabled, because all-four-seat heuristic trajectory export records each seat as a learning seat and can otherwise stall after queued interrupt responses.
- Tile-face indices in observations and tile-specific action ids use the same order as the rules/shanten backend: `man(0-8), pin(9-17), sou(18-26), jihai(27-33), flower(34-41)`.
- Scalar features include overall and route-specific shanten, ukeire, discard look-ahead, wild preservation, visible score potential, and public danger heuristics.
- Scalar indices 42-57 carry Chongci/match-context features: mode flag, hand progress, remaining hand fraction, rank strength, leader pressure, large-loss safety margin, own bust safety, opponent large-loss pressure, normalized score/net progress, relative score gaps, next-rank pressure, lower-rank cushion, and public current-hand threat.
- Heuristic trajectory export keeps immediate step rewards in `TrajectorySample.rewards` and stores final payouts/outcomes separately in `TrajectorySample.terminal_rewards` and `TrajectorySample.terminal_outcome`; Chongci `GenerateHeuristicTrajectory` keeps each sample's `TerminalRewards` equal to `matchEndRewards`, so offline return-shaping remains match net-change based.
- Branch evaluation through `advanceToTerminalWithHeuristics` is unchanged by Chongci dense per-step rewards.
- `FLOWER_REVEAL` is treated as a system action and is intentionally excluded from the agent action space.
- Tile-type keys, the 0-33 index, and proto Tile/Action deep-clones come from the shared `tiles` package (`github.com/plasma/fh-mahjong/tiles`) — do not re-inline `suit*100+value` or re-add local `cloneTile`/`cloneAction`.
