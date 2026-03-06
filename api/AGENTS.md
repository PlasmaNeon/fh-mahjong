# api/

> REST API + WebSocket server — authentication, game rooms, matchmaking, and real-time state sync.

## Overview

This package implements the network layer: HTTP routes via Gin, WebSocket connections via gorilla/websocket, JWT authentication, and the room/matchmaker orchestration that connects players to game instances. It is stateless with respect to game logic — all game mutations are delegated to `core.Game`.

## Key Files

- **server.go** — Gin HTTP server setup and route registration:
  - Public: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/guest`
  - Public tool routes: `/api/v1/calc`, `/api/v1/ws`
  - CORS configuration

- **auth.go** — JWT authentication handlers:
  - `Register()` — Create user with bcrypt password hash
  - `Login()` — Authenticate and return JWT
  - `GuestLogin()` — Anonymous play with auto-generated credentials

- **ws.go** — WebSocket upgrade and client management:
  - `Hub` struct — Manages all active WebSocket clients
  - `HandleWebSocket()` — Upgrades HTTP → WS, creates `Client`
  - Binary Protobuf message protocol

- **room.go** — Single match room orchestration:
  - `Room` struct — 4 `Client` seats + 1 `core.Game` engine
  - `ActionQueue` channel — Serializes player actions
  - `Run()` — Main goroutine: processes actions, broadcasts state, manages interrupt timer
  - `BroadcastState()` — Serializes `GameState` Protobuf to all connected players
  - Replay recording (appends state snapshots to binary blob)

- **client.go** — Individual player WebSocket connection:
  - `Client` struct — UserID, Send channel, WebSocket conn
  - `ReadPump()` / `WritePump()` — Goroutine message loops

- **matchmaker.go** — Player queue and pairing:
  - `Matchmaker` struct — Queue of waiting clients
  - Groups 4 players into a `Room`

- **middleware.go** — JWT token validation middleware for protected routes

- **calc.go** — Hand evaluation API endpoint (stateless scoring calculator):
  - Accepts structured calculator payloads: closed hand, win tile, single wild tile type, open melds, flower melds, winds, tsumo/ron, and kong bonus flags
  - Open meld rows can carry per-kan kong flags; repeated flag selections across multiple kan melds are counted and stacked in the calculator response
  - Validates meld shapes, hand size, tile copy limits, and wind ranges before scoring
  - Translates request data into proto `GameState` / `PlayerState` / `Meld` values with unique tile IDs
  - Returns `canWin`, total score, score breakdown, and a normalized debug summary for the frontend

- **calc_test.go** — Calculator API coverage:
  - Request validation failures
  - Tsumo / Ron calculator responses
  - Wild tile translation and scoring
  - Open meld called-tile preservation
  - Flower meld and kong-flag propagation into the evaluation state

## Architecture Notes

- All game actions flow: Client → WebSocket → Room.ActionQueue → core.Game.ProcessPlayerAction() → BroadcastState()
- The room processes actions sequentially via a single goroutine (no mutex needed for game state).
- The interrupt timer runs in a separate goroutine and calls `ResolveInterrupts()` directly — potential race condition to be aware of.
- State is broadcast as raw Protobuf bytes; no per-player filtering yet (all players see full state including opponent hands).
- `/api/v1/calc` is intentionally isolated from room/game orchestration so rules bugs can be reproduced without creating a live match.
