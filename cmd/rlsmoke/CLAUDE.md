# cmd/rlsmoke/

> Paipu-v2 rollout-gate smoke driver against a LIVE server (local or production).

## Overview

End-to-end gate that plays a real match over the real protocol and then verifies every paipu-v2 provenance guarantee. **Exit 0 means the gate is satisfied and shadow-game accumulation may resume; anything else means it is not.**

It exercises the whole stack rather than mocking any of it:

1. Registers a throwaway account.
2. Creates a private table.
3. Seats RL agents in every empty seat — exercising health-gated policy resolution plus the CSRF-protected REST flow.
4. Starts a classic (single-hand) match.
5. Plays the host seat over the real WebSocket protocol with `bot.NewHeuristicPolicy`, mirroring the server bot pump (heuristic action on turn/claim, `READY` at round end).
6. Waits for `PHASE_MATCH_END`.
7. Requires the match to list under `/users/me/replays` — that is the matches-table persistence check.
8. Fetches the paipu and verifies the provenance gates below.

## Usage

```bash
go run ./cmd/rlsmoke                                    # against localhost:8080
go run ./cmd/rlsmoke -base-url https://<prod-host> -timeout 15m
```

| Flag | Default | Meaning |
|---|---|---|
| `-base-url` | `http://localhost:8080` | Server base URL (http/https) |
| `-mode` | `classic` | Match mode for the smoke table (classic = single hand, fastest) |
| `-timeout` | `10m` | Overall deadline for the whole smoke |

## The provenance gates

`verifyPaipu` requires **all** of:

- paipu `version` is 2
- decision rows carry non-empty legal-id sets, each containing the chosen id
- explicit pass rows are present (`chosenId` 0)
- human rows exist for the host seat
- remote rows all carry a `checkpoint` sha256
- zero `legalIdsError`
- `status: "completed"`

First ran clean against production 2026-08-12 (match `5ad64d61…`, 29 decisions, 22 remote with sha).

## Key Files

- **main.go** — `run()` drives the sequence above; `postJSON`/`postProtoJSON`/`getJSON` are the REST helpers, `dialWS` opens the authenticated socket, `playToMatchEnd` is the bot pump, `waitForReplayListing` polls the replay index, and `verifyPaipu` applies the gates.
- **main_test.go** — table-driven tests pinning `verifyPaipu`'s **per-gate failure behavior**, so a gate cannot silently stop failing.

## Architecture Notes

- This talks to a live server; it is not part of `go test ./...` coverage of the engine. Treat a failure as "the deployed stack is not gate-clean", not "the code does not compile".
- Sibling to `cmd/rlpaipu`, which generates a paipu fixture offline instead of verifying a live one.
- Paipu-v2 background: `docs/superpowers/specs/2026-08-09-paipu-v2-provenance-design.md`.
