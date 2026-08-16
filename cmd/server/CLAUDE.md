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

- This is the main production binary. Run with the **package form** `go run ./cmd/server` (or `make run` / `make dev`). The file form `go run cmd/server/main.go` misses `policy_autostart.go` and fails to compile — `undefined: maybeStartPolicyServer`, `undefined: rlEndpointURL`, `undefined: installSignalCleanup`.
- Database config defaults: host=localhost, port=5432, user=fh_admin, dbname=fh_mahjong.
- Set `AI_BOT_POLICY_URL=http://host:port/act` to let empty seats call the served Python checkpoint policy. Leave it unset to use the deterministic heuristic bot.
- `RL_AGENT_POLICY_URL` / `RL_AGENT_SHADOW_POLICY_URL` / `RL_AGENT_CHECKPOINT_ID` / `RL_AGENT_AUTOSTART` / `RL_AGENT_SERVE_CMD` govern the private-room RL agent (see `policy_autostart.go`); `RL_AGENT_SHADOW_EVENT_WINDOW` (default 128) sets the shadow policy's event-history window.
- **Policy warmup** (`newRLWarmupHook`, `warmupTTL`): one process-wide `remote.WarmupManager` warms the primary and (when configured) shadow endpoints via `POST /warmup` before the first RL private table is admitted (`api.Matchmaker.WarmRLEndpoints`); a warmup failure refuses the table start (503) rather than letting RL seats silently fall back to the heuristic. `RL_AGENT_SHADOW_POLICY_TOKEN` must be set to the candidate service's `FH_MJ_EVALUATE_TOKEN` when that service is token-gated (`/warmup` reuses the evaluate token; empty = the service is tokenless and `/warmup` is open, which is the primary's posture). `RL_AGENT_WARMUP_TTL` (a `time.ParseDuration` string) re-warms an endpoint after it has been considered warm that long; **it defaults to `15m`** (unset, unparseable, or negative all yield the default) because the policy service restarts/redeploys independently — a warm-once manager would keep the gate green against a service that has since gone cold. Setting it explicitly to `0` disables the TTL (warm once per process). Attempts log grep-able `policy warmup:` lines.
- `RL_AGENT_EVENT_WINDOW` (parsed once in `main()` via `parseEventWindowEnv`, default 0, capped at `rl.MaxEventHistoryWindow`=512 — same family/semantics as `internal/api/review.go`'s `reviewEventWindow`) sets the event-history wire contract (`remote.WithEventWindow`) for BOTH primary remote policies: the `AI_BOT_POLICY_URL` matchmaking-bot policy and the RL primary in `SeatPolicyResolver`. The matchmaking-bot policy is a single shared `*remote.HTTPPolicy` instance (its seats don't feed per-seat paipu attribution). The RL primary is deliberately NOT shared: `SeatPolicyResolver` calls `newRLPrimaryPolicy()` to build a brand-new instance on every invocation, because `HTTPPolicy.DecisionCounts`/`ObservedPolicyIDs` are per-instance counters that `Room.reconcileRLPolicyIDs` (`internal/api/room.go`) reads to attribute each seat's paipu — a shared instance would let one seat's fallback/reload counters leak into every other room's dataset. rlHTTPClient (and its connection pool) is still shared across every RL-primary instance; only the counters/config are per-seat. The startup contract check below covers the shared config via one dedicated probe instance, not a per-seat validation.
- Every primary/shadow `*remote.HTTPPolicy` gets a one-shot, backgrounded `ValidateServer` healthz handshake at construction (`validatePolicyContractAsync`, 5s timeout): a mismatch or unreachable server logs loudly (`"POLICY CONTRACT MISMATCH / server unreachable"`) but never blocks boot or crashes — the policy server may not be up yet (autostart brings it up as a child process), and a real mismatch still fails closed at decision time via the heuristic fallback / `serve_policy`'s own 400s. For the RL primary this validation runs against one dedicated probe instance at boot (not one goroutine per seat) since it only exercises shared config (URL/window), not per-seat state.
