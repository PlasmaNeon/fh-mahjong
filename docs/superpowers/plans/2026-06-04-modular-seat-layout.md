# Modular Seat Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose the monolithic `SeatLane` + separate `DiscardLane` into a modular `PlayerSeat` hierarchy (ClosedHand / FlowerZone / DiscardZone / OpenMeldZone→OpenMelds), and fix open melds so they sit in an inset table-corner region, ordered right-to-left (rightmost = first formed), with existing melds fixed when a new meld animates in.

**Architecture:** Each seat's four zones become independent, direction-aware React components composed by one `PlayerSeat`, rendered per seat by `TableBoard`. Pure ordering helpers move to testable modules. Zones are absolutely positioned within `.mahjong-table` (already `position: relative`) via per-direction CSS classes, replacing the old `seat-lane-shell` flex chain. The floating draw/discard animation system is untouched — its `data-board-tile-id` / `data-board-tile-role` attributes are preserved.

**Tech Stack:** React 19, TypeScript, framer-motion, Vite, Tailwind v4 + hand-written CSS in `web/src/index.css`. Vitest (added in Task 1) for the pure helpers.

**Reference spec:** `docs/superpowers/specs/2026-06-04-modular-seat-layout-design.md`

**Working directory for all commands:** `web/` (the front-end package). Paths below are repo-relative.

---

## File Structure

New (`web/src/table/`):
- `types.ts` — shared types (`TileLike`, `MeldLike`, `PlayerTableView`, `SeatLaneDirection`, `HudChip`, `RoundResult*`).
- `Tile.tsx` — `TileComponent` (extracted).
- `meldOrdering.ts` — pure `orderMelds`, `reorderMeldTiles`, `tileIdsEqual`.
- `handOrdering.ts` — pure `computeStableDisplayOrder` + helpers (extracted).
- `seat/OpenMelds.tsx` — pure meld content (motion entrance, stable keys).
- `seat/OpenMeldZone.tsx` — positioned, direction-aware meld container.
- `seat/FlowerZone.tsx` — flower rail, above melds.
- `seat/ClosedHand.tsx` — hand + drawn tile + shanten indicator.
- `seat/DiscardZone.tsx` — discard pool (extracted verbatim from `DiscardLane`).
- `seat/PlayerSeat.tsx` — composes the four zones.
- `seat/__dev__/SeatPreview.tsx` — dev-only visual harness (removed/gated at the end).
- `meldOrdering.test.ts` — unit tests.

Modified:
- `web/src/table/TableScene.tsx` — remove `SeatLane` + `DiscardLane`, render `PlayerSeat`, reuse `OpenMelds` in the round-result overlay, re-export moved symbols.
- `web/src/index.css` — replace seat-lane flex chain with per-zone anchor rules + z-index layering.
- `web/src/App.tsx` — add the dev harness route (Task 12), removed in Task 14.
- `web/package.json` — add Vitest (Task 1).

---

## Task 1: Add Vitest for the pure helpers

**Files:**
- Modify: `web/package.json`
- Create: `web/vitest.config.ts`
- Create: `web/src/table/smoke.test.ts` (temporary smoke test, deleted in step 6)

- [ ] **Step 1: Install Vitest**

Run (in `web/`):
```bash
npm install --legacy-peer-deps -D vitest@^2
```
Expected: adds `vitest` to devDependencies. (`--legacy-peer-deps` is required — the repo has a pre-existing `protobufjs-cli` peer conflict.)

- [ ] **Step 2: Add the test script**

In `web/package.json`, replace the `test` script line:
```json
    "test": "echo \"Error: no test specified\" && exit 1",
```
with:
```json
    "test": "vitest run",
    "test:watch": "vitest",
```

- [ ] **Step 3: Add Vitest config**

Create `web/vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
})
```

- [ ] **Step 4: Add a temporary smoke test**

Create `web/src/table/smoke.test.ts`:
```ts
import { describe, it, expect } from 'vitest'

describe('vitest wiring', () => {
  it('runs', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 5: Run it**

Run (in `web/`): `npm test`
Expected: PASS, 1 test passed.

- [ ] **Step 6: Delete the smoke test and commit**

```bash
rm web/src/table/smoke.test.ts
git add web/package.json web/package-lock.json web/vitest.config.ts
git commit -m "chore(web): add vitest for unit tests"
```

---

## Task 2: Extract shared types and TileComponent

**Files:**
- Create: `web/src/table/types.ts`
- Create: `web/src/table/Tile.tsx`
- Modify: `web/src/table/TableScene.tsx` (remove the moved definitions, import + re-export)

- [ ] **Step 1: Create `web/src/table/types.ts`**

Move the type definitions out of `TableScene.tsx` verbatim:
```ts
import type { ReactNode } from 'react'

export type SeatLaneDirection = 'bottom' | 'right' | 'top' | 'left'

export type TileLike = {
  id: number
  suit: number
  value: number
}

export type MeldLike = {
  tiles: TileLike[]
  calledTileId?: number | null
  calledDirection?: number | null
}

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

export type HudChip = {
  label: string
  tone?: 'default' | 'danger'
}

export type RoundResultBreakdownEntry = {
  name: string
  points: number
}

export type RoundResultPayout = {
  seat: number
  label: string
  amount: number
  readyLabel?: string | null
  readyActive?: boolean
}

export type RoundResultView = {
  isDraw: boolean
  winType?: 'tsumo' | 'ron'
  winnerLabel?: string
  discarderLabel?: string | null
  closedHand?: TileLike[]
  winTile?: TileLike | null
  winningMelds?: MeldLike[]
  flowers?: TileLike[]
  breakdown?: RoundResultBreakdownEntry[]
  totalScore?: number
  payouts?: RoundResultPayout[]
  actions?: ReactNode
}
```

- [ ] **Step 2: Create `web/src/table/Tile.tsx`**

Move `TileComponent` verbatim (it currently lives at `TableScene.tsx:138-168`):
```tsx
import { memo } from 'react'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import type { TileLike } from './types'

type TileComponentProps = {
  tile: TileLike
  isInteractive?: boolean
  size?: 'normal' | 'small'
  noGlow?: boolean
  isWild?: boolean
  onDiscard?: (tile: TileLike) => void
}

export const TileComponent = memo(function TileComponent({
  tile,
  isInteractive = false,
  size = 'normal',
  noGlow = false,
  isWild = false,
  onDiscard,
}: TileComponentProps) {
  const svgName = getTileSvgName(tile)

  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${isInteractive ? 'interactive' : ''} ${size === 'small' ? 'small' : ''}`}
      onClick={() => isInteractive && onDiscard?.(tile)}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        boxShadow: (isWild && !noGlow) ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
        position: 'relative',
      }}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
        draggable="false"
      />
    </div>
  )
})
```

- [ ] **Step 3: Update `TableScene.tsx` — delete moved code, import, re-export**

In `web/src/table/TableScene.tsx`:
1. Delete the type definitions now in `types.ts` (the `export type SeatLaneDirection` through `export type RoundResultView` blocks, lines ~8-67) and the `TileComponentProps` type + `TileComponent` definition (lines ~69-76 and ~138-168).
2. At the top of the file, add imports and re-exports:
```ts
import { TileComponent } from './Tile'
import type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
} from './types'

export { TileComponent }
export type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
}
```
(Keep `getTileName`/`getTileSvgName` imports only if still used elsewhere in the file; `getSuitOrder` is still used by the ordering helpers, leave it.)

- [ ] **Step 4: Typecheck + build**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors. (`Game.tsx` and `Replay.tsx` import `TileComponent`/`TableBoard`/`TableRoundResultOverlay` from `TableScene` — the re-export keeps them working.)

- [ ] **Step 5: Commit**

```bash
git add web/src/table/types.ts web/src/table/Tile.tsx web/src/table/TableScene.tsx
git commit -m "refactor(web): extract table types and TileComponent into modules"
```

---

## Task 3: Pure meld-ordering helpers (TDD)

**Files:**
- Create: `web/src/table/meldOrdering.ts`
- Test: `web/src/table/meldOrdering.test.ts`
- Modify: `web/src/table/TableScene.tsx` (import `tileIdsEqual`, `reorderMeldTiles`; delete its local copies + `getOrderedOpenMelds`)

**Contract:**
- `tileIdsEqual(a, b)` — true if both non-null and string-equal (matches current behavior).
- `reorderMeldTiles(meld)` — places the called tile per `calledDirection` (1=right→push, 3=left→unshift, 2=across→index 1); unchanged from current logic.
- `orderMelds(melds, direction)` — returns meld groups in DOM order so the first-formed meld lands at the anchored edge. `melds` arrives in formation order (index 0 = first formed). For `bottom` and `right` the DOM order is reversed (newest first in DOM, oldest pinned at the anchored edge); for `top` and `left` it is identity. Paired with the per-direction CSS anchor in Task 5 this yields "rightmost/first-formed pinned, new melds grow inward, existing melds fixed."

> NOTE: `getOrderedOpenMelds` is still used by `SeatLane` and is NOT touched in this task — it is deleted in Task 8 when `SeatLane` is removed. This task only extracts `tileIdsEqual` and `reorderMeldTiles`.

- [ ] **Step 1: Write the failing tests**

Create `web/src/table/meldOrdering.test.ts`:
```ts
import { describe, it, expect } from 'vitest'
import { tileIdsEqual, reorderMeldTiles, orderMelds } from './meldOrdering'
import type { MeldLike } from './types'

const t = (id: number) => ({ id, suit: 0, value: id })

describe('tileIdsEqual', () => {
  it('matches equal ids', () => expect(tileIdsEqual(5, 5)).toBe(true))
  it('matches across number/string', () => expect(tileIdsEqual(5, '5')).toBe(true))
  it('is false for null', () => {
    expect(tileIdsEqual(null, 5)).toBe(false)
    expect(tileIdsEqual(5, null)).toBe(false)
  })
})

describe('reorderMeldTiles', () => {
  it('pushes a right-called tile (dir 1) to the end', () => {
    const meld: MeldLike = { tiles: [t(10), t(11), t(12)], calledTileId: 10, calledDirection: 1 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([11, 12, 10])
  })
  it('unshifts a left-called tile (dir 3) to the front', () => {
    const meld: MeldLike = { tiles: [t(10), t(11), t(12)], calledTileId: 12, calledDirection: 3 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([12, 10, 11])
  })
  it('inserts an across-called tile (dir 2) at index 1', () => {
    const meld: MeldLike = { tiles: [t(10), t(11), t(12)], calledTileId: 10, calledDirection: 2 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([11, 10, 12])
  })
  it('leaves a concealed meld (dir 0) untouched', () => {
    const meld: MeldLike = { tiles: [t(10), t(11), t(12)], calledTileId: -1, calledDirection: 0 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([10, 11, 12])
  })
})

describe('orderMelds', () => {
  const a: MeldLike = { tiles: [t(1)] }
  const b: MeldLike = { tiles: [t(2)] }
  const c: MeldLike = { tiles: [t(3)] }
  it('reverses for bottom (first-formed pinned at right)', () => {
    expect(orderMelds([a, b, c], 'bottom')).toEqual([c, b, a])
  })
  it('reverses for right', () => {
    expect(orderMelds([a, b, c], 'right')).toEqual([c, b, a])
  })
  it('keeps order for top', () => {
    expect(orderMelds([a, b, c], 'top')).toEqual([a, b, c])
  })
  it('keeps order for left', () => {
    expect(orderMelds([a, b, c], 'left')).toEqual([a, b, c])
  })
  it('does not mutate the input', () => {
    const input = [a, b, c]
    orderMelds(input, 'bottom')
    expect(input).toEqual([a, b, c])
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run (in `web/`): `npm test -- meldOrdering`
Expected: FAIL — `Failed to resolve import './meldOrdering'`.

- [ ] **Step 3: Implement `web/src/table/meldOrdering.ts`**

```ts
import type { MeldLike, SeatLaneDirection } from './types'

export function tileIdsEqual(left: unknown, right: unknown): boolean {
  if (left == null || right == null) return false
  return String(left) === String(right)
}

export function reorderMeldTiles(meld: MeldLike) {
  const displayTiles = [...(meld.tiles || [])]
  const calledTileId = meld.calledTileId ?? -1
  const calledDirection = meld.calledDirection ?? 0
  const stolenIdx = displayTiles.findIndex((tile) => tileIdsEqual(tile.id, calledTileId))

  if (stolenIdx !== -1 && calledDirection > 0) {
    const stolen = displayTiles.splice(stolenIdx, 1)[0]
    if (calledDirection === 3) displayTiles.unshift(stolen)
    else if (calledDirection === 1) displayTiles.push(stolen)
    else if (calledDirection === 2) displayTiles.splice(1, 0, stolen)
  }

  return displayTiles
}

// Melds arrive in formation order (index 0 = first formed). Return the order in
// which meld groups should appear in the DOM along the flex main axis. Combined
// with the per-direction CSS anchor, the first-formed meld is pinned at the
// anchored (inner) edge and new melds grow inward without moving existing ones.
export function orderMelds(melds: MeldLike[], direction: SeatLaneDirection): MeldLike[] {
  if (direction === 'bottom' || direction === 'right') {
    return [...melds].reverse()
  }
  return [...melds]
}
```

- [ ] **Step 4: Run to verify pass**

Run (in `web/`): `npm test -- meldOrdering`
Expected: PASS, all tests green.

- [ ] **Step 5: Point `TableScene.tsx` at the shared helpers**

In `web/src/table/TableScene.tsx`:
1. Delete ONLY the local `tileIdsEqual` (lines ~260-263) and `reorderMeldTiles` (lines ~295-309). Leave `getOrderedOpenMelds` (lines ~311-315) in place — `SeatLane` still uses it until Task 8.
2. Add the import:
```ts
import { tileIdsEqual, reorderMeldTiles } from './meldOrdering'
```
(The round-result overlay still calls `reorderMeldTiles`; the `useLayoutEffect` snapshot and `getOrderedOpenMelds` still call `tileIdsEqual` — wait, `getOrderedOpenMelds` does not call `tileIdsEqual`; the snapshot does. Both `reorderMeldTiles` and `tileIdsEqual` are now imported, so both keep working.)

- [ ] **Step 6: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add web/src/table/meldOrdering.ts web/src/table/meldOrdering.test.ts web/src/table/TableScene.tsx
git commit -m "refactor(web): extract pure meld-ordering helpers with tests"
```

---

## Task 4: Extract `computeStableDisplayOrder` into `handOrdering.ts`

**Files:**
- Create: `web/src/table/handOrdering.ts`
- Modify: `web/src/table/TableScene.tsx` (delete the moved helpers if unused there)

- [ ] **Step 1: Create `web/src/table/handOrdering.ts`**

Move `compareTileSortKey`, `sortTiles`, `insertTileAtRightmostOfGroup`, and `computeStableDisplayOrder` verbatim from `TableScene.tsx` (lines ~174-258):
```ts
import { getSuitOrder } from '../utils/tileUtils'
import type { TileLike } from './types'

export function compareTileSortKey(a: TileLike, b: TileLike) {
  const suitA = getSuitOrder(a.suit)
  const suitB = getSuitOrder(b.suit)
  if (suitA !== suitB) return suitA - suitB
  return a.value - b.value
}

function sortTiles(tiles: TileLike[]) {
  return [...tiles].sort((a, b) => {
    const cmp = compareTileSortKey(a, b)
    if (cmp !== 0) return cmp
    return a.id - b.id
  })
}

function insertTileAtRightmostOfGroup(
  order: number[],
  tile: TileLike,
  tileMap: Map<number, TileLike>,
) {
  let insertIdx = order.length
  for (let i = 0; i < order.length; i++) {
    const current = tileMap.get(order[i])
    if (current && compareTileSortKey(tile, current) < 0) {
      insertIdx = i
      break
    }
  }
  order.splice(insertIdx, 0, tile.id)
}

export function computeStableDisplayOrder(
  baseTiles: TileLike[],
  previousOrder: number[] | null,
): number[] {
  const tileMap = new Map(baseTiles.map((t) => [t.id, t]))

  if (!previousOrder) {
    return sortTiles(baseTiles).map((t) => t.id)
  }

  const currentIds = baseTiles.map((t) => t.id)
  const currentIdSet = new Set(currentIds)
  const previousIdSet = new Set(previousOrder)
  const removedIds = previousOrder.filter((id) => !currentIdSet.has(id))
  const addedIds = currentIds.filter((id) => !previousIdSet.has(id))
  const newOrder = previousOrder.filter((id) => currentIdSet.has(id))

  if (removedIds.length === 1 && addedIds.length === 1) {
    const removedId = removedIds[0]
    const addedId = addedIds[0]
    const addedTile = tileMap.get(addedId)
    if (!addedTile) return newOrder
    const removedPosition = previousOrder.indexOf(removedId)
    const leftTile =
      removedPosition > 0 ? tileMap.get(newOrder[removedPosition - 1]) ?? null : null
    const rightTile =
      removedPosition < newOrder.length ? tileMap.get(newOrder[removedPosition]) ?? null : null
    const fits =
      (leftTile == null || compareTileSortKey(leftTile, addedTile) <= 0) &&
      (rightTile == null || compareTileSortKey(addedTile, rightTile) <= 0)
    if (fits) {
      newOrder.splice(removedPosition, 0, addedId)
    } else {
      insertTileAtRightmostOfGroup(newOrder, addedTile, tileMap)
    }
  } else {
    for (const addedId of addedIds) {
      const tile = tileMap.get(addedId)
      if (tile) insertTileAtRightmostOfGroup(newOrder, tile, tileMap)
    }
  }

  return newOrder
}
```

- [ ] **Step 2: Remove the moved copies from `TableScene.tsx`**

Delete `compareTileSortKey`, `sortTiles`, `insertTileAtRightmostOfGroup`, and `computeStableDisplayOrder` from `TableScene.tsx`. They are still referenced by `SeatLane` (until Task 10), so add an import to keep it compiling:
```ts
import { computeStableDisplayOrder } from './handOrdering'
```
(`compareTileSortKey`/`sortTiles`/`insertTileAtRightmostOfGroup` are not referenced elsewhere in `TableScene.tsx`, so no other import is needed.)

- [ ] **Step 3: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/table/handOrdering.ts web/src/table/TableScene.tsx
git commit -m "refactor(web): extract closed-hand stable ordering into handOrdering"
```

---

## Task 5: `OpenMelds` content component

**Files:**
- Create: `web/src/table/seat/OpenMelds.tsx`

Pure content: ordered meld groups → tiles, with a transform-based entrance per group keyed by stable meld identity.

- [ ] **Step 1: Create `web/src/table/seat/OpenMelds.tsx`**

```tsx
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { orderMelds, reorderMeldTiles, tileIdsEqual } from '../meldOrdering'
import type { MeldLike, SeatLaneDirection, TileLike } from '../types'

type OpenMeldsProps = {
  melds: MeldLike[]
  direction: SeatLaneDirection
  isWildTile?: (tile: TileLike) => boolean
}

// Stable identity so only a newly-appended meld mounts (and plays the entrance);
// existing melds keep their DOM node and never re-animate or move.
function meldKey(meld: MeldLike, index: number): string {
  if (meld.calledTileId != null) return `c-${meld.calledTileId}`
  const first = meld.tiles?.[0]
  return first ? `t-${first.id}` : `i-${index}`
}

export function OpenMelds({ melds, direction, isWildTile = () => false }: OpenMeldsProps) {
  const ordered = orderMelds(melds, direction)

  return (
    <>
      {ordered.map((meld, meldIndex) => (
        <motion.div
          key={meldKey(meld, meldIndex)}
          className={`seat-meld-group seat-meld-group--${direction}`}
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.18, ease: 'easeOut' }}
        >
          {reorderMeldTiles(meld).map((tile, tileIndex) => {
            const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
            return (
              <div key={tileIndex} className={`pov-${direction} small ${isStolen ? 'stolen-tile' : ''}`}>
                <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
              </div>
            )
          })}
        </motion.div>
      ))}
    </>
  )
}
```

- [ ] **Step 2: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/table/seat/OpenMelds.tsx
git commit -m "feat(web): add OpenMelds content component"
```

---

## Task 6: `OpenMeldZone`, `FlowerZone`, `ClosedHand`, `DiscardZone` components

**Files:**
- Create: `web/src/table/seat/OpenMeldZone.tsx`
- Create: `web/src/table/seat/FlowerZone.tsx`
- Create: `web/src/table/seat/ClosedHand.tsx`
- Create: `web/src/table/seat/DiscardZone.tsx`

- [ ] **Step 1: `OpenMeldZone.tsx`**

```tsx
import { OpenMelds } from './OpenMelds'
import type { MeldLike, SeatLaneDirection, TileLike } from '../types'

type OpenMeldZoneProps = {
  direction: SeatLaneDirection
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function OpenMeldZone({ direction, melds, isWildTile }: OpenMeldZoneProps) {
  if (!melds || melds.length === 0) return null
  return (
    <div className={`zone-melds zone-melds--${direction}`}>
      <OpenMelds melds={melds} direction={direction} isWildTile={isWildTile} />
    </div>
  )
}
```

- [ ] **Step 2: `FlowerZone.tsx`**

```tsx
import { TileComponent } from '../Tile'
import type { SeatLaneDirection, TileLike } from '../types'

type FlowerZoneProps = {
  direction: SeatLaneDirection
  flowers: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function FlowerZone({ direction, flowers, isWildTile = () => false }: FlowerZoneProps) {
  if (!flowers || flowers.length === 0) return null
  return (
    <div className={`zone-flowers zone-flowers--${direction}`}>
      {flowers.map((tile, index) => (
        <div key={`f-${tile.id}-${index}`} className={`pov-${direction} small`}>
          <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: `ClosedHand.tsx`** (moves the hand/drawn-tile logic out of `SeatLane`)

```tsx
import { useRef } from 'react'
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { computeStableDisplayOrder } from '../handOrdering'
import { tileIdsEqual } from '../meldOrdering'
import type { PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type ClosedHandProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

function getDrawAnimationOffset(direction: SeatLaneDirection) {
  if (direction === 'bottom') return { x: 0, y: -30 }
  if (direction === 'top') return { x: 0, y: 30 }
  if (direction === 'left') return { x: 30, y: 0 }
  return { x: -30, y: 0 }
}

export function ClosedHand({
  direction,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: ClosedHandProps) {
  const lastDrawnTileId = useRef<number | null>(null)
  const displayOrderRef = useRef<number[] | null>(null)
  const isBottomSeat = direction === 'bottom'
  const drawMotionOffset = getDrawAnimationOffset(direction)
  const showClosedHand = player.showClosedHand !== false
  const handTiles = player.closedHand || []
  const handBackCount = player.handBackCount ?? handTiles.length

  const hasDrawnTile = player.drawnTileId != null
  const baseTiles = [...handTiles]
  let drawnTile: TileLike | null = null

  if (hasDrawnTile) {
    const drawnTileIndex = baseTiles.findIndex((tile) => tileIdsEqual(tile.id, player.drawnTileId))
    if (drawnTileIndex !== -1) {
      drawnTile = baseTiles.splice(drawnTileIndex, 1)[0]
    }
  }

  if (drawnTile) {
    lastDrawnTileId.current = drawnTile.id
  }

  const nextDisplayOrder = computeStableDisplayOrder(baseTiles, displayOrderRef.current)
  displayOrderRef.current = nextDisplayOrder
  const baseTileMap = new Map(baseTiles.map((t) => [t.id, t]))
  const sortedBaseTiles = nextDisplayOrder
    .map((id) => baseTileMap.get(id))
    .filter((t): t is TileLike => t != null)

  const renderHandTile = (tile: TileLike, { isCurrentDrawnSlot = false }: { isCurrentDrawnSlot?: boolean } = {}) => {
    const isRecentlyDrawn = isBottomSeat && lastDrawnTileId.current === tile.id && !hasDrawnTile
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
        className={`pov-${direction} ${!isBottomSeat ? 'small' : ''} ${isCurrentDrawnSlot ? 'drawn-tile' : ''}`}
        data-board-tile-id={isCurrentDrawnSlot ? undefined : tile.id}
        data-board-tile-role={isCurrentDrawnSlot ? undefined : 'hand'}
      >
        <TileComponent
          tile={tile}
          isInteractive={canDiscard}
          isWild={isWildTile(tile)}
          onDiscard={onDiscard}
          size={isBottomSeat ? 'normal' : 'small'}
        />
      </motion.div>
    )
  }

  return (
    <div className={`zone-hand zone-hand--${direction}`}>
      <div className={`seat-hand seat-hand--${direction}`}>
        <div className={`seat-hand__tiles seat-hand__tiles--${direction}`}>
          {showClosedHand ? (
            sortedBaseTiles.map((tile) => renderHandTile(tile))
          ) : (
            Array(handBackCount).fill(null).map((_, index) => (
              <div key={`back-${index}`} className={`pov-${direction} small`}>
                <div className="mahjong-tile-back small" />
              </div>
            ))
          )}
        </div>

        {showClosedHand && drawnTile && (
          <div
            className={`seat-hand__drawn-slot seat-hand__drawn-slot--${direction}`}
            data-board-tile-id={drawnTile.id}
            data-board-tile-role="drawn"
          >
            <motion.div
              initial={{ opacity: 0, ...drawMotionOffset }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{
                opacity: { duration: 0.16, ease: 'easeOut' },
                x: { duration: 0.22, ease: 'easeOut' },
                y: { duration: 0.22, ease: 'easeOut' },
              }}
            >
              {renderHandTile(drawnTile, { isCurrentDrawnSlot: true })}
            </motion.div>
          </div>
        )}
      </div>

      {isBottomSeat && player.shantenLabel && (
        <div className="shanten-indicator">{player.shantenLabel}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: `DiscardZone.tsx`** (extract `DiscardLane` verbatim, rename)

```tsx
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { tileIdsEqual } from '../meldOrdering'
import type { SeatLaneDirection, TileLike } from '../types'

type DiscardZoneProps = {
  direction: SeatLaneDirection
  discards: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscardTileId?: number | null
  hiddenTileIds?: Set<number>
}

export function DiscardZone({
  direction,
  discards,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscardTileId = null,
  hiddenTileIds,
}: DiscardZoneProps) {
  return (
    <div className={`discard-lane discard-lane--${direction} ${discards.length === 0 ? 'discard-lane--empty' : ''}`}>
      {discards.length === 0 ? (
        <div className="discard-lane__placeholder" aria-hidden="true" />
      ) : (
        discards.map((tile) => {
          const isNewDiscard = animateDiscardTileIds?.has(tile.id) ?? false
          const isCallableDiscard = tileIdsEqual(callableDiscardTileId, tile.id)

          return (
            <motion.div
              key={tile.id}
              initial={isNewDiscard ? { opacity: 0, scale: 0.82 } : false}
              animate={{ opacity: 1, scale: 1 }}
              transition={{
                opacity: { duration: 0.08, ease: 'easeOut' },
                scale: { duration: 0.1, ease: 'easeOut' },
              }}
              className={`discard-lane__tile ${isCallableDiscard ? 'discard-lane__tile--callable' : ''}`}
              style={hiddenTileIds?.has(tile.id) ? { visibility: 'hidden' } : undefined}
            >
              <motion.div
                layout="position"
                transition={{ layout: { duration: 0.18, ease: 'easeOut' } }}
                className={`pov-${direction} small`}
                data-board-tile-id={tile.id}
                data-board-tile-role="discard"
              >
                <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} noGlow={isCallableDiscard} />
              </motion.div>
            </motion.div>
          )
        })
      )}
    </div>
  )
}
```
> NOTE: verify the inner `motion.div` close tags match the original `DiscardLane` (the original closes both `motion.div`s and the map). Copy the exact closing structure from `TableScene.tsx:393-437` if unsure.

- [ ] **Step 5: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/table/seat/OpenMeldZone.tsx web/src/table/seat/FlowerZone.tsx web/src/table/seat/ClosedHand.tsx web/src/table/seat/DiscardZone.tsx
git commit -m "feat(web): add zone components (melds, flowers, hand, discards)"
```

---

## Task 7: `PlayerSeat` composition

**Files:**
- Create: `web/src/table/seat/PlayerSeat.tsx`

- [ ] **Step 1: Create `web/src/table/seat/PlayerSeat.tsx`**

```tsx
import { ClosedHand } from './ClosedHand'
import { FlowerZone } from './FlowerZone'
import { DiscardZone } from './DiscardZone'
import { OpenMeldZone } from './OpenMeldZone'
import type { PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type PlayerSeatProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

export function PlayerSeat({
  direction,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
  animateDiscardTileIds,
  callableDiscard,
}: PlayerSeatProps) {
  const callableDiscardTileId =
    callableDiscard?.seat === player.seat ? callableDiscard.tileId : null

  return (
    <>
      <DiscardZone
        direction={direction}
        discards={player.discards || []}
        isWildTile={isWildTile}
        animateDiscardTileIds={animateDiscardTileIds}
        callableDiscardTileId={callableDiscardTileId}
        hiddenTileIds={hiddenTileIds}
      />
      <OpenMeldZone
        direction={direction}
        melds={player.openMelds || []}
        isWildTile={isWildTile}
      />
      <FlowerZone
        direction={direction}
        flowers={player.flowerMelds || []}
        isWildTile={isWildTile}
      />
      <ClosedHand
        direction={direction}
        player={player}
        canDiscard={canDiscard}
        onDiscard={onDiscard}
        isWildTile={isWildTile}
        hiddenTileIds={hiddenTileIds}
      />
    </>
  )
}
```
> DOM order here (discards → melds → flowers → hand) is the natural stacking fallback; explicit `z-index` is added in Task 9 so stacking does not depend on it.

- [ ] **Step 2: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/table/seat/PlayerSeat.tsx
git commit -m "feat(web): add PlayerSeat composing the four zones"
```

---

## Task 8: Wire `PlayerSeat` into `TableBoard`; reuse `OpenMelds` in the overlay; remove old code

**Files:**
- Modify: `web/src/table/TableScene.tsx`

- [ ] **Step 1: Replace the two seat loops with one `PlayerSeat` loop**

In `TableScene.tsx`, find the `DiscardLane` loop (~lines 721-731) and the `SeatLane` loop (~lines 733-743) inside `TableBoard`'s return. Replace BOTH with a single loop:
```tsx
      {seatViews.map(({ player, direction }) => (
        <PlayerSeat
          key={`seat-${player.seat}`}
          direction={direction}
          player={player}
          canDiscard={direction === 'bottom' && player.seat === canDiscardSeat}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
          animateDiscardTileIds={animateDiscardTileIds}
          callableDiscard={callableDiscard}
        />
      ))}
```

- [ ] **Step 2: Import `PlayerSeat` and `OpenMelds`; delete dead components/helpers**

In `TableScene.tsx`:
1. Add imports:
```ts
import { PlayerSeat } from './seat/PlayerSeat'
import { OpenMelds } from './seat/OpenMelds'
```
2. Delete the now-dead `SeatLane` component, `DiscardLane` component, `SeatLaneProps`/`DiscardLaneProps` types, `getOrderedOpenMelds`, and `getDrawAnimationOffset` (now living in `ClosedHand`). Keep `getTileRotation`, `FloatingTile`, the `useLayoutEffect` snapshot, `getSeatDirection`, `WIND_KANJI`, `POSITIONS`, `CenterHud` usage, and `TableRoundResultOverlay`.

- [ ] **Step 3: Reuse `OpenMelds` in the round-result overlay**

In `TableRoundResultOverlay` (~lines 813-828), replace the inline winning-melds map:
```tsx
                {winningMelds.length > 0 && (
                  <div className="round-result-melds-divider">
                    {winningMelds.map((meld, meldIndex) => (
                      <div key={`m-${meldIndex}`} className="seat-meld-group seat-meld-group--bottom">
                    {reorderMeldTiles(meld).map((tile, tileIndex) => {
                          const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
                          return (
                            <div key={tileIndex} className={`pov-bottom small ${isStolen ? 'stolen-tile' : ''}`}>
                              <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                            </div>
                          )
                        })}
                      </div>
                    ))}
                  </div>
                )}
```
with:
```tsx
                {winningMelds.length > 0 && (
                  <div className="round-result-melds-divider">
                    <OpenMelds melds={winningMelds} direction="bottom" isWildTile={isWildTile} />
                  </div>
                )}
```
> The overlay should show winning melds in formation order; if visual review in Task 13 shows they read reversed, pass an already-ordered array or add a dedicated prop. Leave as-is for now.

- [ ] **Step 4: Typecheck**

Run (in `web/`): `npx tsc --noEmit`
Expected: no errors. If tsc flags an unused `reorderMeldTiles` import (now only used via `OpenMelds`), remove it from the import in `TableScene.tsx`; keep `tileIdsEqual` (still used by the snapshot).

- [ ] **Step 5: Commit**

```bash
git add web/src/table/TableScene.tsx
git commit -m "refactor(web): render PlayerSeat per seat; reuse OpenMelds in overlay"
```

---

## Task 9: Per-zone CSS — anchors, inset meld region, z-index layering

**Files:**
- Modify: `web/src/index.css`

These are *starting* values; exact insets/gaps are tuned in Task 11.

- [ ] **Step 1: Add layout vars**

In the `.game-stage .mahjong-table` rule (the var block starting ~line 1332), add after `--seat-exposed-gap: 10px;`:
```css
  --meld-inset-x: 56px;
  --meld-inset-y: 40px;
  --meld-group-gap: 12px;
  --meld-row-size: var(--tile-small-height);
  --flower-meld-gap: 10px;
  --hand-bottom-offset: 28px;
  --hand-center-shift: 96px;
  --zone-z-discards: 12;
  --zone-z-melds: 14;
  --zone-z-flowers: 15;
  --zone-z-hand: 16;
```

- [ ] **Step 2: Add zone anchor rules**

Append a new block to `web/src/index.css` (after the existing seat rules, near line ~1790):
```css
/* ===== Modular per-player zones (PlayerSeat) ===== */

.game-stage .zone-hand {
  position: absolute;
  z-index: var(--zone-z-hand);
  pointer-events: auto;
}
/* Position only — tile orientation is handled by the existing `pov-{dir}` and
   `seat-hand--{dir}` classes inside ClosedHand. Do NOT rotate the container, or
   it double-rotates the already-pov-oriented tiles. The translate offsets the
   hand toward the side OPPOSITE that seat's meld region (tuned in Task 11). */
.game-stage .zone-hand--bottom {
  left: 50%;
  bottom: var(--hand-bottom-offset);
  transform: translateX(calc(-50% - var(--hand-center-shift)));
}
.game-stage .zone-hand--top {
  left: 50%;
  top: var(--hand-bottom-offset);
  transform: translateX(calc(-50% + var(--hand-center-shift)));
}
.game-stage .zone-hand--left {
  left: var(--side-hand-edge);
  top: 50%;
  transform: translateY(calc(-50% - var(--hand-center-shift)));
}
.game-stage .zone-hand--right {
  right: var(--side-hand-edge);
  top: 50%;
  transform: translateY(calc(-50% + var(--hand-center-shift)));
}

.game-stage .zone-melds {
  position: absolute;
  display: flex;
  gap: var(--meld-group-gap);
  z-index: var(--zone-z-melds);
  pointer-events: none;
}
.game-stage .zone-melds--bottom {
  right: var(--meld-inset-x);
  bottom: var(--meld-inset-y);
  flex-direction: row;
  align-items: flex-end;
}
.game-stage .zone-melds--top {
  left: var(--meld-inset-x);
  top: var(--meld-inset-y);
  flex-direction: row;
  align-items: flex-start;
}
.game-stage .zone-melds--right {
  right: var(--meld-inset-x);
  top: var(--meld-inset-y);
  flex-direction: column;
  align-items: flex-end;
}
.game-stage .zone-melds--left {
  left: var(--meld-inset-x);
  bottom: var(--meld-inset-y);
  flex-direction: column;
  align-items: flex-start;
  /* keep the upward-growing stack clear of the upper-left wild-tile box */
  max-height: calc(100% - var(--meld-inset-y) - var(--wild-tile-top) - 140px);
  overflow: visible;
}

.game-stage .zone-flowers {
  position: absolute;
  display: flex;
  gap: 4px;
  z-index: var(--zone-z-flowers);
  pointer-events: none;
}
.game-stage .zone-flowers--bottom {
  right: var(--meld-inset-x);
  bottom: calc(var(--meld-inset-y) + var(--meld-row-size) + var(--flower-meld-gap));
  flex-direction: row-reverse;
}
.game-stage .zone-flowers--top {
  left: var(--meld-inset-x);
  top: calc(var(--meld-inset-y) + var(--meld-row-size) + var(--flower-meld-gap));
  flex-direction: row;
}
.game-stage .zone-flowers--right {
  right: calc(var(--meld-inset-x) + var(--meld-row-size) + var(--flower-meld-gap));
  top: var(--meld-inset-y);
  flex-direction: column-reverse;
}
.game-stage .zone-flowers--left {
  left: calc(var(--meld-inset-x) + var(--meld-row-size) + var(--flower-meld-gap));
  bottom: var(--meld-inset-y);
  flex-direction: column;
}

.game-stage .discard-lane { z-index: var(--zone-z-discards); }
```

- [ ] **Step 3: Keep meld-group + stolen-tile rules**

Confirm the existing `.seat-meld-group`, `.seat-meld-group--{dir}` (lines ~772-803) and `.pov-*.stolen-tile` (lines ~1783-1789) rules remain — `OpenMelds` still uses those class names. Do not delete them.

- [ ] **Step 4: Remove the dead seat-lane CSS**

Delete the now-unused rules: `.seat-lane-shell*`, `.seat-lane`, `.seat-lane--*`, `.seat-lane__closed*`, `.seat-lane__gap*`, `.seat-exposed*`, `.seat-flower-rail*`, and `.seat-meld-rail*` (the `.game-stage` variants around lines ~1516-1781, plus any base copies). Keep `.seat-hand*`, `.seat-hand__tiles*`, `.seat-hand__drawn-slot*` (still used by `ClosedHand`), `.shanten-indicator`, `.discard-lane*`, `.mahjong-tile*`, `.pov-*`, and `.mahjong-tile-back*`.

- [ ] **Step 5: Build**

Run (in `web/`): `npx tsc --noEmit && npm run build`
Expected: build succeeds (no TS or Vite errors).

- [ ] **Step 6: Commit**

```bash
git add web/src/index.css
git commit -m "style(web): per-zone anchors, inset meld region, z-index layering"
```

---

## Task 10: Dev-only visual harness route

**Files:**
- Create: `web/src/table/seat/__dev__/SeatPreview.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Create the harness**

`web/src/table/seat/__dev__/SeatPreview.tsx`:
```tsx
import { useState } from 'react'
import { TableBoard } from '../../TableScene'
import type { MeldLike, PlayerTableView, TileLike } from '../../types'

const tile = (id: number, suit = 0, value = 1): TileLike => ({ id, suit, value })
const pung = (base: number, suit: number, value: number, calledDirection = 1): MeldLike => ({
  tiles: [tile(base, suit, value), tile(base + 1, suit, value), tile(base + 2, suit, value)],
  calledTileId: base,
  calledDirection,
})

function makePlayer(seat: number, meldCount: number): PlayerTableView {
  const melds = [
    pung(100 + seat * 50, 0, 2, 1),
    pung(110 + seat * 50, 1, 5, 2),
    pung(120 + seat * 50, 2, 7, 3),
    pung(130 + seat * 50, 0, 9, 1),
  ].slice(0, meldCount)
  return {
    seat,
    seatWind: seat + 1,
    score: 0,
    showClosedHand: seat === 0,
    closedHand: Array.from({ length: 13 - meldCount * 3 }, (_, i) => tile(seat * 20 + i, i % 3, (i % 9) + 1)),
    handBackCount: 13 - meldCount * 3,
    flowerMelds: [tile(900 + seat * 4, 5, 1), tile(901 + seat * 4, 5, 2)],
    openMelds: melds,
    discards: Array.from({ length: 6 }, (_, i) => tile(700 + seat * 20 + i, i % 3, (i % 9) + 1)),
  }
}

export default function SeatPreview() {
  const [meldCount, setMeldCount] = useState(2)
  const players = [0, 1, 2, 3].map((seat) => makePlayer(seat, meldCount))

  return (
    <div className="game-stage" style={{ width: '100vw', height: '100vh' }}>
      <div style={{ position: 'absolute', zIndex: 999, top: 8, right: 8, display: 'flex', gap: 8 }}>
        <button onClick={() => setMeldCount((n) => Math.max(0, n - 1))}>- meld</button>
        <span style={{ color: '#fff' }}>{meldCount} melds</span>
        <button onClick={() => setMeldCount((n) => Math.min(4, n + 1))}>+ meld</button>
      </div>
      <div className="mahjong-table">
        <div className="wild-tile-corner">
          <div className="wild-tile-corner-main">
            <div className="wild-tile-corner-label">Wild Tile</div>
          </div>
        </div>
        <TableBoard viewSeat={0} players={players} activeSeat={0} />
      </div>
    </div>
  )
}
```
> The `+ meld` / `- meld` buttons let you confirm existing melds stay fixed and only the new one animates in.

- [ ] **Step 2: Add a dev route in `App.tsx`**

Add to the route list in `web/src/App.tsx` (next to the other `<Route>` entries):
```tsx
import SeatPreview from './table/seat/__dev__/SeatPreview'
```
```tsx
                            <Route path="/dev/seat" element={<SeatPreview />} />
```

- [ ] **Step 3: Run the dev server and open the harness**

Run (in `web/`): `npm run dev`
Open `/dev/seat`. Expected: the four seats render with hands, flowers, discards, and melds.

- [ ] **Step 4: Commit**

```bash
git add web/src/table/seat/__dev__/SeatPreview.tsx web/src/App.tsx
git commit -m "test(web): add dev-only seat layout preview harness"
```

---

## Task 11: Visual verification and tuning

**Files:**
- Modify: `web/src/index.css` (tune vars only)

Use the running dev server + `/dev/seat`, and the browser preview tools.

- [ ] **Step 1: Verify bottom seat**

Confirm: hand near center but offset left with a clear gap to the meld stack; flowers directly above the melds, growing right-to-left; melds in an inset bottom-right region (not jammed in the corner); rightmost meld = first formed. Toggle `+ meld` and confirm existing melds do not move and only the new one animates in.

- [ ] **Step 2: Verify the other three seats**

Confirm top/left/right mirror correctly and nothing leaves the table. Specifically test the **left seat at 4 melds** and confirm its hand and upward-growing meld stack stay clear of the upper-left wild-tile box. Adjust `--meld-inset-x/y`, `--flower-meld-gap`, `--hand-center-shift`, and the `zone-melds--left` `max-height` as needed.

- [ ] **Step 3: Verify animations + overlay**

In a real game (or by inspection), confirm draw/discard floating-tile animation still fires, discards still animate/​highlight when callable, the shanten indicator shows for the bottom seat, and the round-result overlay melds render.

- [ ] **Step 4: Commit any tuning**

```bash
git add web/src/index.css
git commit -m "style(web): tune seat zone insets and gaps"
```

---

## Task 12: Remove the harness (or gate it) and finalize

**Files:**
- Modify: `web/src/App.tsx`
- Delete: `web/src/table/seat/__dev__/SeatPreview.tsx`

- [ ] **Step 1: Remove the dev route and harness**

Remove the `SeatPreview` import and the `/dev/seat` `<Route>` from `App.tsx`, and delete the harness file:
```bash
git rm web/src/table/seat/__dev__/SeatPreview.tsx
```
(If you prefer to keep it for future use, instead guard the route with `import.meta.env.DEV` so it is excluded from production builds — choose one.)

- [ ] **Step 2: Full check**

Run (in `web/`): `npm test && npx tsc --noEmit && npm run build`
Expected: tests pass, no type errors, build succeeds.

- [ ] **Step 3: Commit**

```bash
git add web/src/App.tsx
git commit -m "chore(web): remove dev seat preview harness"
```

---

## Self-Review Notes (for the implementer)

- **Spec coverage:** modular hierarchy (Tasks 5-7), meld order + stability + entrance (Tasks 3, 5, 9, 11), inset meld region (Task 9), discards folded into `PlayerSeat` (Tasks 6-8), flowers above melds (Tasks 6, 9), hand offset-left (Task 9), wild-tile clearance (Tasks 9, 11), round-result reuse (Task 8), unit tests (Tasks 1, 3), visual harness (Tasks 10-12).
- **Stability invariant:** the meld zone is anchored at the first-formed edge (right/bottom for `bottom`) and `orderMelds` reverses bottom/right so the oldest meld is pinned; new melds prepend on the growth side. Confirm visually in Task 11 — if existing melds shift, the anchor side and `orderMelds` direction for that seat are mismatched.
- **Do not break** the `data-board-tile-id` / `data-board-tile-role` attributes — `FloatingTile` depends on them.
