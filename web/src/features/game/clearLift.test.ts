import { describe, expect, it } from 'vitest'
import { shouldClearLift } from './clearLift'

describe('shouldClearLift', () => {
  it('does not clear when nothing is lifted', () => {
    expect(shouldClearLift({ liftedTileId: null, roundChanged: true, closedHandIds: [], drawnTileId: null })).toBe(false)
  })

  it('clears on a round change even if an id collision keeps the tile "present"', () => {
    expect(shouldClearLift({ liftedTileId: 5, roundChanged: true, closedHandIds: [5, 6, 7], drawnTileId: null })).toBe(true)
  })

  it('keeps the lift within a round while the tile is still in the closed hand (carry-over)', () => {
    expect(shouldClearLift({ liftedTileId: 5, roundChanged: false, closedHandIds: [3, 5, 9], drawnTileId: null })).toBe(false)
  })

  it('keeps the lift when the lifted tile is the freshly drawn tile', () => {
    expect(shouldClearLift({ liftedTileId: 12, roundChanged: false, closedHandIds: [3, 5, 9], drawnTileId: 12 })).toBe(false)
  })

  it('clears within a round when the lifted tile has left the hand (discard/meld)', () => {
    expect(shouldClearLift({ liftedTileId: 5, roundChanged: false, closedHandIds: [3, 9], drawnTileId: 7 })).toBe(true)
  })

  it('compares ids with tileIdsEqual (string/number-insensitive, null-safe)', () => {
    expect(shouldClearLift({ liftedTileId: 5, roundChanged: false, closedHandIds: ['5'], drawnTileId: null })).toBe(false)
  })
})
