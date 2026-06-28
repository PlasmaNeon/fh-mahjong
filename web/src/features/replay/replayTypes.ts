// Suit constants matching proto/game.proto Suit enum values
const SUIT_SOU = 1
const SUIT_MAN = 3
const SUIT_PIN = 2
const SUIT_JIHAI = 4
const SUIT_FLOWER = 5

export interface PaipuTile {
  id: number
  suit: number
  value: number
}

export interface PaipuPlayer {
  seat: number
  name: string
  userId: number
}

export interface PaipuAction {
  act: string
  seat: number
  tile?: number | null
  tiles?: number[]
  from?: number | null
}

export interface PaipuFlowerReveal {
  seat: number
  flower: number
  replacement: number
}

export interface PaipuMeld {
  type: string
  tiles: number[]
  from?: number
}

export interface PaipuBreakdown {
  name: string
  points: number
}

export interface PaipuRoundResult {
  type: string
  winner: number | null
  winType?: string
  discarder: number | null
  winTile?: number | null
  hand?: number[]
  melds?: PaipuMeld[]
  flowers?: number[]
  breakdown?: PaipuBreakdown[]
  totalScore?: number
  scoreChanges: number[]
}

export interface PaipuRound {
  round: number
  prevailingWind: number
  dealer: number
  dice: [number, number]
  wallSeed: string
  wildTiles: PaipuTile[]
  wangpaiStacks: number
  startingScores: [number, number, number, number]
  deals: [number[], number[], number[], number[]]
  initialFlowers: PaipuFlowerReveal[]
  actions: PaipuAction[]
  result: PaipuRoundResult | null
}

export interface Paipu {
  version: number
  matchId: string
  ruleset: string
  players: PaipuPlayer[]
  rounds: PaipuRound[]
  finalScores: [number, number, number, number]
}

// Convert tile ID (0-143) to {suit, value} matching rules/fh.go GetInitialWall()
export function tileFromId(id: number): { suit: number; value: number } {
  if (id < 36) return { suit: SUIT_SOU, value: Math.floor(id / 4) + 1 }
  if (id < 72) return { suit: SUIT_MAN, value: Math.floor((id - 36) / 4) + 1 }
  if (id < 108) return { suit: SUIT_PIN, value: Math.floor((id - 72) / 4) + 1 }
  if (id < 136) return { suit: SUIT_JIHAI, value: Math.floor((id - 108) / 4) + 1 }
  return { suit: SUIT_FLOWER, value: id - 136 + 1 }
}

// Build a full tile object from an ID (for rendering)
export function tileObjectFromId(id: number): { id: number; suit: number; value: number } {
  const { suit, value } = tileFromId(id)
  return { id, suit, value }
}
