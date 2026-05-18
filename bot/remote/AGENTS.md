# bot/remote

> Remote non-human seat policies.

## Overview

This package adapts Python-served AI checkpoints to the Go bot policy interface. The Python service returns an `action_id`; this package always decodes that id through `rlenv.DecodeActionID` before returning a `PlayerAction`, so the Go engine remains the final legality authority.

## Key Files

- **http_policy.go** — HTTP JSON client for `fh-mj-serve-policy` with heuristic fallback on service errors, malformed responses, or illegal action ids. It exposes `Stats()` counters for remote calls, remote successes, fallback totals, and fallback reason categories, and logs a periodic summary by default every 100 remote decisions.
- **http_policy_test.go** — Tests for successful remote decisions, fallback behavior, fallback logging, and instrumentation counters.

## Architecture Notes

- This is a subpackage rather than part of `bot/` to avoid an import cycle: `rlenv` already imports `bot`, while remote AI policies need `rlenv` observation/action helpers.
- The fallback policy should remain deterministic and local. Use the shared heuristic policy unless a caller explicitly injects another fallback.
- Do not trust the Python service for legality. Decode every returned id against the current `GameState` and seat before applying it.
- Use `HTTPPolicy.Stats()` during live-table checks to verify the remote checkpoint is actually serving actions and not silently falling back to the heuristic path.
