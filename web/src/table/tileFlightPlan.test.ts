import { describe, it, expect } from 'vitest'
import { planTileFlights, type MotionSnapshot, type TileMotionDescriptor, type TileRect } from './tileFlightPlan'
import { hiddenHandSlotsByDirection } from './tileFlightPlan'
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
      fromDrawnByDirection: new Map([['top', true]]),
    })
    expect(animations).toHaveLength(1)
    expect(animations[0].fromRect.left).toBe(60) // drawn slot
    expect(animations[0].toRect.left).toBe(200)
    expect(animations[0].asBack).toBeFalsy()
  })

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

  it('falls back to the generic hand origin when the seat has no tracked hand/drawn rects', () => {
    // No per-tile locations for 'top' (e.g. the opponent's hand rects weren't
    // captured), only a hand-origin region — so neither the drawn-slot nor a
    // random hand-slot origin is available and the generic anchor is used.
    const previousSnapshot: MotionSnapshot = {
      locations: new Map(),
      rects: new Map(),
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
    })
    expect(animations).toHaveLength(1)
    // centered on the handOrigin region (left 0, width 80) -> 0 + 40 - 5 = 35
    expect(animations[0].fromRect.left).toBe(35)
    expect(animations[0].asBack).toBeFalsy()
  })

  it('suppresses tedashi origin AND the drawn-back merge flight on a multi-discard resync', () => {
    // 'top' has hand + drawn rects, so a SINGLE tedashi discard would fly from a
    // random hand slot (10) AND emit an asBack merge flight (drawn 60 -> 40).
    // With TWO discards in the delta the per-seat flag can't be trusted, so 'top'
    // falls back to its generic origin and no merge flight is produced.
    const previousSnapshot: MotionSnapshot = {
      locations: new Map<number, TileMotionDescriptor>([
        [1001, { tile: tile(1001), direction: 'top', role: 'hand' }],
        [1009, { tile: tile(1009), direction: 'top', role: 'drawn' }],
      ]),
      rects: new Map<number, TileRect>([[1001, rect(10)], [1009, rect(60)]]),
      handOrigins: new Map([['top', { left: 0, top: 0, width: 80, height: 14 }]]),
    }
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [43, { tile: tile(43), direction: 'left', role: 'discard' }],
      [1009, { tile: tile(1009), direction: 'top', role: 'hand' }], // drawn merged into rail
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE], [43, PILE], [1009, rect(40)]])
    const animations = planTileFlights({
      previousSnapshot,
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]), // tedashi
      random: () => 0,
    })
    expect(animations.every((a) => !a.asBack)).toBe(true) // merge flight suppressed
    const topDiscard = animations.find((a) => a.tile.id === 42)!
    expect(topDiscard.fromRect.left).toBe(35) // generic anchor, NOT a random hand slot (10)
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
    })
    expect(animations).toHaveLength(1)
    expect(animations[0].fromRect.left).toBe(10) // tracked real position, not random/merge
    expect(animations[0].asBack).toBeFalsy() // no merge flight leaked onto the tracked path
  })
})

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
