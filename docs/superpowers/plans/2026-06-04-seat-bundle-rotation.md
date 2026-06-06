# Seat Bundle (Rotation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind each player's closed hand + open melds + flowers into one canonical `SeatBundle`, placed per seat by a single rotate+translate, so left/right are exact rotations and symmetry can't drift.

**Architecture:** `SeatBundle` renders the three zones in one fixed bottom-orientation layout (tiles upright, hand sized by self/opponent). `PlayerSeat` wraps it in a 0-size pivot anchored at the player's edge midpoint and rotates the bundle by θ (0/180/90/−90 for bottom/top/left/right). The open-meld block is absolutely positioned off the hand's right edge so it never affects the hand's centering. Discards stay separate.

**Tech Stack:** React 19, TypeScript, framer-motion, Vite, CSS in `web/src/index.css`. Vitest for the (unchanged) pure helpers.

**Reference spec:** `docs/superpowers/specs/2026-06-04-seat-bundle-rotation-design.md`

**Working dir for commands:** `web/`. Use the project-local TS: `node_modules/.bin/tsc --noEmit`.

---

## File Structure

- `web/src/table/seat/ClosedHand.tsx` — becomes canonical (drop `direction`; take `isSelf`; always `pov-bottom`).
- `web/src/table/seat/OpenMelds.tsx` — canonical groups (`pov-bottom`, `seat-meld-group--bottom`); drop `direction` from rendering.
- `web/src/table/seat/OpenMeldZone.tsx` — canonical `.zone-melds` container (no `--{dir}`).
- `web/src/table/seat/FlowerZone.tsx` — canonical `.zone-flowers` row (no `--{dir}`).
- `web/src/table/seat/SeatBundle.tsx` — **new**; composes hand + exposed(flowers, melds).
- `web/src/table/seat/PlayerSeat.tsx` — becomes `DiscardZone` + pivot wrapper around `SeatBundle`.
- `web/src/table/TableScene.tsx` — the round-result overlay's `<OpenMelds direction="bottom" …>` drops the now-removed `direction` prop.
- `web/src/index.css` — replace the per-direction `.zone-*--{dir}` rules with `.seat-bundle*` + `.seat-bundle-pivot--{dir}`.

---

## Task 1: Make `ClosedHand` canonical

**Files:** Modify `web/src/table/seat/ClosedHand.tsx`

- [ ] **Step 1: Rewrite the component canonical (size by `isSelf`, always `pov-bottom`)**

Replace the entire file with:
```tsx
import { useRef } from 'react'
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { computeStableDisplayOrder } from '../handOrdering'
import { tileIdsEqual } from '../meldOrdering'
import type { PlayerTableView, TileLike } from '../types'

type ClosedHandProps = {
  isSelf: boolean
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

// Canonical (bottom-orientation) draw-in offset; the bundle's rotation reorients
// it per seat.
const DRAW_OFFSET = { x: 0, y: -30 }

export function ClosedHand({
  isSelf,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: ClosedHandProps) {
  const lastDrawnTileId = useRef<number | null>(null)
  const displayOrderRef = useRef<number[] | null>(null)
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

  return (
    <div className="zone-hand">
      <div className="seat-hand seat-hand--bottom">
        <div className="seat-hand__tiles seat-hand__tiles--bottom">
          {showClosedHand ? (
            sortedBaseTiles.map((tile) => renderHandTile(tile))
          ) : (
            Array(handBackCount).fill(null).map((_, index) => (
              <div key={`back-${index}`} className="pov-bottom small">
                <div className="mahjong-tile-back small" />
              </div>
            ))
          )}
        </div>

        {showClosedHand && drawnTile && (
          <div
            className="seat-hand__drawn-slot seat-hand__drawn-slot--bottom"
            data-board-tile-id={drawnTile.id}
            data-board-tile-role="drawn"
          >
            <motion.div
              initial={{ opacity: 0, ...DRAW_OFFSET }}
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

      {isSelf && player.shantenLabel && (
        <div className="shanten-indicator">{player.shantenLabel}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck (expect failures in callers — that's fine, fixed in Task 5)**

Run: `node_modules/.bin/tsc --noEmit`
Expected: errors only in `PlayerSeat.tsx` (still passes `direction` to `ClosedHand`). No errors inside `ClosedHand.tsx` itself. (PlayerSeat is rewritten in Task 5.)

---

## Task 2: Make `OpenMelds`, `OpenMeldZone`, `FlowerZone` canonical

**Files:** Modify `web/src/table/seat/OpenMelds.tsx`, `OpenMeldZone.tsx`, `FlowerZone.tsx`

- [ ] **Step 1: `OpenMelds.tsx` — canonical groups, no direction**

Replace the file with:
```tsx
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { reorderMeldTiles, tileIdsEqual } from '../meldOrdering'
import type { MeldLike, TileLike } from '../types'

type OpenMeldsProps = {
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
}

// Stable identity so only a newly-formed meld mounts (and plays the entrance).
function meldKey(meld: MeldLike, index: number): string {
  if (meld.calledTileId != null) return `c-${meld.calledTileId}`
  const first = meld.tiles?.[0]
  return first ? `t-${first.id}` : `i-${index}`
}

export function OpenMelds({ melds, isWildTile = () => false }: OpenMeldsProps) {
  return (
    <>
      {melds.map((meld, meldIndex) => (
        <motion.div
          key={meldKey(meld, meldIndex)}
          className="seat-meld-group seat-meld-group--bottom"
          layout
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.18, ease: 'easeOut', layout: { duration: 0.18, ease: 'easeOut' } }}
        >
          {reorderMeldTiles(meld).map((tile, tileIndex) => {
            const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
            return (
              <div key={tileIndex} className={`pov-bottom small ${isStolen ? 'stolen-tile' : ''}`}>
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
> Melds are passed in formation order; the `.zone-melds` container's `row-reverse` (Task 6) puts the first-formed at the outer end. `layout` smooths the outward shift when a new meld is added.

- [ ] **Step 2: `OpenMeldZone.tsx` — canonical container**

Replace the file with:
```tsx
import { OpenMelds } from './OpenMelds'
import type { MeldLike, TileLike } from '../types'

type OpenMeldZoneProps = {
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function OpenMeldZone({ melds, isWildTile }: OpenMeldZoneProps) {
  if (!melds || melds.length === 0) return null
  return (
    <div className="zone-melds">
      <OpenMelds melds={melds} isWildTile={isWildTile} />
    </div>
  )
}
```

- [ ] **Step 3: `FlowerZone.tsx` — canonical row**

Replace the file with:
```tsx
import { TileComponent } from '../Tile'
import type { TileLike } from '../types'

type FlowerZoneProps = {
  flowers: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function FlowerZone({ flowers, isWildTile = () => false }: FlowerZoneProps) {
  if (!flowers || flowers.length === 0) return null
  return (
    <div className="zone-flowers">
      {flowers.map((tile, index) => (
        <div key={`f-${tile.id}-${index}`} className="pov-bottom small">
          <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
        </div>
      ))}
    </div>
  )
}
```

- [ ] **Step 4: Typecheck**

Run: `node_modules/.bin/tsc --noEmit`
Expected: remaining errors only in `PlayerSeat.tsx` and the round-result overlay call in `TableScene.tsx` (both still pass `direction` to `OpenMelds`/zones). Fixed in Tasks 5–6.

---

## Task 3: `SeatBundle` component

**Files:** Create `web/src/table/seat/SeatBundle.tsx`

- [ ] **Step 1: Create the bundle**

```tsx
import { ClosedHand } from './ClosedHand'
import { FlowerZone } from './FlowerZone'
import { OpenMeldZone } from './OpenMeldZone'
import type { PlayerTableView, TileLike } from '../types'

type SeatBundleProps = {
  isSelf: boolean
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

// Canonical bottom-orientation bundle. The closed hand is in flow (so the pivot
// can center it); the exposed stack (flowers above melds) is positioned off the
// hand's right edge in CSS, so it never affects the hand's width/centering.
export function SeatBundle({
  isSelf,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: SeatBundleProps) {
  const flowers = player.flowerMelds || []
  const melds = player.openMelds || []
  const hasExposed = flowers.length > 0 || melds.length > 0

  return (
    <div className="seat-bundle">
      <ClosedHand
        isSelf={isSelf}
        player={player}
        canDiscard={canDiscard}
        onDiscard={onDiscard}
        isWildTile={isWildTile}
        hiddenTileIds={hiddenTileIds}
      />
      {hasExposed && (
        <div className="seat-bundle__exposed">
          <FlowerZone flowers={flowers} isWildTile={isWildTile} />
          <OpenMeldZone melds={melds} isWildTile={isWildTile} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck (same expected remaining errors as Task 2)**

Run: `node_modules/.bin/tsc --noEmit`
Expected: errors only in `PlayerSeat.tsx` / `TableScene.tsx` overlay.

---

## Task 4: Fix the round-result overlay call

**Files:** Modify `web/src/table/TableScene.tsx`

- [ ] **Step 1: Drop the removed `direction` prop**

Find (in `TableRoundResultOverlay`):
```tsx
                    <OpenMelds melds={winningMelds} direction="bottom" isWildTile={isWildTile} />
```
Replace with:
```tsx
                    <OpenMelds melds={winningMelds} isWildTile={isWildTile} />
```

- [ ] **Step 2: Typecheck**

Run: `node_modules/.bin/tsc --noEmit`
Expected: remaining errors only in `PlayerSeat.tsx` (next task).

---

## Task 5: `PlayerSeat` = discards + rotated bundle pivot

**Files:** Modify `web/src/table/seat/PlayerSeat.tsx`

- [ ] **Step 1: Rewrite PlayerSeat**

Replace the file with:
```tsx
import { DiscardZone } from './DiscardZone'
import { SeatBundle } from './SeatBundle'
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
  // Self is always rendered at the bottom (getSeatDirection(viewSeat, viewSeat) === 'bottom').
  const isSelf = direction === 'bottom'

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
      <div className={`seat-bundle-pivot seat-bundle-pivot--${direction}`}>
        <SeatBundle
          isSelf={isSelf}
          player={player}
          canDiscard={canDiscard}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
        />
      </div>
    </>
  )
}
```

- [ ] **Step 2: Typecheck**

Run: `node_modules/.bin/tsc --noEmit`
Expected: no errors.

---

## Task 6: CSS — bundle layout, pivot rotation, remove old zone rules

**Files:** Modify `web/src/index.css`

- [ ] **Step 1: Replace the layout vars**

In the `.game-stage .mahjong-table` var block, replace the previous seat-layout vars (the block from `--meld-inset` through `--hand-center-shift`, added by the prior layout work) with:
```css
  --bundle-hand-meld-gap: 18px;
  --bundle-flower-meld-gap: 8px;
  --bundle-edge-offset: 28px;
  --bundle-edge-offset-side: 40px;
  --zone-z-discards: 12;
  --zone-z-bundle: 16;
```
(Keep `--meld-group-gap` if present, else add `--meld-group-gap: 12px;`.)

- [ ] **Step 2: Remove the old per-direction zone CSS**

Delete the entire previous `/* ===== Modular per-player zones (PlayerSeat) ===== */` block (the `.zone-hand--*`, `.zone-melds--*`, `.zone-flowers--*` rules and the `.discard-lane { z-index }` line at the end of the file).

- [ ] **Step 3: Append the bundle + pivot CSS**

Append to `web/src/index.css`:
```css
/* ===== Seat bundle (canonical, rotated per seat) ===== */

/* 0-size pivot at each player's edge midpoint; rotated by theta. The bundle
   inside hangs off this point by its hand's bottom-centre. */
.game-stage .seat-bundle-pivot {
  position: absolute;
  width: 0;
  height: 0;
  z-index: var(--zone-z-bundle);
}
.game-stage .seat-bundle-pivot--bottom {
  left: 50%;
  bottom: var(--bundle-edge-offset);
}
.game-stage .seat-bundle-pivot--top {
  left: 50%;
  top: var(--bundle-edge-offset);
  transform: rotate(180deg);
}
.game-stage .seat-bundle-pivot--left {
  left: var(--bundle-edge-offset-side);
  top: 50%;
  transform: rotate(90deg);
}
.game-stage .seat-bundle-pivot--right {
  right: var(--bundle-edge-offset-side);
  top: 50%;
  transform: rotate(-90deg);
}

/* The bundle: closed hand in flow, centred on the pivot by its bottom-centre. */
.game-stage .seat-bundle {
  position: absolute;
  bottom: 0;
  left: 50%;
  transform: translateX(-50%);
  pointer-events: none;
}
.game-stage .seat-bundle .zone-hand {
  pointer-events: auto;
}
/* content-size the hand so the melds sit a fixed gap from the real tiles */
.game-stage .seat-bundle .seat-hand--bottom {
  width: auto;
}

/* Exposed stack (flowers above melds) hangs off the hand's right edge, so it
   does not affect the hand's width/centring. */
.game-stage .seat-bundle__exposed {
  position: absolute;
  left: 100%;
  bottom: 0;
  margin-left: var(--bundle-hand-meld-gap);
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--bundle-flower-meld-gap);
}

.game-stage .seat-bundle .zone-flowers {
  display: flex;
  flex-direction: row-reverse;
  gap: 4px;
}
/* row-reverse: first-formed meld ends up at the outer (far-from-hand) end; new
   melds appear at the inner end and the block extends outward. */
.game-stage .seat-bundle .zone-melds {
  display: flex;
  flex-direction: row-reverse;
  align-items: flex-end;
  gap: var(--meld-group-gap);
}

.game-stage .discard-lane {
  z-index: var(--zone-z-discards);
}
```

- [ ] **Step 4: Build**

Run: `node_modules/.bin/tsc --noEmit && npm run build`
Expected: clean (TS + Vite).

- [ ] **Step 5: Commit Tasks 1–6**

```bash
git add web/src/table/seat/ web/src/table/TableScene.tsx web/src/index.css
git commit -m "feat(web): rotation-based seat bundle for symmetric seats"
```

---

## Task 7: Harness verification + tuning

**Files:** Modify `web/src/index.css` (tune vars / pivot only)

Dev server: `npm run dev`; open `/dev/seat`; the `± meld` buttons toggle meld count. Use the browser preview tools to measure rects.

- [ ] **Step 1: Verify symmetry & layout**

Confirm via measured rects:
- The four bundles are exact rotations of each other (left and right are mirror-symmetric through the table centre).
- Hand and melds share the baseline; flowers sit above the melds; first-formed meld at the outer end.
- Toggling melds animates only the new meld in.

- [ ] **Step 2: Verify bounds & wild box**

At 4 melds on every seat: nothing leaves the table; the **left** bundle clears the upper-left wild-tile box. Tune `--bundle-edge-offset`, `--bundle-edge-offset-side`, and the gaps as needed. If a side bundle rides into the wild box, increase `--bundle-edge-offset-side` or shift that pivot.

- [ ] **Step 3: Commit any tuning**

```bash
git add web/src/index.css
git commit -m "style(web): tune seat bundle offsets"
```

---

## Task 8: Regression check

- [ ] **Step 1: Full check**

Run: `npm test && node_modules/.bin/tsc --noEmit && npm run build`
Expected: 9 tests pass, no type errors, build succeeds.

- [ ] **Step 2: Confirm draw/discard animation + overlay (in a real game or by inspection)**

Verify `FloatingTile` still fires on draw/discard (relies on `data-board-tile-id`), the shanten indicator shows on the self seat, and the round-result overlay melds render.

> Harness removal + branch completion is handled by Task 12 of the prior plan (`2026-06-04-modular-seat-layout.md`): remove `/dev/seat` + `SeatPreview`, then finish the branch.

---

## Self-Review Notes

- **Spec coverage:** canonical bundle (Task 3), per-seat rotation pivot (Tasks 5–6), canonical tile rendering (Tasks 1–2), first-formed-outer via `row-reverse` (Task 6), flowers above melds off the hand's right (Task 6), discards separate (Task 5), symmetry/wild-box verification (Task 7), regression (Task 8).
- **Prop consistency:** `ClosedHand` now takes `isSelf` (not `direction`); `OpenMelds`/`OpenMeldZone`/`FlowerZone` take no `direction`; `SeatBundle` takes `isSelf`; `PlayerSeat` keeps `direction` (for pivot class + discards) and derives `isSelf`.
- **Animation/IDs:** `data-board-tile-id`/`-role` preserved on hand/drawn/discard tiles.
