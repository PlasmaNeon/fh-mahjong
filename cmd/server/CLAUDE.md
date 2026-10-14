# cmd/server/

> The production HTTP server.

Connects to Postgres, runs `storage.AutoMigrate`, builds the Hub and Matchmaker, wires bot and
RL policies, registers routes, and serves on `:8080` (or `PORT`).

## Key files

- **main.go** — bootstrap, database, queue watchers, HTTP startup, drain on SIGINT/SIGTERM.
- **policy_wiring.go** — `configurePolicies`, policy factories, event-window parsing, health
  checks, and warmup; returns cleanup for the optional managed policy child.
- **rl_agents.go** — the private-room RL agent registry: `parseRLAgents` (`RL_AGENTS`),
  `legacyRLAgent`, and `rlAgentSet` (one `remote.HealthChecker` per agent; `Infos`, `Identity`,
  `Resolver`, `WarmHook`), used by `configurePolicies`.
- **policy_autostart.go** — starts `uv run --project ai fh-mj-serve-policy` as a child process
  when the RL endpoint is the localhost default (`RL_AGENT_AUTOSTART=0` disables;
  `RL_AGENT_SERVE_CMD` overrides the command).

## Notes

- Run the package: `go run ./cmd/server` (or `make run` / `make dev`). The file form
  `go run cmd/server/main.go` omits `policy_wiring.go` and `policy_autostart.go`, leaving
  `configurePolicies` and `installSignalCleanup` undefined.
- Database: `DATABASE_URL`, else `host=localhost port=5433 user=fh_admin dbname=fh_mahjong` (the
  docker-compose database).
- Policy wiring (variables in [`docs/architecture.md`](../../docs/architecture.md)):
  - `AI_BOT_POLICY_URL` routes public-queue bot seats through one shared `remote.HTTPPolicy`;
    unset means the heuristic bot. `AI_BOT_EVENT_WINDOW` sets its window.
  - Private-room RL agents come from `RL_AGENTS`, a JSON array in menu order (first = default):
    `[{"id":"v4","label":"AI v4","url":"http://…/act","eventWindow":128}, …]`. Ids match
    `^[a-z0-9-]{1,32}$` and are unique; any invalid entry is fatal at startup. Unset, there is
    one legacy agent `rl` ("AI") at `RL_AGENT_POLICY_URL` (else `AI_BOT_POLICY_URL`, else
    localhost) with `RL_AGENT_EVENT_WINDOW` (default 0, max `rl.MaxEventHistoryWindow` = 512).
  - Each agent has one health checker (availability incl. the event-window contract, and the
    paipu identity; `RL_AGENT_CHECKPOINT_ID` labels the legacy agent when `/healthz` reports
    none). Each RL seat gets a fresh `HTTPPolicy` for its agent so per-seat counters do not mix
    across rooms; the HTTP client is shared.
  - `RL_AGENT_SHADOW_POLICY_URL` (+ `_EVENT_WINDOW`, default 128, and `_TOKEN`) wraps the
    default agent's seats in a `bot.ShadowPolicy`.
  - One `remote.WarmupManager` warms exactly the agents a table seats (and the shadow with the
    default agent) before it starts; `RL_AGENT_WARMUP_TTL` (default `15m`; `0` = once per
    process) re-warms after that long, because policy services restart independently.
  - The local policy server autostarts only for the legacy localhost agent (`RL_AGENTS` unset).
  - Every remote policy gets a background `/healthz` contract check at startup. A mismatch or an
    unreachable server logs `POLICY CONTRACT MISMATCH / server unreachable` but never blocks boot.
