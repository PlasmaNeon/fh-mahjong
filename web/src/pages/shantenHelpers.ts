import {
  TILE_LIBRARY as SHARED_TILE_LIBRARY,
  formatHand as sharedFormatHand,
  formatTile as sharedFormatTile,
  parseHand as sharedParseHand,
  sameTileValue,
  sortBySuitValue,
  countTiles as sharedCountTiles,
  remainingCount as sharedRemainingCount,
  tileKey as sharedTileKey,
  type ParseMessages,
  type TileValue as SharedTileValue,
  type TileDraft as SharedTileDraft,
} from '../utils/tileModel'

export type TileValue = SharedTileValue
export type TileDraft = SharedTileDraft

export interface UsefulTileInfo {
  suit: SharedTileValue['suit']
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

export const TILE_LIBRARY: TileValue[] = SHARED_TILE_LIBRARY

const messages: ParseMessages = {
  notation: 'Use notation like 123m456p789s1z',
  unknownSuit: (ch) => `Unknown suit: ${ch}`,
  outOfRange: (digit, ch) => `Tile ${digit}${ch} is out of range`,
}

let nextId = 1

export function createDraft(tile: TileValue): TileDraft {
  return { ...tile, id: `st-${nextId++}` }
}

export function sameTile(a: TileValue | null, b: TileValue | null): boolean {
  return sameTileValue(a, b)
}

export function sortHand(tiles: TileDraft[]): TileDraft[] {
  return sortBySuitValue(tiles)
}

export function formatTile(tile: TileValue): string {
  return sharedFormatTile(tile)
}

export function formatHand(tiles: TileValue[]): string {
  return sharedFormatHand(tiles)
}

export function parseHand(input: string): { tiles: TileValue[]; error: string | null } {
  const { tiles, errors } = sharedParseHand(input, messages, false)
  return { tiles, error: errors.length > 0 ? errors[0] : null }
}

export function parseSingleTile(input: string): { tile: TileValue | null; error: string | null } {
  const { tiles, error } = parseHand(input)
  if (error) return { tile: null, error }
  if (tiles.length !== 1) return { tile: null, error: 'Enter exactly one tile (e.g. 3z)' }
  return { tile: tiles[0], error: null }
}

export function tileKey(tile: TileValue): string {
  return sharedTileKey(tile)
}

export function countTiles(tiles: TileValue[]): Map<string, number> {
  return sharedCountTiles(tiles)
}

export function remainingCount(tile: TileValue, usedCounts: Map<string, number>): number {
  return sharedRemainingCount(tile, usedCounts)
}

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
