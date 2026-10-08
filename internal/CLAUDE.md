# internal/

> All Go library packages (module-private: importable only from `github.com/plasma/fh-mahjong`).

| Package | Role |
|---------|------|
| `engine` | Game state machine (`Game`) and the `RuleEngine` interface; ruleset-agnostic |
| `rules` | `FenghuaRuleset`: hand evaluation, scoring, legality |
| `rules/shanten` | Route-by-route shanten and useful-tile analysis (rules, bot, RL observation, shanten API) |
| `api` | Gin REST + WebSocket server: auth, rooms, matchmaking, bot seats, persistence, review API |
| `storage` | GORM models (users, sessions, matches, paipu, reviews, imports, study jobs) and migrations |
| `bot` | Heuristic policy, policy interfaces, shadow wrapper |
| `bot/remote` | HTTP client that plays a seat through a Python policy server |
| `rl` | RL environment, observation encoder, 204-action catalog, env and search pools |
| `review` | Paipu → decisions → policy report and replay study |
| `tiles` | Shared tile keys, 0–33 index, wild sets, clones |

## Dependency rules

- `engine` never imports `rules`; `RuleEngine` is the only coupling.
- `tiles` imports only `proto`; `engine` does not use it.
- `rl` imports `bot`; `bot/remote` imports `rl` (hence the separate package).
- `review` may import `engine`, `rules`, `rl`, and `tiles`; it never feeds oracle observations.

How the packages fit together: [`docs/architecture.md`](../docs/architecture.md).
