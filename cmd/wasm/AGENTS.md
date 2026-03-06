# cmd/wasm/

> WebAssembly build target for client-side game validation in the browser.

## Overview

Compiles the Go game engine to WebAssembly (`GOOS=js GOARCH=wasm`) so the browser can validate player actions locally before sending them to the server. This enables zero-latency feedback on legal moves while the server performs authoritative re-validation.

## Key Files

- **main.go** — WASM entry point:
  - Exports Go functions to JavaScript via `syscall/js`
  - Exposes hand evaluation and valid action checking
  - Bridges `rules.HometownRuleset` to browser JS

## Architecture Notes

- Build command: `GOOS=js GOARCH=wasm go build -o web/public/mahjong.wasm cmd/wasm/main.go`
- Requires `wasm_exec.js` (Go WASM runtime) in the frontend public directory.
- Cannot be built with standard `go build` (requires WASM build tags). Tests will show `[setup failed]` — this is expected.
- The frontend loads this via `web/src/hooks/useMahjongWasm.ts`.
