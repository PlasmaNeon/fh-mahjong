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

- **Calc.tsx** — Typed Fenghua rules debugger for `/calc`:
  - Header language toggle switches the calculator UI between English and Chinese
  - Hybrid editor: canonical notation fields plus local tile palettes embedded directly into the closed-hand, win-tile, and wild-tile sections
  - Successful `Apply` actions on closed hand / win tile / wild tile collapse that section’s input controls and hide its palette until the user reopens it with the section-level edit button
  - Open meld editing uses an inline per-row palette on the active meld instead of a shared top-of-page palette
  - Explicit open meld rows with type, called tile index, and called direction controls; `CHII` rows lock called direction to left
  - Add-chii / add-pon / add-kan actions live at the bottom of the open-meld section so follow-up meld creation stays close to the current row list
  - Kan-only context controls are embedded inside each `KAN` meld row as a single dropdown selector, mirroring the meld-type control and keeping one context per kan
  - Multiple kan melds are supported; repeated kong bonus selections across different kan rows are preserved and stacked in the calculator payload/result
  - Full scoring context: tsumo/ron toggle, seat wind, prevailing wind, flower meld toggles
  - Client-side validation for meld shape, hand size, and physical tile copy limits before calling `/api/v1/calc`
  - Result panel for total score / breakdown and a normalized backend debug summary

- **calcHelpers.ts** — Calculator-only helpers:
  - Typed draft models for tiles and melds
  - Canonical tile notation parse/format helpers
  - Meld validation, expected hand-size calculation, and request-payload builders

## Architecture Notes

- `Game.tsx` consumes `useGameState()` and `useSocket()` from contexts.
- `Calc.tsx` is intentionally self-contained and does not share state with gameplay pages; it is a rules-debugging tool, not part of the live match flow.
- Player perspective: the `mySeatId` determines which player is rendered at the bottom position; others are rotated around the table.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
