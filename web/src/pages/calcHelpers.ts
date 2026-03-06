import { ActionType, MeldDirection, Suit } from '../proto/game.ts'

export interface CalcTileValue {
  suit: Suit
  value: number
}

export interface CalcTileDraft extends CalcTileValue {
  id: string
}

export type CalcKongContextKey = keyof CalcKongFlags | ''

export interface CalcMeldDraft {
  id: string
  type: ActionType
  tiles: CalcTileDraft[]
  calledTileIndex: number
  calledDirection: MeldDirection
  kongContext: CalcKongContextKey
}

export interface CalcKongFlags {
  hasBuddingDirectKong: boolean
  hasBloomingDirectKong: boolean
  hasBuddingClosedKong: boolean
  hasBloomingClosedKong: boolean
  hasBuddingRiskyKong: boolean
  hasBloomingRiskyKong: boolean
  hasBloomingFlowerKong: boolean
}

export interface CalcRequestPayload {
  closedHand: CalcTileValue[]
  winTile: CalcTileValue | null
  wildTile: CalcTileValue | null
  openMelds: Array<{
    type: ActionType
    tiles: CalcTileValue[]
    calledTileIndex: number
    calledDirection: MeldDirection
    kongFlags: CalcKongFlags
  }>
  flowerMelds: number[]
  seatWind: number
  prevailingWind: number
  isTsumo: boolean
  kongFlags: CalcKongFlags
}

export interface CalcEntryResponse {
  patternName: string
  points: number
}

export interface CalcNormalizedMeldResponse {
  type: string
  tiles: string
  calledTile: string
  calledTileIndex: number
  calledDirection: string
  kongFlags: string[]
}

export interface CalcNormalizedResponse {
  closedHand: string
  winTile: string
  wildTile: string
  openMelds: CalcNormalizedMeldResponse[]
  flowerMelds: string[]
  seatWind: string
  prevailingWind: string
  winType: string
  kongFlags: string[]
  expectedHandLen: number
}

export interface CalcSuccessResponse {
  canWin: boolean
  score: number
  entries: CalcEntryResponse[]
  normalized: CalcNormalizedResponse
}

export interface CalcErrorResponse {
  errors: string[]
}

const EMPTY_NORMALIZED_RESPONSE: CalcNormalizedResponse = {
  closedHand: '',
  winTile: '',
  wildTile: '',
  openMelds: [],
  flowerMelds: [],
  seatWind: '',
  prevailingWind: '',
  winType: '',
  kongFlags: [],
  expectedHandLen: 0,
}

export const TILE_LIBRARY: CalcTileValue[] = [
  ...buildSuitTiles(Suit.SUIT_MAN, 9),
  ...buildSuitTiles(Suit.SUIT_PIN, 9),
  ...buildSuitTiles(Suit.SUIT_SOU, 9),
  ...buildSuitTiles(Suit.SUIT_JIHAI, 7),
]

export const WIND_OPTIONS = [
  { value: 1, label: 'East' },
  { value: 2, label: 'South' },
  { value: 3, label: 'West' },
  { value: 4, label: 'North' },
] as const

export const FLOWER_OPTIONS = [
  { value: 1, label: 'Flower 1' },
  { value: 2, label: 'Flower 2' },
  { value: 3, label: 'Flower 3' },
  { value: 4, label: 'Flower 4' },
  { value: 5, label: 'Flower 5' },
  { value: 6, label: 'Flower 6' },
  { value: 7, label: 'Flower 7' },
  { value: 8, label: 'Flower 8' },
] as const

export const DEFAULT_KONG_FLAGS: CalcKongFlags = {
  hasBuddingDirectKong: false,
  hasBloomingDirectKong: false,
  hasBuddingClosedKong: false,
  hasBloomingClosedKong: false,
  hasBuddingRiskyKong: false,
  hasBloomingRiskyKong: false,
  hasBloomingFlowerKong: false,
}

let nextTileDraftId = 1
let nextMeldDraftId = 1

function buildSuitTiles(suit: Suit, maxValue: number): CalcTileValue[] {
  const tiles: CalcTileValue[] = []
  for (let value = 1; value <= maxValue; value += 1) {
    tiles.push({ suit, value })
  }
  return tiles
}

export function createTileDraft(tile: CalcTileValue): CalcTileDraft {
  return {
    ...tile,
    id: `tile-${nextTileDraftId++}`,
  }
}

export function createMeldDraft(type: ActionType = ActionType.ACTION_CHII): CalcMeldDraft {
  return {
    id: `meld-${nextMeldDraftId++}`,
    type,
    tiles: [],
    calledTileIndex: 0,
    calledDirection: MeldDirection.MELD_DIRECTION_LEFT,
    kongContext: '',
  }
}

export function toTileValue(tile: CalcTileDraft | CalcTileValue): CalcTileValue {
  return { suit: tile.suit, value: tile.value }
}

export function sameTileValue(left: CalcTileDraft | CalcTileValue | null, right: CalcTileDraft | CalcTileValue | null): boolean {
  return Boolean(left && right && left.suit === right.suit && left.value === right.value)
}

export function sortTiles(tiles: CalcTileDraft[]): CalcTileDraft[] {
  return [...tiles].sort((left, right) => {
    const leftOrder = suitSortOrder(left.suit)
    const rightOrder = suitSortOrder(right.suit)
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder
    }
    return left.value - right.value
  })
}

export function formatTile(tile: CalcTileValue | CalcTileDraft | null): string {
  if (!tile) {
    return ''
  }

  switch (tile.suit) {
    case Suit.SUIT_MAN:
      return `${tile.value}m`
    case Suit.SUIT_PIN:
      return `${tile.value}p`
    case Suit.SUIT_SOU:
      return `${tile.value}s`
    case Suit.SUIT_JIHAI:
      return `${tile.value}z`
    default:
      return ''
  }
}

export function formatTehai(tiles: Array<CalcTileDraft | CalcTileValue>): string {
  if (tiles.length === 0) {
    return ''
  }

  const sorted = [...tiles].sort((left, right) => {
    const leftOrder = suitSortOrder(left.suit)
    const rightOrder = suitSortOrder(right.suit)
    if (leftOrder !== rightOrder) {
      return leftOrder - rightOrder
    }
    return left.value - right.value
  })

  const groups: string[] = []
  let currentSuit: Suit | null = null
  let currentGroup = ''

  sorted.forEach((tile) => {
    if (currentSuit !== null && tile.suit !== currentSuit) {
      groups.push(currentGroup)
      currentGroup = ''
    }
    currentGroup += formatTile(tile)
    currentSuit = tile.suit
  })

  if (currentGroup) {
    groups.push(currentGroup)
  }

  return groups.join(' ')
}

export function parseTehaiInput(input: string): { tiles: CalcTileValue[]; errors: string[] } {
  const trimmed = input.trim()
  if (!trimmed) {
    return { tiles: [], errors: [] }
  }

  const compact = trimmed.replace(/\s+/g, '')
  const matches = [...compact.matchAll(/([0-9]+)([mpsz])/gi)]
  const consumed = matches.map((match) => match[0]).join('')

  if (consumed !== compact) {
    return {
      tiles: [],
      errors: ['Use canonical tile notation like 1m2m3m 4p5p6p 7z.'],
    }
  }

  const tiles: CalcTileValue[] = []
  const errors: string[] = []

  matches.forEach((match) => {
    const digits = match[1]
    const suitChar = match[2].toLowerCase()
    digits.split('').forEach((digit: string) => {
      const value = Number(digit)
      const suit = charToSuit(suitChar)
      if (suit === null) {
        errors.push(`Unknown suit: ${suitChar}`)
        return
      }
      if (!isValueValidForSuit(suit, value)) {
        errors.push(`Tile ${digit}${suitChar} is out of range.`)
        return
      }
      tiles.push({ suit, value })
    })
  })

  return { tiles, errors }
}

export function parseSingleTileInput(input: string): { tile: CalcTileValue | null; errors: string[] } {
  const trimmed = input.trim()
  if (!trimmed) {
    return { tile: null, errors: [] }
  }

  const parsed = parseTehaiInput(trimmed)
  if (parsed.errors.length > 0) {
    return { tile: null, errors: parsed.errors }
  }
  if (parsed.tiles.length !== 1) {
    return {
      tile: null,
      errors: ['Enter exactly one tile, like 3z or 9s.'],
    }
  }

  return { tile: parsed.tiles[0], errors: [] }
}

export function expectedClosedHandSize(openMeldsCount: number): number {
  return 13 - (3 * openMeldsCount)
}

export function meldRequiredTileCount(type: ActionType): number {
  return type === ActionType.ACTION_KAN ? 4 : 3
}

export function validateMeldShape(meld: CalcMeldDraft): string | null {
  const requiredCount = meldRequiredTileCount(meld.type)
  if (meld.tiles.length !== requiredCount) {
    return `${getMeldLabel(meld.type)} must contain ${requiredCount} tiles.`
  }
  if (meld.calledTileIndex < 0 || meld.calledTileIndex >= meld.tiles.length) {
    return `${getMeldLabel(meld.type)} called tile index is out of range.`
  }

  if (meld.type === ActionType.ACTION_CHII) {
    const suit = meld.tiles[0]?.suit
    if (!isSuitedTile(suit)) {
      return 'Chii tiles must be man, pin, or sou.'
    }
    if (meld.tiles.some((tile) => tile.suit !== suit)) {
      return 'Chii tiles must share the same suit.'
    }
    const values = meld.tiles.map((tile) => tile.value).sort((left, right) => left - right)
    if (values[0] + 1 !== values[1] || values[1] + 1 !== values[2]) {
      return 'Chii tiles must form a consecutive sequence.'
    }
    return null
  }

  const firstTile = meld.tiles[0]
  if (meld.tiles.some((tile) => tile.suit !== firstTile.suit || tile.value !== firstTile.value)) {
    return `${getMeldLabel(meld.type)} tiles must all be identical.`
  }

  return null
}

export function validateCalculatorState(args: {
  closedHand: CalcTileDraft[]
  winTile: CalcTileDraft | null
  wildTile: CalcTileDraft | null
  openMelds: CalcMeldDraft[]
  flowerMelds: number[]
  seatWind: number
  prevailingWind: number
}): string[] {
  const errors: string[] = []
  const expectedLength = expectedClosedHandSize(args.openMelds.length)

  if (args.winTile === null) {
    errors.push('Pick a win tile before calculating.')
  }
  if (args.closedHand.length !== expectedLength) {
    errors.push(`Closed hand must contain ${expectedLength} tiles for ${args.openMelds.length} open meld(s).`)
  }
  if (args.seatWind < 1 || args.seatWind > 4) {
    errors.push('Seat wind must be between East and North.')
  }
  if (args.prevailingWind < 1 || args.prevailingWind > 4) {
    errors.push('Prevailing wind must be between East and North.')
  }
  if (args.flowerMelds.length > 8) {
    errors.push('Flower meld count cannot exceed 8.')
  }

  args.openMelds.forEach((meld, index) => {
    const meldError = validateMeldShape(meld)
    if (meldError) {
      errors.push(`Open meld ${index + 1}: ${meldError}`)
    }
  })

  const counts = new Map<string, number>()
  const addTileCount = (tile: CalcTileDraft | CalcTileValue) => {
    const key = formatTile(tile)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }

  args.closedHand.forEach(addTileCount)
  if (args.winTile) {
    addTileCount(args.winTile)
  }
  args.openMelds.forEach((meld) => {
    meld.tiles.forEach(addTileCount)
  })

  counts.forEach((count, key) => {
    if (count > 4) {
      errors.push(`Tile ${key} appears ${count} times; physical tiles are capped at 4 copies.`)
    }
  })

  return errors
}

export function buildCalcRequestPayload(args: {
  closedHand: CalcTileDraft[]
  winTile: CalcTileDraft | null
  wildTile: CalcTileDraft | null
  openMelds: CalcMeldDraft[]
  flowerMelds: number[]
  seatWind: number
  prevailingWind: number
  isTsumo: boolean
}): CalcRequestPayload {
  const kongFlags = aggregateKongFlags(args.openMelds)

  return {
    closedHand: args.closedHand.map(toTileValue),
    winTile: args.winTile ? toTileValue(args.winTile) : null,
    wildTile: args.wildTile ? toTileValue(args.wildTile) : null,
    openMelds: args.openMelds.map((meld) => ({
      type: meld.type,
      tiles: meld.tiles.map(toTileValue),
      calledTileIndex: meld.calledTileIndex,
      calledDirection: meld.calledDirection,
      kongFlags: buildKongFlagsFromContext(meld.kongContext),
    })),
    flowerMelds: [...args.flowerMelds],
    seatWind: args.seatWind,
    prevailingWind: args.prevailingWind,
    isTsumo: args.isTsumo,
    kongFlags,
  }
}

export function normalizeCalcSuccessResponse(payload: unknown): CalcSuccessResponse {
  const record = isRecord(payload) ? payload : {}
  const normalizedRecord = isRecord(record.normalized) ? record.normalized : {}

  const entries = Array.isArray(record.entries)
    ? record.entries.map((entry) => {
        const entryRecord = isRecord(entry) ? entry : {}
        return {
          patternName: readString(entryRecord.patternName) ?? readString(entryRecord.PatternName) ?? 'Unknown entry',
          points: readNumber(entryRecord.points) ?? readNumber(entryRecord.Points) ?? 0,
        }
      })
    : []

  const normalized: CalcNormalizedResponse = {
    closedHand: readString(normalizedRecord.closedHand) ?? EMPTY_NORMALIZED_RESPONSE.closedHand,
    winTile: readString(normalizedRecord.winTile) ?? EMPTY_NORMALIZED_RESPONSE.winTile,
    wildTile: readString(normalizedRecord.wildTile) ?? EMPTY_NORMALIZED_RESPONSE.wildTile,
    openMelds: Array.isArray(normalizedRecord.openMelds)
      ? normalizedRecord.openMelds.map((meld) => {
          const meldRecord = isRecord(meld) ? meld : {}
          return {
            type: readString(meldRecord.type) ?? 'unknown',
            tiles: readString(meldRecord.tiles) ?? '',
            calledTile: readString(meldRecord.calledTile) ?? '',
            calledTileIndex: readNumber(meldRecord.calledTileIndex) ?? 0,
            calledDirection: readString(meldRecord.calledDirection) ?? '',
            kongFlags: Array.isArray(meldRecord.kongFlags)
              ? meldRecord.kongFlags.map((flag) => String(flag))
              : [],
          }
        })
      : EMPTY_NORMALIZED_RESPONSE.openMelds,
    flowerMelds: Array.isArray(normalizedRecord.flowerMelds)
      ? normalizedRecord.flowerMelds.map((flower) => String(flower))
      : EMPTY_NORMALIZED_RESPONSE.flowerMelds,
    seatWind: readString(normalizedRecord.seatWind) ?? EMPTY_NORMALIZED_RESPONSE.seatWind,
    prevailingWind: readString(normalizedRecord.prevailingWind) ?? EMPTY_NORMALIZED_RESPONSE.prevailingWind,
    winType: readString(normalizedRecord.winType) ?? EMPTY_NORMALIZED_RESPONSE.winType,
    kongFlags: Array.isArray(normalizedRecord.kongFlags)
      ? normalizedRecord.kongFlags.map((flag) => String(flag))
      : EMPTY_NORMALIZED_RESPONSE.kongFlags,
    expectedHandLen: readNumber(normalizedRecord.expectedHandLen) ?? EMPTY_NORMALIZED_RESPONSE.expectedHandLen,
  }

  return {
    canWin: readBoolean(record.canWin) ?? false,
    score: readNumber(record.score) ?? 0,
    entries,
    normalized,
  }
}

export function normalizeCalcErrorResponse(payload: unknown): CalcErrorResponse {
  const record = isRecord(payload) ? payload : {}
  return {
    errors: Array.isArray(record.errors) ? record.errors.map((error) => String(error)) : ['Calculator request failed.'],
  }
}

export function getMeldLabel(type: ActionType): string {
  switch (type) {
    case ActionType.ACTION_CHII:
      return 'Chii'
    case ActionType.ACTION_PON:
      return 'Pon'
    case ActionType.ACTION_KAN:
      return 'Kan'
    default:
      return 'Meld'
  }
}

export function getDirectionLabel(direction: MeldDirection): string {
  switch (direction) {
    case MeldDirection.MELD_DIRECTION_RIGHT:
      return 'Right'
    case MeldDirection.MELD_DIRECTION_ACROSS:
      return 'Across'
    case MeldDirection.MELD_DIRECTION_LEFT:
      return 'Left'
    default:
      return 'Unknown'
  }
}

function suitSortOrder(suit: Suit): number {
  switch (suit) {
    case Suit.SUIT_MAN:
      return 1
    case Suit.SUIT_PIN:
      return 2
    case Suit.SUIT_SOU:
      return 3
    case Suit.SUIT_JIHAI:
      return 4
    default:
      return 5
  }
}

function charToSuit(char: string): Suit | null {
  switch (char) {
    case 'm':
      return Suit.SUIT_MAN
    case 'p':
      return Suit.SUIT_PIN
    case 's':
      return Suit.SUIT_SOU
    case 'z':
      return Suit.SUIT_JIHAI
    default:
      return null
  }
}

function isValueValidForSuit(suit: Suit, value: number): boolean {
  if (suit === Suit.SUIT_JIHAI) {
    return value >= 1 && value <= 7
  }
  return value >= 1 && value <= 9
}

function isSuitedTile(suit: Suit | undefined): suit is Suit.SUIT_MAN | Suit.SUIT_PIN | Suit.SUIT_SOU {
  return suit === Suit.SUIT_MAN || suit === Suit.SUIT_PIN || suit === Suit.SUIT_SOU
}

function aggregateKongFlags(openMelds: CalcMeldDraft[]): CalcKongFlags {
  return openMelds.reduce<CalcKongFlags>(
    (mergedFlags, meld) => {
      if (meld.type !== ActionType.ACTION_KAN) {
        return mergedFlags
      }

      const meldFlags = buildKongFlagsFromContext(meld.kongContext)

      return {
        hasBuddingDirectKong: mergedFlags.hasBuddingDirectKong || meldFlags.hasBuddingDirectKong,
        hasBloomingDirectKong: mergedFlags.hasBloomingDirectKong || meldFlags.hasBloomingDirectKong,
        hasBuddingClosedKong: mergedFlags.hasBuddingClosedKong || meldFlags.hasBuddingClosedKong,
        hasBloomingClosedKong: mergedFlags.hasBloomingClosedKong || meldFlags.hasBloomingClosedKong,
        hasBuddingRiskyKong: mergedFlags.hasBuddingRiskyKong || meldFlags.hasBuddingRiskyKong,
        hasBloomingRiskyKong: mergedFlags.hasBloomingRiskyKong || meldFlags.hasBloomingRiskyKong,
        hasBloomingFlowerKong: mergedFlags.hasBloomingFlowerKong || meldFlags.hasBloomingFlowerKong,
      }
    },
    { ...DEFAULT_KONG_FLAGS },
  )
}

function buildKongFlagsFromContext(context: CalcKongContextKey): CalcKongFlags {
  if (!context) {
    return { ...DEFAULT_KONG_FLAGS }
  }

  return {
    ...DEFAULT_KONG_FLAGS,
    [context]: true,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function readString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function readNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function readBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}
