import type { ReactNode } from 'react'

export type SeatLaneDirection = 'bottom' | 'right' | 'top' | 'left'

export type TileLike = {
  id: number
  suit: number
  value: number
}

export type MeldLike = {
  tiles: TileLike[]
  calledTileId?: number | null
  calledDirection?: number | null
}

export type PlayerTableView = {
  seat: number
  seatWind?: number
  score?: number
  closedHand?: TileLike[]
  handBackCount?: number
  showClosedHand?: boolean
  drawnTileId?: number | null
  openMelds?: MeldLike[]
  flowerMelds?: TileLike[]
  discards?: TileLike[]
  shantenLabel?: string | null
}

export type HudChip = {
  label: string
  tone?: 'default' | 'danger'
}

export type RoundResultBreakdownEntry = {
  name: string
  points: number
}

export type RoundResultPayout = {
  seat: number
  label: string
  amount: number
  readyLabel?: string | null
  readyActive?: boolean
}

export type RoundResultView = {
  isDraw: boolean
  winType?: 'tsumo' | 'ron'
  winnerLabel?: string
  discarderLabel?: string | null
  closedHand?: TileLike[]
  winTile?: TileLike | null
  winningMelds?: MeldLike[]
  flowers?: TileLike[]
  breakdown?: RoundResultBreakdownEntry[]
  totalScore?: number
  payouts?: RoundResultPayout[]
  actions?: ReactNode
}
