import { describe, it, expect } from 'vitest'
import { concealedHandReserveTiles } from './handReserve'

// The seat bundle reserves a fixed concealed-hand width so the exposed stack
// (flowers + melds) doesn't shake when a tile is drawn/discarded. The reserved
// width must track the hand's real max size for its meld count — a hand with
// called melds holds fewer concealed tiles (engine invariant: concealed + 3*melds
// == 14 at most). Over-reserving (always 14) overflows the bundle span and shoves
// the exposed melds past the table edge.
describe('concealedHandReserveTiles', () => {
  it('reserves a full 14-tile hand when no melds are called', () => {
    expect(concealedHandReserveTiles(0)).toBe(14)
  })

  it('drops 3 tiles per called meld', () => {
    expect(concealedHandReserveTiles(1)).toBe(11)
    expect(concealedHandReserveTiles(2)).toBe(8)
    expect(concealedHandReserveTiles(3)).toBe(5)
  })

  it('reserves 2 tiles at the four-meld maximum', () => {
    expect(concealedHandReserveTiles(4)).toBe(2)
  })

  it('never returns fewer than 2 tiles', () => {
    expect(concealedHandReserveTiles(5)).toBe(2)
    expect(concealedHandReserveTiles(99)).toBe(2)
  })
})
