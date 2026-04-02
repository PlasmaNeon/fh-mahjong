# web/src/pages/

> Route page components — each corresponds to a URL path in the app.

## Overview

Contains the top-level page components rendered by React Router. Each page represents a distinct screen in the user flow: authentication → lobby → pre-game table → live game. The Calc page is a standalone scoring calculator tool.

## Key Files

- **Login.tsx** — Registration and login form. Calls runtime-configured auth endpoints via `getApiUrl(...)`. Stores JWT in localStorage.
  - Includes a direct entry link to `/create-room` for private-table sharing without matchmaking.
  - Uses the same emerald/deep-green glass styling language as the live game and pre-game table pages instead of the old plain auth card

- **Lobby.tsx** — Game lobby. Shows matchmaking queue, lets players create/join rooms via runtime-configured API URLs.
  - Restyled to match the live table theme and clearly split public matchmaking from private-room entry

- **CreateRoom.tsx** — Public private-room generator page for `/create-room`:
  - Generates a random `tableId` client-side and builds a shareable `/table/:tableId` URL
  - Lets the user copy the link or open/join the generated table immediately
  - Reuses the existing private-table queue flow instead of adding a separate backend room-creation API
  - Shares the same tabletop/glass visual language as the waiting room and game pages

- **Table.tsx** — Pre-game room. Shows 4 seats, player ready status. Uses runtime-configured auth/matchmaking URLs and initiates the WebSocket connection to the room.
  - Now renders as a pre-game table scene with seat cards, central status HUD, share-link panel, and ready-state side panel so `/table/:tableId` visually matches the live game more closely
  - Restores the private-room guest session from durable local storage for the same `tableId`, so reopening the shared link in the same browser can reconnect to the live room instead of silently creating a brand new guest identity
  - If the server reports that the shared table is already active, original participants are redirected back to the current `matchId` while non-participants are blocked from spawning a second game off the same link
  - Listens for JSON `lobby_update` socket messages for the current `tableId` while the room is filling

- **privateRoomSession.ts** — Private-room browser session helpers:
  - Persists the active private-room guest token, username, and `tableId` in local storage
  - Decodes JWT expiry client-side so obviously stale guest sessions are discarded before the UI tries to reconnect with them
  - Shared by `Table.tsx` and `Game.tsx` so both waiting-room and live-game routes can recover the same private-room identity

- **Game.tsx** — Live match controller page:
  - Owns socket / action submission flow, interrupt state, auto-flower reveal handling, and the live round-result action buttons
  - Adapts backend player state into the shared `TableBoard` / `TableRoundResultOverlay` view models from `web/src/table/TableScene.tsx`
  - Supplies live HUD chips, callable discard highlighting, discard animation IDs, and bottom-seat action-bar content to the shared table presenter
  - Keeps the fixed 1600x900 stage scaling via `useGameStageLayout()` so the shared seat/discard lanes stay locked to one coordinate system during resize and rotation
  - Private-room reconnect fallback now reads the durable private-room session helper instead of a per-tab session value, so a refreshed live game can recover the same guest identity

- **Replay.tsx** — Replay viewer route:
  - Fetches paipu data, advances the local `ReplayEngine`, and adapts replay state into the same shared `TableBoard` / `TableRoundResultOverlay` presenter used by live play
  - Must forward replay-time `drawnTileId` state into the shared table presenter so the current draw stays in its separate slot instead of collapsing into the concealed hand
  - Keeps its replay transport controls, perspective selector, and “show all hands” toggle in a side panel while the actual table layout stays shared with `Game.tsx`
  - The table shell lives in a flex row beside a fixed-width side panel, so it must override the default `width: 100%` shell behavior with `flex: 1 1 0%`, `width: auto`, and `min-width: 0`; the centered fixed stage inside that shell should use a scaled frame sized from `scaledWidth`/`scaledHeight` so the whole logical board remains visible when the split pane shrinks
  - Replay renders a loading screen before the table shell exists, so any stage-layout integration must tolerate the shell mounting after the hook has already run once
  - Reuses the same fixed-stage scaling system as live play so replay seat lanes and discard lanes match the live board exactly

- **Calc.tsx** — Typed Fenghua rules debugger for `/calc`:
  - Header language toggle switches the calculator UI between English and Chinese
  - Hybrid editor: canonical notation fields plus local tile palettes embedded directly into the closed-hand, win-tile, and wild-tile sections
  - Calculator palette tiles are intentionally larger and more widely spaced than normal hand tiles to reduce misclicks during hand composition
  - Successful `Apply` actions on closed hand / win tile / wild tile collapse that section’s input controls and hide its palette until the user reopens it with the section-level edit button
  - Open meld editing uses an inline per-row palette on the active meld instead of a shared top-of-page palette
  - Explicit open meld rows with type, called tile index, and called direction controls; `CHII` rows lock called direction to left
  - Add-chii / add-pon / add-kan actions live at the bottom of the open-meld section so follow-up meld creation stays close to the current row list
  - Kan-only context controls are embedded inside each `KAN` meld row as a single dropdown selector, mirroring the meld-type control and keeping one context per kan
  - Multiple kan melds are supported; repeated kong bonus selections across different kan rows are preserved and stacked in the calculator payload/result
  - Full scoring context: tsumo/ron toggle, seat wind, prevailing wind, flower meld toggles
  - Client-side validation for meld shape, hand size, and physical tile copy limits before calling the runtime-configured calculator endpoint
  - Calculator network handling validates response content type before parsing JSON and surfaces a clear backend-configuration error on Vercel when `VITE_API_BASE_URL` is missing
  - Result panel for total score / breakdown and a normalized backend debug summary

- **calcHelpers.ts** — Calculator-only helpers:
  - Typed draft models for tiles and melds
  - Canonical tile notation parse/format helpers
  - Meld validation, expected hand-size calculation, and request-payload builders

## Architecture Notes

- `Game.tsx` consumes `useGameState()` and `useSocket()` from contexts.
- `Game.tsx` and `Replay.tsx` should not own seat/discard layout markup directly anymore; shared table layout belongs in `web/src/table/`.
- The live gameplay board is intentionally not a canvas; the fixed-stage DOM approach preserves Framer Motion, SVG tiles, and clickable DOM interactions while eliminating viewport-unit drift.
- `Calc.tsx` is intentionally self-contained and does not share state with gameplay pages; it is a rules-debugging tool, not part of the live match flow.
- Player perspective: the `mySeatId` determines which player is rendered at the bottom position; others are rotated around the table.
- Action buttons appear contextually: interrupt actions during `PHASE_WAIT_DISCARDS` (phase 3), turn actions during `PHASE_PLAYER_TURN` (phase 2).
