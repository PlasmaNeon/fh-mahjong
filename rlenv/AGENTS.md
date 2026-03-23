# rlenv/

> Deterministic RL environment wrapper around the Go game engine.

## Overview

This package keeps the authoritative simulator in Go while exposing a training-oriented interface: fixed action ids, seat-relative observations, deterministic seeded resets, step-to-next-decision flow control, and heuristic trajectory export.

## Key Files

- **action.go** — 204-action catalog plus action-mask generation and action encode/decode helpers.
- **observation.go** — Seat-relative observation encoder (`39 x 42 x 1` planes, 29 scalars) with no hidden-opponent tile leakage.
- **env.go** — `Env` wrapper with deterministic `Reset`, `Step`, and `GenerateHeuristicTrajectory`.
- **env_test.go** — Determinism, action round-trip, hidden-information, and trajectory-export tests.

## Architecture Notes

- `rlenv/` wraps `core.Game`; it must not fork rules or state-transition logic.
- Non-learning seats are automated through the shared Go heuristic bot when `auto_play_heuristics` is enabled.
- `advanceToDecision()` only resolves WAIT_DISCARDS automatically after verifying every pending interrupt seat has already queued a response; otherwise it returns an error instead of silently skipping input.
- Heuristic trajectory export keeps immediate step rewards in `TrajectorySample.rewards` and stores final round payouts separately in `TrajectorySample.terminal_rewards`.
- `FLOWER_REVEAL` is treated as a system action and is intentionally excluded from the agent action space.
