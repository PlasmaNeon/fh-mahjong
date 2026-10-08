# cmd/play/

> Terminal match: you play seat 0, the heuristic bot plays seats 1–3.

`go run ./cmd/play`. Plays a full `engine.Game` round without the server, database, or network,
exercising both turn and interrupt decisions — handy for sanity-checking rule changes without a
browser. For scoring a specific hand use `/tools/calc` instead.

- **main.go** — the game loop; imports `internal/engine`, `internal/rules`, `internal/bot`, and
  `proto`.
