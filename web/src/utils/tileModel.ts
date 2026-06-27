import { Suit } from '../proto/game.ts'

export interface TileValue {
  suit: Suit
  value: number
}

export interface TileDraft extends TileValue {
  id: string
}

export function buildSuitTiles(suit: Suit, maxValue: number): TileValue[] {
  const tiles: TileValue[] = []
  for (let value = 1; value <= maxValue; value += 1) {
    tiles.push({ suit, value })
  }
  return tiles
}

export const TILE_LIBRARY: TileValue[] = [
  ...buildSuitTiles(Suit.SUIT_MAN, 9),
  ...buildSuitTiles(Suit.SUIT_PIN, 9),
  ...buildSuitTiles(Suit.SUIT_SOU, 9),
  ...buildSuitTiles(Suit.SUIT_JIHAI, 7),
]

export function suitOrder(suit: Suit): number {
  switch (suit) {
    case Suit.SUIT_MAN: return 0
    case Suit.SUIT_PIN: return 1
    case Suit.SUIT_SOU: return 2
    case Suit.SUIT_JIHAI: return 3
    default: return 9
  }
}

export function suitChar(suit: Suit): string {
  switch (suit) {
    case Suit.SUIT_MAN: return 'm'
    case Suit.SUIT_PIN: return 'p'
    case Suit.SUIT_SOU: return 's'
    case Suit.SUIT_JIHAI: return 'z'
    default: return '?'
  }
}

export function charToSuit(char: string): Suit | null {
  switch (char) {
    case 'm': return Suit.SUIT_MAN
    case 'p': return Suit.SUIT_PIN
    case 's': return Suit.SUIT_SOU
    case 'z': return Suit.SUIT_JIHAI
    default: return null
  }
}

export function maxValueForSuit(suit: Suit): number {
  return suit === Suit.SUIT_JIHAI ? 7 : 9
}

export function isValueValidForSuit(suit: Suit, value: number): boolean {
  return value >= 1 && value <= maxValueForSuit(suit)
}

export function isSuitedTile(
  suit: Suit | undefined,
): suit is Suit.SUIT_MAN | Suit.SUIT_PIN | Suit.SUIT_SOU {
  return suit === Suit.SUIT_MAN || suit === Suit.SUIT_PIN || suit === Suit.SUIT_SOU
}

export function sameTileValue(a: TileValue | null, b: TileValue | null): boolean {
  return Boolean(a && b && a.suit === b.suit && a.value === b.value)
}

export function compareBySuitValue(a: TileValue, b: TileValue): number {
  const ao = suitOrder(a.suit)
  const bo = suitOrder(b.suit)
  return ao !== bo ? ao - bo : a.value - b.value
}

export function sortBySuitValue<T extends TileValue>(tiles: T[]): T[] {
  return [...tiles].sort(compareBySuitValue)
}

// Returns '' for non-standard suits (man/pin/sou/jihai only are renderable here).
export function formatTile(tile: TileValue | null): string {
  if (!tile) return ''
  const ch = suitChar(tile.suit)
  return ch === '?' ? '' : `${tile.value}${ch}`
}

export interface FormatHandOptions {
  separator?: string
  perTile?: boolean
}

// perTile=false yields compact groups ("123m"); perTile=true repeats the suit
// per tile ("1m2m3m"). Groups are joined by `separator`.
export function formatHand(tiles: TileValue[], options: FormatHandOptions = {}): string {
  const { separator = '', perTile = false } = options
  if (tiles.length === 0) return ''
  const sorted = sortBySuitValue(tiles)
  const groups: string[] = []
  let currentSuit: Suit | null = null
  let currentGroup = ''
  for (const tile of sorted) {
    if (currentSuit !== null && tile.suit !== currentSuit) {
      groups.push(perTile ? currentGroup : `${currentGroup}${suitChar(currentSuit)}`)
      currentGroup = ''
    }
    currentGroup += perTile ? formatTile(tile) : String(tile.value)
    currentSuit = tile.suit
  }
  if (currentGroup && currentSuit !== null) {
    groups.push(perTile ? currentGroup : `${currentGroup}${suitChar(currentSuit)}`)
  }
  return groups.join(separator)
}

export interface ParseMessages {
  notation: string
  unknownSuit: (rawChar: string) => string
  outOfRange: (digit: string, rawChar: string) => string
}

export interface ParseResult {
  tiles: TileValue[]
  errors: string[]
}

// Parses compact notation like "123m4p". With collectAll=false it returns on
// the first error with empty tiles; with collectAll=true it keeps valid tiles
// and accumulates every error. Message strings are supplied by the caller so
// each page keeps its exact wording.
export function parseHand(input: string, messages: ParseMessages, collectAll: boolean): ParseResult {
  const compact = input.trim().replace(/\s+/g, '')
  if (!compact) return { tiles: [], errors: [] }

  const matches = [...compact.matchAll(/([0-9]+)([mpsz])/gi)]
  const consumed = matches.map((m) => m[0]).join('')
  if (consumed !== compact) {
    return { tiles: [], errors: [messages.notation] }
  }

  const tiles: TileValue[] = []
  const errors: string[] = []
  for (const match of matches) {
    const digits = match[1]
    const rawChar = match[2]
    const suit = charToSuit(rawChar.toLowerCase())
    if (suit === null) {
      errors.push(messages.unknownSuit(rawChar))
      if (!collectAll) return { tiles: [], errors }
      continue
    }
    for (const d of digits) {
      const v = Number(d)
      if (!isValueValidForSuit(suit, v)) {
        errors.push(messages.outOfRange(d, rawChar))
        if (!collectAll) return { tiles: [], errors }
        continue
      }
      tiles.push({ suit, value: v })
    }
  }
  return { tiles, errors }
}

export function parseSingleTile(
  input: string,
  messages: ParseMessages,
): { tile: TileValue | null; errors: string[] } {
  const trimmed = input.trim()
  if (!trimmed) return { tile: null, errors: [] }
  const parsed = parseHand(trimmed, messages, true)
  if (parsed.errors.length > 0) return { tile: null, errors: parsed.errors }
  if (parsed.tiles.length !== 1) return { tile: null, errors: [] }
  return { tile: parsed.tiles[0], errors: [] }
}

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
