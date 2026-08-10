# internal/bot/remote

> Remote non-human seat policies.

## Overview

This package adapts Python-served AI checkpoints to the Go bot policy interface. The Python service returns an `action_id`; this package always decodes that id through `rl.DecodeActionID` before returning a `PlayerAction`, so the Go engine remains the final legality authority.

## Key Files

- **health.go** — `HealthChecker` probes the policy endpoint's `GET /healthz` (derived from the `/act` URL) with a short-TTL cache. `Healthy()` gates the RL seat option; `Identity()` extracts the served checkpoint identity (basename-only `"<ckpt>@step<N>"` from the healthz JSON — paipu are public, never a path/URL; empty when unreported) used to label RL seats in the paipu/`MatchPlayer` rows.
- **http_policy.go** — HTTP JSON client for `fh-mj-serve-policy` with heuristic fallback on service errors, malformed responses, or illegal action ids. Tracks dataset provenance per policy instance: `ObservedPolicyIDs()` (distinct sanitized checkpoint identities that served validated actions — hot reloads add entries; bounded 8×256 chars) and `DecisionCounts()` (remote-served vs fallback decisions), both reconciled into the paipu at `Room.persistMatch`. It exposes `Stats()` counters for remote calls, remote successes, fallback totals, and fallback reason categories, and logs a periodic summary by default every 100 remote decisions.
  - **`ChooseActionCtxProv` (paipu v2, `bot.ProvenanceContextPolicy`)** — the
    single place remote/fallback outcomes are decided; `ChooseActionCtx`
    itself is now a thin wrapper that discards the provenance. Decodes the
    `/act` JSON response's `checkpoint_sha256` field (empty string on a
    legacy server that predates it — never an error) into
    `bot.DecisionProvenance{Source: "remote", CheckpointName, CheckpointStep,
    CheckpointSha}` atomically from the SAME response that produced the
    action id (never a separate `/healthz` read, which could race a
    `/reload`). Any fallback path returns `bot.DecisionProvenance{Source:
    "fallback", FallbackReason: <one of the 9 reasons>}` instead.
- **http_policy_test.go** — Tests for successful remote decisions, fallback behavior, fallback logging, and instrumentation counters.

## Architecture Notes

- This is a subpackage rather than part of `bot/` to avoid an import cycle: `rl` already imports `bot`, while remote AI policies need `rl` observation/action helpers.
- The fallback policy should remain deterministic and local. Use the shared heuristic policy unless a caller explicitly injects another fallback.
- Do not trust the Python service for legality. Decode every returned id against the current `GameState` and seat before applying it.
- Use `HTTPPolicy.Stats()` during live-table checks to verify the remote checkpoint is actually serving actions and not silently falling back to the heuristic path.
