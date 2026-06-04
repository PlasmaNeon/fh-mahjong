import type { SeatLaneDirection, TileLike } from './TableScene'

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
  return (
    ((previousRole === 'hand' || previousRole === 'drawn') && currentRole === 'discard') ||
    (previousRole === 'drawn' && currentRole === 'hand')
  )
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
}

export function planTileFlights({
  previousSnapshot,
  currentLocations,
  currentRects,
  currentHandOrigins,
  isWildTile,
  startKey,
}: PlanTileFlightsParams): FlyingTileAnimation[] {
  const animations: FlyingTileAnimation[] = []
  let key = startKey

  currentLocations.forEach((currentTile, tileId) => {
    const toRect = currentRects.get(tileId)
    if (!toRect) return

    const previousTile = previousSnapshot.locations.get(tileId)
    let fromRect: TileRect | undefined

    if (previousTile) {
      // The viewer's own tiles are tracked across renders by id, so we know
      // exactly where the tile started.
      if (previousTile.direction !== currentTile.direction) return
      if (!shouldAnimateTileTransfer(previousTile.role, currentTile.role)) return
      fromRect = previousSnapshot.rects.get(tileId)
    } else if (currentTile.role === 'discard') {
      // Newly revealed discard from a concealed (opponent) hand: there is no
      // tracked source tile, so fly from the seat's hand region. Prefer the
      // pre-discard hand position from the previous snapshot.
      const origin =
        previousSnapshot.handOrigins.get(currentTile.direction) ??
        currentHandOrigins.get(currentTile.direction)
      if (origin) {
        fromRect = centerRectOn(origin, toRect)
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
    })
  })

  return animations
}
