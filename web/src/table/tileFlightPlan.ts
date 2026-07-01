import type { SeatLaneDirection, TileLike } from './types'

// Pure (React-free) flight planning for tile motion. Given the previous and
// current board snapshots, decide which tiles should "fly" and from/to where.
// Kept free of React/DOM so it can be reasoned about and tested in isolation.

export type TileMotionRole = 'hand' | 'drawn' | 'discard'

export type TileMotionDescriptor = {
  tile: TileLike
  direction: SeatLaneDirection
  role: TileMotionRole
}

export type TileRect = {
  left: number
  top: number
  width: number
  height: number
}

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

export type MotionSnapshot = {
  locations: Map<number, TileMotionDescriptor>
  rects: Map<number, TileRect>
  handOrigins: Map<SeatLaneDirection, TileRect>
}

// Below this many pixels of travel a flight isn't worth showing (e.g. a tile
// that merely re-sorted in place).
const MIN_TRAVEL_DISTANCE = 4

export function tileIdsEqual(left: unknown, right: unknown) {
  if (left == null || right == null) return false
  return String(left) === String(right)
}

function shouldAnimateTileTransfer(previousRole: TileMotionRole, currentRole: TileMotionRole) {
  // Only fly tiles leaving a hand for the discard pond. The drawn -> hand merge
  // (a tile sliding from the drawn slot into its sorted spot on discard) is owned
  // by the closed hand's own layoutId animation; flying it here too would hide
  // that slide behind the portal overlay and snap it at the end.
  return (previousRole === 'hand' || previousRole === 'drawn') && currentRole === 'discard'
}

// Build a tile-sized rect centered on a (larger) origin region, used as the
// start point for tiles flying out of a concealed opponent hand.
function centerRectOn(origin: TileRect, size: TileRect): TileRect {
  return {
    left: origin.left + origin.width / 2 - size.width / 2,
    top: origin.top + origin.height / 2 - size.height / 2,
    width: size.width,
    height: size.height,
  }
}

export type PlanTileFlightsParams = {
  previousSnapshot: MotionSnapshot
  currentLocations: Map<number, TileMotionDescriptor>
  currentRects: Map<number, TileRect>
  currentHandOrigins: Map<SeatLaneDirection, TileRect>
  isWildTile: (tile: TileLike) => boolean
  // Monotonic key seed so each produced animation gets a unique React key.
  startKey: number
  // Per-seat "was that seat's most recent discard a tsumogiri" flags, keyed by
  // seat direction. Used only for redacted opponents, where the discard's real
  // id cannot be tracked back to a fake-id hand tile; looked up by the
  // discarder's direction.
  fromDrawnByDirection?: Map<SeatLaneDirection, boolean>
  // Injectable RNG for the random tedashi source slot (deterministic in tests).
  random?: () => number
}

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

// Tile ids whose settled position should stay hidden while their flight is
// airborne. `asBack` merge flights (the tedashi drawn-back slide) are excluded:
// their `tile.id` is a stale previous-broadcast fake id, and in production those
// ids are re-randomized every broadcast, so feeding it here could blank an
// unrelated current concealed tile that the new obfuscation map assigned the same
// fake id. The merge's gap is hidden via `hideHandSlot` instead.
export function hiddenTileIdsFromAnimations(animations: FlyingTileAnimation[]): Set<number> {
  const ids = new Set<number>()
  for (const animation of animations) {
    if (animation.asBack) continue
    ids.add(animation.tile.id)
  }
  return ids
}

export function planTileFlights({
  previousSnapshot,
  currentLocations,
  currentRects,
  currentHandOrigins,
  isWildTile,
  startKey,
  fromDrawnByDirection,
  random = Math.random,
}: PlanTileFlightsParams): FlyingTileAnimation[] {
  const animations: FlyingTileAnimation[] = []
  let key = startKey

  // Count discards newly revealed since the previous snapshot. The per-seat
  // tsumogiri flag describes only each seat's *latest* discard, so on a
  // multi-discard delta (e.g. a resync after dropped broadcasts) it can't be
  // trusted to label an older discard in the batch — those fall back to the
  // generic origin instead of a (possibly mislabeled) tedashi/tsumogiri origin.
  let newDiscardCount = 0
  currentLocations.forEach((t, id) => {
    if (t.role === 'discard' && !previousSnapshot.locations.has(id)) newDiscardCount += 1
  })
  const singleNewDiscard = newDiscardCount === 1

  currentLocations.forEach((currentTile, tileId) => {
    const toRect = currentRects.get(tileId)
    if (!toRect) return

    const previousTile = previousSnapshot.locations.get(tileId)
    let fromRect: TileRect | undefined
    // Set for a tedashi discard: the concealed rail slot to blank while the
    // discard flies, so the gap is visible whether or not a drawn tile fills it.
    let hideHandSlot: { direction: SeatLaneDirection; index: number } | undefined

    if (previousTile) {
      // The viewer's own tiles are tracked across renders by id, so we know
      // exactly where the tile started.
      if (previousTile.direction !== currentTile.direction) return
      if (!shouldAnimateTileTransfer(previousTile.role, currentTile.role)) return
      fromRect = previousSnapshot.rects.get(tileId)
    } else if (currentTile.role === 'discard') {
      const dir = currentTile.direction
      // A single newly-revealed discard is the one just made, so the discarder's
      // most-recent-discard flag describes it; skip the special origin on a
      // multi-discard delta where the flag can't be trusted per older discard.
      const fromDrawn = fromDrawnByDirection?.get(dir) ?? false

      if (singleNewDiscard && fromDrawn) {
        // Tsumogiri: fly the discard straight from the separated drawn slot.
        const drawnId = prevTileIdsByRole(previousSnapshot, dir, 'drawn')[0]
        if (drawnId != null) fromRect = previousSnapshot.rects.get(drawnId)
      } else if (singleNewDiscard) {
        // Tedashi: the discard leaves a random concealed hand slot (the "gap").
        // Blank that slot for the discard's own flight so the gap is visible for
        // EVERY tedashi — including a pon/chii discard, which has no drawn tile.
        // When the player did draw this turn, also slide the drawn back into the
        // gap to fill it; otherwise the gap simply closes as the rail reflows.
        // Everything is read from the PREVIOUS snapshot, so it survives the
        // per-broadcast id rotation (no current-frame id lookup).
        const handIds = prevTileIdsByRole(previousSnapshot, dir, 'hand')
        if (handIds.length > 0) {
          // Clamp guards against an injected RNG returning exactly 1.0 (Math.random is [0,1)).
          const slotIndex = Math.min(handIds.length - 1, Math.floor(random() * handIds.length))
          const gapRect = previousSnapshot.rects.get(handIds[slotIndex])
          fromRect = gapRect

          if (gapRect) {
            // The current rail may be one shorter than the previous snapshot (a
            // pon/chii discard doesn't draw a replacement), so clamp the blanked
            // slot to the current hand length to keep it on a rendered tile.
            let currentHandCount = 0
            currentLocations.forEach((t) => {
              if (t.direction === dir && t.role === 'hand') currentHandCount += 1
            })
            const hideIndex = currentHandCount > 0 ? Math.min(slotIndex, currentHandCount - 1) : slotIndex
            hideHandSlot = { direction: dir, index: hideIndex }

            const drawnId = prevTileIdsByRole(previousSnapshot, dir, 'drawn')[0]
            const mergeFrom = drawnId != null ? previousSnapshot.rects.get(drawnId) : undefined
            const drawnTileObj = drawnId != null ? previousSnapshot.locations.get(drawnId)?.tile : undefined
            if (mergeFrom && drawnTileObj) {
              // Normal/kan tedashi: slide the drawn back into the gap to fill it.
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
                })
              }
            } else if (currentHandCount > 0) {
              // Pon/chii tedashi (no draw): collapse the concealed hand — every
              // back to the right of the gap slides one slot left to close it, so
              // the hand tightens up. Purely cosmetic (identical face-down backs),
              // driven by previous-snapshot slot rects rather than real tile ids;
              // each sliding back also blanks the current slot it lands on so the
              // real (already-reflowed) rail doesn't show through the animation.
              for (let i = slotIndex + 1; i < handIds.length; i += 1) {
                const slideFrom = previousSnapshot.rects.get(handIds[i])
                const slideTo = previousSnapshot.rects.get(handIds[i - 1])
                const backTile = previousSnapshot.locations.get(handIds[i])?.tile
                const landIndex = i - 1
                if (!slideFrom || !slideTo || !backTile || landIndex > currentHandCount - 1) continue
                key += 1
                animations.push({
                  key,
                  tile: backTile,
                  direction: dir,
                  fromRect: slideFrom,
                  toRect: slideTo,
                  isWild: false,
                  asBack: true,
                  hideHandSlot: { direction: dir, index: landIndex },
                })
              }
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

    if (!fromRect) return

    const travelDistance = Math.hypot(toRect.left - fromRect.left, toRect.top - fromRect.top)
    if (travelDistance < MIN_TRAVEL_DISTANCE) return

    key += 1
    animations.push({
      key,
      tile: currentTile.tile,
      direction: currentTile.direction,
      fromRect,
      toRect,
      isWild: isWildTile(currentTile.tile),
      hideHandSlot,
    })
  })

  return animations
}
