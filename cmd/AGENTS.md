# cmd/

> Executable entry points for the project's three compilation targets.

## Overview

Contains `main.go` files for each build target. The Go module produces three distinct binaries: a production HTTP server, a CLI debugging tool, and a WebAssembly module for browser-side validation.

## Subdirectories

- **server/** — Production HTTP server (Gin + WebSocket, connects to PostgreSQL/Redis)
- **cli/** — Offline CLI tool for hand evaluation and game simulation
- **wasm/** — WebAssembly build (`GOOS=js GOARCH=wasm`) for client-side action validation
