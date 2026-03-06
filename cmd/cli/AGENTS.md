# cmd/cli/

> CLI debugging tool for offline hand evaluation and game simulation.

## Overview

A command-line utility for testing hand evaluation and scoring without running the full server. Useful for verifying pattern recognition, debugging scoring edge cases, and rapid iteration on ruleset logic.

## Key Files

- **main.go** — CLI entry point:
  - Constructs tile hands programmatically
  - Calls `rules.HometownRuleset.EvaluateHand()` directly
  - Prints score breakdown to stdout

## Architecture Notes

- Does not require PostgreSQL, Redis, or any network connectivity.
- Directly imports `rules/` and `proto/` packages.
- Run with `go run cmd/cli/main.go`.
