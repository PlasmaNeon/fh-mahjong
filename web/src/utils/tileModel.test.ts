import { describe, it, expect } from 'vitest'
import { game } from '../proto/game'
import {
  TILE_LIBRARY,
  formatTile,
  formatHand,
  parseHand,
  sortBySuitValue,
  sameTileValue,
  remainingCount,
  countTiles,
  type ParseMessages,
} from './tileModel'

const messages: ParseMessages = {
  notation: 'bad',
  unknownSuit: (ch) => `Unknown suit: ${ch}`,
  outOfRange: (d, ch) => `Tile ${d}${ch} out of range`,
}

describe('tileModel', () => {
  it('builds the 34-tile library', () => {
    expect(TILE_LIBRARY).toHaveLength(34)
    expect(TILE_LIBRARY[0]).toEqual({ suit: game.Suit.SUIT_MAN, value: 1 })
  })

  it('formats a single tile', () => {
    expect(formatTile({ suit: game.Suit.SUIT_PIN, value: 5 })).toBe('5p')
    expect(formatTile(null)).toBe('')
  })

  it('formats a hand compact (no separator) and per-tile (spaced)', () => {
    const hand = [
      { suit: game.Suit.SUIT_PIN, value: 4 },
      { suit: game.Suit.SUIT_MAN, value: 1 },
      { suit: game.Suit.SUIT_MAN, value: 2 },
    ]
    expect(formatHand(hand)).toBe('12m4p')
    expect(formatHand(hand, { separator: ' ', perTile: true })).toBe('1m2m 4p')
  })

  it('sorts man < pin < sou < jihai then by value', () => {
    const sorted = sortBySuitValue([
      { suit: game.Suit.SUIT_JIHAI, value: 1 },
      { suit: game.Suit.SUIT_MAN, value: 3 },
      { suit: game.Suit.SUIT_MAN, value: 1 },
    ])
    expect(sorted.map((t) => `${t.value}-${t.suit}`)).toEqual([
      `1-${game.Suit.SUIT_MAN}`,
      `3-${game.Suit.SUIT_MAN}`,
      `1-${game.Suit.SUIT_JIHAI}`,
    ])
  })

  it('parses valid notation', () => {
    const r = parseHand('123m4p', messages, true)
    expect(r.errors).toEqual([])
    expect(r.tiles).toHaveLength(4)
  })

  it('collectAll=false stops at first error with empty tiles', () => {
    const r = parseHand('1z9z', messages, false)
    expect(r.errors).toEqual(['Tile 9z out of range'])
    expect(r.tiles).toEqual([])
  })

  it('collectAll=true keeps valid tiles and all errors', () => {
    const r = parseHand('1z9z', messages, true)
    expect(r.tiles).toEqual([{ suit: game.Suit.SUIT_JIHAI, value: 1 }])
    expect(r.errors).toEqual(['Tile 9z out of range'])
  })

  it('counts tiles and computes remaining', () => {
    const used = countTiles([
      { suit: game.Suit.SUIT_SOU, value: 5 },
      { suit: game.Suit.SUIT_SOU, value: 5 },
    ])
    expect(remainingCount({ suit: game.Suit.SUIT_SOU, value: 5 }, used)).toBe(2)
  })

  it('sameTileValue compares by face', () => {
    expect(sameTileValue({ suit: game.Suit.SUIT_MAN, value: 1 }, { suit: game.Suit.SUIT_MAN, value: 1 })).toBe(true)
    expect(sameTileValue({ suit: game.Suit.SUIT_MAN, value: 1 }, null)).toBe(false)
  })
})
