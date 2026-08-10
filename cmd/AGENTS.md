# cmd/

> Executable entry points for the project's Go binaries and compilation targets.

## Overview

Contains `main.go` files for each build target. The Go module now produces five distinct binaries: a production HTTP server, a CLI debugging tool, a WebAssembly module for browser-side validation, a c-shared RL bridge for Python training, and an RL paipu fixture exporter for replay visualization.

## Subdirectories

- **server/** — Production HTTP server (Gin + WebSocket, connects to PostgreSQL)
- **cli/** — Offline CLI tool for hand evaluation and game simulation, now using the shared heuristic bot for non-human seats
- **wasm/** — WebAssembly build (`GOOS=js GOARCH=wasm`) for client-side action validation
- **rlbridge/** — c-shared build target exposing protobuf-based RL environment functions to Python via `ctypes`
- **rlpaipu/** — Debug CLI that plays a deterministic heuristic round through `engine.Game` with `PaipuRecorder` attached and writes replay-viewer-compatible paipu JSON. Now records a paipu v2 `Decisions` supervision trace alongside the heuristic play (snapshotting legal ids/chosen id the same way `internal/api/room_decisions.go` does, labelled `source: "heuristic"`), so its output passes `internal/review`'s v2 decision cross-check; `TestGeneratedPaipuPassesReview` (in this package) pins that a freshly generated paipu round-trips clean through `review.ExtractDecisions`.
