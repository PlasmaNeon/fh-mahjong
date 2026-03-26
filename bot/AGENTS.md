# bot/

> Deterministic non-human seat policies.

## Overview

This package hosts server-side and CLI bot logic. Policies consume a `GameState`, seat index, and the legal actions already populated by the core engine, then return one concrete `PlayerAction`. The initial implementation is a deterministic heuristic bot built on top of the shared shanten analysis package.

## Key Files

- **heuristic.go** — Heuristic baseline policy:
  - prioritizes `TSUMO`, `RON`, and `ACCEPT_HAITEI`
  - ranks discards using shanten, useful tiles, route damage, and simple shape heuristics
  - respects haitei turn restrictions by discarding only the accepted haitei tile when no tsumo is available
  - simulates `CHII` / `PON` follow-up discards before deciding to call
  - applies conservative `KAN` rules that avoid wild tiles and unstable hand shapes
  - clones protobuf actions/tiles field-by-field to avoid copying generated message mutex state
- **heuristic_test.go** — Coverage for discard ranking, route preservation, call choices, and legality.

## Architecture Notes

- The package intentionally stays outside `core/` so the state machine remains ruleset-agnostic.
- Policies only rely on state already produced by the engine; they do not re-implement rules or mutate the game directly.
- The same policy should be reused by CLI demos, server-side empty seats, and future RL self-play data generation.
