# web/src/

> Application source: feature routes, the shared table presenter, contexts, theme, i18n, and
> utilities.

## Entry

- **main.tsx** — mounts `<App />` inside the device-aware `I18nProvider`; imports
  `theme/index.css` once.
- **App.tsx** — providers `AuthProvider → SocketProvider → GameProvider`, a route-backed login
  overlay, and the routes:
  `/`, `/login`, `/play`, `/account`, `/room/new`, `/room/:roomId`, `/match/:matchId`, `/replay`,
  `/replay/:matchId`, `/replay/import/:importId`, `/tools/calc`, `/tools/shanten`,
  `/tools/table-sample`, `/tools/round-result` (`/tools` → `/tools/calc`; unknown → `/`).
- **config.ts** — `getApiUrl(path)` and `getWebSocketUrl(path)`: use `VITE_API_BASE_URL` /
  `VITE_WS_BASE_URL` when set (http(s) is normalized to ws(s)), else same-origin. Always use these
  instead of hard-coded `/api` paths.
- **index.css** — app globals only: Tailwind, the root reset, and imports of
  `table/roundResult.css` and `table/table-geometry.css`.

## Directories

| Directory | Owns |
|---|---|
| `features/` | Route pages and their helpers: `auth`, `lobby`, `game`, `replay`, `calc`, `shanten`, `dev` |
| `table/` | The shared tabletop presenter for live play and replay (`stage/`, `seat/`) |
| `contexts/` | Auth, socket, and game-state providers |
| `theme/` | Design tokens, base CSS, typed primitives, Direct play shells |
| `i18n/` | English and Simplified Chinese resources (plus three reviewer-only languages) |
| `utils/` | Tile display, the tile value-model, winds, API JSON helpers |
| `proto/` | Generated protobuf bindings |
| `hooks/` | `useMahjongWasm.ts`, unreferenced |
| `test/` | Shared test helpers: `cssContract.ts`, `renderStatic.tsx`, `memoryStorage.ts` |

There is no `pages/` directory.

## Architecture

- State flow: WebSocket binary frame → `GameContext` decodes `GameState` → components re-render.
- Live play (`features/game/Game.tsx`) and replay (`features/replay/Replay.tsx`) adapt their own
  state into one presenter, `table/TableBoard.tsx`, on a fixed 1600×900 stage scaled as a unit.
- The client never decides legality: actions come from `PlayerState.valid_actions`.
  `ACTION_FLOWER_REVEAL` is auto-submitted and hidden from the action bar.
- Menu routes use the light Direct play shell; the table keeps its own scoped skin.
- Sessions live only in the server-set HttpOnly cookie; browser storage never holds a token.
  Multi-tab play uses the same signed-in account.
