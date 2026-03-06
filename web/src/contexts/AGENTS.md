# web/src/contexts/

> React context providers for WebSocket connection and game state synchronization.

## Overview

Provides global state management via React Context API. Two providers wrap the entire app: one for the WebSocket connection and one for the decoded game state. All child components access these via hooks.

## Key Files

- **SocketContext.tsx** — WebSocket connection provider:
  - `useSocket()` hook — Returns the active WebSocket instance
  - Manages connection lifecycle (connect, reconnect, cleanup)
  - Sends/receives binary Protobuf messages

- **GameContext.tsx** — Game state provider:
  - `useGameState()` hook — Returns the current decoded `GameState`
  - Listens to WebSocket `onmessage`, decodes Protobuf with `game.GameState.decode()`
  - Tracks `mySeatId` (which seat this client controls)

## Architecture Notes

- Provider nesting order: `SocketProvider` → `GameProvider` (game depends on socket).
- State updates are immediate — no debouncing or batching. Every server broadcast triggers a re-render.
- The `GameState` object matches the Protobuf schema exactly (via `protobufjs` codegen).
