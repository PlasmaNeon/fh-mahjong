# cmd/

> Executable entry points for the project's Go binaries and compilation targets.

## Overview

Contains `main.go` files for each build target. The Go module now produces five distinct binaries: a production HTTP server, a CLI debugging tool, a WebAssembly module for browser-side validation, a c-shared RL bridge for Python training, and an RL paipu fixture exporter for replay visualization.

## Subdirectories

- **server/** — Production HTTP server (Gin + WebSocket, connects to PostgreSQL/Redis)
- **cli/** — Offline CLI tool for hand evaluation and game simulation, now using the shared heuristic bot for non-human seats
- **wasm/** — WebAssembly build (`GOOS=js GOARCH=wasm`) for client-side action validation
- **rlbridge/** — c-shared build target exposing protobuf-based RL environment functions to Python via `ctypes`
- **rlpaipu/** — Debug CLI that plays a deterministic heuristic round through `core.Game` with `PaipuRecorder` attached and writes replay-viewer-compatible paipu JSON.
