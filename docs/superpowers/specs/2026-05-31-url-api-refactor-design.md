# URL & API Refactor — Design

**Date:** 2026-05-31
**Status:** Approved

## Goal

Refactor the game's frontend routes and backend API paths so the URL structure
matches users' mental models, and make the orphaned tool/replay pages
discoverable. The current layout is misleading: `/` is the login screen,
`/table/:id` is actually the *waiting room* while `/game/:id` is the live table,
and `/calc`, `/shanten`, `/replay` have no navigation links at all.

## Scope

- **In scope:** Frontend client-side routes AND backend API paths.
- **Hard cut, no aliases.** The frontend is the only API client and is updated
  in lockstep. Old routes/paths are deleted, not redirected.
- **Not a full IA overhaul:** no persistent global header/nav bar, no
  replay-history list page, no auth changes, no visual redesign of existing
  pages.

## Decisions (from brainstorming)

1. Scope = frontend URLs + API paths.
2. Play-flow vocabulary = **room → match → replay**.
3. Root becomes a real **Home** page; login moves to `/login`; tools move under
   `/tools/*`.
4. Transition = **hard cut**, no backward-compatible aliases or redirects.
5. Keep the private-room link generator as a dedicated `/room/new` page (not
   folded into Home).
6. Include a small **"Watch replay"** button on the match-end overlay.

## A. Frontend route mapping

| New URL | Page component | Was |
|---|---|---|
| `/` | `Home.tsx` (new) | was `Login` at `/` |
| `/login` | `Login.tsx` | was `/` |
| `/play` | `Lobby.tsx` (matchmaking queue) | was `/lobby` |
| `/room/new` | `CreateRoom.tsx` (link generator) | was `/create-room` |
| `/room/:roomId` | `Table.tsx` (waiting room: seats/AI/mode + Start) | was `/table/:tableId` |
| `/match/:matchId` | `Game.tsx` (live match) | was `/game/:matchId` |
| `/replay/:matchId` | `Replay.tsx` | same path; now discoverable |
| `/tools/calc` | `Calc.tsx` | was `/calc` |
| `/tools/shanten` | `Shanten.tsx` | was `/shanten` |
| `*` | → `/` | same |

Notes:
- React Router v6 ranks the static segment `/room/new` above the param route
  `/room/:roomId`, so there is no conflict.
- The `useParams()` key stays `tableId` inside `Table.tsx` only if the route
  param is named `:tableId`. We rename the route param to `:roomId`, so
  `Table.tsx` reads `const { roomId } = useParams()`. Same for `Game.tsx` /
  `Replay.tsx` which already use `:matchId` (unchanged).

### New Home page (`Home.tsx`)

Lightweight landing that replaces login-at-root. Reuses the existing
emerald/glass styling language. Contents:
- **Play** card → `/play` (public matchmaking)
- **Private room** card → `/room/new` (generate + share a room link)
- **Tools** card → links to `/tools/calc` and `/tools/shanten`
- **Account** affordance → `/login` (or shows the logged-in username if a token
  is present in `localStorage`)

No new global nav/header; discoverability comes from the Home cards plus the
inter-page links listed in section C.

## B. API path mapping (hard cut)

Defined in `api/server.go` `setupRoutes()`.

| New API path | Was | Handler (unchanged) |
|---|---|---|
| `POST /api/v1/tools/calc` | `POST /api/v1/calc` | `s.handleCalc` |
| `POST /api/v1/tools/shanten` | `POST /api/v1/shanten` | `s.handleShanten` |
| `GET /api/v1/replays/:matchId` | `GET /api/v1/paipu/:matchId` | `s.handleGetPaipu` |
| `POST /api/v1/replays/:matchId` | `POST /api/v1/paipu/:matchId` | `s.handleUploadPaipu` |
| `GET /api/v1/rooms/:roomId` | `GET /api/v1/private-tables/:tableId` | `s.handlePrivateTableGet` |
| `POST /api/v1/rooms/:roomId/join` | `.../private-tables/:tableId/join` | `s.handlePrivateTableJoin` |
| `POST /api/v1/rooms/:roomId/seat` | `.../private-tables/:tableId/seat` | `s.handlePrivateTableSeat` |
| `POST /api/v1/rooms/:roomId/start` | `.../private-tables/:tableId/start` | `s.handlePrivateTableStart` |
| `POST /api/v1/rooms/:roomId/mode` | `.../private-tables/:tableId/mode` | `s.handlePrivateTableMode` |
| `POST /api/v1/matchmaking/join` | unchanged | `s.handleJoinQueue` |
| `POST /api/v1/auth/{register,login,guest}`, `GET /api/v1/users/me`, `GET /api/v1/ws` | unchanged | |

- The Gin path param is renamed `:tableId` → `:roomId`; handlers read it via
  `c.Param("roomId")`. Internal Go identifiers (`tableID`, `TableID`,
  struct/field names) may remain as-is to limit churn — only the **route param
  name** and the **URL segment** change. Handler bodies still operate on the
  same table store.

### WebSocket `lobby_update` envelope

Rename the broadcast envelope field `table` → `room` for consistency with
`/rooms`:
- Backend: `api/private_tables.go` ~line 213, the anonymous struct field
  `Table string \`json:"table"\`` → `Room string \`json:"room"\`` and the
  assignment `Table: table.TableID` → `Room: table.TableID`.
- Frontend: `web/src/pages/Table.tsx` ~line 78, `data.table === tableId` →
  `data.room === roomId`.
- Also the join/conflict JSON responses at lines ~243/246 use a `"table"` key;
  rename those to `"room"` for consistency. The frontend ignores those keys
  except `matchId`, so this is cosmetic but kept consistent.

## C. Navigation / discoverability fixes

All `navigate()` and `<Link to=...>` targets updated to the new paths:

| File | Old target | New target |
|---|---|---|
| `web/src/pages/Login.tsx` | `navigate('/lobby')` | `navigate('/play')` |
| `web/src/pages/Login.tsx` | `<Link to="/create-room">` | `<Link to="/room/new">` |
| `web/src/pages/Lobby.tsx` | `navigate('/game/${matchId}')` | `navigate('/match/${matchId}')` |
| `web/src/pages/Lobby.tsx` | `navigate('/')` (no token) | `navigate('/login')` |
| `web/src/pages/Lobby.tsx` | `<Link to="/create-room">`, `<Link to="/">` (back to login) | `/room/new`, `/login` |
| `web/src/pages/CreateRoom.tsx` | builds `/table/${roomId}`, `<Link to="/table/${roomId}">`, `<Link to="/">`, `<Link to="/lobby">` | `/room/${roomId}`, `/login`, `/play` |
| `web/src/pages/Table.tsx` | `navigate('/game/${matchId}')` (×3) | `navigate('/match/${matchId}')` |
| `web/src/pages/Game.tsx` | `navigate('/')` (×2, on disconnect/leave) | `navigate('/')` (Home is fine) |
| `web/src/pages/MatchEndOverlay.tsx` | `navigate('/lobby')` | `navigate('/play')` **+ add "Watch replay" → `navigate('/replay/${matchId}')`** |
| `web/src/pages/Shanten.tsx` | `<a href="/calc">` | `<a href="/tools/calc">` |
| `web/src/pages/Calc.tsx` | (add) link to shanten | `<a href="/tools/shanten">` |

### "Watch replay" button (MatchEndOverlay)

`MatchEndOverlay` currently only renders a "Back to lobby" button. It receives
`state` and `seatNames` props. It must also know the `matchId` to build the
replay link. `matchId` is available from `useParams()` in the parent `Game.tsx`;
pass it down as a new prop `matchId: string`. Add a secondary button "Watch
replay" that calls `navigate('/replay/${matchId}')`. Keep the existing "Back to
lobby" button but point it at `/play`.

### API call-site updates (`getApiUrl(...)`)

| File | Old endpoint | New endpoint |
|---|---|---|
| `web/src/pages/Calc.tsx` | `/api/v1/calc` | `/api/v1/tools/calc` |
| `web/src/pages/Shanten.tsx` | `/api/v1/shanten` | `/api/v1/tools/shanten` |
| `web/src/pages/Table.tsx` | `/api/v1/private-tables/${tableId}` (+`/join`,`/seat`,`/start`,`/mode`) | `/api/v1/rooms/${roomId}/...` |
| `web/src/pages/Replay.tsx` | `/api/v1/paipu/${matchId}` | `/api/v1/replays/${matchId}` |

(`matchmaking/join`, `auth/*`, `users/me`, `ws` are unchanged.)

## D. Tests

Backend (`api/*_test.go`):
- `calc_test.go` posts to `/api/v1/calc` → update to `/api/v1/tools/calc`.
- `private_tables_test.go` exercises `/private-tables/...` paths → update to
  `/rooms/:roomId/...` and assert the `lobby_update` envelope uses `room`.
- `paipu`-related assertions (if any) → `/replays/:matchId`.

Frontend: there is no existing component test harness for pages (the repo has no
`*.test.tsx`). We will not add a new frontend test framework (YAGNI). Frontend
verification is by `npm run build` (type-check + bundle) succeeding, since route
and param renames are type-checked through `useParams`/`getApiUrl` usage.

## E. Documentation & config touch points

- `web/src/pages/AGENTS.md` — update route descriptions (`/calc`, `/shanten`,
  `/table`, `/create-room`, `/game`) to the new paths; add the new `Home.tsx`.
- `web/AGENTS.md` — fix the stale `vercel.json` reference (the file does not
  currently exist at `web/vercel.json`) and the `/calc`, `/table/:tableId`
  examples.
- `api/AGENTS.md` — update any documented route paths.
- If a SPA-rewrite config (`vercel.json` or equivalent) is found during
  implementation, ensure new routes (`/play`, `/room/*`, `/match/*`,
  `/replay/*`, `/tools/*`, `/login`) resolve to `index.html`. If no such file
  exists, none is added (the Go server's `NoRoute` SPA fallback already serves
  `index.html` for all non-API, non-asset GETs, so client routes work in the
  bundled deployment regardless).

## Out of scope (YAGNI)

- Persistent global header / nav bar.
- Replay history list page.
- Auth flow changes.
- Backend route aliases or redirects (hard cut).
- Visual redesign of existing pages beyond the new Home landing.
- Renaming internal Go identifiers (`tableID`, `TableID`) — only URL segments,
  route param names, and the JSON envelope field change.
