# web/src/

> React application source code — pages, state management, hooks, and utilities.

## Overview

Contains all React components, context providers, custom hooks, and utility functions for the Mahjong frontend. The app uses React Router for navigation, context providers for global state (socket connection + game state), and Framer Motion for tile animations.

## Key Files

- **main.tsx** — React bootstrap, renders `<App />` into DOM
- **App.tsx** — Router wrapper with context providers:
  - `SocketProvider` → `GameProvider` → `Routes`
  - Routes: `/login`, `/lobby`, `/create-room`, `/calc`, `/table/:roomId`, `/game/:matchId`
- **config.ts** — Frontend runtime URL helpers:
  - `getApiUrl(path)` uses `VITE_API_BASE_URL` when present, otherwise falls back to same-origin relative paths for local dev
  - `getWebSocketUrl(path)` uses `VITE_WS_BASE_URL` when present, otherwise falls back to browser-origin WebSocket URLs
  - `VITE_WS_BASE_URL` may be supplied as `http(s)` or `ws(s)`; the helper normalizes `http -> ws` and `https -> wss`
- **pages/privateRoomSession.ts** — Durable private-room session helper:
  - Stores the active guest token, username, and `tableId` in local storage for private-room reconnects
  - Drops expired guest JWTs before the UI attempts a reconnect
- **index.css** — Global styles (TailwindCSS + custom classes for tiles, melds, table layout)
  - Includes table-corner HUD styling such as the face-up wild-tile badge shown on the game table
  - Includes the centered match HUD and discard-tray placeholder styling used by `Game.tsx`
  - Discard trays are sized for a full 6 small tiles per row/column before wrapping
  - Newly discarded tiles use a faster move-in animation for every seat, and callable discards use a brighter teal-cyan pulse ring rather than the wild-tile gold glow
  - Includes the glass action-bar styling used for bottom-player `CHII / PON / KAN / RON / TSUMO / SKIP` controls in the elevated lower-right table gap beside the bottom discard tray, kept above the bottom hand line
  - Includes a glass round-result modal styled to match the table HUD/cards instead of the older flat dark dialog, but without backdrop blur so players can still inspect the table behind it
  - The left seat keeps its melds in a dedicated lower-left anchor and aligns concealed hand plus melds off a shared inner-left lane so the tile columns line up visually
  - The live table now has a fixed-stage override layer: a 1600x900 board scaled as one unit inside a safe-area-aware shell so resizing the viewport no longer reflows each hand/discard region independently

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **pages/** — Route page components (Login, Lobby, Table, Game, Calc)
- **hooks/** — Custom React hooks (WASM loader)
- **utils/** — Utility functions (tile name/SVG mapping)
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- The `Game.tsx` page is the largest component (~32KB), handling tile rendering, meld display, table-overlay action buttons, discard pools, and the round-result modal.
- The live board now uses `useGameStageLayout()` from `hooks/` to compute a uniform DOM stage scale instead of depending on `vw`/`vh` geometry for seat placement.
- `Game.tsx` defensively auto-submits backend `ACTION_FLOWER_REVEAL` messages and hides that action from the button bar, matching the intended auto-reveal flower UX.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
- Network calls should use `getApiUrl()` / `getWebSocketUrl()` instead of hard-coded same-origin `/api` paths so the frontend can run behind Vercel while talking to a separate backend host.
- The non-game route pages (`/`, `/lobby`, `/create-room`, `/table/:tableId`) now intentionally share the same emerald/glass tabletop visual language as the live game so the room-creation and waiting flow feels continuous.
- Private-room reconnects intentionally use durable browser storage rather than per-tab session storage, because `/table/:tableId` is a share link and reopening it in a new tab should preserve the same guest identity when possible.
