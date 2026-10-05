# web/src/

> React application source code — feature routes, the shared table presenter, state, and utilities.

## Overview

Contains all React components, context providers, custom hooks, and utility functions for the Mahjong frontend. The app uses React Router for navigation, context providers for global state (socket connection + game state), and Framer Motion for tile animations.

## Key Files

- **main.tsx** — React bootstrap, wraps `<App />` in the device-aware `I18nProvider`, then renders into DOM
- **App.tsx** — Router wrapper with context providers:
  - `AuthProvider` → `SocketProvider` → `GameProvider` → route-backed login overlay + primary `Routes`
  - `/login` can preserve a background location for optional authentication; direct/protected login renders the same paper dialog over a neutral club stage
  - Routes: `/`, `/login`, `/play`, `/account`, `/room/new`, `/room/:roomId`, `/match/:matchId`, `/replay`, `/replay/:matchId`, `/tools/calc`, `/tools/shanten`, `/tools/table-sample`, `/tools/round-result` (`/tools` redirects to `/tools/calc`; unknown paths to `/`)
- **config.ts** — Frontend runtime URL helpers:
  - `getApiUrl(path)` uses `VITE_API_BASE_URL` when present, otherwise falls back to same-origin relative paths for local dev
  - `getWebSocketUrl(path)` uses `VITE_WS_BASE_URL` when present, otherwise falls back to browser-origin WebSocket URLs
  - `VITE_WS_BASE_URL` may be supplied as `http(s)` or `ws(s)`; the helper normalizes `http -> ws` and `https -> wss`
- **contexts/AuthContext.tsx** — Owns persistent-login bootstrap and the in-memory CSRF token; API credentials live only in the server-set HttpOnly cookie
- **features/game/privateRoomSession.ts** — Stores only the non-sensitive current `tableId` so an expired login can return to the correct invite after authentication
- **index.css** — App globals only (23 lines): the Tailwind import, the `body` / `#root` / `.app-root` reset, and `@import`s of `table/roundResult.css` and `table/table-geometry.css`
- **table/table-geometry.css** — The fixed-stage table geometry. Rainy Club visual values live under `theme/` and `table/table-theme.css`
  - Includes table-corner HUD styling such as the face-up wild-tile badge shown on the game table
  - Includes the centered match HUD plus the fixed-stage seat-lane / discard-lane styling used by the shared table presenter
  - Seat lanes own concealed-hand, flex-gap, open-meld, and flower geometry as reusable bottom/right/top/left primitives instead of page-specific side rules
  - Left/right seat lanes are intentionally not rotationally symmetric: right concealed hands flow `column-reverse`, left concealed hands flow `column`, right exposed rails live above the hand, and left exposed rails live below it
  - The shared seat lane keeps the drawn tile in a dedicated slot next to the concealed-hand rail instead of folding it back into the sorted closed-hand list
  - Discard lanes are sized by the small tile main-axis dimension so only 6 discards fit before wrapping, align off the center HUD rather than fixed edge offsets, and keep the horizontal trays left-anchored instead of center-anchored
  - The center HUD is sized from that same 6-tile discard-lane footprint, with a slightly larger HUD-to-discard gap so the center panel and discard trays read as aligned but visually separated
  - All four discard trays use the same center-HUD-relative gap variable, so the top/right/bottom/left tray spacing from the panel stays symmetric
  - Newly discarded tiles use a faster move-in animation for every seat, and callable discards use a brighter teal-cyan pulse ring rather than the wild-tile gold glow
  - Includes the glass action-bar styling used for bottom-player `CHII / PON / KAN / RON / TSUMO / SKIP` controls in the elevated lower-right table gap beside the bottom discard tray, kept above the bottom hand line; multiple chii candidates collapse to one call button and are resolved by selecting two highlighted hand tiles
  - Imports `table/roundResult.css`, the focused Fenghua settlement-sheet module shared by live and replay; the result body scrolls independently while its action footer stays reachable on phone viewports
  - The live table is a fixed stage: a 1600x900 board scaled as one unit inside a safe-area-aware shell, so resizing the viewport never reflows hand/discard regions independently
  - Desktop self-hand tiles use 66x94 design pixels (about 53x75 CSS pixels at 1280x720), keeping their ~10.4% table-height ratio as the fixed canvas zooms; action controls sit above that enlarged rail
  - Compact short-stage geometry gives the local hand a 76x107 design-pixel tile rail (about 42x59 CSS pixels at 667x375), keeps the drawn tile separated, and raises/shortens both opponent side bundles so they cannot cover the local interaction band
  - The shell should measure the actual available pane size and keep the logical 1600x900 board on a stable coordinate system; the stage uses `zoom` instead of a transformed parent so Framer Motion tile transitions stay in a less surprising coordinate space

## Subdirectories

- **contexts/** — React context providers (Socket, Game state)
- **features/** — Feature folders, each owning its routes + components + helpers:
  - `auth/` — Login, Account (routes `/login`, `/account`)
  - `lobby/` — Home, Lobby, CreateRoom (routes `/`, `/play`, `/room/new`)
  - `calc/` — Calc + calcHelpers (route `/tools/calc`)
  - `shanten/` — Shanten + shantenHelpers (route `/tools/shanten`)
  - `replay/` — Account paipu library, Replay + replayEngine, and the post-game review panel (routes `/replay`, `/replay/:matchId`)
  - `game/` — Game, PrivateRoom, SeatCard, MatchEndOverlay, ExitMatchButton, privateRoomSession, rejoinMatch (routes `/room/:roomId`, `/match/:matchId`)
  - `dev/` — TableSample, RoundResultDemo (routes `/tools/table-sample`, `/tools/round-result`)
- **table/** — Shared tabletop presentation primitives for live play and replay; `table/stage/` owns the fixed-stage layout
- **hooks/** — `useMahjongWasm.ts` only (unreferenced)
- **utils/** — Tile display mapping, the shared tile value-model, wind labels, API JSON helpers
- **test/** — Shared test helpers (`cssContract.ts`, `renderStatic.tsx`, `memoryStorage.ts`)
- **i18n/** — Typed English/Simplified Chinese resources, device-language selection, document-language synchronization, and the shared translation hook
- **proto/** — Auto-generated Protobuf JS/TS bindings

## Architecture Notes

- State flow: WebSocket binary message → `GameContext` decodes Protobuf → `gameState` updates → components re-render.
- Live play and replay adapt their own state into the shared presenter in `web/src/table/TableBoard.tsx` instead of maintaining two separate seat/discard DOM trees.
- The live board uses `useGameStageLayout()` from `table/stage/` to compute a uniform DOM stage scale instead of depending on `vw`/`vh` geometry for seat placement.
- `Game.tsx` defensively auto-submits backend `ACTION_FLOWER_REVEAL` messages and hides that action from the button bar, matching the intended auto-reveal flower UX.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with `small` modifier for different viewpoints and sizes.
- Network calls should use `getApiUrl()` / `getWebSocketUrl()` instead of hard-coded same-origin `/api` paths so the frontend can run behind Vercel while talking to a separate backend host.
- Menu routes use Direct play light surfaces and blue controls; live/replay tables use the scoped slate-blue table skin. Home and `/play` now share the production Direct play entry; ordinary menu routes use the light DirectShell while table materials remain scoped to gameplay.
- Private-room identity is account-backed. Browser storage never contains a session token; multi-tab play uses the same signed-in account.

Replay adds `/replay/import/:importId` for private native paipu uploads and uses the existing shared table plus a Decision/Rounds/Risk study drawer. Its background job client is account-bound and guards obsolete responses. The reviewer namespace supports five languages through the shared i18n provider.
