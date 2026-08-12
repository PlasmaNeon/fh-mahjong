# cmd/

> Executable entry points for the project's Go binaries and compilation targets.

## Overview

Contains `main.go` files for each build target. The Go module now produces six distinct binaries: a production HTTP server, a CLI debugging tool, a WebAssembly module for browser-side validation, a c-shared RL bridge for Python training, an RL paipu fixture exporter for replay visualization, and a paipu-v2 rollout-gate smoke driver.

## Subdirectories

- **server/** — Production HTTP server (Gin + WebSocket, connects to PostgreSQL)
- **cli/** — Offline CLI tool for hand evaluation and game simulation, now using the shared heuristic bot for non-human seats
- **wasm/** — WebAssembly build (`GOOS=js GOARCH=wasm`) for client-side action validation
- **rlbridge/** — c-shared build target exposing protobuf-based RL environment functions to Python via `ctypes`
- **rlsmoke/** — Rollout-gate smoke driver against a LIVE server (local or production): registers a throwaway account, creates a private table, seats RL agents in every empty seat (exercising the health-gated policy resolution + CSRF-protected REST flow), starts a classic (single-hand) match, plays the host seat over the real WebSocket protocol with `bot.NewHeuristicPolicy` (mirroring the server bot pump: heuristic action on turn/claim, READY at round end), waits for `PHASE_MATCH_END`, requires the match to list under `/users/me/replays` (matches-table persistence), then fetches the paipu and verifies every paipu-v2 provenance gate: version 2, decision rows with non-empty legal-id sets containing the chosen id, explicit pass rows (`chosenId` 0), human rows for the host seat, remote rows all carrying a checkpoint sha256, zero `legalIdsError`, and `status: "completed"`. Exit 0 = gate satisfied (shadow-game accumulation may resume); anything else = not satisfied. First ran clean against production 2026-08-12 (match `5ad64d61…`, 29 decisions, 22 remote w/ sha). `verifyPaipu`'s per-gate failure behavior is pinned by table-driven tests in this package.
- **rlpaipu/** — Debug CLI that plays a deterministic heuristic round through `engine.Game` with `PaipuRecorder` attached and writes replay-viewer-compatible paipu JSON. Now records a paipu v2 `Decisions` supervision trace alongside the heuristic play (snapshotting legal ids/chosen id the same way `internal/api/room_decisions.go` does, labelled `source: "heuristic"`), so its output passes `internal/review`'s v2 decision cross-check; `TestGeneratedPaipuPassesReview` (in this package) pins that a freshly generated paipu round-trips clean through `review.ExtractDecisions`.
