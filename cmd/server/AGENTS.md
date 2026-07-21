# cmd/server/

> Production HTTP server entry point.

## Overview

Bootstraps the full backend: connects to PostgreSQL via GORM, initializes the WebSocket Hub and Matchmaker, registers API routes, and starts the Gin HTTP server on `:8080`.

## Key Files

- **main.go** — Server bootstrap:
  - PostgreSQL connection (configurable via env vars or defaults to localhost:5432)
  - `storage.AutoMigrate()` for schema setup
  - `api.Hub`, `api.Matchmaker` initialization
  - Optional `AI_BOT_POLICY_URL` wiring for Python-served remote AI bots on automated seats, with local heuristic fallback inside the remote policy
  - Route registration via `api.SetupRouter()`
  - Listens on `:8080`

## Architecture Notes

- This is the main production binary. Run with `go run cmd/server/main.go` (package form — `go run main.go` alone misses `policy_autostart.go`).
- Database config defaults: host=localhost, port=5432, user=fh_admin, dbname=fh_mahjong.
- Set `AI_BOT_POLICY_URL=http://host:port/act` to let empty seats call the served Python checkpoint policy. Leave it unset to use the deterministic heuristic bot.
- `RL_AGENT_POLICY_URL` / `RL_AGENT_SHADOW_POLICY_URL` / `RL_AGENT_CHECKPOINT_ID` / `RL_AGENT_AUTOSTART` / `RL_AGENT_SERVE_CMD` govern the private-room RL agent (see `policy_autostart.go`); `RL_AGENT_SHADOW_EVENT_WINDOW` (default 128) sets the shadow policy's event-history window.
- `RL_AGENT_EVENT_WINDOW` (parsed once in `main()` via `parseEventWindowEnv`, default 0, capped at `rl.MaxEventHistoryWindow`=512 — same family/semantics as `internal/api/review.go`'s `reviewEventWindow`) sets the event-history wire contract (`remote.WithEventWindow`) for BOTH primary remote policies: the `AI_BOT_POLICY_URL` matchmaking-bot policy and the RL primary in `SeatPolicyResolver`. Both are now built as a single shared `*remote.HTTPPolicy` instance (not one per bot/seat) so the startup contract check below only has to validate each once.
- Every primary/shadow `*remote.HTTPPolicy` gets a one-shot, backgrounded `ValidateServer` healthz handshake at construction (`validatePolicyContractAsync`, 5s timeout): a mismatch or unreachable server logs loudly (`"POLICY CONTRACT MISMATCH / server unreachable"`) but never blocks boot or crashes — the policy server may not be up yet (autostart brings it up as a child process), and a real mismatch still fails closed at decision time via the heuristic fallback / `serve_policy`'s own 400s.
