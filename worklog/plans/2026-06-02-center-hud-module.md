# Center HUD Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract the table center panel into a standalone `CenterHud` module, move the wind marks out of the panel so they stop being blocked, and show each player's live score rotated to face their own seat.

**Architecture:** A new presentational `CenterHud` component renders a compact info panel (Wall/dice/王牌/海底) plus four wind+score blocks. `.center-info` becomes a transparent full-footprint wrapper (positioning context, ≈207px) holding a smaller visible panel at its center; the four blocks sit in the ring between the visible panel and the surrounding discard lanes, each rotated to face its seat. Score data is threaded from `gameState.players[].score` through `playerViews` → `PlayerTableView` → `CenterHud`.

**Tech Stack:** React + TypeScript (Vite), plain CSS in `web/src/index.css`. No JS test framework exists in `web/` (intentionally out of scope); verification is `tsc` typecheck + browser-preview screenshots.

---

## File Structure

- **Create:** `web/src/table/CenterHud.tsx` — the center HUD module (panel + rotated wind+score blocks). Presentational only.
- **Modify:** `web/src/table/TableScene.tsx` — add `score` to `PlayerTableView`; remove the inlined center JSX; build `centerSeats` and render `<CenterHud />`.
- **Modify:** `web/src/pages/Game.tsx` — add `score` to the `playerViews` mapping.
- **Modify:** `web/src/index.css` — split `.center-info` into wrapper + `.center-info-panel`; stack chips vertically; replace `.center-wind-*` with `.center-seat*` ring placement.

Verification baseline (run from `web/`): `npx tsc --noEmit` must pass; the app builds with `npm run build`.

---

## Task 1: Thread `score` into the player view type and data

**Files:**
- Modify: `web/src/table/TableScene.tsx:21-32` (the `PlayerTableView` type)
- Modify: `web/src/pages/Game.tsx:284-301` (the `playerViews` mapping)

- [ ] **Step 1: Add `score` to the `PlayerTableView` type**

In `web/src/table/TableScene.tsx`, the type currently is:

```ts
export type PlayerTableView = {
  seat: number
  seatWind?: number
  closedHand?: TileLike[]
  handBackCount?: number
  showClosedHand?: boolean
  drawnTileId?: number | null
  openMelds?: MeldLike[]
  flowerMelds?: TileLike[]
  discards?: TileLike[]
  shantenLabel?: string | null
}
```

Add a `score` field after `seatWind`:

```ts
export type PlayerTableView = {
  seat: number
  seatWind?: number
  score?: number
  closedHand?: TileLike[]
  handBackCount?: number
  showClosedHand?: boolean
  drawnTileId?: number | null
  openMelds?: MeldLike[]
  flowerMelds?: TileLike[]
  discards?: TileLike[]
  shantenLabel?: string | null
}
```

- [ ] **Step 2: Populate `score` in `playerViews`**

In `web/src/pages/Game.tsx`, the mapping currently starts:

```tsx
const playerViews = useMemo(() => gameState.players.map((player: any) => ({
    seat: player.seat,
    seatWind: player.seatWind,
    closedHand: player.closedHand || [],
```

Add the `score` line right after `seatWind`:

```tsx
const playerViews = useMemo(() => gameState.players.map((player: any) => ({
    seat: player.seat,
    seatWind: player.seatWind,
    score: player.score ?? 0,
    closedHand: player.closedHand || [],
```

(Leave the rest of the mapping and its dependency array unchanged. `player.score` comes from the decoded `PlayerState.score` proto field.)

- [ ] **Step 3: Typecheck**

Run (from `web/`): `npx tsc --noEmit`
Expected: PASS (no errors). The new optional field is unused so far; this just confirms it compiles.

- [ ] **Step 4: Commit**

```bash
git add web/src/table/TableScene.tsx web/src/pages/Game.tsx
git commit -m "feat(table): thread player score into PlayerTableView"
```

---

## Task 2: Create the `CenterHud` module

**Files:**
- Create: `web/src/table/CenterHud.tsx`

- [ ] **Step 1: Write the component**

Create `web/src/table/CenterHud.tsx` with exactly this content:

```tsx
import type { HudChip } from './TableScene'

export type CenterHudSeat = {
  direction: 'bottom' | 'right' | 'top' | 'left'
  windKanji: string
  score: number
  isActive: boolean
}

type CenterHudProps = {
  hudChips: HudChip[]
  seats: CenterHudSeat[]
}

export function CenterHud({ hudChips, seats }: CenterHudProps) {
  return (
    <div className="center-info text-white text-center">
      <div className="center-info-panel">
        <div className="center-info-stats">
          {hudChips.map((chip, index) => (
            <span
              key={`${chip.label}-${index}`}
              className="center-info-chip"
              style={chip.tone === 'danger' ? { color: '#ff6b6b' } : undefined}
            >
              {chip.label}
            </span>
          ))}
        </div>
      </div>

      {seats.map((seat) => (
        <div
          key={seat.direction}
          className={`center-seat center-seat-${seat.direction} ${seat.isActive ? 'center-seat-active' : ''}`}
        >
          {seat.windKanji && <span className="center-seat-wind">{seat.windKanji}</span>}
          <span className="center-seat-score">{seat.score}</span>
        </div>
      ))}
    </div>
  )
}
```

Notes:
- `HudChip` is imported as a **type only** (`import type`) from `TableScene.tsx`. This avoids a runtime circular import even though `TableScene.tsx` will import `CenterHud`.
- The chip markup is copied verbatim from the current inline panel so behavior (including the `danger` tone color) is unchanged.
- The score renders as a raw integer (`{seat.score}`) — no thousands separator.

- [ ] **Step 2: Typecheck**

Run (from `web/`): `npx tsc --noEmit`
Expected: PASS. (The component is not yet imported anywhere; this confirms it is self-consistent.)

- [ ] **Step 3: Commit**

```bash
git add web/src/table/CenterHud.tsx
git commit -m "feat(table): add CenterHud module"
```

---

## Task 3: Render `CenterHud` from `TableBoard` and remove the inline panel

**Files:**
- Modify: `web/src/table/TableScene.tsx` (import at top; replace inline center JSX at lines ~703-728)

- [ ] **Step 1: Import `CenterHud`**

At the top of `web/src/table/TableScene.tsx`, after the existing `tileUtils` import (line ~5), add:

```ts
import { CenterHud, type CenterHudSeat } from './CenterHud'
```

- [ ] **Step 2: Replace the inline center JSX**

Find this block in the `TableBoard` return (currently ~lines 703-728):

```tsx
      <div className="center-info text-white text-center">
        {POSITIONS.map((direction, idx) => {
          const seat = players.find((player) => getSeatDirection(player.seat, viewSeat) === POSITIONS[idx])
          if (!seat) return null
          const wind = seat.seatWind ?? 0
          const isActive = seat.seat === activeSeat

          return (
            <div key={direction} className={`center-wind center-wind-${direction} ${isActive ? 'center-wind-active' : ''}`}>
              {WIND_KANJI[wind] || ''}
            </div>
          )
        })}

        <div className="center-info-stats">
          {hudChips.map((chip, index) => (
            <span
              key={`${chip.label}-${index}`}
              className="center-info-chip"
              style={chip.tone === 'danger' ? { color: '#ff6b6b' } : undefined}
            >
              {chip.label}
            </span>
          ))}
        </div>
      </div>
```

Replace the **entire block above** with:

```tsx
      <CenterHud
        hudChips={hudChips}
        seats={POSITIONS.map((direction) => {
          const seat = players.find((player) => getSeatDirection(player.seat, viewSeat) === direction)
          if (!seat) return null
          return {
            direction,
            windKanji: WIND_KANJI[seat.seatWind ?? 0] || '',
            score: seat.score ?? 0,
            isActive: seat.seat === activeSeat,
          }
        }).filter((seat): seat is CenterHudSeat => seat !== null)}
      />
```

(`POSITIONS`, `WIND_KANJI`, and `getSeatDirection` are already defined in this file. `players`, `viewSeat`, `activeSeat`, and `hudChips` are already in scope in `TableBoard`.)

- [ ] **Step 3: Typecheck**

Run (from `web/`): `npx tsc --noEmit`
Expected: PASS. If `tsc` reports `WIND_KANJI` is now unused, it is still referenced inside the new `.map`, so there should be no unused-symbol error. Fix any genuine type error before continuing.

- [ ] **Step 4: Commit**

```bash
git add web/src/table/TableScene.tsx
git commit -m "feat(table): render CenterHud, remove inline center panel"
```

---

## Task 4: Restyle — wrapper + compact panel + ring-placed wind/score blocks

**Files:**
- Modify: `web/src/index.css:365-464` (the `.center-info`, `.center-info-stats`, and `.center-wind*` rules)

- [ ] **Step 1: Replace the `.center-info` and stats rules**

Find the current `.center-info` rule (lines ~365-386):

```css
.center-info {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 25;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 140px;
  height: 140px;
  padding: 0;
  background: linear-gradient(180deg, rgba(6, 23, 24, 0.82), rgba(8, 35, 37, 0.74));
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: 20px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 18px 48px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(14px);
  pointer-events: none;
}
```

Replace it with a transparent wrapper plus a new compact panel:

```css
/* Wrapper: full center footprint, positioning context only — no background. */
.center-info {
  position: absolute;
  top: 50%;
  left: 50%;
  z-index: 25;
  transform: translate(-50%, -50%);
  width: 140px;
  height: 140px;
  pointer-events: none;
}

/* Visible compact panel, centered in the wrapper. */
.center-info-panel {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.5rem 0.6rem;
  background: linear-gradient(180deg, rgba(6, 23, 24, 0.82), rgba(8, 35, 37, 0.74));
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: 16px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    0 18px 48px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(14px);
}
```

- [ ] **Step 2: Stack the chips vertically**

Find the current `.center-info-stats` rule (lines ~397-401):

```css
.center-info-stats {
  display: flex;
  gap: 0.55rem;
  margin-bottom: 0.85rem;
}
```

Replace it with a vertical stack (so the panel stays narrow enough to leave a ring):

```css
.center-info-stats {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
  margin: 0;
}
```

(Leave `.center-info-chip` unchanged.)

- [ ] **Step 3: Replace the `.center-wind*` rules with `.center-seat*`**

Find and remove this whole group (lines ~428-464):

```css
/* Wind direction labels around center HUD */
.center-wind {
  position: absolute;
  font-size: 1.1rem;
  font-weight: 700;
  color: rgba(148, 163, 184, 0.5);
  transition: color 0.2s;
}

.center-wind-active {
  color: #86efac;
  text-shadow: 0 0 10px rgba(134, 239, 172, 0.3);
}

.center-wind-bottom {
  bottom: 6px;
  left: 50%;
  transform: translateX(-50%);
}

.center-wind-top {
  top: 6px;
  left: 50%;
  transform: translateX(-50%) rotate(180deg);
}

.center-wind-right {
  right: 6px;
  top: 50%;
  transform: translateY(-50%) rotate(-90deg);
}

.center-wind-left {
  left: 6px;
  top: 50%;
  transform: translateY(-50%) rotate(90deg);
}
```

Replace the whole group with the new seat blocks:

```css
/* Per-seat wind + score blocks, placed in the ring outside the compact panel
   and inside the surrounding discard lanes. Each faces its own seat. */
.center-seat {
  position: absolute;
  display: flex;
  flex-direction: column;
  align-items: center;
  line-height: 1.1;
}

.center-seat-wind {
  font-size: 1.05rem;
  font-weight: 800;
  color: rgba(110, 231, 183, 0.6);
  transition: color 0.2s;
}

.center-seat-score {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: rgba(226, 232, 240, 0.82);
}

.center-seat-active .center-seat-wind {
  color: #86efac;
  text-shadow: 0 0 12px rgba(134, 239, 172, 0.45);
}

.center-seat-active .center-seat-score {
  color: #f8fafc;
}

.center-seat-bottom {
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
}

.center-seat-top {
  top: 2px;
  left: 50%;
  transform: translateX(-50%) rotate(180deg);
}

.center-seat-right {
  right: 2px;
  top: 50%;
  transform: translateY(-50%) rotate(-90deg);
}

.center-seat-left {
  left: 2px;
  top: 50%;
  transform: translateY(-50%) rotate(90deg);
}
```

(The in-game wrapper size comes from `.game-stage .center-info { width/height: var(--center-hud-size) }` at line ~1657, which already overrides the 140px base to ≈207px — no change needed there. The blocks anchor to that wrapper's edges, landing in the ≈14px+ ring before the discard lanes.)

- [ ] **Step 4: Typecheck/build still green**

Run (from `web/`): `npx tsc --noEmit`
Expected: PASS (CSS-only change; confirms nothing else broke).

- [ ] **Step 5: Commit**

```bash
git add web/src/index.css
git commit -m "style(table): compact center panel, ring-placed wind+score blocks"
```

---

## Task 5: Visual verification and offset tuning

**Files:** (tuning only, if needed) `web/src/index.css`

- [ ] **Step 1: Start the dev server and open the table**

Use the browser-preview workflow: start the Vite dev server (`npm run dev` in `web/`, or the preview tool's start), then navigate to a live table view (start/join a game so `gameState.players` is populated with scores).

- [ ] **Step 2: Capture a screenshot and inspect**

Take a preview screenshot of the table center. Confirm all of the following:
- The compact panel shows Wall / 🎲 dice / 王牌 (and 海底 when applicable), pills stacked vertically.
- Four wind+score blocks sit **outside** the panel — none overlapped by the panel background.
- No block overlaps the discard tiles.
- Each block is rotated to face its seat: bottom upright, top 180°, right −90°, left 90°.
- Wind kanji is green, score is light; the **active** seat's block is brighter (green wind glow + white score).
- Scores match `gameState.players[].score` and change after a round payout.

- [ ] **Step 3: Tune offsets if needed**

If any block overlaps the panel or the discards, adjust the `bottom/top/left/right` inset in the `.center-seat-{bottom,top,right,left}` rules (try `0px`–`8px`) and/or the `.center-info-panel` `padding` to resize the panel. Re-screenshot until spacing is clean. Commit any tuning:

```bash
git add web/src/index.css
git commit -m "style(table): tune center seat block offsets"
```

- [ ] **Step 4: Final typecheck**

Run (from `web/`): `npx tsc --noEmit`
Expected: PASS.

---

## Self-Review Notes

- **Spec coverage:** Module extraction (Tasks 2–3), overlap fix via wrapper+ring (Task 4), live scores threaded (Task 1) and rendered (Tasks 2–3), rotation per seat (Task 4), two-tone + active styling (Task 4). All spec sections map to a task.
- **Deviation from spec:** The spec said "keep the panel box styling as-is." Implementation requires shrinking the visible panel (wrapper + `.center-info-panel`, chips stacked vertically) because the discard ring is only ~14px — otherwise blocks can't sit outside the panel without colliding with discards. This matches the approved mockup (compact panel, vertical pills).
- **Types:** `CenterHudSeat` defined in Task 2 is used consistently in Task 3's `filter` type guard. `HudChip` imported type-only to avoid a circular runtime import.
- **No test framework:** `web/` has none; verification is `tsc` + browser preview, consistent with the repo.
