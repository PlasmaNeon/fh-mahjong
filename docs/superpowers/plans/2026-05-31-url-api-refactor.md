# URL & API Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure frontend routes and backend API paths to match user mental models (room → match → replay), add a discoverable Home page, and unify all non-game pages under one "Tabletop Glass" theme.

**Architecture:** Go (Gin) backend serving a React (Vite + React Router v6 + TailwindCSS v4) SPA. Hard cut — no backward-compatible aliases; the frontend is the only API client and is updated in lockstep.

**Tech Stack:** Go/Gin, React 19, React Router v6, TailwindCSS v4, protobufjs, Vite 7.

**Spec:** `docs/superpowers/specs/2026-05-31-url-api-refactor-design.md`

**Verification model:** Backend has Go tests (`go test ./api/...`). Frontend has no component-test harness; frontend verification is `cd web && npm run build` (TypeScript type-check + bundle) succeeding, since route/param/endpoint renames are type-checked through `useParams`/`getApiUrl` usage.

---

## Task 1: Backend API path renames

**Files:**
- Modify: `api/server.go:54-82` (`setupRoutes`)
- Modify: `api/private_tables.go` (handlers read `c.Param("tableId")` → `c.Param("roomId")`)
- Modify: `api/paipu.go` (handlers read `c.Param("matchId")` — unchanged param name)
- Test: `api/calc_test.go`, `api/private_tables_test.go`

- [ ] **Step 1: Update tests to new paths (red)**

In `api/calc_test.go` change the route registration and request path from `/api/v1/calc` to `/api/v1/tools/calc`.
In `api/private_tables_test.go` change every `/api/v1/private-tables/<id>...` to `/api/v1/rooms/<id>...` and the Gin route param to `:roomId`. Any paipu path → `/api/v1/replays/:matchId`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `go test ./api/... 2>&1 | head -40`
Expected: FAIL (routes 404 / param mismatch).

- [ ] **Step 3: Rename routes in `setupRoutes`**

```go
// Public routes
v1.POST("/auth/register", authHandler.Register)
v1.POST("/auth/login", authHandler.Login)
v1.POST("/auth/guest", authHandler.GuestLogin)
v1.POST("/tools/calc", s.handleCalc)
v1.POST("/tools/shanten", s.handleShanten)
v1.GET("/replays/:matchId", s.handleGetPaipu)
v1.POST("/replays/:matchId", s.handleUploadPaipu)
v1.GET("/ws", func(c *gin.Context) { ServeWs(s.Hub, c) })

// Protected routes
protected := v1.Group("/")
protected.Use(AuthMiddleware())
{
    protected.GET("/users/me", s.handleGetMe)
    protected.POST("/matchmaking/join", s.handleJoinQueue)

    protected.GET("/rooms/:roomId", s.handlePrivateTableGet)
    protected.POST("/rooms/:roomId/join", s.handlePrivateTableJoin)
    protected.POST("/rooms/:roomId/seat", s.handlePrivateTableSeat)
    protected.POST("/rooms/:roomId/start", s.handlePrivateTableStart)
    protected.POST("/rooms/:roomId/mode", s.handlePrivateTableMode)
}
```

- [ ] **Step 4: Update handler param reads**

In `api/private_tables.go`, every `c.Param("tableId")` → `c.Param("roomId")`. (Internal variable names like `tableID` may stay.) `api/paipu.go` keeps `c.Param("matchId")`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `go test ./api/... 2>&1 | tail -20`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "api: rename routes to /tools, /replays, /rooms"
```

---

## Task 2: Rename `lobby_update` WebSocket envelope field `table` → `room`

**Files:**
- Modify: `api/private_tables.go:~211-217` (envelope struct + assignment) and `:~243-246` (status JSON keys)
- Test: `api/private_tables_test.go`

- [ ] **Step 1: Assert new field in test (red)**

In `api/private_tables_test.go`, where the `lobby_update` payload is decoded/asserted, expect JSON key `room` instead of `table`.

- [ ] **Step 2: Run test, verify fail**

Run: `go test ./api/... -run PrivateTable 2>&1 | tail -20`
Expected: FAIL (key `room` missing).

- [ ] **Step 3: Rename the field**

In `api/private_tables.go` envelope:

```go
payload := struct {
    Type  string          `json:"type"`
    Room  string          `json:"room"`
    State json.RawMessage `json:"state"`
}{
    Type:  "lobby_update",
    Room:  table.TableID,
    State: stateJSON,
}
```

(Adjust to match the exact existing struct fields.) Also change the two `gin.H{... "table": tableID ...}` responses (~lines 243, 246) to `"room": tableID`.

- [ ] **Step 4: Run test, verify pass**

Run: `go test ./api/... -run PrivateTable 2>&1 | tail -20`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/private_tables.go api/private_tables_test.go
git commit -m "api: rename lobby_update envelope field table -> room"
```

---

## Task 3: Shared theme primitives

**Files:**
- Create: `web/src/components/PageShell.tsx`, `GlassCard.tsx`, `Eyebrow.tsx`, `PageHeading.tsx`, `Button.tsx`, `AGENTS.md`

- [ ] **Step 1: Create `PageShell.tsx`**

```tsx
import type { ReactNode } from 'react'

export default function PageShell({
    children,
    maxWidth = 'max-w-6xl',
}: { children: ReactNode; maxWidth?: string }) {
    return (
        <div className="min-h-screen bg-[radial-gradient(circle_at_50%_18%,_rgba(16,185,129,0.18),_transparent_22%),linear-gradient(180deg,_#03111a_0%,_#06352d_58%,_#041019_100%)] text-white">
            <div className={`mx-auto flex min-h-screen w-full ${maxWidth} flex-col px-6 py-10`}>
                {children}
            </div>
        </div>
    )
}
```

- [ ] **Step 2: Create `GlassCard.tsx`**

```tsx
import type { ReactNode } from 'react'

export default function GlassCard({
    children,
    className = '',
}: { children: ReactNode; className?: string }) {
    return (
        <div className={`rounded-[28px] border border-white/10 bg-slate-950/62 p-8 shadow-[0_22px_70px_rgba(0,0,0,0.3)] backdrop-blur-sm ${className}`}>
            {children}
        </div>
    )
}
```

- [ ] **Step 3: Create `Eyebrow.tsx` and `PageHeading.tsx`**

```tsx
// Eyebrow.tsx
import type { ReactNode } from 'react'
export default function Eyebrow({ children, className = '' }: { children: ReactNode; className?: string }) {
    return <p className={`text-[11px] font-black uppercase tracking-[0.34em] text-emerald-300/78 ${className}`}>{children}</p>
}
```

```tsx
// PageHeading.tsx
import type { ReactNode } from 'react'
export default function PageHeading({ children, className = '' }: { children: ReactNode; className?: string }) {
    return <h1 className={`text-4xl font-black uppercase tracking-[0.12em] text-emerald-100 sm:text-5xl ${className}`}>{children}</h1>
}
```

- [ ] **Step 4: Create `Button.tsx`**

```tsx
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

type Variant = 'primary' | 'secondary' | 'ghost'
const base = 'inline-block text-center rounded-[24px] px-7 py-3 text-sm font-black uppercase tracking-[0.18em] transition hover:-translate-y-0.5 disabled:cursor-not-allowed disabled:opacity-45'
const variants: Record<Variant, string> = {
    primary: 'border border-emerald-300/24 bg-emerald-600 text-white shadow-[0_20px_40px_rgba(5,150,105,0.32)] hover:bg-emerald-500',
    secondary: 'border border-cyan-300/20 bg-cyan-950/60 text-cyan-100 hover:bg-cyan-900/70',
    ghost: 'border border-white/10 bg-white/5 text-slate-100 hover:bg-white/10',
}

export function ButtonLink({ to, variant = 'primary', className = '', children }: { to: string; variant?: Variant; className?: string; children: ReactNode }) {
    return <Link to={to} className={`${base} ${variants[variant]} ${className}`}>{children}</Link>
}

export function Button({ variant = 'primary', className = '', children, ...rest }: { variant?: Variant; className?: string; children: ReactNode } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
    return <button className={`${base} ${variants[variant]} ${className}`} {...rest}>{children}</button>
}
```

- [ ] **Step 5: Create `web/src/components/AGENTS.md`** documenting each primitive's purpose and props.

- [ ] **Step 6: Verify build**

Run: `cd web && npm run build 2>&1 | tail -15`
Expected: build succeeds (components compile even if unused).

- [ ] **Step 7: Commit**

```bash
git add web/src/components/
git commit -m "web: add shared Tabletop Glass theme primitives"
```

---

## Task 4: Route restructure + new Home page

**Files:**
- Modify: `web/src/App.tsx`
- Create: `web/src/pages/Home.tsx`

- [ ] **Step 1: Create `Home.tsx`** using `PageShell`/`GlassCard`/`Eyebrow`/`PageHeading`/`ButtonLink`, with feature buttons: Play (`/play`, primary), Create Private Room (`/room/new`, secondary), Scoring Calculator (`/tools/calc`, ghost), Shanten Calculator (`/tools/shanten`, ghost), Login/Account (`/login`, ghost — show username from `localStorage.fh_token` if present). Layout: account button top-right, hero heading, 2×2 feature card grid (mirrors `docs/superpowers/specs/home-mockup.html`).

- [ ] **Step 2: Update `App.tsx` routes**

```tsx
import Home from './pages/Home'
// ...
<Routes>
    <Route path="/" element={<Home />} />
    <Route path="/login" element={<Login />} />
    <Route path="/play" element={<Lobby />} />
    <Route path="/room/new" element={<CreateRoom />} />
    <Route path="/room/:roomId" element={<Table />} />
    <Route path="/match/:matchId" element={<Game />} />
    <Route path="/replay/:matchId" element={<Replay />} />
    <Route path="/tools/calc" element={<Calc />} />
    <Route path="/tools/shanten" element={<Shanten />} />
    <Route path="*" element={<Navigate to="/" />} />
</Routes>
```

- [ ] **Step 3: Verify build**

Run: `cd web && npm run build 2>&1 | tail -15`
Expected: succeeds (Table still reads `useParams().tableId` — fixed in Task 5; build may warn but `tableId` becomes `undefined` only at runtime; route param rename handled in Task 5).

Note: To avoid a runtime gap, do Step 2 of Task 5 (Table param rename) before testing in browser. Build (tsc) passes regardless since `useParams()` returns `Record<string,string|undefined>`.

- [ ] **Step 4: Commit**

```bash
git add web/src/App.tsx web/src/pages/Home.tsx
git commit -m "web: add Home page and restructure routes (room/match/tools)"
```

---

## Task 5: Update navigation targets + route params + API call sites

**Files:** `Login.tsx`, `Lobby.tsx`, `CreateRoom.tsx`, `Table.tsx`, `Game.tsx`, `MatchEndOverlay.tsx`, `Calc.tsx`, `Shanten.tsx`, `Replay.tsx`

- [ ] **Step 1: Login.tsx** — `navigate('/lobby')` → `navigate('/play')`; `<Link to="/create-room">` → `to="/room/new"`.

- [ ] **Step 2: Lobby.tsx** — `navigate(\`/game/${gameState.matchId}\`)` → `\`/match/...\``; `navigate('/')` (no token) → `navigate('/login')`; `<Link to="/create-room">` → `/room/new`; `<Link to="/">` (Back To Login) → `/login`.

- [ ] **Step 3: CreateRoom.tsx** — `\`${origin}/table/${roomId}\`` → `\`${origin}/room/${roomId}\``; `<Link to={\`/table/${roomId}\`}>` → `\`/room/${roomId}\``; `<Link to="/">` → `/login`; `<Link to="/lobby">` → `/play`.

- [ ] **Step 4: Table.tsx** — rename `const { tableId } = useParams()` → `const { roomId } = useParams()` and replace every `tableId` usage in this file with `roomId` (including `private-tables` API paths → `rooms`, see Step 8, and `loadPrivateRoomSession(tableId)` etc.); `navigate(\`/game/${matchId}\`)` (×3) → `\`/match/...\``; `data.table === tableId` (lobby_update handler) → `data.room === roomId`.

- [ ] **Step 5: Game.tsx** — leave `navigate('/')` (now Home) as-is. Pass `matchId` from `useParams()` into `<MatchEndOverlay matchId={matchId} .../>` (Task 6).

- [ ] **Step 6: MatchEndOverlay.tsx** — `navigate('/lobby')` → `navigate('/play')` (see Task 6 for the replay button).

- [ ] **Step 7: Shanten.tsx** — `<a href="/calc">` → `href="/tools/calc"`. Calc.tsx — add `<a href="/tools/shanten">` cross-link (re-skin in Task 7).

- [ ] **Step 8: API call sites (`getApiUrl`)** —
  - `Calc.tsx`: `/api/v1/calc` → `/api/v1/tools/calc`
  - `Shanten.tsx`: `/api/v1/shanten` → `/api/v1/tools/shanten`
  - `Replay.tsx`: `/api/v1/paipu/${matchId}` → `/api/v1/replays/${matchId}`
  - `Table.tsx`: `/api/v1/private-tables/${roomId}` (+`/join`,`/seat`,`/start`,`/mode`) → `/api/v1/rooms/${roomId}/...`

- [ ] **Step 9: Verify build**

Run: `cd web && npm run build 2>&1 | tail -15`
Expected: succeeds, no TS errors.

- [ ] **Step 10: Commit**

```bash
git add web/src/pages/
git commit -m "web: update navigation, route params, and API call sites to new scheme"
```

---

## Task 6: "Watch replay" button on MatchEndOverlay

**Files:** `web/src/pages/MatchEndOverlay.tsx`, `web/src/pages/Game.tsx`

- [ ] **Step 1: Add `matchId` prop** to `MatchEndOverlay` `Props` (`matchId: string`).

- [ ] **Step 2: Render two buttons** — a `Watch Replay` button → `navigate(\`/replay/${matchId}\`)` and the existing `Back To Lobby` button → `navigate('/play')`.

- [ ] **Step 3: Pass `matchId`** in `Game.tsx` where `<MatchEndOverlay .../>` is rendered (~line 371), using `useParams().matchId`.

- [ ] **Step 4: Verify build**

Run: `cd web && npm run build 2>&1 | tail -15`
Expected: succeeds.

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/MatchEndOverlay.tsx web/src/pages/Game.tsx
git commit -m "web: add Watch Replay action to match-end overlay"
```

---

## Task 7: Adopt theme primitives + re-skin Calc/Shanten

**Files:** `Login.tsx`, `Lobby.tsx`, `CreateRoom.tsx`, `Table.tsx`, `MatchEndOverlay.tsx`, `Calc.tsx`, `Shanten.tsx`

- [ ] **Step 1: Refactor matching pages** (`Login`, `Lobby`, `CreateRoom`, `Table`, `MatchEndOverlay`) to wrap their outer `<div className="min-h-screen bg-[radial-gradient...">` + inner container in `<PageShell>`, replace glass-card `<div>`s with `<GlassCard>`, eyebrow `<p>`s with `<Eyebrow>`, page `<h1>`s with `<PageHeading>`, and primary/secondary/ghost buttons & `<Link>`s with `Button`/`ButtonLink`. Visual output must be unchanged.

- [ ] **Step 2: Re-skin `Calc.tsx`** — outer `<div className="w-full bg-slate-950 text-slate-100">` + `<div className="mx-auto ... max-w-7xl ...">` → `<PageShell maxWidth="max-w-7xl">`; header eyebrow/title → `Eyebrow`/`PageHeading`; section cards `rounded-3xl border border-slate-800 bg-slate-900/70 ...` → `<GlassCard>`; amber accents (`border-amber-400/40`, `text-amber-200`, `rounded-full` toggle/cross-links) → emerald/cyan `Button`/`ButtonLink`; active-state amber highlights → emerald. Keep all input/palette/result internals.

- [ ] **Step 3: Re-skin `Shanten.tsx`** — same treatment as Calc: `<div className="w-full bg-slate-950 text-slate-100 min-h-screen">` → `<PageShell maxWidth="max-w-7xl">`; cards → `GlassCard`; amber → emerald/cyan; the `/tools/calc` cross-link → `ButtonLink`.

- [ ] **Step 4: Verify build**

Run: `cd web && npm run build 2>&1 | tail -15`
Expected: succeeds.

- [ ] **Step 5: Visual spot-check (optional)** — run `npm run dev` and confirm Calc/Shanten now use the emerald glass theme and other pages look unchanged.

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/
git commit -m "web: unify all non-game pages on Tabletop Glass theme; re-skin Calc/Shanten"
```

---

## Task 8: Documentation updates

**Files:** `web/src/pages/AGENTS.md`, `web/AGENTS.md`, `api/AGENTS.md`

- [ ] **Step 1:** Update `web/src/pages/AGENTS.md` — new route paths, add `Home.tsx`, note Calc/Shanten use shared theme.

- [ ] **Step 2:** Update `web/AGENTS.md` — fix stale `vercel.json` reference (file does not exist) and the `/calc`/`/table/:tableId` examples → new paths; mention `web/src/components/` theme primitives.

- [ ] **Step 3:** Update `api/AGENTS.md` — document renamed routes (`/tools/*`, `/replays/:matchId`, `/rooms/:roomId/*`) and the `lobby_update` `room` field.

- [ ] **Step 4: Commit**

```bash
git add web/AGENTS.md web/src/pages/AGENTS.md api/AGENTS.md
git commit -m "docs: update AGENTS notes for new URL/API scheme and theme"
```

---

## Task 9: Full verification

- [ ] **Step 1:** `go build ./... && go test ./api/...` → all pass.
- [ ] **Step 2:** `cd web && npm run build` → succeeds.
- [ ] **Step 3:** Grep for stragglers — `grep -rn "private-tables\|/paipu/\|'/lobby'\|/create-room\|/game/\|/api/v1/calc\|/api/v1/shanten" web/src api --include=*.tsx --include=*.ts --include=*.go` should return only intentional matches (none for the old paths).
- [ ] **Step 4:** Manual smoke (optional): `npm run dev`, walk `/` → `/login` → `/play` → `/room/new` → `/room/:id` → match → match-end → `/replay/:id`, and `/tools/calc` ↔ `/tools/shanten`.
