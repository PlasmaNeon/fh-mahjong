# web/src/

> React application source code — pages, state management, hooks, and utilities.

## Overview

Contains all React components, context providers, custom hooks, and utility functions for the Mahjong frontend. The app uses React Router for navigation, context providers for global state (socket connection + game state), and Framer Motion for tile animations.

## Key Files

- **main.tsx** — React bootstrap, renders `<App />` into DOM
- **App.tsx** — Router wrapper with context providers:
  - `SocketProvider` → `GameProvider` → `Routes`
  - Routes: `/login`, `/lobby`, `/calc`, `/table/:roomId`, `/game/:matchId`
- **config.ts** — Frontend runtime URL helpers:
  - `getApiUrl(path)` uses `VITE_API_BASE_URL` when present, otherwise falls back to same-origin relative paths for local dev
  - `getWebSocketUrl(path)` uses `VITE_WS_BASE_URL` when present, otherwise falls back to browser-origin WebSocket URLs
  - `VITE_WS_BASE_URL` may be supplied as `http(s)` or `ws(s)`; the helper normalizes `http -> ws` and `https -> wss`
- **index.css** — Global styles (TailwindCSS + custom classes for tiles, melds, table layout)
  - Includes table-corner HUD styling such as the face-up wild-tile badge shown on the game table
  - Includes the centered match HUD and discard-tray placeholder styling used by `Game.tsx`
  - Includes the glass action-bar styling used for bottom-player `CHII / PON / KAN / RON / TSUMO / SKIP` controls in the elevated lower-right table gap beside the bottom discard tray, kept above the bottom hand line
  - The left seat keeps its melds in a dedicated lower-left anchor and aligns concealed hand plus melds off a shared inner-left lane so the tile columns line up visually

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **pages/** — Route page components (Login, Lobby, Table, Game, Calc)
- **hooks/** — Custom React hooks (WASM loader)
- **utils/** — Utility functions (tile name/SVG mapping)
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- The `Game.tsx` page is the largest component (~32KB), handling tile rendering, meld display, table-overlay action buttons, discard pools, and the round-result modal.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
- Network calls should use `getApiUrl()` / `getWebSocketUrl()` instead of hard-coded same-origin `/api` paths so the frontend can run behind Vercel while talking to a separate backend host.
