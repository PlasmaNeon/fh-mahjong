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
    expect(animations[0].asBack).toBeFalsy() // no merge flight leaked onto the tracked path
  })
})
