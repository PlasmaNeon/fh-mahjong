import { Suit } from '../proto/game.ts'

export interface TileValue {
  suit: Suit
  value: number
}

export interface TileDraft extends TileValue {
  id: string
}

export interface UsefulTileInfo {
  suit: Suit
  value: number
  remaining: number
}

export interface DiscardOption {
  discard: TileValue
  shanten: number
  usefulTiles: UsefulTileInfo[]
  totalUseful: number
}

export interface ShantenResult {
  shanten: number
  drawnTile?: TileValue | null
  discardOptions: DiscardOption[]
}

export const TILE_LIBRARY: TileValue[] = [
  ...buildSuitTiles(Suit.SUIT_MAN, 9),
  ...buildSuitTiles(Suit.SUIT_PIN, 9),
  ...buildSuitTiles(Suit.SUIT_SOU, 9),
  ...buildSuitTiles(Suit.SUIT_JIHAI, 7),
]

function buildSuitTiles(suit: Suit, maxValue: number): TileValue[] {
  const tiles: TileValue[] = []
  for (let value = 1; value <= maxValue; value++) {
    tiles.push({ suit, value })
  }
  return tiles
}

let nextId = 1

export function createDraft(tile: TileValue): TileDraft {
  return { ...tile, id: `st-${nextId++}` }
}

export function sameTile(a: TileValue | null, b: TileValue | null): boolean {
  return Boolean(a && b && a.suit === b.suit && a.value === b.value)
}

export function sortHand(tiles: TileDraft[]): TileDraft[] {
  return [...tiles].sort((a, b) => {
    const ao = suitOrder(a.suit)
    const bo = suitOrder(b.suit)
    if (ao !== bo) return ao - bo
    return a.value - b.value
  })
}

function suitOrder(suit: Suit): number {
  switch (suit) {
    case Suit.SUIT_MAN: return 0
    case Suit.SUIT_PIN: return 1
    case Suit.SUIT_SOU: return 2
    case Suit.SUIT_JIHAI: return 3
    default: return 9
  }
}

function suitChar(suit: Suit): string {
  switch (suit) {
    case Suit.SUIT_MAN: return 'm'
    case Suit.SUIT_PIN: return 'p'
    case Suit.SUIT_SOU: return 's'
    case Suit.SUIT_JIHAI: return 'z'
    default: return '?'
  }
}

function charToSuit(ch: string): Suit | null {
  switch (ch) {
    case 'm': return Suit.SUIT_MAN
    case 'p': return Suit.SUIT_PIN
    case 's': return Suit.SUIT_SOU
    case 'z': return Suit.SUIT_JIHAI
    default: return null
  }
}

function maxValue(suit: Suit): number {
  return suit === Suit.SUIT_JIHAI ? 7 : 9
}

export function formatTile(tile: TileValue): string {
  return `${tile.value}${suitChar(tile.suit)}`
}

export function formatHand(tiles: TileValue[]): string {
  if (tiles.length === 0) return ''
  const sorted = [...tiles].sort((a, b) => {
    const ao = suitOrder(a.suit)
    const bo = suitOrder(b.suit)
    return ao !== bo ? ao - bo : a.value - b.value
  })
  const groups: string[] = []
  let curSuit: Suit | null = null
  let curValues = ''
  for (const t of sorted) {
    if (curSuit !== null && t.suit !== curSuit) {
      groups.push(`${curValues}${suitChar(curSuit)}`)
      curValues = ''
    }
    curValues += t.value
    curSuit = t.suit
  }
  if (curValues && curSuit !== null) {
    groups.push(`${curValues}${suitChar(curSuit)}`)
  }
  return groups.join('')
}

export function parseHand(input: string): { tiles: TileValue[]; error: string | null } {
  const compact = input.trim().replace(/\s+/g, '')
  if (!compact) return { tiles: [], error: null }

  const matches = [...compact.matchAll(/([0-9]+)([mpsz])/gi)]
  const consumed = matches.map(m => m[0]).join('')
  if (consumed !== compact) {
    return { tiles: [], error: 'Use notation like 123m456p789s1z' }
  }

  const tiles: TileValue[] = []
  for (const match of matches) {
    const digits = match[1]
    const suit = charToSuit(match[2].toLowerCase())
    if (!suit) return { tiles: [], error: `Unknown suit: ${match[2]}` }
    for (const d of digits) {
      const v = Number(d)
      if (v < 1 || v > maxValue(suit)) {
        return { tiles: [], error: `Tile ${d}${match[2]} is out of range` }
      }
      tiles.push({ suit, value: v })
    }
  }
  return { tiles, error: null }
}

export function parseSingleTile(input: string): { tile: TileValue | null; error: string | null } {
  const { tiles, error } = parseHand(input)
  if (error) return { tile: null, error }
  if (tiles.length !== 1) return { tile: null, error: 'Enter exactly one tile (e.g. 3z)' }
  return { tile: tiles[0], error: null }
}

// Count how many copies of each tile type are used
export function tileKey(tile: TileValue): string {
  return `${tile.suit}-${tile.value}`
}

export function countTiles(tiles: TileValue[]): Map<string, number> {
  const counts = new Map<string, number>()
  for (const t of tiles) {
    const k = tileKey(t)
    counts.set(k, (counts.get(k) ?? 0) + 1)
  }
  return counts
}

export function remainingCount(tile: TileValue, usedCounts: Map<string, number>): number {
  return 4 - (usedCounts.get(tileKey(tile)) ?? 0)
}

// URL state encoding/decoding
export function encodeUrlState(hand: TileValue[], wildTile: TileValue | null, openMelds: number): string {
  const params = new URLSearchParams()
  if (hand.length > 0) params.set('q', formatHand(hand))
  if (wildTile) params.set('w', formatTile(wildTile))
  if (openMelds > 0) params.set('m', String(openMelds))
  return params.toString()
}

export function decodeUrlState(search: string): {
  hand: TileValue[]
  wildTile: TileValue | null
  openMelds: number
} {
  const params = new URLSearchParams(search)
  const q = params.get('q')
  const w = params.get('w')
  const m = params.get('m')

  let hand: TileValue[] = []
  if (q) {
    const parsed = parseHand(q)
    if (!parsed.error) hand = parsed.tiles
  }

  let wildTile: TileValue | null = null
  if (w) {
    const parsed = parseSingleTile(w)
    if (!parsed.error && parsed.tile) wildTile = parsed.tile
  }

  const openMelds = m ? Math.min(4, Math.max(0, parseInt(m, 10) || 0)) : 0

  return { hand, wildTile, openMelds }
}
