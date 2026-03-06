# web/src/

> React application source code — pages, state management, hooks, and utilities.

## Overview

Contains all React components, context providers, custom hooks, and utility functions for the Mahjong frontend. The app uses React Router for navigation, context providers for global state (socket connection + game state), and Framer Motion for tile animations.

## Key Files

- **main.tsx** — React bootstrap, renders `<App />` into DOM
- **App.tsx** — Router wrapper with context providers:
  - `SocketProvider` → `GameProvider` → `Routes`
  - Routes: `/login`, `/lobby`, `/calc`, `/table/:roomId`, `/game/:matchId`
- **index.css** — Global styles (TailwindCSS + custom classes for tiles, melds, table layout)

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **pages/** — Route page components (Login, Lobby, Table, Game, Calc)
- **hooks/** — Custom React hooks (WASM loader)
- **utils/** — Utility functions (tile name/SVG mapping)
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- The `Game.tsx` page is the largest component (~32KB), handling tile rendering, meld display, action buttons, discard pools, and the round-result modal.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
