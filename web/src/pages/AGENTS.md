# web/src/pages/

> Route page components — each corresponds to a URL path in the app.

## Overview

Contains the top-level page components rendered by React Router. Routes: `/` Home, `/login`, `/play` matchmaking, `/room/new` link generator, `/room/:roomId` waiting room, `/match/:matchId` live game, `/replay/:matchId`, `/tools/calc`, `/tools/shanten`. Every non-game page shares the "Tabletop Glass" theme via the primitives in `web/src/components/`; only the live game/replay board uses the in-game theme.

## Key Files

- **Home.tsx** — Landing page at `/`. One-click feature buttons (Play, Create Private Room, Scoring Calculator, Shanten Calculator, Login/Account). Reads the JWT from `localStorage` to show signed-in state. Built from the shared `PageShell`/`GlassCard`/`Eyebrow`/`PageHeading`/`ButtonLink` primitives.

- **Login.tsx** — Registration and login form at `/login`. Calls runtime-configured auth endpoints via `getApiUrl(...)`. Stores JWT in localStorage. On login, navigates to `/play`.
  - Includes a direct entry link to `/room/new` for private-room sharing without matchmaking.
  - Uses the emerald/deep-green glass styling language shared across non-game pages.

- **Lobby.tsx** — Matchmaking page at `/play`. Shows the matchmaking queue and links to the private-room flow.
  - On match found, navigates to `/match/:matchId`.

- **CreateRoom.tsx** — Private-room link generator page for `/room/new`:
  - Generates a random room id client-side and builds a shareable `/room/:roomId` URL
  - Lets the user copy the link or open/join the generated room immediately
  - Acts purely as a link generator; the seat-configuration flow happens on `/room/:roomId`

- **Table.tsx** — Private-room waiting/seat-configuration screen for `/room/:roomId` (route param `roomId`):
  - Reads/POSTs `/api/v1/rooms/:roomId/...` for join, get, seat mutation, mode, and start
  - Renders four `SeatCard` components; the host (first joiner) sees per-empty-seat AI controls and a "Start Match" button enabled when all seats are filled
  - Subscribes to `lobby_update` envelopes (`room` key + full `PrivateTableState` JSON) and re-renders on every broadcast
  - On `state === 'started'`, redirects everyone to `/match/:matchId`
  - Uses tab-scoped private-room session storage for guest-token reconnects (the storage record still keys on `tableId` internally)

- **SeatCard.tsx** — Single seat-card component. Renders waiting/human/bot states; if `canEdit` is true, shows "Add AI · Heuristic" buttons for empty seats and a "Remove AI" button for bot seats. Pure presentation; all mutations bubble up to `Table.tsx`.

- **privateRoomSession.ts** — Private-room browser session helpers:
  - Persists the active private-room guest token, username, and `tableId` in session storage
  - Decodes JWT expiry client-side so obviously stale guest sessions are discarded before the UI tries to reconnect with them, and removes the old local-storage key from the reverted cross-tab reconnect flow
  - Shared by `Table.tsx` and `Game.tsx` so both waiting-room and live-game routes can recover the same private-room identity

- **Game.tsx** — Live match controller page:
  - Owns socket / action submission flow, interrupt state, auto-flower reveal handling, and the live round-result action buttons
  - Adapts backend player state into the shared `TableBoard` / `TableRoundResultOverlay` view models from `web/src/table/TableScene.tsx`
  - Supplies live HUD chips, callable discard highlighting, discard animation IDs, and bottom-seat action-bar content to the shared table presenter
  - Keeps the fixed 1600x900 stage scaling via `useGameStageLayout()` so the shared seat/discard lanes stay locked to one coordinate system during resize and rotation
  - Uses the tab-scoped private-room session helper so a refreshed live game can recover the same guest identity without making every same-browser tab collapse into one player

- **Replay.tsx** — Replay viewer route:
  - Fetches paipu data, advances the local `ReplayEngine`, and adapts replay state into the same shared `TableBoard` / `TableRoundResultOverlay` presenter used by live play
  - Must forward replay-time `drawnTileId` state into the shared table presenter so the current draw stays in its separate slot instead of collapsing into the concealed hand
  - Keeps its replay transport controls, perspective selector, and “show all hands” toggle in a side panel while the actual table layout stays shared with `Game.tsx`
  - The table shell lives in a flex row beside a fixed-width side panel, so it must override the default `width: 100%` shell behavior with `flex: 1 1 0%`, `width: auto`, and `min-width: 0`; replay also renders a loading screen before the real shell exists, so the stage-layout hook must tolerate the shell mounting after its first render
  - Reuses the same fixed-stage scaling system as live play so replay seat lanes and discard lanes match the live board exactly

- **Calc.tsx** — Typed Fenghua rules debugger for `/tools/calc`:
  - Posts to `/api/v1/tools/calc`; uses the shared Tabletop Glass theme (`PageShell` + glass cards, emerald accents)
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

- **MatchEndOverlay.tsx** — Chongci final-standings modal rendered when `gameState.phase === PHASE_MATCH_END`. Offers "Watch Replay" (→ `/replay/:matchId`, when a `matchId` prop is passed) and "Leave" (→ `/play`).

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
