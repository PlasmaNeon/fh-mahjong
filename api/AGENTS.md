# api/

> REST API + WebSocket server — authentication, game rooms, matchmaking, and real-time state sync.

## Overview

This package implements the network layer: HTTP routes via Gin, WebSocket connections via gorilla/websocket, JWT authentication, and the room/matchmaker orchestration that connects players to game instances. It is stateless with respect to game logic — all game mutations are delegated to `core.Game`.

## Key Files

- **server.go** — Gin HTTP server setup and route registration:
  - Public: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/guest`
  - Public tool routes: `/api/v1/calc`, `/api/v1/shanten`, `/api/v1/paipu/:matchId`, `/api/v1/ws`
  - Optional SPA/static serving from `web/dist` for single-service production deploys
  - Production SPA asset mounts use explicit `GET`/`HEAD` file handlers for `/assets` and `/Regular_shortnames` so built JS/CSS/SVG requests resolve to real files instead of falling through to `index.html`
  - Trusted proxy configuration via `TRUSTED_PROXIES` (defaults to trusting none)
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
  - `BotPolicy` — deterministic policy used for seats with no connected client entry
  - `WithBotPolicy()` — room option for injecting a non-default automated-seat policy while keeping the heuristic default
  - Initializes `core.PaipuRecorder`, registers all 4 seats at room start, and uses placeholder bot names for automated seats so paipu exports always have complete player metadata
  - `ActionQueue` channel — Serializes player actions
  - `Run()` — Main goroutine: processes actions, broadcasts state, manages interrupt timer
  - `advanceAutomatedSeats()` — Plays through missing-seat turns, interrupt responses, and round-end `READY` actions for automated seats, with a circuit-breaker to avoid runaway automation loops
  - `BroadcastState()` — Serializes `GameState` Protobuf to all connected players
  - Replay recording (appends state snapshots to binary blob)

- **paipu.go** — Read-only paipu API:
  - `handleGetPaipu()` — Loads persisted paipu JSON for a completed match and returns it as raw JSON
  - Local-dev fallback: serves checked-in `testdata/paipu/<matchId>.json` fixtures when no in-memory/DB record exists, which keeps replay pages usable without a populated database
  - Only queries the legacy `matches` table for canonical UUID match IDs; per-hand IDs like `match-1` skip the UUID-only lookup to avoid noisy Postgres cast errors

- **client.go** — Individual player WebSocket connection:
  - `Client` struct — UserID, Send channel, WebSocket conn
  - `ReadPump()` / `WritePump()` — Goroutine message loops

- **matchmaker.go** — Player queue and pairing:
  - `Matchmaker` struct — Queue of waiting clients
  - Groups 4 players into a `Room`
  - `BotPolicyFactory` creates one automated-seat policy per new room; the server uses this to enable remote AI bots without sharing policy state across matches
  - Tracks active private tables by `tableId` so the same `/table/:tableId` link cannot accidentally start a second game while the first one is still running
  - Lets returning players from the original 4 receive an `"active"` private-table response with the current `matchId` instead of being re-queued

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

- **room_bot_test.go** — Automated-seat room coverage:
  - Missing seats advance through legal bot actions
  - `NewRoom()` initializes paipu recording for match replay export
  - Round-end automation marks bot seats ready and can advance all-bot tables into the next round
  - Paipu player registration includes placeholder bot seats alongside connected humans

## Architecture Notes

- All game actions flow: Client → WebSocket → Room.ActionQueue → core.Game.ProcessPlayerAction() → BroadcastState()
- The room processes actions sequentially via a single goroutine (no mutex needed for game state).
- Seats with no connected `Room.Seats` entry are treated as automated seats and act through the same authoritative engine path instead of being hard-coded to `PASS`.
- Replay persistence has two outputs: the binary protobuf replay blob (`ReplayURL`) and the structured paipu JSON (`PaipuJSON`).
- The interrupt timer runs in a separate goroutine and calls `ResolveInterrupts()` directly — potential race condition to be aware of.
- State is broadcast as raw Protobuf bytes; no per-player filtering yet (all players see full state including opponent hands).
- Private tables are now a two-stage concept: `tableId` is the shareable waiting-room key, and once 4 players are ready the server records an active `tableId -> matchId + participant set` mapping so reconnects can rejoin the live room while non-participants are rejected.
- `/api/v1/calc` is intentionally isolated from room/game orchestration so rules bugs can be reproduced without creating a live match.
- When `web/dist/index.html` exists, unmatched non-API `GET`/`HEAD` routes fall back to the frontend SPA shell so routes like `/calc` and `/create-room` work behind the Go server.
- Asset-like paths (`/assets/...`, `/Regular_shortnames/...`, and common static-file extensions) must never use the SPA fallback; they return the real file or `404`.

- **server_test.go** — SPA/static serving regression coverage:
  - Built JS asset requests return JavaScript, not `index.html`
  - Missing asset requests return `404`, not the SPA shell

- **private_table_test.go** — Private-room join regression coverage:
  - Inactive private tables queue normally
  - Returning participants get `"active"` with the existing `matchId`
  - Fresh users cannot queue into an already-active private table
