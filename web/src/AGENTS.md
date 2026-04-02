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
  - Stores the active guest token, username, and `tableId` in tab-scoped session storage so refreshes reconnect cleanly without making every tab share the same guest identity
  - Drops expired guest JWTs before the UI attempts a reconnect and clears the legacy local-storage key from the short-lived cross-tab experiment
- **index.css** — Global styles (TailwindCSS + custom classes for tiles, melds, table layout)
  - Includes table-corner HUD styling such as the face-up wild-tile badge shown on the game table
  - Includes the centered match HUD plus the fixed-stage seat-lane / discard-lane styling used by the shared table presenter
  - Seat lanes now own concealed-hand, flex-gap, open-meld, and flower geometry as reusable bottom/right/top/left primitives instead of page-specific side rules
  - Left/right seat lanes intentionally preserve the old main-branch semantics rather than pure rotational symmetry: right concealed hands flow `column-reverse`, left concealed hands flow `column`, right exposed rails live above the hand, and left exposed rails live below it
  - The shared seat lane keeps the drawn tile in a dedicated slot next to the concealed-hand rail instead of folding it back into the sorted closed-hand list
  - Discard lanes are sized by the small tile main-axis dimension so only 6 discards fit before wrapping, align off the center HUD rather than fixed edge offsets, and keep the horizontal trays left-anchored instead of center-anchored
  - The center HUD is now sized from that same 6-tile discard-lane footprint, with a slightly larger HUD-to-discard gap so the center panel and discard trays read as aligned but visually separated
  - All four discard trays now use the same center-HUD-relative gap variable, so the top/right/bottom/left tray spacing from the panel stays symmetric
  - Newly discarded tiles use a faster move-in animation for every seat, and callable discards use a brighter teal-cyan pulse ring rather than the wild-tile gold glow
  - Includes the glass action-bar styling used for bottom-player `CHII / PON / KAN / RON / TSUMO / SKIP` controls in the elevated lower-right table gap beside the bottom discard tray, kept above the bottom hand line
  - Includes a glass round-result modal styled to match the table HUD/cards instead of the older flat dark dialog, but without backdrop blur so players can still inspect the table behind it
  - The live table now has a fixed-stage override layer: a 1600x900 board scaled as one unit inside a safe-area-aware shell so resizing the viewport no longer reflows each hand/discard region independently
  - The shell should measure the actual available pane size and keep the logical 1600x900 board on a stable coordinate system; the current stage uses `zoom` instead of a transformed parent so Framer Motion tile transitions stay in a less surprising coordinate space

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **pages/** — Route page components (Login, Lobby, Table, Game, Calc)
- **table/** — Shared tabletop presentation primitives for live play and replay
- **hooks/** — Custom React hooks (WASM loader)
- **utils/** — Utility functions (tile name/SVG mapping)
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- Live play and replay now adapt their own state into the shared presenter in `web/src/table/TableScene.tsx` instead of maintaining two separate seat/discard DOM trees.
- The live board now uses `useGameStageLayout()` from `hooks/` to compute a uniform DOM stage scale instead of depending on `vw`/`vh` geometry for seat placement.
- `Game.tsx` defensively auto-submits backend `ACTION_FLOWER_REVEAL` messages and hides that action from the button bar, matching the intended auto-reveal flower UX.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
- Network calls should use `getApiUrl()` / `getWebSocketUrl()` instead of hard-coded same-origin `/api` paths so the frontend can run behind Vercel while talking to a separate backend host.
- The non-game route pages (`/`, `/lobby`, `/create-room`, `/table/:tableId`) now intentionally share the same emerald/glass tabletop visual language as the live game so the room-creation and waiting flow feels continuous.
- Private-room reconnects intentionally use per-tab browser storage so refreshes still reconnect, but opening multiple `/table/:tableId` tabs in the same browser can simulate multiple local players without all tabs sharing one guest identity.
