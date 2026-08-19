# cmd/

> Executable entry points for the project's Go binaries and compilation targets.

## Overview

Contains `main.go` files for each build target. The Go module now produces six distinct binaries: a production HTTP server, a CLI debugging tool, a WebAssembly module for browser-side validation, a c-shared RL bridge for Python training, an RL paipu fixture exporter for replay visualization, and a paipu-v2 rollout-gate smoke driver.

## Subdirectories

- **server/** — Production HTTP server (Gin + WebSocket, connects to PostgreSQL)
- **play/** — Interactive terminal match: seat 0 is you, seats 1-3 are the shared heuristic bot (renamed from `cli/` in 2026-08)
- **wasm/** — WebAssembly build (`GOOS=js GOARCH=wasm`) for client-side action validation
- **rlbridge/** — c-shared build target exposing protobuf-based RL environment functions to Python via `ctypes`
- **rlsmoke/** — Paipu-v2 rollout-gate smoke driver against a LIVE server: plays a real match end-to-end over the real protocol, then verifies every provenance gate. Exit 0 = gate satisfied. See [rlsmoke/CLAUDE.md](rlsmoke/CLAUDE.md).
- **rlpaipu/** — Debug CLI that plays a deterministic heuristic round offline and writes replay-viewer-compatible paipu JSON, including a paipu-v2 decision trace. See [rlpaipu/CLAUDE.md](rlpaipu/CLAUDE.md).

Each subdirectory has its own `CLAUDE.md` with entry-point detail, flags, and gotchas.
