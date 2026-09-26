# cmd/wasm/

> WebAssembly build target exposing the Fenghua ruleset's valid-action query to JavaScript.

## Overview

Compiles `rules.FenghuaRuleset` to WebAssembly (`GOOS=js GOARCH=wasm`). **The frontend does not
load it**: `web/src/hooks/useMahjongWasm.ts` has no importers, and the client takes legal actions
from the server's `PlayerState.valid_actions`.

## Key Files

- **main.go** — registers two globals via `syscall/js`:
  - `mahjongInit()` — returns `"Wasm Ready"`
  - `mahjongGetValidActions(stateBytes, seat)` — unmarshals a `GameState` and returns the seat's valid `ActionType` ints

## Architecture Notes

- Build: `GOOS=js GOARCH=wasm go build -o web/public/mahjong.wasm ./cmd/wasm`. Needs `wasm_exec.js` (Go WASM runtime) in `web/public/`.
- The `js && wasm` build tag excludes the package from native builds, so `go build ./...` / `go test ./...` skip it.
