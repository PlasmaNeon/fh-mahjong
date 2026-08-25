# Opponent Tedashi Drawn-Tile Slide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an opponent's tedashi animate like the self player — the discarded tile leaves a gap in the concealed hand and the drawn back slides in to fill it — using hand-slot positions instead of tile ids.

**Architecture:** The discard-flight planner (`planTileFlights`, pure/React-free) already flies an opponent tedashi discard from a random previous hand slot. Extend it to (a) slide the drawn back from the drawn slot into that same gap rect and (b) emit a `hideHandSlot` marker; a pure helper turns active flights into a per-direction set of hidden slot indices, which the flight hook returns and the seat components thread into `ClosedHand` to blank that rail slot during the flight. No tile-id tracking across frames, so it survives production's per-broadcast id rotation.

**Tech Stack:** React 19 + TypeScript, Framer Motion, Vite 7, Vitest 2 (node env).

## Global Constraints

- **Frontend only.** No changes to `proto/`, `internal/engine`, `internal/api`, or any Go. No proto regeneration.
- **Do not change self-seat or tsumogiri behavior.** Only the opponent tedashi path gains the merge/gap.
- **Tests:** Vitest runs in a `node` environment over `web/src/**/*.test.ts` only — there is **no** DOM/component-test infra. Pure logic goes in `web/src/table/tileFlightPlan.ts` and is unit-tested in `web/src/table/tileFlightPlan.test.ts`. React component/threading changes are verified with `tsc`/`vite build` + manual dev, not unit tests.
- **Run tests/build from `web/`:** `npm run test` (= `vitest run`) and `npm run build` (= `tsc && vite build`).
- **Local opponents are anonymized by default** (redaction is fail-closed since commit `be044ab`). Set `MAHJONG_DEV_REVEAL_HANDS=1` on the backend only to reveal real faces; leave it unset to exercise the real anonymized path.
- Commit after each task. Keep changes DRY / YAGNI.

---

### Task 1: Slot-based tedashi merge in the flight planner

**Files:**
- Modify: `web/src/table/tileFlightPlan.ts` (type `FlyingTileAnimation` ~lines 22–32; the tedashi branch ~lines 147–177)
- Test: `web/src/table/tileFlightPlan.test.ts` (replace the existing `tedashi` test ~lines 44–68; add a new no-draw test)

**Interfaces:**
- Consumes: existing `planTileFlights`, `MotionSnapshot`, `prevTileIdsByRole`, `MIN_TRAVEL_DISTANCE`.
- Produces: `FlyingTileAnimation` gains `hideHandSlot?: { direction: SeatLaneDirection; index: number }`. On an opponent tedashi *with a preceding draw*, `planTileFlights` returns two animations: the discard (from the chosen hand-slot rect `R`) and a `{ asBack: true, hideHandSlot }` drawn-back merge whose `fromRect` is the drawn-slot rect and `toRect` is `R`.

- [ ] **Step 1: Replace the existing tedashi test with a rotation-modeling test**

In `web/src/table/tileFlightPlan.test.ts`, replace the whole `it('tedashi: ...')` block (currently lines ~44–68) with the version below. The difference that matters: the drawn tile's previous id (`1009`) is **absent from `currentLocations`/`currentRects`**, modeling production's per-broadcast id rotation (the drawn tile's current id is different/unknowable). The merge must still be produced from previous-snapshot rects.

```ts
  it('tedashi: discard flies from a random hand slot + drawn back slides into that gap (id-rotation safe)', () => {
    // Drawn tile 1009 is NOT present in the current frame under its old id
    // (production re-randomizes opponent ids every broadcast).
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE]])
    const animations = planTileFlights({
      previousSnapshot: prevSnapshot(),
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]),
      random: () => 0, // deterministic: pick the first hand slot (1001 @ left 10)
    })
    expect(animations).toHaveLength(2)
    const discard = animations.find((a) => a.tile.id === 42)!
    const merge = animations.find((a) => a.asBack)!
    // Discard leaves the chosen gap slot.
    expect(discard.fromRect.left).toBe(10)
    expect(discard.toRect.left).toBe(200)
    // Drawn back slides from the drawn slot INTO the same gap rect (no current-id lookup).
    expect(merge.fromRect.left).toBe(60)
    expect(merge.toRect.left).toBe(10)
    expect(merge.tile.id).toBe(1009)
    // The chosen rail slot is flagged for hiding during the flight.
    expect(merge.hideHandSlot).toEqual({ direction: 'top', index: 0 })
  })

  it('tedashi with no preceding draw: discard flies, but no merge/gap', () => {
    // Opponent discarding after a pon (no drawn tile in the previous snapshot).
    const previousSnapshot: MotionSnapshot = {
      locations: new Map<number, TileMotionDescriptor>([
        [1001, { tile: tile(1001), direction: 'top', role: 'hand' }],
        [1002, { tile: tile(1002), direction: 'top', role: 'hand' }],
      ]),
      rects: new Map<number, TileRect>([[1001, rect(10)], [1002, rect(20)]]),
      handOrigins: new Map([['top', { left: 0, top: 0, width: 80, height: 14 }]]),
    }
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE]])
    const animations = planTileFlights({
      previousSnapshot,
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]),
      random: () => 0,
    })
    expect(animations).toHaveLength(1)
    expect(animations[0].asBack).toBeFalsy()
    expect(animations[0].hideHandSlot).toBeUndefined()
    expect(animations[0].fromRect.left).toBe(10) // still from a hand slot
  })
```

- [ ] **Step 2: Run the tests to verify the new tedashi test fails**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: FAIL — the rotation test expects length 2 but current code produces length 1 (its `mergeTo = currentRects.get(1009)` is `undefined`, so no merge flight), and `merge.hideHandSlot` doesn't exist. (The no-draw test may already pass.)

- [ ] **Step 3: Add `hideHandSlot` to the animation type**

In `web/src/table/tileFlightPlan.ts`, extend `FlyingTileAnimation` (keep the existing fields and the `asBack` doc comment):

```ts
export type FlyingTileAnimation = {
  key: number
  tile: TileLike
  direction: SeatLaneDirection
  fromRect: TileRect
  toRect: TileRect
  isWild: boolean
  // True for the drawn-back "merge into hand" flight on a tedashi (renders a
  // face-down back instead of the tile face).
  asBack?: boolean
  // When set, the seat's concealed rail slot at `index` is blanked for the
  // flight's duration so the tedashi gap is visible while the drawn back fills it.
  hideHandSlot?: { direction: SeatLaneDirection; index: number }
}
```

- [ ] **Step 4: Rewrite the tedashi branch to be slot-based**

In `web/src/table/tileFlightPlan.ts`, replace the `else if (singleNewDiscard) { ... }` tedashi block (the one containing `// Tedashi: fly the discard from a RANDOM concealed hand slot`, currently ~lines 147–177) with:

```ts
      } else if (singleNewDiscard) {
        // Tedashi: the discard leaves a random concealed hand slot (the "gap"),
        // and the drawn back slides from the drawn slot into that SAME gap. Both
        // the gap origin and the merge target are read from the PREVIOUS
        // snapshot, so this works even though production re-randomizes opponent
        // tile ids every broadcast (no current-frame id lookup).
        const handIds = prevTileIdsByRole(previousSnapshot, dir, 'hand')
        if (handIds.length > 0) {
          // Clamp guards against an injected RNG returning exactly 1.0 (Math.random is [0,1)).
          const slotIndex = Math.min(handIds.length - 1, Math.floor(random() * handIds.length))
          const gapRect = previousSnapshot.rects.get(handIds[slotIndex])
          fromRect = gapRect

          // Slide the drawn back into the vacated gap and blank that slot for the
          // flight. Only when a drawn tile is present (a real tedashi-after-draw),
          // which keeps the rail count — and so slot positions — stable across
          // the discard.
          const drawnId = prevTileIdsByRole(previousSnapshot, dir, 'drawn')[0]
          const mergeFrom = drawnId != null ? previousSnapshot.rects.get(drawnId) : undefined
          const drawnTileObj = drawnId != null ? previousSnapshot.locations.get(drawnId)?.tile : undefined
          if (mergeFrom && gapRect && drawnTileObj) {
            const mergeDist = Math.hypot(gapRect.left - mergeFrom.left, gapRect.top - mergeFrom.top)
            if (mergeDist >= MIN_TRAVEL_DISTANCE) {
              key += 1
              animations.push({
                key,
                tile: drawnTileObj,
                direction: dir,
                fromRect: mergeFrom,
                toRect: gapRect,
                isWild: false,
                asBack: true,
                hideHandSlot: { direction: dir, index: slotIndex },
              })
            }
          }
        }
      }
```

(The tsumogiri branch above it and the `if (!fromRect) { ...generic anchor... }` fallback below it are unchanged.)

- [ ] **Step 5: Run the full flight-plan test file to verify green**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: PASS — all tests, including both new ones and the unchanged tsumogiri / multi-discard-resync / self / fallback tests.

- [ ] **Step 6: Commit**

```bash
git add web/src/table/tileFlightPlan.ts web/src/table/tileFlightPlan.test.ts
git commit -m "feat(web): slot-based opponent tedashi merge (id-rotation safe)"
```

---

### Task 2: Hidden-slots helper + flight-hook return value

**Files:**
- Modify: `web/src/table/tileFlightPlan.ts` (add exported helper)
- Modify: `web/src/table/tileFlight.tsx` (`UseTileFlightResult` ~lines 131–137; hook body ~lines 219–231)
- Test: `web/src/table/tileFlightPlan.test.ts` (add a `describe` for the helper)

**Interfaces:**
- Consumes: `FlyingTileAnimation` (with `hideHandSlot` from Task 1).
- Produces: `hiddenHandSlotsByDirection(animations: FlyingTileAnimation[]): Map<SeatLaneDirection, Set<number>>`. `useTileFlight` now returns `{ hiddenTileIds: Set<number>; hiddenHandSlots: Map<SeatLaneDirection, Set<number>>; flights: ReactNode }`.

- [ ] **Step 1: Write the failing helper test**

Append to `web/src/table/tileFlightPlan.test.ts`:

```ts
import { hiddenHandSlotsByDirection } from './tileFlightPlan'

describe('hiddenHandSlotsByDirection', () => {
  const anim = (over: Partial<import('./tileFlightPlan').FlyingTileAnimation>): import('./tileFlightPlan').FlyingTileAnimation => ({
    key: 1, tile: tile(1), direction: 'top', fromRect: rect(0), toRect: rect(0), isWild: false, ...over,
  })

  it('collects hideHandSlot indices grouped by direction', () => {
    const map = hiddenHandSlotsByDirection([
      anim({ hideHandSlot: { direction: 'top', index: 2 } }),
      anim({ hideHandSlot: { direction: 'top', index: 5 } }),
      anim({ hideHandSlot: { direction: 'left', index: 1 } }),
      anim({}), // no hideHandSlot -> ignored
    ])
    expect([...(map.get('top') ?? [])].sort()).toEqual([2, 5])
    expect([...(map.get('left') ?? [])]).toEqual([1])
    expect(map.has('right')).toBe(false)
  })

  it('returns an empty map when no animation hides a slot', () => {
    expect(hiddenHandSlotsByDirection([anim({})]).size).toBe(0)
  })
})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: FAIL — `hiddenHandSlotsByDirection` is not exported.

- [ ] **Step 3: Implement the helper**

Add to `web/src/table/tileFlightPlan.ts` (below `planTileFlights`):

```ts
// Collect the per-direction concealed rail slot indices that should be blanked
// while their tedashi flights are airborne (see FlyingTileAnimation.hideHandSlot).
export function hiddenHandSlotsByDirection(
  animations: FlyingTileAnimation[],
): Map<SeatLaneDirection, Set<number>> {
  const map = new Map<SeatLaneDirection, Set<number>>()
  for (const animation of animations) {
    if (!animation.hideHandSlot) continue
    const { direction, index } = animation.hideHandSlot
    let set = map.get(direction)
    if (!set) {
      set = new Set<number>()
      map.set(direction, set)
    }
    set.add(index)
  }
  return map
}
```

- [ ] **Step 4: Run to verify the helper tests pass**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: PASS — all tests green.

- [ ] **Step 5: Return `hiddenHandSlots` from the hook**

In `web/src/table/tileFlight.tsx`:

Add `hiddenHandSlotsByDirection` to the import from `./tileFlightPlan`, and import the `SeatLaneDirection` type if not already in scope (it is, via `./TableScene`).

Update the result type (~lines 131–137):

```ts
type UseTileFlightResult = {
  // Tile ids currently airborne; their settled positions stay hidden until the
  // flight overlay lands.
  hiddenTileIds: Set<number>
  // Per-direction concealed rail slot indices to blank while a tedashi drawn-back
  // flight is airborne (opponent gap fill).
  hiddenHandSlots: Map<SeatLaneDirection, Set<number>>
  // Portal overlay rendering every in-flight tile.
  flights: ReactNode
}
```

Update the hook tail (~lines 219–231) so it derives and returns the map:

```ts
  const hiddenTileIds = new Set(flyingTiles.map((animation) => animation.tile.id))
  const hiddenHandSlots = hiddenHandSlotsByDirection(flyingTiles)

  const flights = flyingTiles.map((animation) => (
    <FloatingTile
      key={animation.key}
      animation={animation}
      onComplete={() => {
        setFlyingTiles((existing) => existing.filter((item) => item.key !== animation.key))
      }}
    />
  ))

  return { hiddenTileIds, hiddenHandSlots, flights }
```

- [ ] **Step 6: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS (no type errors). `TableBoard` still destructures only `{ hiddenTileIds, flights }`, which remains valid.

- [ ] **Step 7: Commit**

```bash
git add web/src/table/tileFlightPlan.ts web/src/table/tileFlightPlan.test.ts web/src/table/tileFlight.tsx
git commit -m "feat(web): derive hiddenHandSlots from active flights"
```

---

### Task 3: Thread hidden slots into ClosedHand and blank the gap

**Files:**
- Modify: `web/src/table/TableScene.tsx` (`useTileFlight` destructure ~line 74; `PlayerSeat` render ~lines 106–118)
- Modify: `web/src/table/seat/PlayerSeat.tsx`
- Modify: `web/src/table/seat/SeatBundle.tsx`
- Modify: `web/src/table/seat/ClosedHand.tsx`

**Interfaces:**
- Consumes: `hiddenHandSlots: Map<SeatLaneDirection, Set<number>>` from `useTileFlight` (Task 2).
- Produces: a `hiddenSlots?: Set<number>` prop flowing `TableBoard → PlayerSeat → SeatBundle → ClosedHand`; `ClosedHand` renders its anonymous rail slot `index` with `visibility: hidden` when `hiddenSlots.has(index)`.

- [ ] **Step 1: TableBoard — read the map and pass the per-seat set**

In `web/src/table/TableScene.tsx`, change the hook destructure (~line 74):

```ts
  const { hiddenTileIds, hiddenHandSlots, flights } = useTileFlight({ seatViews, isWildTile, tableRef })
```

In the `seatViews.map(...)` PlayerSeat render (~lines 106–118), add the prop:

```tsx
        <PlayerSeat
          key={`seat-${player.seat}`}
          direction={direction}
          player={player}
          canDiscard={direction === 'bottom' && player.seat === canDiscardSeat}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
          hiddenSlots={hiddenHandSlots.get(direction)}
          animateDiscardTileIds={animateDiscardTileIds}
          callableDiscard={callableDiscard}
        />
```

- [ ] **Step 2: PlayerSeat — accept and forward `hiddenSlots`**

In `web/src/table/seat/PlayerSeat.tsx`, add `hiddenSlots` to `PlayerSeatProps` and forward it to `SeatBundle`:

```tsx
type PlayerSeatProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  hiddenSlots?: Set<number>
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}
```

Destructure `hiddenSlots` in the function params, then pass it to `<SeatBundle ... hiddenSlots={hiddenSlots} />` (add the prop alongside the existing `hiddenTileIds={hiddenTileIds}`).

- [ ] **Step 3: SeatBundle — accept and forward `hiddenSlots`**

In `web/src/table/seat/SeatBundle.tsx`, add `hiddenSlots?: Set<number>` to `SeatBundleProps`, destructure it, and pass it to `<ClosedHand ... hiddenSlots={hiddenSlots} />` (alongside the existing `hiddenTileIds={hiddenTileIds}`).

- [ ] **Step 4: ClosedHand — accept `hiddenSlots` and blank the gap slot**

In `web/src/table/seat/ClosedHand.tsx`:

Add `hiddenSlots?: Set<number>` to `ClosedHandProps` and destructure it in the function params (next to `hiddenTileIds`).

Extend `renderHandTile`'s options and its hidden calc so a flagged slot is blanked:

```tsx
  const renderHandTile = (
    tile: TileLike,
    { isCurrentDrawnSlot = false, slotKey, hiddenSlot = false }:
      { isCurrentDrawnSlot?: boolean; slotKey?: string; hiddenSlot?: boolean } = {},
  ) => {
    const isMergingDrawnTile = isSelf && lastDrawnTileId.current === tile.id && !hasDrawnTile
    const isHiddenByOverlay = (hiddenTileIds?.has(tile.id) ?? false) || hiddenSlot
```

(Everything else in `renderHandTile` stays; `visibility` already keys off `isHiddenByOverlay`.)

Pass the flag from the anonymous rail map (the `isAnonymous ? ... : ...` block ~lines 116–119):

```tsx
          {showClosedHand ? (
            isAnonymous
              ? baseTiles.map((tile, index) =>
                  renderHandTile(tile, { slotKey: `slot-${index}`, hiddenSlot: hiddenSlots?.has(index) ?? false }),
                )
              : sortedBaseTiles.map((tile) => renderHandTile(tile))
          ) : (
```

- [ ] **Step 5: Typecheck and build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: PASS — no type errors; `vite build` succeeds.

- [ ] **Step 6: Run the full web test suite**

Run: `cd web && npm run test`
Expected: PASS — all vitest suites (flight plan, hand/meld ordering, etc.) green.

- [ ] **Step 7: Commit**

```bash
git add web/src/table/TableScene.tsx web/src/table/seat/PlayerSeat.tsx web/src/table/seat/SeatBundle.tsx web/src/table/seat/ClosedHand.tsx
git commit -m "feat(web): blank the tedashi gap slot while the drawn back fills it"
```

---

### Task 4: Manual end-to-end verification in dev

**Files:** none (verification only).

**Interfaces:** Consumes the running app. No code produced.

- [ ] **Step 1: Start the backend (anonymized opponents — the real path)**

From the repo root, with ports 8080/3000 free:

```bash
go run cmd/server/main.go
```

Do **not** set `MAHJONG_DEV_REVEAL_HANDS` — leaving it unset keeps opponents anonymized (fail-closed redaction), which is exactly the production path this fix targets.

- [ ] **Step 2: Start the frontend**

```bash
cd web && npm run dev
```

- [ ] **Step 3: Play into an opponent tedashi and observe**

Open `http://localhost:3000`, create a private room, fill the other three seats with bots, and start. Watch an opponent's turn where they discard a tile that is **not** the one they just drew (a tedashi — the bot changing its hand). Confirm:
- the discarded tile flies to the pond from within the concealed hand, leaving a visible **empty slot** (gap), and
- the separated drawn back **slides from the drawn slot into that gap** and fills it, leaving the row contiguous.

- [ ] **Step 4: Confirm no regressions on the other cases**

In the same game, confirm:
- **Tsumogiri** (opponent discards the tile they just drew): the discard flies straight from the drawn slot; no gap opens in the row.
- **Self player:** your own tedashi still slides the drawn tile into your hand exactly as before (unchanged framer `layoutId` behavior).
- No leftover blanked slot after any flight settles (the gap always fills).

- [ ] **Step 5: Record the result**

Note the outcome in the PR description when opening it (what was observed for tedashi, tsumogiri, and self). No commit.

---

## Self-Review

**Spec coverage:**
- Slot-based merge (discard from `R`, drawn back to `R`) → Task 1. ✅
- Gate on preceding draw (no merge/gap after a pon) → Task 1 (drawn-present guard) + no-draw test. ✅
- `hideHandSlot` on `FlyingTileAnimation` → Task 1. ✅
- Derive `hiddenHandSlots` in the hook → Task 2. ✅
- Thread through TableScene/PlayerSeat/SeatBundle/ClosedHand and blank the slot → Task 3. ✅
- Tests: rotation-safe tedashi, no-draw, tsumogiri/multi/self unchanged → Task 1; helper → Task 2. ✅
- Manual dev verification (anonymized path) → Task 4. ✅
- No proto/engine/server change → respected (all files under `web/src/table`). ✅

**Placeholder scan:** No TBD/TODO; every code step shows the exact code and every run step shows the command + expected result.

**Type consistency:** `hideHandSlot: { direction: SeatLaneDirection; index: number }` (Task 1) is read by `hiddenHandSlotsByDirection` (Task 2) and produced as `Map<SeatLaneDirection, Set<number>>`; the hook returns that exact type (Task 2) and `TableBoard` calls `hiddenHandSlots.get(direction)` → `Set<number> | undefined`, matching the `hiddenSlots?: Set<number>` prop threaded in Task 3. `ClosedHand` reads `hiddenSlots?.has(index)`. Consistent end to end.

## Notes / risks

- The merge lands at `R` = the *previous* frame's slot-`slotIndex` rect, used as the current gap position. Valid because a tedashi-after-draw keeps the concealed rail count (and thus slot positions) equal before/after. If counts ever differ, `hiddenSlots.has(index)` simply matches no rendered slot (safe no-op — worst case the gap doesn't blank; never a crash or misplaced tile).
- Identical backs make the exact gap slot cosmetic; a random slot reads correctly. No attempt is made to reveal the true discarded position (concealed by design).
