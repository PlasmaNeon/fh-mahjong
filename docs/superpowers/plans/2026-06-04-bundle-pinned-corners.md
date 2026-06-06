# Seat Bundle — Pinned Corners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the closed hand's left edge and the open melds' right edge fixed (never move as melds grow) and guarantee no overflow at four kongs, by turning the bundle into a fixed-width box that pins the hand bottom-left and the melds bottom-right with the gap filling the middle.

**Architecture:** `.seat-bundle` becomes a fixed-width flex box (`justify-content: space-between`, width chosen by a `--self`/`--opp` modifier), still centered + rotated per seat. The hand pins to the left edge, the exposed stack (flowers above melds, melds right-aligned) pins to the right edge; the gap is the leftover middle space.

**Tech Stack:** React 19, TypeScript, CSS in `web/src/index.css`. Vitest for unchanged helpers.

**Reference spec:** `docs/superpowers/specs/2026-06-04-bundle-pinned-corners-design.md`

**Working dir for commands:** `web/`. Project-local TS: `node_modules/.bin/tsc --noEmit`.

---

## Task 1: `SeatBundle` — add self/opp modifier class

**Files:** Modify `web/src/table/seat/SeatBundle.tsx`

- [ ] **Step 1: Add the modifier class and fix the stale comment**

Replace the comment block (lines ~15–18) and the opening `<div className="seat-bundle">` (line ~32):

Comment:
```tsx
// Canonical (bottom-orientation) bundle: a fixed-width box that pins the closed
// hand to its bottom-left and the exposed stack (flowers above melds) to its
// bottom-right, with the gap filling the middle. The width depends on whether
// this is the self seat (normal tiles) or an opponent (small tiles).
```
Opening div:
```tsx
    <div className={`seat-bundle seat-bundle--${isSelf ? 'self' : 'opp'}`}>
```

- [ ] **Step 2: Typecheck**

Run: `node_modules/.bin/tsc --noEmit`
Expected: no errors.

---

## Task 2: CSS — fixed-span bundle that pins both corners

**Files:** Modify `web/src/index.css`

- [ ] **Step 1: Replace the hand-meld gap var with span + min-gap vars**

In the `.game-stage .mahjong-table` var block, replace:
```css
  --bundle-hand-meld-gap: 42px;
```
with:
```css
  --bundle-min-gap: 24px;
  --bundle-span-self: 900px;
  --bundle-span-opp: 680px;
```
(Keep `--bundle-flower-meld-gap`, `--bundle-edge-offset`, `--bundle-edge-offset-side`. The `--bundle-hand-shift` var was already removed.)

- [ ] **Step 2: Make `.seat-bundle` a fixed-width space-between box**

Replace the `.seat-bundle` rule (currently centered, content-width, `gap: var(--bundle-hand-meld-gap)`):
```css
.game-stage .seat-bundle {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: flex-end;
  gap: var(--bundle-min-gap);
  pointer-events: none;
}
```
with:
```css
.game-stage .seat-bundle {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--bundle-min-gap);
  pointer-events: none;
}
.game-stage .seat-bundle--self {
  width: var(--bundle-span-self);
}
.game-stage .seat-bundle--opp {
  width: var(--bundle-span-opp);
}
```
> `justify-content: space-between` pushes the hand to the left edge and the exposed stack to the right edge; `gap` is the *minimum* gutter so the two never touch at max content. `align-items: flex-end` keeps the hand bottom = meld bottom and (via the exposed's own `align-items: flex-end`) the meld right edge = box right edge.

- [ ] **Step 3: Build**

Run: `node_modules/.bin/tsc --noEmit && npm run build`
Expected: clean.

- [ ] **Step 4: Commit Tasks 1–2**

```bash
git add web/src/table/seat/SeatBundle.tsx web/src/index.css
git commit -m "feat(web): pin hand-left and meld-right via fixed-span bundle"
```

---

## Task 3: Harness verification + span tuning

**Files:** Modify `web/src/index.css` (tune span/gap vars only)

Dev server: `npm run dev`; open `/dev/seat`; `± meld` toggles meld count (harness uses kongs).

- [ ] **Step 1: Verify the invariant (anchors don't move)**

Measure each seat at meld counts 0, 1, 2, 4. Confirm:
- the **first hand tile's** screen position is identical across all counts;
- the **rightmost meld's** screen position is identical across all counts (≥1 meld);
- only the middle gap changes.

Measurement helper (browser eval), per seat `d`:
```js
const hand = document.querySelector(`.seat-bundle-pivot--${d} .zone-hand .pov-bottom`)?.getBoundingClientRect();
const melds = document.querySelector(`.seat-bundle-pivot--${d} .zone-melds`)?.getBoundingClientRect();
// record hand.left/top (first tile) and melds.right/bottom (rightmost meld) at each meld count
```

- [ ] **Step 2: Verify no overflow + symmetry**

- At **0 melds** (full hand) and **4 kongs**, no zone's rect is `<0` or `> viewport` on any seat.
- The hand and melds never overlap in the middle (gap ≥ 0). If they collide, increase the relevant span var.
- Left/right/top remain exact rotations (point-reflection of left↔right through table center is exact).
- Shrink `--bundle-span-self` / `--bundle-span-opp` to the smallest values that still satisfy the above (so the gap isn't needlessly huge at low meld counts).

- [ ] **Step 3: Commit tuning**

```bash
git add web/src/index.css
git commit -m "style(web): tune bundle spans"
```

---

## Task 4: Regression check

- [ ] **Step 1: Full check**

Run: `npm test && node_modules/.bin/tsc --noEmit && npm run build`
Expected: 9 tests pass, no type errors, build succeeds.

- [ ] **Step 2: Confirm animations + overlay**

`FloatingTile` draw/discard still fires; shanten indicator on self; round-result overlay melds render.

> Harness removal + branch completion remain Task 12 of `2026-06-04-modular-seat-layout.md`.

---

## Self-Review Notes

- **Spec coverage:** invariant via `space-between` pinning (Task 2), span sizing self/opp (Tasks 1–2, tuned Task 3), no-overflow + symmetry verification (Task 3), regression (Task 4).
- **Consistency:** `SeatBundle` emits `seat-bundle--self`/`--opp`; CSS widths key off those exact classes.
- **Unchanged:** pivot rotation, canonical components, `zone-melds` `row-reverse` (first-formed at right), exposed `align-items: flex-end`.
