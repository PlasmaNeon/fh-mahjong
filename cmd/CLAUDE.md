# cmd/

> Go entry points. Run each as a package (`go run ./cmd/<name>`); several are multi-file.

| Directory | Binary |
|---|---|
| `server/` | Production HTTP + WebSocket server |
| `play/` | Terminal match: you in seat 0, heuristic bots in seats 1–3 |
| `wasm/` | WebAssembly build of the ruleset's valid-action query (not loaded by the frontend) |
| `rlbridge/` | c-shared library exposing the RL environment, env pool, and search pool to Python |
| `rlpaipu/` | Writes a deterministic heuristic paipu (with a v2 decision trace) for the replay viewer |
| `rlsmoke/` | Plays a real match against a live server and verifies paipu v2 provenance |

Each subdirectory's `CLAUDE.md` has flags and gotchas.
