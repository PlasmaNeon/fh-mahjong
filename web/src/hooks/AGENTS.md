# web/src/hooks/

> Custom React hooks.

## Overview

Contains reusable React hooks for the application. Currently focused on WASM integration for client-side game validation.

## Key Files

- **useMahjongWasm.ts** — Hook to load and interact with the Go WASM module:
  - Loads `mahjong.wasm` from the public directory
  - Initializes the Go WASM runtime (`wasm_exec.js`)
  - Exposes hand evaluation and action validation functions to React components
  - Returns loading state and callable functions

## Architecture Notes

- The WASM module is compiled from `cmd/wasm/main.go`.
- Loading is async — components should check the loading state before calling WASM functions.
- Used for client-side prediction (zero-latency feedback); server always re-validates.
