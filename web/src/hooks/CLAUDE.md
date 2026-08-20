# web/src/hooks/

> Custom React hooks.

## Overview

Reusable React hooks. The fixed-stage layout hook that used to live here moved to
`web/src/table/stage/` in PR 2, so this directory is now only the WASM loader.

## Key Files

- **useMahjongWasm.ts** — Hook to load and interact with the Go WASM module:
  - Loads `mahjong.wasm` from the public directory
  - Initializes the Go WASM runtime (`wasm_exec.js`)
  - Exposes hand evaluation and action validation functions to React components
  - Returns loading state and callable functions

  **Currently unreferenced.** No component imports it; the client-side prediction path it was
  written for is not wired up. Kept pending a decision on whether to revive or delete it.

## Architecture Notes

- The WASM module is compiled from `cmd/wasm/main.go`.
- Loading is async — components should check the loading state before calling WASM functions.
