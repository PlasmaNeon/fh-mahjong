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
