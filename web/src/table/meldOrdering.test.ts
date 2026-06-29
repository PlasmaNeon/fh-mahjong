import { describe, it, expect } from 'vitest'
import { tileIdsEqual, reorderMeldTiles, orderMelds, orderMeldsForRecap } from './meldOrdering'
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
  it('excludes the added tile of a risky kong from the inline row', () => {
    // pon(10,11,called=12) upgraded with added=13; added is rendered stacked, not inline.
    const meld: MeldLike = {
      tiles: [t(10), t(11), t(12), t(13)],
      calledTileId: 12,
      calledDirection: 1,
      addedTileId: 13,
    }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([10, 11, 12])
  })
  it('keeps the tile with id 0 inline when there is no added tile', () => {
    // Regression: tile id 0 is a real tile (the first 1s). An unset added_tile_id
    // arrives as null/undefined (proto optional), NOT 0, so the id-0 tile must
    // stay in the inline row instead of being pulled out as a phantom 加杠 tile.
    const meld: MeldLike = { tiles: [t(0), t(1), t(2)], calledTileId: 2, calledDirection: 1 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([0, 1, 2])
  })
  it('honors a real added tile whose id is 0', () => {
    // pon(1,2,called=3) upgraded with added=0 (the first 1s). addedTileId is
    // explicitly 0 here, so the id-0 tile is correctly excluded (rendered stacked).
    const meld: MeldLike = {
      tiles: [t(1), t(2), t(3), t(0)],
      calledTileId: 3,
      calledDirection: 1,
      addedTileId: 0,
    }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([1, 2, 3])
  })
  it('does not reorder a concealed meld whose called id defaults to null', () => {
    // Concealed kong: called_tile_id unset → null (not 0), so the id-0 tile is not
    // mistaken for the called tile and the meld keeps its natural order.
    const meld: MeldLike = { tiles: [t(0), t(1), t(2), t(3)], calledTileId: null, calledDirection: 0 }
    expect(reorderMeldTiles(meld).map((x) => x.id)).toEqual([0, 1, 2, 3])
  })
})

describe('orderMelds', () => {
  const a: MeldLike = { tiles: [t(1)] }
  const b: MeldLike = { tiles: [t(2)] }
  const c: MeldLike = { tiles: [t(3)] }
  it('keeps formation order for every direction (first-formed nearest the hand)', () => {
    for (const dir of ['bottom', 'top', 'left', 'right'] as const) {
      expect(orderMelds([a, b, c], dir)).toEqual([a, b, c])
    }
  })
  it('does not mutate the input', () => {
    const input = [a, b, c]
    orderMelds(input, 'bottom')
    expect(input).toEqual([a, b, c])
  })
})

describe('orderMeldsForRecap', () => {
  const a: MeldLike = { tiles: [t(1)] }
  const b: MeldLike = { tiles: [t(2)] }
  const c: MeldLike = { tiles: [t(3)] }
  it('reverses formation order so the recap mirrors the seat (row-reverse zone)', () => {
    expect(orderMeldsForRecap([a, b, c])).toEqual([c, b, a])
  })
  it('handles empty and single-meld hands', () => {
    expect(orderMeldsForRecap([])).toEqual([])
    expect(orderMeldsForRecap([a])).toEqual([a])
  })
  it('does not mutate the input', () => {
    const input = [a, b, c]
    orderMeldsForRecap(input)
    expect(input).toEqual([a, b, c])
  })
})
