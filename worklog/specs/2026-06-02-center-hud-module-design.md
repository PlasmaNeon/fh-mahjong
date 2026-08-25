# Center HUD Module — Design

**Date:** 2026-06-02
**Status:** Approved (pending implementation plan)

## Problem

The table's center panel (the rounded box showing `Wall`, dice, `王牌`) has three issues:

1. **It blocks the wind marks.** The per-seat wind kanji are rendered as children of `.center-info`, absolutely positioned `6px` *inside* the ~207px opaque panel box. The panel's blurred gradient background and centered chips crowd them, so the winds read as obscured.
2. **Player points are not shown.** Each player's score exists in game state (`gameState.players[].score`, defined in proto `PlayerState.score`) but is never surfaced on the table.
3. **The panel is not a module.** It is inlined JSX inside `TableBoard` ([`web/src/table/TableScene.tsx`](../../../web/src/table/TableScene.tsx) ~lines 703–728), built partly from `hudChips` constructed in [`web/src/pages/Game.tsx`](../../../web/src/pages/Game.tsx). This coupling makes it hard to adjust in isolation.

## Goals

- Extract the center panel into a self-contained, independently adjustable `CenterHud` component.
- Move the wind marks out of the panel so they are never visually blocked.
- Display each player's live score next to their wind mark.
- Orient each wind+score block to face its own seat.

## Non-Goals

- Player names in the center (scores only).
- Changes to how scores are computed or paid out (server-side, unchanged).
- Restyling the seats, hands, discards, or the info pills themselves.

## Chosen Layout (Option A, rotated, two-tone)

Wind kanji + score move **outside** the panel, against the four table-center edges, around (not inside) the panel:

- **Bottom** (local player / active example): upright.
- **Top:** rotated 180°.
- **Right:** rotated −90°.
- **Left:** rotated 90°.

So each player reads their own wind + score right-side-up from their chair.

Two-tone styling:
- Wind kanji: green (`rgba(110, 231, 183, .6)` inactive).
- Score: light (`rgba(226, 232, 240, .82)` inactive).
- **Active seat:** wind brightens to `#86efac` with glow; score brightens to `#f8fafc`.

Score format: **raw integer, no thousands separator** (e.g. `25000`). The value is live per-player state; `25000` is only example data and nothing is hardcoded.

The info panel itself (Wall / 🎲 dice / 王牌 / 海底 chips) keeps its current content and box styling.

## Architecture

### New component: `web/src/table/CenterHud.tsx`

A presentational component. No data fetching, no game logic — props in, JSX out.

```ts
type CenterHudSeat = {
  direction: 'bottom' | 'right' | 'top' | 'left'
  windKanji: string   // '' | '東' | '南' | '西' | '北'
  score: number
  isActive: boolean
}

type CenterHudProps = {
  hudChips: HudChip[]      // reuse existing HudChip type from TableScene
  seats: CenterHudSeat[]   // 0–4 entries; render only present seats
}
```

Renders:
- The `.center-info` panel box with the `hudChips` row (markup unchanged from today).
- One rotated wind+score block per seat, positioned outside the corresponding panel edge.

`HudChip` is exported from `TableScene.tsx`; `CenterHud` imports the type from there. `WIND_KANJI` (`['', '東', '南', '西', '北']`) maps `seatWind` → kanji; the mapping stays where wind data is assembled (caller), so `CenterHud` receives the resolved kanji string.

### `TableScene.tsx` changes

- Remove the inlined center JSX (the `.center-info` block and the per-seat wind `.map`).
- Import and render `<CenterHud hudChips={hudChips} seats={centerSeats} />` in its place.
- Build `centerSeats` from the existing `players` / `viewSeat` / `activeSeat` data already present in `TableBoard`, resolving direction (`getSeatDirection`), `windKanji` (via `WIND_KANJI[seat.seatWind ?? 0]`), `isActive` (`seat.seat === activeSeat`), and `score`.
- Add `score?: number` to the `PlayerTableView` type so the score can flow in.

### `Game.tsx` changes

- Add `score: player.score` to the `playerViews` mapping (~line 284) so each `PlayerTableView` carries its score.
- `hudChips` construction is unchanged.

### CSS changes (`web/src/index.css`)

- Replace the `.center-wind` / `.center-wind-{bottom,top,right,left}` rules (lines ~429–464) with placement that sits **outside** the panel box rather than `6px` inside it.
- Add a two-line wind+score block: `.center-seat` (container, flex column, rotated per direction) with `.center-seat-wind` (green) and `.center-seat-score` (light) children, plus active-state overrides.
- The panel box styling (`.center-info`, `.center-info-stats`, `.center-info-chip`) is unchanged.
- Positioning anchors off the existing `--center-hud-size` variable so spacing scales with the rest of the stage.

## Data Flow

```
gameState.players[].score
  └─ Game.tsx playerViews: { ..., score }   (PlayerTableView)
       └─ TableBoard: build centerSeats[] { direction, windKanji, score, isActive }
            └─ <CenterHud hudChips seats />
                 ├─ info panel (hudChips)
                 └─ per-seat rotated wind+score block
```

## Edge Cases

- **Missing seat / fewer than 4 players:** render only the seats present (current code already guards with `players.find(...)` returning null).
- **`seatWind` unset (0):** `WIND_KANJI[0]` is `''` — block shows score only, no kanji. Acceptable.
- **`score` unset/undefined:** fall back to `0` (or omit the score line). Default: show `0`.
- **Active seat:** exactly one seat matches `activeSeat`; only that block gets the active styling.

## Testing / Verification

- Run the web app and load a table; verify in the browser preview:
  - All four wind+score blocks sit outside the panel, none overlapped by the panel background.
  - Each block is rotated to face its seat (bottom upright, top 180°, sides ±90°).
  - Scores match `gameState.players[].score` and update after a round payout.
  - Active seat's block is visibly highlighted.
- Confirm no TypeScript errors from the new `score` field and `CenterHud` props.

## Files Touched

- **New:** `web/src/table/CenterHud.tsx`
- **Edit:** `web/src/table/TableScene.tsx` (remove inline center JSX, render `CenterHud`, add `score` to `PlayerTableView`)
- **Edit:** `web/src/pages/Game.tsx` (add `score` to `playerViews`)
- **Edit:** `web/src/index.css` (replace `.center-wind-*`, add `.center-seat*` blocks)
