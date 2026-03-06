# web/src/pages/

> Route page components — each corresponds to a URL path in the app.

## Overview

Contains the top-level page components rendered by React Router. Each page represents a distinct screen in the user flow: authentication → lobby → pre-game table → live game. The Calc page is a standalone scoring calculator tool.

## Key Files

- **Login.tsx** — Registration and login form. Calls `/api/v1/auth/register` and `/api/v1/auth/login`. Stores JWT in localStorage.

- **Lobby.tsx** — Game lobby. Shows matchmaking queue, lets players create/join rooms.

- **Table.tsx** — Pre-game room. Shows 4 seats, player ready status. Initiates WebSocket connection to the room.

- **Game.tsx** — Main tabletop renderer (~32KB, the largest component):
  - Renders 4 player positions (bottom=self, right, top, left)
  - Tile rendering with layered SVGs (`Front.svg` + face)
  - Sorted closed hand with drawn tile separation
  - Open melds with stolen tile rotation (`pov-{dir} small stolen-tile`)
  - Discard pools per player
  - Action buttons: CHOW, PONG, KONG, RON, TSUMO, SKIP
  - Round-result modal: winning hand display, score breakdown, payouts, ready button
  - Framer Motion `layoutId` animations for tile movement
  - `TileComponent` helper for consistent tile rendering
  - `getSuitOrder()` / `getTileSvgName()` / `getTileName()` utilities

- **Calc.tsx** — Hand calculator page. Input tiles manually, evaluate scoring patterns and see breakdown. Calls `/api/v1/calc` endpoint.

## Architecture Notes

- `Game.tsx` consumes `useGameState()` and `useSocket()` from contexts.
- Player perspective: the `mySeatId` determines which player is rendered at the bottom position; others are rotated around the table.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
