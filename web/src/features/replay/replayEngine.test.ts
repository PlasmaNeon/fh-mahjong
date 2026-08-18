import { describe, it, expect } from 'vitest'
import { ReplayEngine } from './replayEngine'
import type { Paipu, PaipuAction } from './replayTypes'

// Ids are laid out SOU-first (see replayTypes.tileFromId): 0-35 sou, 36-71 man.
// 36,37,38 are the four copies of 1m; 40,41 are copies of 2m.
const CLAIMER = 1
const DISCARDER = 0

function paipuWith(actions: PaipuAction[]): Paipu {
  const deal = (seat: number) => Array.from({ length: 13 }, (_, i) => seat * 13 + i + 100)
  return {
    version: 2,
    matchId: 'steal-test',
    ruleset: 'fenghua',
    players: [0, 1, 2, 3].map((seat) => ({ seat, name: `P${seat}`, userId: 0 })),
    finalScores: [0, 0, 0, 0],
    rounds: [{
      round: 1,
      prevailingWind: 1,
      dealer: 0,
      dice: [3, 4],
      wallSeed: 'seed',
      wildTiles: [],
      wangpaiStacks: 7,
      startingScores: [0, 0, 0, 0],
      // Give the claimer the two tiles it will meld with.
      deals: [deal(0), [36, 37, ...deal(1).slice(2)], deal(2), deal(3)],
      initialFlowers: [],
      actions,
      result: null,
    }],
  } as Paipu
}

/** Steps an engine to the end of its only round and returns the final state. */
function finalState(actions: PaipuAction[]) {
  const engine = new ReplayEngine(paipuWith(actions))
  while (engine.stepForward()) { /* advance to the last action */ }
  return engine.getState()
}

describe('ReplayEngine steal-from-discard melds', () => {
  const discard: PaipuAction = { act: 'discard', seat: DISCARDER, tile: 38 }

  it('pon takes the discard off the discarder and melds it with the claimed tiles', () => {
    const state = finalState([
      discard,
      { act: 'pon', seat: CLAIMER, tiles: [36, 37], from: DISCARDER },
    ])
    expect(state.players[DISCARDER].discards).toHaveLength(0)
    const meld = state.players[CLAIMER].melds[0]
    expect(meld.type).toBe('pon')
    expect(meld.from).toBe(DISCARDER)
    expect(meld.tiles.map((t) => t.id)).toEqual([36, 37, 38])
    expect(state.activeDiscard).toBeNull()
  })

  it('chii records the meld under its own action name', () => {
    const state = finalState([
      discard,
      { act: 'chii', seat: CLAIMER, tiles: [36, 37], from: DISCARDER },
    ])
    expect(state.players[CLAIMER].melds[0].type).toBe('chii')
  })

  it('okan records the meld as a kan, not as "okan"', () => {
    const state = finalState([
      discard,
      { act: 'okan', seat: CLAIMER, tiles: [36, 37, 39], from: DISCARDER },
    ])
    const meld = state.players[CLAIMER].melds[0]
    expect(meld.type).toBe('kan')
    expect(meld.tiles.map((t) => t.id)).toEqual([36, 37, 39, 38])
    expect(state.players[DISCARDER].discards).toHaveLength(0)
  })

  it('does not meld when the discarder has no discard to steal', () => {
    const state = finalState([
      { act: 'pon', seat: CLAIMER, tiles: [36, 37], from: DISCARDER },
    ])
    expect(state.players[CLAIMER].melds).toHaveLength(0)
  })
})
