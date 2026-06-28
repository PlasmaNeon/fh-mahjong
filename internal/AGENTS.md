# internal/

All Go library packages live here, enforcing Go's `internal/` visibility boundary (only importable by code rooted at `github.com/plasma/fh-mahjong`). Entry points (`cmd/`) import from here; nothing outside this module can.

## Package Map

| Package | Import path | Description |
|---------|-------------|-------------|
| `engine` | `…/internal/engine` | Game state machine (`Game` struct) and `RuleEngine` interface. Ruleset-agnostic: must never import `internal/rules/`. |
| `rules` | `…/internal/rules` | Fenghua (`HometownRuleset`) scoring and hand evaluation plugin. Implements `engine.RuleEngine`. |
| `rules/shanten` | `…/internal/rules/shanten` | Shanten-number and tile-efficiency analysis used by the rules engine and bot. |
| `api` | `…/internal/api` | Gin-based REST + gorilla/websocket server. Bridges HTTP/WS clients to `engine.Game` sessions. |
| `storage` | `…/internal/storage` | GORM database models (`User`, `Match`) and DB initialisation. |
| `bot` | `…/internal/bot` | Deterministic heuristic bot policies used by CLI, empty seats, and RL bootstrapping. |
| `bot/remote` | `…/internal/bot/remote` | HTTP client wrapper that drives an external policy server (e.g. Python RL model) as a bot player. |
| `rl` | `…/internal/rl` | Deterministic RL environment wrapper (`Env`), observation encoder, and fixed 204-action catalog. |
| `tiles` | `…/internal/tiles` | Shared low-level tile helpers (keying, cloning) used across engine, rules, bot, and rl. |

## Invariants

- `internal/engine` **must not** import `internal/rules` — the `RuleEngine` interface is the only coupling point.
- All packages here are module-private (`internal/`). External projects cannot import them.
