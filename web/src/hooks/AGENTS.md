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

- **useGameStageLayout.ts** — Hook for the live game’s fixed-stage layout:
  - Observes the available shell size with `ResizeObserver`
  - Computes a uniform scale for the 1600x900 landscape game board
  - Returns stage dimensions, scaled bounds, and centered offsets so `Game.tsx` can keep the whole table locked to one coordinate system during resize/orientation changes

## Architecture Notes

- The WASM module is compiled from `cmd/wasm/main.go`.
- Loading is async — components should check the loading state before calling WASM functions.
- Used for client-side prediction (zero-latency feedback); server always re-validates.
- `useGameStageLayout.ts` is intentionally live-game-specific rather than a generic layout hook; it exists to stop seat/hand/discard drift by scaling a fixed DOM stage as one unit instead of reflowing each region from viewport units.
