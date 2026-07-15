# web/src/contexts/

> React context providers for WebSocket connection and game state synchronization.

## Overview

Provides global state management via React Context API. Authentication bootstraps first, followed by the cookie-authenticated WebSocket and decoded game state.

## Key Files

- **AuthContext.tsx** — Loads `GET /api/v1/auth/session`, keeps the user and CSRF token in memory, adds credentials/CSRF to API mutations, separates `401` from offline bootstrap failures, and revokes only the current session on successful logout
- **SocketContext.tsx** — WebSocket connection provider:
  - `useSocket()` hook — Returns the active WebSocket instance
  - Manages connection lifecycle (connect, reconnect, cleanup)
  - Sends/receives binary Protobuf messages
  - Opens `/api/v1/ws` without query credentials; the browser supplies the HttpOnly session cookie

- **GameContext.tsx** — Game state provider:
  - `useGameState()` hook — Returns the current decoded `GameState`
  - Listens to WebSocket `onmessage`, decodes Protobuf with `game.GameState.decode()`
  - Tracks `mySeatId` (which seat this client controls)

## Architecture Notes

- Provider nesting order: `AuthProvider` → `SocketProvider` → `GameProvider`.
- State updates are immediate — no debouncing or batching. Every server broadcast triggers a re-render.
- The `GameState` object matches the Protobuf schema exactly (via `protobufjs` codegen).
