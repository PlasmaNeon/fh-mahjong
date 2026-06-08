import { describe, it, expect } from 'vitest'
import { computeStableDisplayOrder, sortTiles } from './handOrdering'
import type { TileLike } from './types'

// same suit for all -> only value drives ordering
const t = (id: number, value: number): TileLike => ({ id, suit: 0, value })

describe('computeStableDisplayOrder', () => {
  it('sorts from scratch when there is no previous order', () => {
    const order = computeStableDisplayOrder([t(4, 8), t(1, 6), t(3, 7), t(2, 6)], null)
    // value-sorted, ties broken by id
    expect(order).toEqual([1, 2, 3, 4])
  })

  it('scenario A: draw 6m, discard 8m -> new 6m lands at the rightmost 6m slot', () => {
    // before draw: hand [6a,6b,7,8]
    let order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], null)
    expect(order).toEqual([1, 2, 3, 4])
    // draw 6c (id5): shown separately, baseTiles unchanged
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], order)
    expect(order).toEqual([1, 2, 3, 4])
    // discard 8 (id4); drawn 6c (id5) merges -> baseTiles [6a,6b,7,6c]
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(5, 6)], order)
    expect(order).toEqual([1, 2, 5, 3]) // 6a,6b,6c,7
  })

  it('scenario B: draw 8m, discard 7m -> new 8m fills the vacated 7m slot', () => {
    let order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], null)
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(3, 7), t(4, 8)], order)
    // discard 7 (id3); drawn 8d (id6) merges -> baseTiles [6a,6b,8,8d]
    order = computeStableDisplayOrder([t(1, 6), t(2, 6), t(4, 8), t(6, 8)], order)
    expect(order).toEqual([1, 2, 6, 4]) // 6a,6b,8d,8
  })

  it('keeps equal tiles positionally stable (no spontaneous swaps)', () => {
    // two 5m already displayed as [id10, id11]; an unrelated tile is added
    let order = computeStableDisplayOrder([t(10, 5), t(11, 5)], null)
    expect(order).toEqual([10, 11])
    order = computeStableDisplayOrder([t(10, 5), t(11, 5), t(12, 9)], order)
    expect(order).toEqual([10, 11, 12])
  })

  it('drops removed tiles and keeps survivors in their existing order', () => {
    let order = computeStableDisplayOrder([t(1, 1), t(2, 2), t(3, 3)], null)
    order = computeStableDisplayOrder([t(1, 1), t(3, 3)], order) // remove id2
    expect(order).toEqual([1, 3])
  })

  it('multi-add (e.g. meld/draw) inserts each addition at its group rightmost', () => {
    // previous [1m,3m]; add two tiles 2m(id20) and 3m(id21) at once
    let order = computeStableDisplayOrder([t(1, 1), t(2, 3)], null) // [1,2] -> values 1,3
    order = computeStableDisplayOrder([t(1, 1), t(2, 3), t(20, 2), t(21, 3)], order)
    expect(order).toEqual([1, 20, 2, 21]) // 1m, 2m, 3m(existing), 3m(new at rightmost of 3m group)
  })
})

describe('sortTiles', () => {
  it('orders by suit, then value, then id', () => {
    const sorted = sortTiles([
      { id: 2, suit: 2, value: 1 }, // pin 1
      { id: 1, suit: 3, value: 9 }, // man 9
      { id: 3, suit: 3, value: 9 }, // man 9 (higher id -> after id1)
    ])
    // getSuitOrder: MAN(3)=1, PIN(2)=2 -> man before pin
    expect(sorted.map((x) => x.id)).toEqual([1, 3, 2])
  })
})
