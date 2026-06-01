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
  replay-history list page, no auth changes.
- **Theme unification (in scope):** all non-game pages share one visual theme
  (section F). This extracts shared style primitives and re-skins the two
  divergent tool pages; it is not a from-scratch redesign of page layouts.

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
emerald/glass styling language. Every feature is reachable with one click via a
clearly labeled navigation button. Contents:

- **Play / Find Match** button → `/play` (public matchmaking)
- **Create Private Room** button → `/room/new` (generate + share a room link)
- **Scoring Calculator** button → `/tools/calc`
- **Shanten Calculator** button → `/tools/shanten`
- **Login / Account** button → `/login` when logged out; shows the logged-in
  username (from the `fh_token` in `localStorage`) when present

Each button is a React Router `<Link>` styled as a button (same
`rounded`/uppercase/emerald button language used across Login/Lobby) so the
whole card is keyboard- and screen-reader-navigable. Buttons are grouped under
short section headings ("Play", "Tools", "Account") but every feature has its
own distinct button — no nested menus. This is the primary discoverability
mechanism; section C covers the remaining inter-page links.

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

## F. Unified theme system ("Tabletop Glass")

Every non-game page must share one visual language: the existing emerald /
deep-green "tabletop glass" aesthetic (layered radial emerald glow over a deep
teal→navy gradient, dark glass cards, black-weight uppercase eyebrow labels,
emerald primary buttons). Today this is copy-pasted inline (the background
gradient string is duplicated 5× across Login/Lobby/CreateRoom/Table) and two
pages diverge entirely (Calc and Shanten use a flat `bg-slate-950` background
with amber accents and `rounded-full`/`border-slate-800` cards).

**Typography:** keep the existing `Inter`/system body font. No new webfont. This
is a structural (color/surface/layout) unification only.

### F.1 Extract shared primitives (single source of truth)

New directory `web/src/components/` with small, focused, presentational
components (TailwindCSS, no business logic). Visual values are taken verbatim
from the current Login/Lobby pages so existing pages render unchanged.

- **`PageShell.tsx`** — full-height layered background + centered max-width
  container. Background:
  `bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white min-h-screen`.
  Accepts a `maxWidth` prop (default `max-w-6xl`) and `children`.
- **`GlassCard.tsx`** — `rounded-[28px] border border-white/10 bg-slate-950/62
  p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)] backdrop-blur-sm`; accepts
  `className` for per-use overrides (e.g. accent border tint) and `children`.
- **`Eyebrow.tsx`** — `text-[11px] font-black uppercase tracking-[0.34em]
  text-emerald-300/78`; accepts `children`.
- **`PageHeading.tsx`** — `text-4xl font-black uppercase tracking-[0.12em]
  text-emerald-100 sm:text-5xl`; accepts `children`.
- **`Button.tsx`** — `<Link>`/`<button>` styled with a `variant` prop:
  - `primary`: `border border-emerald-300/24 bg-emerald-600 ... shadow-[0_20px_40px_rgba(5,150,105,0.32)] hover:bg-emerald-500` (emerald glow)
  - `secondary`: `border border-cyan-300/20 bg-cyan-950/60 text-cyan-100 hover:bg-cyan-900/70`
  - `ghost`: `border border-white/10 bg-white/5 hover:bg-white/10`
  All variants share `rounded-[24px] px-7 py-3 text-sm font-black uppercase
  tracking-[0.18em]`.

These components have one clear responsibility each and a well-defined prop
interface; pages compose them instead of repeating Tailwind strings.

### F.2 Pages that adopt the primitives (visual result unchanged)

`Login`, `Lobby` (`/play`), `CreateRoom` (`/room/new`), `Table` (`/room/:id`
waiting room), `MatchEndOverlay`, and the new `Home` are refactored to use
`PageShell` / `GlassCard` / `Eyebrow` / `PageHeading` / `Button`. They already
match the theme, so this is a DRY refactor — pixels stay the same.

### F.3 Pages that are re-skinned (visual change)

`Calc` (`/tools/calc`) and `Shanten` (`/tools/shanten`) are migrated off their
slate/amber theme onto Tabletop Glass:
- Page wrapper `<div className="w-full bg-slate-950 ...">` → `<PageShell maxWidth="max-w-7xl">`.
- Section cards `rounded-3xl border border-slate-800 bg-slate-900/70` → `GlassCard`.
- Amber accents (`border-amber-400/40`, `text-amber-200`, the `rounded-full`
  language-toggle / cross-tool buttons) → emerald/cyan `Button` variants and
  `Eyebrow`/`PageHeading` for the header.
- Their dense inner controls (notation inputs, tile palettes, result tables)
  keep their current structure; only outer chrome, card surfaces, and accent
  colors change. The amber highlight currently used for "active/important"
  affordances becomes emerald to stay on-palette.

### F.4 Excluded (in-game theme, untouched)

`Game.tsx` live play, the shared `TableScene` / `.mahjong-table` board styles in
`index.css`, and the **board area** of `Replay.tsx`. Replay's side-panel chrome
(transport controls, perspective selector container) may wrap in `GlassCard`/
`Button` so it doesn't clash, but the table board keeps the in-game theme.

## E. Documentation & config touch points

- `web/src/pages/AGENTS.md` — update route descriptions (`/calc`, `/shanten`,
  `/table`, `/create-room`, `/game`) to the new paths; add the new `Home.tsx`;
  note Calc/Shanten now use the shared Tabletop Glass theme.
- `web/src/components/AGENTS.md` — new file documenting the shared theme
  primitives (`PageShell`, `GlassCard`, `Eyebrow`, `PageHeading`, `Button`).
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
- New display webfont / typography change (keeping Inter — section F).
- From-scratch layout redesign of existing pages (theme unification only).
- Re-theming the in-game board (`Game`, `TableScene`, Replay board area).
- Renaming internal Go identifiers (`tableID`, `TableID`) — only URL segments,
  route param names, and the JSON envelope field change.
