# rlenv/

> Deterministic RL environment wrapper around the Go game engine.

## Overview

This package keeps the authoritative simulator in Go while exposing a training-oriented interface: fixed action ids, seat-relative observations, deterministic seeded resets, step-to-next-decision flow control, and heuristic trajectory export.

## Key Files

- **action.go** — 204-action catalog plus action-mask generation and action encode/decode helpers.
- **observation.go** — Seat-relative observation encoder (`39 x 42 x 1` planes, 29 scalars) with no hidden-opponent tile leakage.
- **env.go** — `Env` wrapper with deterministic `Reset`, `Step`, and `GenerateHeuristicTrajectory`.
  - Terminal responses include `RoundOutcome` metadata for winner, win type, discarder, draw flag, score, and payouts.
- **action_test.go** — Fixed action/tile-index mapping tests; tile faces follow the backend shanten order `man, pin, sou, jihai, flower`.
- **env_test.go** — Determinism, action round-trip, hidden-information, and trajectory-export tests.

## Architecture Notes

- `rlenv/` wraps `core.Game`; it must not fork rules or state-transition logic.
- Non-learning seats are automated through the shared Go heuristic bot when `auto_play_heuristics` is enabled.
- `advanceToDecision()` only resolves WAIT_DISCARDS automatically after verifying every pending interrupt seat has already queued a response; otherwise it returns an error instead of silently skipping input.
- Tile-face indices in observations and tile-specific action ids use the same order as the rules/shanten backend: `man(0-8), pin(9-17), sou(18-26), jihai(27-33), flower(34-41)`.
- Heuristic trajectory export keeps immediate step rewards in `TrajectorySample.rewards` and stores final round payouts/outcomes separately in `TrajectorySample.terminal_rewards` and `TrajectorySample.terminal_outcome`.
- `FLOWER_REVEAL` is treated as a system action and is intentionally excluded from the agent action space.
