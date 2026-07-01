# Tedashi / Tsumogiri Discard Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a redacted (production) opponent's discard animation distinguish **tedashi** (a back flies from a random hand slot, then the drawn back slides into the vacated slot) from **tsumogiri** (the separated drawn back flies straight to the pond).

**Architecture:** The engine exposes one public boolean on `GameState` — `active_discard_from_drawn` — set when a discard equals the discarder's just-drawn tile. The frontend flight planner (`tileFlightPlan.ts`) uses that boolean, plus the per-seat hand/drawn rects already captured in the motion snapshot, to choose the discard's flight origin and (for tedashi) emit a second "drawn back merges into hand" flight. Only the redacted-opponent path changes; self and full-info views already animate from the true source via id tracking and are untouched by construction.

**Tech Stack:** Go 1.25 (engine), Protocol Buffers, React 19 + TypeScript + framer-motion (frontend), Vitest (jsdom) for frontend tests, `go test` for engine tests.

**Design reference:** `docs/superpowers/specs/2026-06-28-tedashi-tsumogiri-discard-animation-design.md`

## Global Constraints

- Module: `github.com/plasma/fh-mahjong`, Go 1.25, `google.golang.org/protobuf v1.36.11`.
- `core/game.go` must NEVER import `rules/` (ruleset-agnostic).
- Proto changes regenerate BOTH Go and TS bindings. TS regen REQUIRES `--null-semantics`.
- The new boolean is public info (reveals nothing about concealed tiles); it rides through the prod redaction clone unchanged — do NOT special-case it in the redaction block.
- No regressions: `go test ./...` and the full frontend `npx vitest run` must stay green; existing flight behavior for self/full-info views must not change.
- After changes, update the relevant `AGENTS.md` files (`proto/AGENTS.md`, `core/AGENTS.md`, `web/src/table/AGENTS.md`).

## File Structure

- `proto/game.proto` — **MODIFY.** Add `bool active_discard_from_drawn = 24;` to `GameState`.
- `proto/game.pb.go`, `web/src/proto/game.js`, `web/src/proto/game.d.ts` — **REGENERATED** (never hand-edited).
- `core/game.go` — **MODIFY.** Add `setActiveDiscard` / `clearActiveDiscard` helpers; route all `ActiveDiscard` writes through them.
- `core/game_test.go` — **MODIFY.** Add tsumogiri/tedashi flag tests.
- `web/src/table/tileFlightPlan.ts` — **MODIFY.** New params + origin selection + merge flight; `asBack` on the animation type.
- `web/src/table/tileFlightPlan.test.ts` — **NEW.** Pure unit tests for the planner.
- `web/src/table/tileFlight.tsx` — **MODIFY.** `FloatingTile` renders a back when `asBack`; `useTileFlight` accepts + forwards the two new values.
- `web/src/table/TableScene.tsx` — **MODIFY.** Thread `activeDiscardId` / `activeDiscardFromDrawn` props into `useTileFlight`.
- `web/src/pages/Game.tsx` — **MODIFY.** Pass `gameState.activeDiscard?.id` and `gameState.activeDiscardFromDrawn` to `TableBoard`.
- `web/src/pages/HandHarness.tsx` + route in `web/src/App.tsx` — **TEMPORARY**, created and removed in the verification task. Never committed.

---

## Task 1: Backend — public `active_discard_from_drawn` flag

**Files:**
- Modify: `proto/game.proto` (`GameState`, next free field 24)
- Modify: `core/game.go`
- Test: `core/game_test.go`
- Regenerated: `proto/game.pb.go`, `web/src/proto/game.js`, `web/src/proto/game.d.ts`

**Interfaces:**
- Produces: `GameState.ActiveDiscardFromDrawn bool` (Go getter `GetActiveDiscardFromDrawn()`; JS/TS field `activeDiscardFromDrawn`). True iff the current `active_discard` was the discarder's just-drawn tile. Transient — valid only while `active_discard` is non-nil.

- [ ] **Step 1: Add the proto field**

In `proto/game.proto`, inside `message GameState`, after the `match_end_result = 23;` line, add:

```proto
  // True when active_discard was the discarder's just-drawn tile (tsumogiri).
  // Public info — reveals nothing about concealed tiles. Transient: valid only
  // while active_discard is set.
  bool active_discard_from_drawn = 24;
```

- [ ] **Step 2: Regenerate Go and TS bindings**

Run from repo root:

```bash
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```

Expected: `proto/game.pb.go` now has an `ActiveDiscardFromDrawn` field; `web/src/proto/game.d.ts` declares `activeDiscardFromDrawn?: (boolean|null)`.

- [ ] **Step 3: Write the failing engine test**

Append to `core/game_test.go` (external `core_test` package, matching the existing tests). Both tests inject a pong pair into South so the game stays in `PHASE_WAIT_DISCARDS` (so `ActiveDiscard` is not cleared before we read the flag — exactly how `TestDiscardAction` keeps the discard live).

```go
func TestActiveDiscardFromDrawn_Tsumogiri(t *testing.T) {
	r := &rules.FenghuaRuleset{}
	g := core.NewGame("test-tsumogiri", r, core.MatchOptions{})
	g.Start()

	dealer := g.State.ActivePlayer
	if g.State.Players[dealer].DrawnTileId == nil {
		t.Fatalf("expected dealer to hold a drawn tile after Start()")
	}
	drawnID := *g.State.Players[dealer].DrawnTileId

	// Find the drawn tile in the dealer's hand and discard exactly it.
	var discardTile *pb.Tile
	for _, tile := range g.State.Players[dealer].ClosedHand {
		if int32(tile.Id) == drawnID {
			discardTile = tile
			break
		}
	}
	if discardTile == nil {
		t.Fatalf("drawn tile id %d not present in dealer hand", drawnID)
	}

	// Keep the discard live: give South a pong-able pair so play enters WAIT_DISCARDS.
	south := (dealer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[south].ClosedHand = append(g.State.Players[south].ClosedHand, clone1, clone2)

	if err := g.ProcessPlayerAction(dealer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	}); err != nil {
		t.Fatalf("discard failed: %v", err)
	}

	if g.State.ActiveDiscard == nil {
		t.Fatalf("expected active discard to remain set in WAIT_DISCARDS")
	}
	if !g.State.ActiveDiscardFromDrawn {
		t.Errorf("expected ActiveDiscardFromDrawn=true for tsumogiri")
	}
}

func TestActiveDiscardFromDrawn_Tedashi(t *testing.T) {
	r := &rules.FenghuaRuleset{}
	g := core.NewGame("test-tedashi", r, core.MatchOptions{})
	g.Start()

	dealer := g.State.ActivePlayer
	if g.State.Players[dealer].DrawnTileId == nil {
		t.Fatalf("expected dealer to hold a drawn tile after Start()")
	}
	drawnID := *g.State.Players[dealer].DrawnTileId

	// Discard a tile that is NOT the drawn tile.
	var discardTile *pb.Tile
	for _, tile := range g.State.Players[dealer].ClosedHand {
		if int32(tile.Id) != drawnID {
			discardTile = tile
			break
		}
	}
	if discardTile == nil {
		t.Fatalf("could not find a non-drawn tile to discard")
	}

	south := (dealer + 1) % 4
	clone1 := &pb.Tile{Id: discardTile.Id + 1000, Suit: discardTile.Suit, Value: discardTile.Value}
	clone2 := &pb.Tile{Id: discardTile.Id + 2000, Suit: discardTile.Suit, Value: discardTile.Value}
	g.State.Players[south].ClosedHand = append(g.State.Players[south].ClosedHand, clone1, clone2)

	if err := g.ProcessPlayerAction(dealer, &pb.PlayerAction{
		Type: pb.ActionType_ACTION_DISCARD,
		Tile: discardTile,
	}); err != nil {
		t.Fatalf("discard failed: %v", err)
	}

	if g.State.ActiveDiscard == nil {
		t.Fatalf("expected active discard to remain set in WAIT_DISCARDS")
	}
	if g.State.ActiveDiscardFromDrawn {
		t.Errorf("expected ActiveDiscardFromDrawn=false for tedashi")
	}
}
```

- [ ] **Step 4: Run the tests, verify the tsumogiri one FAILS**

Run: `go test ./core/ -run TestActiveDiscardFromDrawn -v`
Expected: `TestActiveDiscardFromDrawn_Tsumogiri` FAILS (`ActiveDiscardFromDrawn=false`, not yet wired); `TestActiveDiscardFromDrawn_Tedashi` passes (field defaults false).

- [ ] **Step 5: Add the helpers in `core/game.go`**

Add these methods (place them near the other `*Game` state helpers, e.g. just above `handleActiveTurnAction`):

```go
// setActiveDiscard records the active discard and whether it was the
// discarder's just-drawn tile (tsumogiri). Keeping both fields in one place
// guarantees ActiveDiscardFromDrawn never outlives ActiveDiscard.
func (g *Game) setActiveDiscard(tile *pb.Tile, fromDrawn bool) {
	g.State.ActiveDiscard = tile
	g.State.ActiveDiscardFromDrawn = fromDrawn
}

// clearActiveDiscard clears the active discard and its tsumogiri flag together.
func (g *Game) clearActiveDiscard() {
	g.State.ActiveDiscard = nil
	g.State.ActiveDiscardFromDrawn = false
}
```

- [ ] **Step 6: Set the flag at the discard site**

In `core/game.go`, in the `ACTION_DISCARD` handler, replace this line (currently `core/game.go:730`):

```go
		g.State.ActiveDiscard = action.Tile
```

with:

```go
		fromDrawn := player.DrawnTileId != nil && *player.DrawnTileId == int32(action.Tile.Id)
		g.setActiveDiscard(action.Tile, fromDrawn)
```

(`player.DrawnTileId` is still set here — it is cleared on the very next line, `player.DrawnTileId = nil`, so compute `fromDrawn` first.)

- [ ] **Step 7: Route every `ActiveDiscard = nil` through the helper**

Replace each occurrence of `g.State.ActiveDiscard = nil` with `g.clearActiveDiscard()`. There are six (currently lines 805, 1004, 1015, 1067, 1111, 1290). Verify none remain afterward:

Run: `rg -n "g.State.ActiveDiscard\s*=\s*nil" core/game.go`
Expected: no matches.

(The struct-literal init `ActiveDiscard: nil` at `core/game.go:63` stays as-is — a fresh `GameState` already has `ActiveDiscardFromDrawn` defaulting to false.)

- [ ] **Step 8: Run the engine tests, verify they PASS**

Run: `go test ./core/ -run TestActiveDiscardFromDrawn -v`
Expected: both PASS.

- [ ] **Step 9: Full engine suite + build**

Run: `go test ./...`
Expected: all PASS (no regressions).

- [ ] **Step 10: Update docs**

In `proto/AGENTS.md` and `core/AGENTS.md`, add a one-line note that `GameState.active_discard_from_drawn` is a public, transient tsumogiri marker kept in lockstep with `active_discard` via `setActiveDiscard`/`clearActiveDiscard`.

- [ ] **Step 11: Commit**

```bash
git add proto/game.proto proto/game.pb.go web/src/proto/game.js web/src/proto/game.d.ts core/game.go core/game_test.go proto/AGENTS.md core/AGENTS.md
git commit -m "feat(engine): expose public active_discard_from_drawn (tsumogiri) flag"
```

---

## Task 2: Frontend planner — tsumogiri/tedashi origins + drawn-merge flight

**Files:**
- Modify: `web/src/table/tileFlightPlan.ts`
- Test: `web/src/table/tileFlightPlan.test.ts` (NEW)

**Interfaces:**
- Consumes: `MotionSnapshot` (`locations: Map<number, {tile, direction, role}>`, `rects: Map<number, TileRect>`, `handOrigins`).
- Produces (extended `planTileFlights` signature):
  ```ts
  type FlyingTileAnimation = { key; tile; direction; fromRect; toRect; isWild; asBack?: boolean }
  type PlanTileFlightsParams = {
    previousSnapshot; currentLocations; currentRects; currentHandOrigins;
    isWildTile; startKey;
    activeDiscardId?: number | null;
    activeDiscardFromDrawn?: boolean;
    random?: () => number;   // defaults to Math.random; injected for deterministic tests
  }
  ```

- [ ] **Step 1: Write the failing planner tests**

Create `web/src/table/tileFlightPlan.test.ts`:

```typescript
import { describe, it, expect } from 'vitest'
import { planTileFlights, type MotionSnapshot, type TileMotionDescriptor, type TileRect } from './tileFlightPlan'
import type { TileLike } from './types'

const tile = (id: number): TileLike => ({ id, suit: 0, value: 0 })
const rect = (left: number): TileRect => ({ left, top: 0, width: 10, height: 14 })
const PILE = { left: 200, top: 200, width: 10, height: 14 }

// Opponent ('top') before discard: rail backs 1001/1002/1003 + separated drawn 1009.
function prevSnapshot(): MotionSnapshot {
  const locations = new Map<number, TileMotionDescriptor>([
    [1001, { tile: tile(1001), direction: 'top', role: 'hand' }],
    [1002, { tile: tile(1002), direction: 'top', role: 'hand' }],
    [1003, { tile: tile(1003), direction: 'top', role: 'hand' }],
    [1009, { tile: tile(1009), direction: 'top', role: 'drawn' }],
  ])
  const rects = new Map<number, TileRect>([
    [1001, rect(10)], [1002, rect(20)], [1003, rect(30)], [1009, rect(60)],
  ])
  return { locations, rects, handOrigins: new Map([['top', { left: 0, top: 0, width: 80, height: 14 }]]) }
}

describe('planTileFlights — redacted opponent discard', () => {
  it('tsumogiri: discard flies from the drawn slot, no merge flight', () => {
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE]]) // drawn 1009 is gone
    const animations = planTileFlights({
      previousSnapshot: prevSnapshot(),
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      activeDiscardId: 42,
      activeDiscardFromDrawn: true,
    })
    expect(animations).toHaveLength(1)
    expect(animations[0].fromRect.left).toBe(60) // drawn slot
    expect(animations[0].toRect.left).toBe(200)
    expect(animations[0].asBack).toBeFalsy()
  })

  it('tedashi: discard flies from a random hand slot + drawn back merges into the hand', () => {
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [1009, { tile: tile(1009), direction: 'top', role: 'hand' }], // drawn stays, now in rail
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE], [1009, rect(40)]])
    const animations = planTileFlights({
      previousSnapshot: prevSnapshot(),
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      activeDiscardId: 42,
      activeDiscardFromDrawn: false,
      random: () => 0, // deterministic: pick the first hand id (1001)
    })
    expect(animations).toHaveLength(2)
    const discard = animations.find((a) => a.tile.id === 42)!
    const merge = animations.find((a) => a.tile.id === 1009)!
    expect(discard.fromRect.left).toBe(10) // random hand slot (1001)
    expect(discard.toRect.left).toBe(200)
    expect(merge.asBack).toBe(true)
    expect(merge.fromRect.left).toBe(60) // drawn slot
    expect(merge.toRect.left).toBe(40) // new in-rail position
  })

  it('falls back to the generic hand origin when no active-discard flag is given', () => {
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
      // no activeDiscardId / activeDiscardFromDrawn
    })
    expect(animations).toHaveLength(1)
    // centered on the handOrigin region (left 0, width 80) -> 0 + 40 - 5 = 35
    expect(animations[0].fromRect.left).toBe(35)
    expect(animations[0].asBack).toBeFalsy()
  })

  it('tracked tiles (self) still fly from their real previous position', () => {
    const previousSnapshot: MotionSnapshot = {
      locations: new Map([[5, { tile: tile(5), direction: 'bottom', role: 'hand' }]]),
      rects: new Map([[5, rect(10)]]),
      handOrigins: new Map(),
    }
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [5, { tile: tile(5), direction: 'bottom', role: 'discard' }],
    ])
    const currentRects = new Map<number, TileRect>([[5, PILE]])
    const animations = planTileFlights({
      previousSnapshot,
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      activeDiscardId: 5,
      activeDiscardFromDrawn: false,
    })
    expect(animations).toHaveLength(1)
    expect(animations[0].fromRect.left).toBe(10) // tracked real position, not random/merge
  })
})
```

- [ ] **Step 2: Run the tests, verify they FAIL**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: FAIL — `planTileFlights` does not yet accept `activeDiscardId` / `random` / emit `asBack`; tsumogiri/tedashi assertions fail.

- [ ] **Step 3: Extend the type + params**

In `web/src/table/tileFlightPlan.ts`, add `asBack` to the animation type:

```typescript
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
}
```

Extend `PlanTileFlightsParams`:

```typescript
export type PlanTileFlightsParams = {
  previousSnapshot: MotionSnapshot
  currentLocations: Map<number, TileMotionDescriptor>
  currentRects: Map<number, TileRect>
  currentHandOrigins: Map<SeatLaneDirection, TileRect>
  isWildTile: (tile: TileLike) => boolean
  startKey: number
  // The id of the live active discard, and whether it was the discarder's
  // just-drawn tile (tsumogiri). Used only for redacted opponents, where the
  // discard's real id cannot be tracked back to a fake-id hand tile.
  activeDiscardId?: number | null
  activeDiscardFromDrawn?: boolean
  // Injectable RNG for the random tedashi source slot (deterministic in tests).
  random?: () => number
}
```

- [ ] **Step 4: Add a role-lookup helper**

In `web/src/table/tileFlightPlan.ts`, above `planTileFlights`:

```typescript
// Tile ids in a previous snapshot for a given seat direction + role, in
// insertion order (so an injected RNG can deterministically pick one).
function prevTileIdsByRole(
  snapshot: MotionSnapshot,
  direction: SeatLaneDirection,
  role: TileMotionRole,
): number[] {
  const ids: number[] = []
  snapshot.locations.forEach((descriptor, id) => {
    if (descriptor.direction === direction && descriptor.role === role) ids.push(id)
  })
  return ids
}
```

- [ ] **Step 5: Implement the new branch logic**

In `planTileFlights`, accept the new params (with `random = Math.random` default):

```typescript
export function planTileFlights({
  previousSnapshot,
  currentLocations,
  currentRects,
  currentHandOrigins,
  isWildTile,
  startKey,
  activeDiscardId = null,
  activeDiscardFromDrawn = false,
  random = Math.random,
}: PlanTileFlightsParams): FlyingTileAnimation[] {
```

Replace the existing `else if (currentTile.role === 'discard') { ... }` block with:

```typescript
    } else if (currentTile.role === 'discard') {
      const dir = currentTile.direction
      const isActive = activeDiscardId != null && tileIdsEqual(tileId, activeDiscardId)

      if (isActive && activeDiscardFromDrawn) {
        // Tsumogiri: fly the discard straight from the separated drawn slot.
        const drawnId = prevTileIdsByRole(previousSnapshot, dir, 'drawn')[0]
        if (drawnId != null) fromRect = previousSnapshot.rects.get(drawnId)
      } else if (isActive) {
        // Tedashi: fly the discard from a RANDOM concealed hand slot, and slide
        // the drawn back into the hand (the "tsumo-hai fills the gap").
        const handIds = prevTileIdsByRole(previousSnapshot, dir, 'hand')
        if (handIds.length > 0) {
          const pick = handIds[Math.floor(random() * handIds.length)]
          fromRect = previousSnapshot.rects.get(pick)
        }
        const drawnId = prevTileIdsByRole(previousSnapshot, dir, 'drawn')[0]
        if (drawnId != null) {
          const mergeFrom = previousSnapshot.rects.get(drawnId)
          const mergeTo = currentRects.get(drawnId) // drawn tile's new in-rail rect
          const drawnTileObj = previousSnapshot.locations.get(drawnId)?.tile
          if (mergeFrom && mergeTo && drawnTileObj) {
            const mergeDist = Math.hypot(mergeTo.left - mergeFrom.left, mergeTo.top - mergeFrom.top)
            if (mergeDist >= MIN_TRAVEL_DISTANCE) {
              key += 1
              animations.push({
                key,
                tile: drawnTileObj,
                direction: dir,
                fromRect: mergeFrom,
                toRect: mergeTo,
                isWild: false,
                asBack: true,
              })
            }
          }
        }
      }

      if (!fromRect) {
        // Fallback (no flag, or rects unavailable): existing generic-anchor behavior.
        const origin =
          previousSnapshot.handOrigins.get(dir) ??
          currentHandOrigins.get(dir)
        if (origin) fromRect = centerRectOn(origin, toRect)
      }
    }
```

- [ ] **Step 6: Run the tests, verify they PASS**

Run: `cd web && npx vitest run src/table/tileFlightPlan.test.ts`
Expected: all 4 PASS.

- [ ] **Step 7: Commit**

```bash
git add web/src/table/tileFlightPlan.ts web/src/table/tileFlightPlan.test.ts
git commit -m "feat(table): plan tedashi/tsumogiri discard flights for redacted opponents"
```

---

## Task 3: Frontend rendering + wiring (drawn-back flight, thread the flag)

**Files:**
- Modify: `web/src/table/tileFlight.tsx`
- Modify: `web/src/table/TableScene.tsx`
- Modify: `web/src/pages/Game.tsx`

**Interfaces:**
- Consumes: extended `planTileFlights` (Task 2); `GameState.activeDiscard`, `GameState.activeDiscardFromDrawn` (Task 1).
- Produces: `TableBoardProps` gains `activeDiscardId?: number | null` and `activeDiscardFromDrawn?: boolean`; `useTileFlight` forwards both to `planTileFlights`; `FloatingTile` renders `back.svg` when `animation.asBack`.

- [ ] **Step 1: Render a back for `asBack` flights in `FloatingTile`**

In `web/src/table/tileFlight.tsx`, change the `svgName` line inside `FloatingTile` from:

```typescript
  const svgName = getTileSvgName(animation.tile)
```

to:

```typescript
  const svgName = animation.asBack ? 'back.svg' : getTileSvgName(animation.tile)
```

And change the `<img>` `alt` from `getTileName(animation.tile)` to:

```typescript
              alt={animation.asBack ? 'tile back' : getTileName(animation.tile)}
```

- [ ] **Step 2: Thread the two values through `useTileFlight`**

In `web/src/table/tileFlight.tsx`, extend `UseTileFlightParams`:

```typescript
type UseTileFlightParams = {
  seatViews: SeatView[]
  isWildTile: (tile: TileLike) => boolean
  tableRef: RefObject<HTMLElement | null>
  activeDiscardId?: number | null
  activeDiscardFromDrawn?: boolean
}
```

Update the hook signature and destructuring:

```typescript
export function useTileFlight({
  seatViews,
  isWildTile,
  tableRef,
  activeDiscardId = null,
  activeDiscardFromDrawn = false,
}: UseTileFlightParams): UseTileFlightResult {
```

Pass them into the `planTileFlights` call (add the two fields):

```typescript
      const nextAnimations = planTileFlights({
        previousSnapshot,
        currentLocations,
        currentRects,
        currentHandOrigins,
        isWildTile,
        startKey: animationKeyRef.current,
        activeDiscardId,
        activeDiscardFromDrawn,
      })
```

Add `activeDiscardId` and `activeDiscardFromDrawn` to the `useLayoutEffect` dependency array (currently `[isWildTile, seatViews, tableRef]`):

```typescript
  }, [isWildTile, seatViews, tableRef, activeDiscardId, activeDiscardFromDrawn])
```

- [ ] **Step 3: Add the props to `TableBoard` and forward them**

In `web/src/table/TableScene.tsx`, add to `TableBoardProps`:

```typescript
  activeDiscardId?: number | null
  activeDiscardFromDrawn?: boolean
```

Destructure them in `TableBoard({ ... })` (default both):

```typescript
  activeDiscardId = null,
  activeDiscardFromDrawn = false,
```

Forward them into the `useTileFlight` call:

```typescript
  const { hiddenTileIds, flights } = useTileFlight({
    seatViews,
    isWildTile,
    tableRef,
    activeDiscardId,
    activeDiscardFromDrawn,
  })
```

- [ ] **Step 4: Pass the live values from `Game.tsx`**

In `web/src/pages/Game.tsx`, in the `<TableBoard ... />` JSX (around line 414), add two props:

```tsx
                        activeDiscardId={gameState.activeDiscard?.id ?? null}
                        activeDiscardFromDrawn={gameState.activeDiscardFromDrawn ?? false}
```

- [ ] **Step 5: Typecheck + full frontend test suite**

Run: `cd web && npx tsc --noEmit && npx vitest run`
Expected: typecheck clean; all tests PASS (Task 2 planner tests + existing suites).

- [ ] **Step 6: Update docs**

In `web/src/table/AGENTS.md`, add a one-line note: redacted-opponent discards animate tedashi (random hand-slot origin + drawn-back merge flight) vs tsumogiri (drawn-slot origin) using `GameState.activeDiscardFromDrawn`; full-info/self views are unchanged (tracked by id).

- [ ] **Step 7: Commit**

```bash
git add web/src/table/tileFlight.tsx web/src/table/TableScene.tsx web/src/pages/Game.tsx web/src/table/AGENTS.md
git commit -m "feat(table): drive redacted-opponent discard animation from tsumogiri flag"
```

---

## Task 4: Manual visual verification (temporary harness) + cleanup

**Files:**
- Create (TEMPORARY, never committed): `web/src/pages/HandHarness.tsx`, route in `web/src/App.tsx`

**Goal:** Eyeball both cases for a redacted opponent (face-down backs): tsumogiri sends the separated drawn back to the pond; tedashi sends a back from a random rail slot and slides the drawn back into the gap.

- [ ] **Step 1: Add a temporary harness route**

Create `web/src/pages/HandHarness.tsx` that renders `TableBoard` for a redacted opponent (`showClosedHand: false` is NOT used here — redacted means fake tiles with `suit: 0`; render the opponent with `closedHand` of `suit:0,value:0` tiles and a `drawnTileId`). Drive two renders via a button: first the "drawn, pre-discard" view, then the "post-discard" view, toggling `activeDiscardFromDrawn`. Mirror the structure used previously by the closed-hand slide harness (`docs/superpowers/plans/2026-06-07-closed-hand-drawn-tile-slide-animation.md`). Add a `<Route path="/handharness" element={<HandHarness />} />` to `web/src/App.tsx`.

Minimal opponent fixture (top seat), pre-discard:
```ts
// 13 rail backs + 1 drawn back; ids are fake (>=1000), suit/value 0 so they render as backs
const railIds = [1001,1002,1003,1004,1005,1006,1007,1008,1010,1011,1012,1013,1014]
const drawnId = 1009
const preDiscard = {
  seat: 2, seatWind: 3, score: 0,
  closedHand: [...railIds, drawnId].map((id) => ({ id, suit: 0, value: 0 })),
  handBackCount: 14, showClosedHand: true, drawnTileId: drawnId,
  openMelds: [], flowerMelds: [], discards: [], shantenLabel: null,
}
```
For **tsumogiri** post-discard: remove `drawnId` from `closedHand`, append the real discard `{ id: 42, suit: 3, value: 5 }` to `discards`, set `drawnTileId: null`, and render `TableBoard` with `activeDiscardId={42} activeDiscardFromDrawn={true}`.
For **tedashi** post-discard: remove one rail id (e.g. `1003`) from `closedHand` (keep `drawnId`), append the real discard to `discards`, set `drawnTileId: null`, and render with `activeDiscardId={42} activeDiscardFromDrawn={false}`.

- [ ] **Step 2: Run the dev server and verify both cases**

Run: `cd web && npm run dev`, open `http://localhost:3000/handharness`.
Expected:
- **Tsumogiri:** the separated drawn back flies to the pond; the rail of backs is unchanged.
- **Tedashi:** a back flies to the pond from a (randomly chosen) rail position, and the drawn back slides from its separated slot into the hand. Re-running re-randomizes the source slot.

- [ ] **Step 3: Remove the temporary harness**

Delete `web/src/pages/HandHarness.tsx` and its route from `web/src/App.tsx`.

Run: `cd web && npx tsc --noEmit && git status`
Expected: typecheck clean; `git status` shows no harness files staged or modified (only the deletion of the route line, which must be reverted to original).

- [ ] **Step 4: Final regression gate**

Run: `go test ./... && cd web && npx tsc --noEmit && npx vitest run`
Expected: all green.

---

## Self-Review

**Spec coverage:**
- "Backend public boolean `active_discard_from_drawn`" → Task 1. ✓
- "Engine computes from DrawnTileId before clear; lockstep with ActiveDiscard" → Task 1 Steps 5–7 (helpers). ✓
- "Rides through prod redaction clone unchanged" → no redaction edit; covered by Global Constraints + Task 1 (proto.Clone copies the bool). ✓
- "Tsumogiri: discard flies from drawn slot" → Task 2 tsumogiri branch + test. ✓
- "Tedashi: random hand-slot origin + drawn back merges into gap" → Task 2 tedashi branch + merge flight + test. ✓
- "FloatingTile renders a back for the merge flight" → Task 3 Step 1. ✓
- "Fallback to generic anchor; no regression" → Task 2 fallback + test; Task 2 tracked-tile test. ✓
- "Discarder seat resolved without a new field" → planner uses `currentTile.direction` (the discard descriptor already carries the discarder's direction); active discard matched by `activeDiscardId`. ✓
- "Redacted-only scope; self/full-info untouched" → new logic lives in the no-`previousTile` branch only; tracked-tile test locks it. ✓
- Testing (Go + frontend + manual) → Tasks 1, 2, 4. ✓

**Placeholder scan:** No TBD/TODO; all code blocks complete. ✓

**Type consistency:** `activeDiscardId` / `activeDiscardFromDrawn` / `random` / `asBack` names match across `tileFlightPlan.ts` (Task 2), `tileFlight.tsx` + `TableScene.tsx` + `Game.tsx` (Task 3). Go `ActiveDiscardFromDrawn` matches proto field name; `setActiveDiscard`/`clearActiveDiscard` used consistently. ✓
