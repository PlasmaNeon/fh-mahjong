import { describe, it, expect } from 'vitest'
import { planTileFlights, hiddenHandSlotsByDirection, hiddenTileIdsFromAnimations, type MotionSnapshot, type TileMotionDescriptor, type TileRect } from './tileFlightPlan'
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
    // No previous id survives into the current frame (production re-randomizes
    // opponent ids every broadcast): the rail re-renders as 3 backs with fresh
    // ids, and drawn tile 1009 is gone (merged into the rail under a new id).
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [2001, { tile: tile(2001), direction: 'top', role: 'hand' }],
      [2002, { tile: tile(2002), direction: 'top', role: 'hand' }],
      [2003, { tile: tile(2003), direction: 'top', role: 'hand' }],
    ])
    const currentRects = new Map<number, TileRect>([
      [42, PILE], [2001, rect(10)], [2002, rect(20)], [2003, rect(30)],
    ])
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
    // Discard leaves the chosen gap slot AND flags it for blanking (the gap shows).
    expect(discard.fromRect.left).toBe(10)
    expect(discard.toRect.left).toBe(200)
    expect(discard.hideHandSlot).toEqual({ direction: 'top', index: 0 })
    // Drawn back slides from the drawn slot INTO the same gap rect (no current-id lookup).
    expect(merge.fromRect.left).toBe(60)
    expect(merge.toRect.left).toBe(10)
    expect(merge.asBack).toBe(true)
    expect(merge.tile.id).toBe(1009)
    // The gap-blank rides on the discard flight, not the merge.
    expect(merge.hideHandSlot).toBeUndefined()
  })

  it('tedashi: discard flies from the LAST hand slot when random returns 0.99', () => {
    // Math.floor(0.99 * 3) === 2 → hand tile 1003 @ left 30. The current rail
    // re-renders as 3 backs with fresh rotated ids (drawn merged, discard gone).
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [2001, { tile: tile(2001), direction: 'top', role: 'hand' }],
      [2002, { tile: tile(2002), direction: 'top', role: 'hand' }],
      [2003, { tile: tile(2003), direction: 'top', role: 'hand' }],
    ])
    const currentRects = new Map<number, TileRect>([
      [42, PILE], [2001, rect(10)], [2002, rect(20)], [2003, rect(30)],
    ])
    const animations = planTileFlights({
      previousSnapshot: prevSnapshot(),
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]),
      random: () => 0.99, // deterministic: pick the last hand slot (1003 @ left 30)
    })
    expect(animations).toHaveLength(2)
    const discard = animations.find((a) => a.tile.id === 42)!
    const merge = animations.find((a) => a.asBack)!
    // Discard leaves the chosen gap slot AND flags it (index 2) for blanking.
    expect(discard.fromRect.left).toBe(30)
    expect(discard.hideHandSlot).toEqual({ direction: 'top', index: 2 })
    // Drawn back slides from the drawn slot INTO the same gap rect.
    expect(merge.toRect.left).toBe(30)
    expect(merge.asBack).toBe(true)
    expect(merge.hideHandSlot).toBeUndefined()
  })

  it('tedashi after a pon (no draw): gap opens and the remaining back slides in', () => {
    // Opponent discarding after a pon: prev 2 concealed backs, no drawn tile.
    // Current: 1 back (fresh rotated id) + the discard.
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
      [2001, { tile: tile(2001), direction: 'top', role: 'hand' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE], [2001, rect(10)]])
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
    expect(animations).toHaveLength(2)
    const discard = animations.find((a) => a.tile.id === 42)!
    const slide = animations.find((a) => a.asBack)!
    // The gap shows at the vacated slot while the neighbour slides in to close it.
    expect(discard.fromRect.left).toBe(10)
    expect(discard.hideHandSlot).toEqual({ direction: 'top', index: 0 })
    expect(slide.fromRect.left).toBe(20)
    expect(slide.toRect.left).toBe(10)
    expect(slide.hideHandSlot).toEqual({ direction: 'top', index: 0 })
  })

  it('tedashi after a pon from the END slot: tile flies from the rail end, no blank', () => {
    // Pon-state (previous): 3 concealed backs, no drawn tile. RNG picks the LAST
    // slot, so the rail simply ends where the gap was — nothing needs to slide and
    // no current slot should be blanked (the old clamp blanked the current
    // rightmost back, making an unrelated tile blink out and pop back).
    const previousSnapshot: MotionSnapshot = {
      locations: new Map<number, TileMotionDescriptor>([
        [1001, { tile: tile(1001), direction: 'top', role: 'hand' }],
        [1002, { tile: tile(1002), direction: 'top', role: 'hand' }],
        [1003, { tile: tile(1003), direction: 'top', role: 'hand' }],
      ]),
      rects: new Map<number, TileRect>([[1001, rect(10)], [1002, rect(20)], [1003, rect(30)]]),
      handOrigins: new Map([['top', { left: 0, top: 0, width: 80, height: 14 }]]),
    }
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [2001, { tile: tile(2001), direction: 'top', role: 'hand' }],
      [2002, { tile: tile(2002), direction: 'top', role: 'hand' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE], [2001, rect(10)], [2002, rect(20)]])
    const animations = planTileFlights({
      previousSnapshot,
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]),
      random: () => 0.99, // picks the LAST previous hand slot (index 2)
    })
    // No drawn tile and an end gap -> only the discard flight, nothing blanked.
    expect(animations).toHaveLength(1)
    expect(animations[0].asBack).toBeFalsy()
    expect(animations[0].fromRect.left).toBe(30) // departs from the old rail end
    expect(animations[0].hideHandSlot).toBeUndefined()
  })

  it('tedashi after a pon: the hand collapses — backs slide left to close the gap', () => {
    // Pon-state (previous): 4 concealed backs at slots 0..3, no drawn tile.
    const previousSnapshot: MotionSnapshot = {
      locations: new Map<number, TileMotionDescriptor>([
        [1001, { tile: tile(1001), direction: 'top', role: 'hand' }],
        [1002, { tile: tile(1002), direction: 'top', role: 'hand' }],
        [1003, { tile: tile(1003), direction: 'top', role: 'hand' }],
        [1004, { tile: tile(1004), direction: 'top', role: 'hand' }],
      ]),
      rects: new Map<number, TileRect>([[1001, rect(10)], [1002, rect(20)], [1003, rect(30)], [1004, rect(40)]]),
      handOrigins: new Map([['top', { left: 0, top: 0, width: 80, height: 14 }]]),
    }
    // Current: 3 concealed backs (fresh rotated ids) + the discard.
    const currentLocations = new Map<number, TileMotionDescriptor>([
      [42, { tile: tile(42), direction: 'top', role: 'discard' }],
      [2001, { tile: tile(2001), direction: 'top', role: 'hand' }],
      [2002, { tile: tile(2002), direction: 'top', role: 'hand' }],
      [2003, { tile: tile(2003), direction: 'top', role: 'hand' }],
    ])
    const currentRects = new Map<number, TileRect>([[42, PILE], [2001, rect(10)], [2002, rect(20)], [2003, rect(30)]])
    const animations = planTileFlights({
      previousSnapshot,
      currentLocations,
      currentRects,
      currentHandOrigins: new Map(),
      isWildTile: () => false,
      startKey: 0,
      fromDrawnByDirection: new Map([['top', false]]),
      random: () => 0, // gap at slot 0
    })
    // Discard from slot 0 + a cosmetic collapse of the 3 backs to its right.
    const discard = animations.find((a) => a.tile.id === 42)!
    expect(discard.fromRect.left).toBe(10)
    expect(discard.hideHandSlot).toEqual({ direction: 'top', index: 0 })
    // Each back to the right slides one slot left (40->30, 30->20, 20->10) and
    // blanks the current slot it lands on.
    const slides = animations.filter((a) => a.asBack)
    expect(slides.map((s) => [s.fromRect.left, s.toRect.left])).toEqual([[20, 10], [30, 20], [40, 30]])
    expect(slides.map((s) => s.hideHandSlot)).toEqual([
      { direction: 'top', index: 0 },
      { direction: 'top', index: 1 },
      { direction: 'top', index: 2 },
    ])
    expect(animations).toHaveLength(4) // 1 discard + 3 sliding backs
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

describe('hiddenTileIdsFromAnimations', () => {
  const anim = (over: Partial<import('./tileFlightPlan').FlyingTileAnimation>): import('./tileFlightPlan').FlyingTileAnimation => ({
    key: 1, tile: tile(1), direction: 'top', fromRect: rect(0), toRect: rect(0), isWild: false, ...over,
  })

  it('includes normal flight ids but excludes asBack merge flights (stale fake ids)', () => {
    // The asBack drawn-back merge carries a previous-broadcast fake id; the gap it
    // fills is hidden via hideHandSlot, so its stale id must NOT reach hiddenTileIds
    // (per-broadcast rotation could reuse it for an unrelated current concealed tile).
    const ids = hiddenTileIdsFromAnimations([
      anim({ tile: tile(42) }), // discard (real id) -> hides the pond tile
      anim({ tile: tile(1009), asBack: true, hideHandSlot: { direction: 'top', index: 0 } }),
    ])
    expect(ids.has(42)).toBe(true)
    expect(ids.has(1009)).toBe(false)
    expect(ids.size).toBe(1)
  })
})
