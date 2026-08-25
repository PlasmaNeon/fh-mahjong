# Closed-Hand Drawn-Tile Slide Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the player discards and the just-drawn tile merges into the closed hand, make that tile **slide smoothly into its sorted position** instead of popping there, while every tile's resting order stays exactly as it is today (minimum-movement insertion).

**Architecture:** The resting order is already correct (`computeStableDisplayOrder` in `web/src/table/handOrdering.ts`). The visual jank comes from `ClosedHand.tsx` rendering the drawn tile inside a **separate DOM subtree** (`.seat-hand__drawn-slot`) and then re-rendering the same tile (same React `key`) inside the main hand row (`.seat-hand__tiles`) on discard. Same key + different DOM parent = React remount, so framer-motion's `layout="position"` cannot tween it. The fix gives each closed-hand tile a stable framer-motion **`layoutId`**, which enables a *shared-element* (a.k.a. "magic motion") transition that animates the tile from its drawn-slot box to its new in-row box even across the re-parent.

**Tech Stack:** React 19, framer-motion ^12.34.3, TypeScript, Vite, Vitest (jsdom). Manual visual verification via Vite preview + a temporary harness route.

---

## Background: why this is the fix (read before starting)

Two facts established by investigation, do not re-litigate them:

1. **Order is already correct.** Live browser repro of the user's exact hand confirmed:
   - `6m 6m 7m 8m`, draw `6m`, discard `8m` → rests as `6m 6m 6m 7m` (drawn 6m at the *last* 6m slot, 7m pushed right). ✓
   - `6m 6m 7m 8m`, draw `8m`, discard `7m` → rests as `6m 6m 8m 8m` (drawn 8m fills the 7m slot). ✓
2. **Only the transition is wrong.** Mid-animation the drawn tile is briefly stacked on its neighbor then snaps into place, because it re-parents from `.seat-hand__drawn-slot` into `.seat-hand__tiles`.

framer-motion `layoutId`: when an element with a given `layoutId` unmounts in one place and an element with the **same** `layoutId` mounts elsewhere in the same commit, framer measures the old box and animates the new element from it. That is exactly the drawn-tile-merges-into-row case. Setting `layoutId` also implies layout animation, so it fully replaces the current `layout="position"` for the in-row tiles (siblings shifting, e.g. 7m moving right, keep animating as before).

**Scope guard:** The drawn slot only renders for the self seat (bottom, no ancestor rotation) — `showClosedHand && drawnTile`, and opponents render tile backs. So we do not need to worry about framer layout projection under the rotated-seat transforms for this animation.

---

## File Structure

- `web/src/table/handOrdering.test.ts` — **NEW.** Regression tests locking the minimum-movement order. These pass immediately (the logic is already correct); their job is to fail loudly if the `ClosedHand` change or any future change perturbs ordering. One file, one responsibility: the pure ordering contract.
- `web/src/table/seat/ClosedHand.tsx` — **MODIFY.** Add `layoutId` to the per-tile `motion.div` in `renderHandTile`, replacing the `layout` prop; tune the merged-tile transition + z-index so the slide reads on top. No CSS changes, no structural changes to the drawn slot.
- `web/src/pages/HandHarness.tsx` + route in `web/src/App.tsx` — **TEMPORARY,** created in the verification task and **removed** in the cleanup task. Never committed.

---

## Task 1: Regression tests for the ordering contract

**Files:**
- Create: `web/src/table/handOrdering.test.ts`

These tests characterize the *current, correct* behavior so the animation refactor can't silently change resting order. They mirror the existing test style in `web/src/table/meldOrdering.test.ts` (Vitest `describe`/`it`/`expect`). All tiles use `suit: 0` so only `value` drives ordering (the suit comparison is exercised separately by one case).

- [ ] **Step 1: Write the tests**

```typescript
// web/src/table/handOrdering.test.ts
import { describe, it, expect } from 'vitest'
import { computeStableDisplayOrder, sortTiles } from './handOrdering'
import type { TileLike } from './types'

// same suit for all -> only value drives ordering
const t = (id: number, value: number): TileLike => ({ id, suit: 0, value })

describe('computeStableDisplayOrder', () => {
  it('sorts from scratch when there is no previous order', () => {
    const order = computeStableDisplayOrder([t(4, 8), t(1, 6), t(3, 7), t(2, 6)], null)
    // value-sorted, ties broken by id
    expect(order).toEqual([1, 2, 3, 4])
  })

  it('scenario A: draw 6m, discard 8m -> new 6m lands at the rightmost 6m slot', () => {
    // before draw: hand [6a,6b,7,8]
    let order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], null)
    expect(order).toEqual([1, 2, 3, 4])
    // draw 6c (id5): shown separately, baseTiles unchanged
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], order)
    expect(order).toEqual([1, 2, 3, 4])
    // discard 8 (id4); drawn 6c (id5) merges -> baseTiles [6a,6b,7,6c]
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(5, 6)], order)
    expect(order).toEqual([1, 2, 5, 3]) // 6a,6b,6c,7
  })

  it('scenario B: draw 8m, discard 7m -> new 8m fills the vacated 7m slot', () => {
    let order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], null)
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], order)
    // discard 7 (id3); drawn 8d (id6) merges -> baseTiles [6a,6b,8,8d]
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(4, 8), t(6, 8)], order)
    expect(order).toEqual([1, 2, 6, 4]) // 6a,6b,8d,8
  })

  it('keeps equal tiles positionally stable (no spontaneous swaps)', () => {
    // two 5m already displayed as [id10, id11]; an unrelated tile is added
    let order = computeStableDisplayOrder([t(10, 5), t(11, 5)], null)
    expect(order).toEqual([10, 11])
    order = computeStableDisplayOrder([t(10, 5), t(11, 5), t(12, 9)], order)
    expect(order).toEqual([10, 11, 12])
  })

  it('drops removed tiles and keeps survivors in their existing order', () => {
    let order = computeStableDisplayOrder([t(1, 1), t(2, 2), t(3, 3)], null)
    order = computeStableDisplayOrder([t(1, 1), t(3, 3)], order) // remove id2
    expect(order).toEqual([1, 3])
  })

  it('multi-add (e.g. meld/draw) inserts each addition at its group rightmost', () => {
    // previous [1m,3m]; add two tiles 2m(id20) and 3m(id21) at once
    let order = computeStableDisplayOrder([t(1, 1), t(2, 3)], null) // [1,2] -> values 1,3
    order = computeStableDisplayOrder([t(1, 1), t(2, 3), t(20, 2), t(21, 3)], order)
    expect(order).toEqual([1, 20, 2, 21]) // 1m, 2m, 3m(existing), 3m(new at rightmost of 3m group)
  })
})

describe('sortTiles', () => {
  it('orders by suit, then value, then id', () => {
    const sorted = sortTiles([
      { id: 2, suit: 2, value: 1 }, // pin 1
      { id: 1, suit: 3, value: 9 }, // man 9
      { id: 3, suit: 3, value: 9 }, // man 9 (higher id -> after id1)
    ])
    // getSuitOrder: MAN(3)=1, PIN(2)=2 -> man before pin
    expect(sorted.map((x) => x.id)).toEqual([1, 3, 2])
  })
})
```

- [ ] **Step 2: Run the tests, verify they PASS (green characterization)**

Run: `cd web && npx vitest run src/table/handOrdering.test.ts`
Expected: all 8 tests PASS. (They document existing correct behavior; they are not red-first because the ordering code is already correct.)

If any FAIL, stop — your understanding of the current behavior is wrong; re-read `web/src/table/handOrdering.ts` before continuing.

- [ ] **Step 3: Commit**

```bash
git add web/src/table/handOrdering.test.ts
git commit -m "test(web): regression tests for closed-hand minimum-movement ordering"
```

---

## Task 2: Slide the drawn tile into place with a shared `layoutId`

**Files:**
- Modify: `web/src/table/seat/ClosedHand.tsx` (the `renderHandTile` function, currently lines 57-89)

The only change is inside `renderHandTile`. We:
1. Give every tile a stable `layoutId={`closed-hand-tile-${tile.id}`}` so the merged drawn tile animates across the drawn-slot → row re-parent.
2. Remove the `layout={isCurrentDrawnSlot ? false : 'position'}` prop — `layoutId` supersedes it (it enables both shared-element and layout animation). The drawn-slot copy still gets a `layoutId`, which is harmless on first draw (no prior element with that id exists, so the outer draw-in wrapper plays as today).
3. Make the just-merged tile render **on top** during its slide (`zIndex` high instead of `0`) and give it a smooth, slightly longer transition so the slide is legible.

- [ ] **Step 1: Replace the `renderHandTile` body**

Find this block (currently `web/src/table/seat/ClosedHand.tsx:57-89`):

```tsx
  const renderHandTile = (tile: TileLike, { isCurrentDrawnSlot = false }: { isCurrentDrawnSlot?: boolean } = {}) => {
    const isRecentlyDrawn = isSelf && lastDrawnTileId.current === tile.id && !hasDrawnTile
    const isHiddenByOverlay = hiddenTileIds?.has(tile.id) ?? false

    return (
      <motion.div
        layout={isCurrentDrawnSlot ? false : 'position'}
        key={tile.id}
        style={{
          zIndex: isRecentlyDrawn ? 0 : 10,
          visibility: isHiddenByOverlay ? 'hidden' : undefined,
        }}
        transition={{
          layout: {
            duration: isRecentlyDrawn ? 0.15 : 0.25,
            delay: isRecentlyDrawn ? 0.05 : 0,
            ease: 'easeInOut',
          },
        }}
        className={`pov-bottom ${!isSelf ? 'small' : ''} ${isCurrentDrawnSlot ? 'drawn-tile' : ''}`}
        data-board-tile-id={isCurrentDrawnSlot ? undefined : tile.id}
        data-board-tile-role={isCurrentDrawnSlot ? undefined : 'hand'}
      >
        <TileComponent
          tile={tile}
          isInteractive={canDiscard}
          isWild={isWildTile(tile)}
          onDiscard={onDiscard}
          size={isSelf ? 'normal' : 'small'}
        />
      </motion.div>
    )
  }
```

Replace it with:

```tsx
  const renderHandTile = (tile: TileLike, { isCurrentDrawnSlot = false }: { isCurrentDrawnSlot?: boolean } = {}) => {
    // True only on the render right after a discard, for the tile that was just
    // drawn and is now merging into the row from the separate drawn slot.
    const isMergingDrawnTile = isSelf && lastDrawnTileId.current === tile.id && !hasDrawnTile
    const isHiddenByOverlay = hiddenTileIds?.has(tile.id) ?? false

    return (
      <motion.div
        // Shared-element id: lets the just-drawn tile animate from its drawn-slot
        // box into its sorted in-row box across the DOM re-parent, instead of
        // popping. Also drives the normal sibling-shift layout animation.
        layoutId={`closed-hand-tile-${tile.id}`}
        key={tile.id}
        style={{
          // The merging tile slides over its neighbours, so keep it on top.
          zIndex: isMergingDrawnTile ? 30 : 10,
          visibility: isHiddenByOverlay ? 'hidden' : undefined,
        }}
        transition={{
          layout: {
            duration: isMergingDrawnTile ? 0.28 : 0.25,
            ease: 'easeInOut',
          },
        }}
        className={`pov-bottom ${!isSelf ? 'small' : ''} ${isCurrentDrawnSlot ? 'drawn-tile' : ''}`}
        data-board-tile-id={isCurrentDrawnSlot ? undefined : tile.id}
        data-board-tile-role={isCurrentDrawnSlot ? undefined : 'hand'}
      >
        <TileComponent
          tile={tile}
          isInteractive={canDiscard}
          isWild={isWildTile(tile)}
          onDiscard={onDiscard}
          size={isSelf ? 'normal' : 'small'}
        />
      </motion.div>
    )
  }
```

Key points (do not deviate):
- `data-board-tile-id` / `data-board-tile-role` logic is **unchanged** — `tileFlight.tsx` queries those for cross-zone flight animations; breaking them breaks discard-to-pond flights.
- The drawn-slot wrapper (`ClosedHand.tsx:106-124`, the `.seat-hand__drawn-slot` block with its `initial`/`animate` draw-in offset) is **unchanged**. The inner tile it wraps now carries a `layoutId`; that's intended.
- We dropped the `delay` and renamed `isRecentlyDrawn` → `isMergingDrawnTile` for clarity (same condition).

- [ ] **Step 2: Type-check and unit tests still pass**

Run: `cd web && npx tsc --noEmit && npx vitest run src/table/handOrdering.test.ts src/table/meldOrdering.test.ts`
Expected: `tsc` clean (no errors), all unit tests PASS. (The ordering tests from Task 1 guard that resting order is unchanged.)

- [ ] **Step 3: Commit**

```bash
git add web/src/table/seat/ClosedHand.tsx
git commit -m "fix(web): slide drawn tile into its sorted slot on discard via shared layoutId"
```

---

## Task 3: Verify the slide in a real browser (temporary harness)

framer-motion layout animations are no-ops in jsdom (no real layout), so this behavior **cannot** be unit-tested — it must be verified visually. We mount the real `ClosedHand` with controlled props on a throwaway route, drive draw→discard, and confirm the merged tile *slides* (no overlap/pop) and the resting order matches Task 1.

**Files:**
- Create: `web/src/pages/HandHarness.tsx`
- Modify: `web/src/App.tsx` (add one temporary route + import)

- [ ] **Step 1: Create the harness page**

```tsx
// web/src/pages/HandHarness.tsx
import { useState } from 'react'
import { ClosedHand } from '../table/seat/ClosedHand'
import type { PlayerTableView, TileLike } from '../table/types'

// SUIT_MAN = 3 (see web/src/proto/game.ts)
const m = (id: number, value: number): TileLike => ({ id, suit: 3, value })

// 6m_a=1, 6m_b=2, 7m=3, 8m=4, drawn 6m_c=5, drawn 8m_d=6
const HAND: Record<string, { closedHand: TileLike[]; drawnTileId: number | null; label: string }> = {
  idle: { label: 'Idle: 6m 6m 7m 8m', closedHand: [m(1, 6), m(2, 6), m(3, 7), m(4, 8)], drawnTileId: null },
  draw6: { label: 'Drew 6m (id5) — in drawn slot', closedHand: [m(1, 6), m(2, 6), m(3, 7), m(4, 8), m(5, 6)], drawnTileId: 5 },
  discard8: { label: 'Discarded 8m → expect 6 6 6 7, id5 slides to last 6m slot', closedHand: [m(1, 6), m(2, 6), m(5, 6), m(3, 7)], drawnTileId: null },
  draw8: { label: 'Drew 8m (id6) — in drawn slot', closedHand: [m(1, 6), m(2, 6), m(3, 7), m(4, 8), m(6, 8)], drawnTileId: 6 },
  discard7: { label: 'Discarded 7m → expect 6 6 8 8, id6 slides into 7m slot', closedHand: [m(1, 6), m(2, 6), m(4, 8), m(6, 8)], drawnTileId: null },
}

const SEQ_A = ['idle', 'draw6', 'discard8'] as const
const SEQ_B = ['idle', 'draw8', 'discard7'] as const

export default function HandHarness() {
  const [stateKey, setStateKey] = useState<string>('idle')
  const s = HAND[stateKey]
  const player: PlayerTableView = { seat: 0, closedHand: s.closedHand, drawnTileId: s.drawnTileId, showClosedHand: true }

  return (
    <div className="game-stage" style={{ padding: 40 }}>
      <h2>ClosedHand draw→discard harness</h2>
      <p data-testid="state-label" style={{ color: '#fbbf24', margin: '8px 0 16px' }}>{s.label}</p>
      <div style={{ display: 'flex', gap: 8, marginBottom: 24, flexWrap: 'wrap', alignItems: 'center' }}>
        <strong>Scenario A:</strong>
        {SEQ_A.map((k) => (
          <button key={k} data-testid={`btn-${k}`} onClick={() => setStateKey(k)} style={{ padding: '6px 12px', background: stateKey === k ? '#2563eb' : '#374151', borderRadius: 6 }}>{k}</button>
        ))}
        <strong style={{ marginLeft: 16 }}>Scenario B:</strong>
        {SEQ_B.map((k) => (
          <button key={k} data-testid={`btn-${k}`} onClick={() => setStateKey(k)} style={{ padding: '6px 12px', background: stateKey === k ? '#2563eb' : '#374151', borderRadius: 6 }}>{k}</button>
        ))}
      </div>
      <div style={{ position: 'relative', minHeight: 200, background: '#0f5132', borderRadius: 12, padding: 24 }}>
        <ClosedHand isSelf player={player} canDiscard={false} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add the temporary route to `web/src/App.tsx`**

Add the import after the other page imports (after `import CreateRoom from './pages/CreateRoom'`):

```tsx
import HandHarness from './pages/HandHarness'
```

Add the route just before the catch-all `<Route path="*" ... />`:

```tsx
                            <Route path="/_harness/hand" element={<HandHarness />} />
```

- [ ] **Step 3: Start the dev server and verify visually**

Start the dev server (use the harness on a dedicated port to avoid clashing with any already-running instance). With the preview tooling: `preview_start` the `web` config, then navigate to `/_harness/hand`. If port 3000 is busy, add a `web-harness` config in `.claude/launch.json` pointing at a free port (e.g. `["run","dev","--prefix","web","--","--port","3007","--strictPort"]`).

Verification procedure (Scenario A):
1. Click `idle`, then `draw6`. Confirm the row reads `6m 6m 7m 8m` and the drawn `6m` sits in the separate drawn slot.
2. Click `discard8`. **Watch the transition:** the drawn `6m` must *slide* from the drawn slot leftward into the 3rd position; `7m` slides to the end; `8m` flies/exits. There must be **no frame where the drawn 6m sits stacked on 7m then snaps** — that's the bug we're removing.
3. After settle, assert DOM order and clean transforms:

```js
// run via preview_eval after ~700ms settle
JSON.stringify([...document.querySelectorAll('[data-board-tile-role="hand"]')]
  .map(e => ({ id: e.getAttribute('data-board-tile-id'),
               left: Math.round(e.getBoundingClientRect().left),
               transform: getComputedStyle(e).transform })))
```
Expected (bottom seat lays out as a horizontal row, so order is left-to-right): ids `["1","2","5","3"]` with strictly increasing `left` and `transform: "none"` on all four.

Verification procedure (Scenario B): **reload the page first** (resets `displayOrderRef`), then click `idle` → `draw8` → `discard7`. The drawn `8m` (id6) must slide into the vacated `7m` slot. Settled DOM order: ids `["1","2","6","4"]`, increasing `left`, `transform: "none"`.

- [ ] **Step 4: Capture proof**

Take a screenshot of each settled scenario (`preview_screenshot`) showing `六 六 六 七` (A) and `六 六 八 八` (B). Keep them for the PR description. Do not commit screenshots into the repo.

This task makes **no commit** — it is verification only. The harness is removed in Task 4.

---

## Task 4: Remove the harness and finalize

**Files:**
- Delete: `web/src/pages/HandHarness.tsx`
- Modify: `web/src/App.tsx` (remove the import and the `/_harness/hand` route added in Task 3)

- [ ] **Step 1: Remove the harness file and revert the route**

```bash
rm web/src/pages/HandHarness.tsx
git checkout web/src/App.tsx   # discards the temporary import + route (App.tsx had no other changes)
```

If `.claude/launch.json` was edited in Task 3 to add a `web-harness` port config, restore it to its original single `web` config (this file is gitignored, so edit it by hand).

- [ ] **Step 2: Confirm the tree is clean except the intended changes**

Run: `git status --short`
Expected: nothing related to `HandHarness` or `App.tsx`; the only committed changes are `handOrdering.test.ts` (Task 1) and `ClosedHand.tsx` (Task 2).

- [ ] **Step 3: Full check before wrapping up**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: `tsc` clean; the entire web test suite passes (includes `handOrdering.test.ts` and `meldOrdering.test.ts`).

- [ ] **Step 4: Stop any dev server started for verification**

Stop the preview/dev server(s) you started in Task 3 so nothing is left running.

---

## Self-Review (completed by plan author)

**Spec coverage:**
- "Drawn tile should slide into its minimum-movement slot, not pop / jump to the first position" → Task 2 (the `layoutId` shared-element transition) implements the slide; Task 3 verifies it visually for both of the user's exact scenarios.
- "Resting order must stay minimum-movement" → already true; Task 1 adds regression tests that guard it through the refactor.

**Placeholder scan:** No TBD/TODO/"handle edge cases"/"similar to". Every code step shows complete code; every run step shows the exact command and expected result.

**Type consistency:** `computeStableDisplayOrder(baseTiles, previousOrder)` and `sortTiles(tiles)` signatures match `web/src/table/handOrdering.ts`. `TileLike` (`{ id, suit, value }`) and `PlayerTableView` match `web/src/table/types.ts`. `ClosedHand` is imported as a named export (it is: `export function ClosedHand`) and accepts `isSelf`, `player`, `canDiscard` (matches `ClosedHandProps`). `layoutId` template string is consistent (`closed-hand-tile-${tile.id}`) in the single place it's used.

**Known risk + contingency:** If the slide does not trigger (drawn tile still pops), the most likely cause is that framer-motion isn't matching the `layoutId` across the re-parent in this version. Contingency (only if Task 3 step 2 shows a pop): wrap the two render sites in a shared `<LayoutGroup>` from `framer-motion` — import `LayoutGroup` and wrap the `.seat-hand--bottom` `<div>`'s children (the tiles row and the drawn slot) in `<LayoutGroup>...</LayoutGroup>`. This forces both sites into one layout namespace. Do this only if needed; the plain `layoutId` approach is expected to work because both render sites already live inside the same `ClosedHand` component tree.
