# cmd/cli/

> CLI debugging tool for offline hand evaluation and game simulation.

## Overview

A command-line utility for testing hand evaluation and scoring without running the full server. Useful for verifying pattern recognition, debugging scoring edge cases, and rapid iteration on ruleset logic.

## Key Files

- **main.go** — CLI entry point:
  - Starts a full `core.Game` demo round
  - Leaves seat 0 interactive and drives seats 1-3 through the shared heuristic bot policy
  - Exercises both active-turn and interrupt decision paths without the server runtime

## Architecture Notes

- Does not require PostgreSQL, Redis, or any network connectivity.
- Directly imports `core/`, `rules/`, `proto/`, and the shared `bot/` package.
- Run with `go run cmd/cli/main.go`.
