# web/src/

> React application source code — pages, state management, hooks, and utilities.

## Overview

Contains all React components, context providers, custom hooks, and utility functions for the Mahjong frontend. The app uses React Router for navigation, context providers for global state (socket connection + game state), and Framer Motion for tile animations.

## Key Files

- **main.tsx** — React bootstrap, wraps `<App />` in the device-aware `I18nProvider`, then renders into DOM
- **App.tsx** — Router wrapper with context providers:
  - `SocketProvider` → `GameProvider` → route-backed login overlay + primary `Routes`
  - `/login` can preserve a background location for optional authentication; direct/protected login renders the same paper dialog over a neutral club stage
  - Routes include `/`, `/play`, `/account`, `/room/new`, `/room/:roomId`, `/match/:matchId`, `/replay`, `/replay/:matchId`, and the `/tools/*` workbenches
- **config.ts** — Frontend runtime URL helpers:
  - `getApiUrl(path)` uses `VITE_API_BASE_URL` when present, otherwise falls back to same-origin relative paths for local dev
  - `getWebSocketUrl(path)` uses `VITE_WS_BASE_URL` when present, otherwise falls back to browser-origin WebSocket URLs
  - `VITE_WS_BASE_URL` may be supplied as `http(s)` or `ws(s)`; the helper normalizes `http -> ws` and `https -> wss`
- **contexts/AuthContext.tsx** — Owns persistent-login bootstrap and the in-memory CSRF token; API credentials live only in the server-set HttpOnly cookie
- **features/game/privateRoomSession.ts** — Stores only the non-sensitive current `tableId` so an expired login can return to the correct invite after authentication
- **index.css** — Global reset and fixed-stage geometry (TailwindCSS + table layout); Rainy Club visual values live under `theme/` and `table/table-theme.css`
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
  - Imports `table/roundResult.css`, the focused Fenghua settlement-sheet module shared by live and replay; the result body scrolls independently while its action footer stays reachable on phone viewports
  - The live table now has a fixed-stage override layer: a 1600x900 board scaled as one unit inside a safe-area-aware shell so resizing the viewport no longer reflows each hand/discard region independently
  - The shell should measure the actual available pane size and keep the logical 1600x900 board on a stable coordinate system; the current stage uses `zoom` instead of a transformed parent so Framer Motion tile transitions stay in a less surprising coordinate space

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **features/** — Feature folders, each owning its routes + components + helpers:
  - `auth/` — Login (route `/login`)
  - `lobby/` — Home, Lobby, CreateRoom (routes `/`, `/play`, `/room/new`)
  - `calc/` — Calc + calcHelpers (route `/tools/calc`)
  - `shanten/` — Shanten + shantenHelpers (route `/tools/shanten`)
  - `replay/` — Account paipu library plus Replay + replayEngine + replayTypes (routes `/replay`, `/replay/:matchId`)
  - `game/` — Game, Table, SeatCard, MatchEndOverlay, ExitMatchButton, privateRoomSession, rejoinMatch (routes `/room/:roomId`, `/match/:matchId`)
- **table/** — Shared tabletop presentation primitives for live play and replay
- **hooks/** — Custom React hooks (WASM loader)
- **utils/** — Utility functions (tile name/SVG mapping)
- **i18n/** — Typed English/Simplified Chinese resources, device-language selection, document-language synchronization, and the shared translation hook
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- Live play and replay now adapt their own state into the shared presenter in `web/src/table/TableScene.tsx` instead of maintaining two separate seat/discard DOM trees.
- The live board now uses `useGameStageLayout()` from `hooks/` to compute a uniform DOM stage scale instead of depending on `vw`/`vh` geometry for seat placement.
- `Game.tsx` defensively auto-submits backend `ACTION_FLOWER_REVEAL` messages and hides that action from the button bar, matching the intended auto-reveal flower UX.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
- Network calls should use `getApiUrl()` / `getWebSocketUrl()` instead of hard-coded same-origin `/api` paths so the frontend can run behind Vercel while talking to a separate backend host.
- Every route shares the Rainy Mahjong Club identity: ink/rain backdrops, bone-paper work surfaces, jade controls, brass details, and seal-red danger treatment. Home is a compact club switchboard with the compass and four literal actions.
- Private-room identity is account-backed. Browser storage never contains a session token; multi-tab play uses the same signed-in account.
