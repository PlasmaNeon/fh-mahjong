import type { MeldLike, RoundResultPayout, RoundResultView, TileLike } from '../../table/types'

// Dev-only mock data for the /tools/round-result preview. Suits match
// TableSample.tsx: 1=sou, 2=pin, 3=man, 4=jihai, 5=flower. These hands are for
// visual preview only — they are plausible but not validated by the rules engine.

export type ScenarioKey = 'tsumo' | 'ron' | 'draw' | 'long'

export const SCENARIO_KEYS: ScenarioKey[] = ['tsumo', 'ron', 'draw', 'long']

export const SCENARIO_LABELS: Record<ScenarioKey, string> = {
  tsumo: 'Tsumo win',
  ron: 'Ron win',
  draw: 'Exhaustive draw',
  long: 'Long high-score',
}

// The overlay owns the `actions` footer node; scenarios carry only data.
export type ScenarioData = Omit<RoundResultView, 'actions'>

// Per-seat ready badge. `ready` off => no badge (null); on => alternating
// Ready/waiting, mirroring Game.tsx's playerReady mapping.
function readyBadge(seat: number, ready: boolean): Pick<RoundResultPayout, 'readyLabel' | 'readyActive'> {
  if (!ready) return { readyLabel: null, readyActive: false }
  const active = seat % 2 === 0
  return { readyLabel: active ? 'Ready' : '...', readyActive: active }
}

// amounts must be given in seat order [0,1,2,3] and sum to zero.
function payouts(amounts: [number, number, number, number], ready: boolean): RoundResultPayout[] {
  return amounts.map((amount, seat) => ({
    seat,
    label: `Seat ${seat}`,
    amount,
    ...readyBadge(seat, ready),
  }))
}

export function buildScenario(key: ScenarioKey, ready: boolean): ScenarioData {
  let nextId = 0
  const t = (suit: number, value: number): TileLike => ({ id: nextId++, suit, value })

  switch (key) {
    case 'draw':
      return { isDraw: true }

    case 'ron': {
      const meld = [t(1, 9), t(1, 9), t(1, 9)]
      const winningMelds: MeldLike[] = [
        { tiles: meld, calledTileId: meld[2].id, calledDirection: 2 },
      ]
      return {
        isDraw: false,
        winType: 'ron',
        winnerLabel: 'Seat 1 wins',
        discarderLabel: 'From Seat 3',
        closedHand: [
          t(3, 2), t(3, 3), t(3, 4),
          t(2, 5), t(2, 6), t(2, 7),
          t(1, 5), t(1, 5),
          t(3, 7), t(3, 8),
        ],
        winTile: t(3, 9),
        winningMelds,
        flowers: [],
        breakdown: [
          { name: 'Terminal Triplet (幺九刻)', points: 2 },
          { name: 'Seat Wind (自風)', points: 1 },
          { name: 'Robbing the Kong (搶槓)', points: 8 },
        ],
        totalScore: 11,
        payouts: payouts([-3, 16, -3, -10], ready),
      }
    }

    case 'long': {
      const meld = [t(1, 3), t(1, 3), t(1, 3)]
      const winningMelds: MeldLike[] = [
        { tiles: meld, calledTileId: meld[2].id, calledDirection: 1 },
      ]
      return {
        isDraw: false,
        winType: 'tsumo',
        winnerLabel: 'Seat 2 wins',
        discarderLabel: null,
        closedHand: [
          t(1, 1), t(1, 1), t(1, 2),
          t(1, 4), t(1, 5), t(1, 6),
          t(1, 7), t(1, 8),
          t(1, 9), t(1, 9),
        ],
        winTile: t(1, 8),
        winningMelds,
        flowers: [t(5, 1), t(5, 2), t(5, 3), t(5, 4)],
        breakdown: [
          { name: 'Full Flush (清一色)', points: 24 },
          { name: 'Self-Draw (自摸)', points: 2 },
          { name: 'Concealed Triplet (暗刻)', points: 2 },
          { name: 'Flower Season 1', points: 1 },
          { name: 'Flower Season 2', points: 1 },
          { name: 'Flower Season 3', points: 1 },
          { name: 'Flower Season 4', points: 1 },
          { name: 'Kong Bonus (杠)', points: 2 },
          { name: 'Last Tile Draw (海底)', points: 8 },
          { name: 'Dealer Bonus (庄)', points: 4 },
          { name: 'Wild-Tile Pair (搭)', points: 6 },
          { name: 'All Terminals Fringe', points: 4 },
        ],
        totalScore: 56,
        payouts: payouts([-32, -32, 96, -32], ready),
      }
    }

    case 'tsumo':
    default:
      return {
        isDraw: false,
        winType: 'tsumo',
        winnerLabel: 'Seat 0 wins',
        discarderLabel: null,
        closedHand: [
          t(1, 1), t(1, 2), t(1, 3),
          t(2, 4), t(2, 5), t(2, 6),
          t(3, 7), t(3, 8), t(3, 9),
          t(1, 5), t(1, 5),
          t(2, 3), t(2, 3),
        ],
        winTile: t(2, 3),
        winningMelds: [],
        flowers: [t(5, 1)],
        breakdown: [
          { name: 'Self-Draw (自摸)', points: 2 },
          { name: 'All Sequences (平和)', points: 4 },
          { name: 'Flower (花牌)', points: 1 },
        ],
        totalScore: 7,
        payouts: payouts([24, -8, -8, -8], ready),
      }
  }
}
