# cmd/play/

> Interactive terminal match: you take seat 0, heuristic bots take the rest.

## Overview

Plays a full `engine.Game` round in the terminal without the server runtime, database, or network.
Seat 0 is interactive; seats 1-3 are driven by the shared heuristic bot policy. Useful for
exercising the active-turn and interrupt decision paths by hand, and for sanity-checking ruleset
changes without a browser.

Renamed from `cmd/cli` in the 2026-08 naming refactor (Go renames): "cli" named the interface rather
than the job, and the old doc still advertised "offline hand evaluation" it does not do — that is
what `/tools/calc` and `internal/api`'s calc endpoint are for.

## Key Files

- **main.go** — entry point:
  - Starts a full `engine.Game` demo round
  - Leaves seat 0 interactive and drives seats 1-3 through the shared heuristic bot policy
  - Exercises both active-turn and interrupt decision paths without the server runtime

## Architecture Notes

- Does not require PostgreSQL or any network connectivity.
- Directly imports `internal/engine/`, `internal/rules/`, `proto/`, and the shared `internal/bot/` package.
- Run with `go run ./cmd/play` (package form — the file form omits sibling files in multi-file packages).
