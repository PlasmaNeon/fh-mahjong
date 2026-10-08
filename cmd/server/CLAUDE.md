# cmd/server/

> The production HTTP server.

Connects to Postgres, runs `storage.AutoMigrate`, builds the Hub and Matchmaker, wires bot and
RL policies, registers routes, and serves on `:8080` (or `PORT`).

## Key files

- **main.go** — bootstrap, database, policy wiring, drain on SIGINT/SIGTERM.
- **policy_autostart.go** — starts `uv run --project ai fh-mj-serve-policy` as a child process
  when the RL endpoint is the localhost default (`RL_AGENT_AUTOSTART=0` disables;
  `RL_AGENT_SERVE_CMD` overrides the command).

## Notes

- Run the package: `go run ./cmd/server` (or `make run` / `make dev`). The file form
  `go run cmd/server/main.go` omits `policy_autostart.go` and fails to compile.
- Database: `DATABASE_URL`, else `host=localhost port=5433 user=fh_admin dbname=fh_mahjong` (the
  docker-compose database).
- Policy wiring (variables in [`docs/architecture.md`](../../docs/architecture.md)):
  - `AI_BOT_POLICY_URL` routes public-queue bot seats through one shared `remote.HTTPPolicy`;
    unset means the heuristic bot. `AI_BOT_EVENT_WINDOW` sets its window.
  - The private-room RL seat uses `RL_AGENT_POLICY_URL` (else `AI_BOT_POLICY_URL`, else
    localhost) with `RL_AGENT_EVENT_WINDOW` (default 0, max `rl.MaxEventHistoryWindow` = 512).
    Each RL seat gets a fresh `HTTPPolicy` so per-seat counters do not mix across rooms; the HTTP
    client is shared.
  - `RL_AGENT_SHADOW_POLICY_URL` (+ `_EVENT_WINDOW`, default 128, and `_TOKEN`) wraps each RL
    seat in a `bot.ShadowPolicy`.
  - One `remote.WarmupManager` warms the primary and shadow endpoints before an RL table starts;
    `RL_AGENT_WARMUP_TTL` (default `15m`; `0` = once per process) re-warms after that long,
    because the policy service restarts independently.
  - Every remote policy gets a background `/healthz` contract check at startup. A mismatch or an
    unreachable server logs `POLICY CONTRACT MISMATCH / server unreachable` but never blocks boot.
