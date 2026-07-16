import { describe, expect, it } from 'vitest'
import { resolveHandTileClick } from './handTileClick'

describe('resolveHandTileClick', () => {
  it('single mode on-turn discards immediately (no lift step)', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: false, canDiscard: true }).kind).toBe('discard')
    // even a re-tap of the same tile just discards on-turn
    expect(resolveHandTileClick({ mode: 'single', isLifted: true, canDiscard: true }).kind).toBe('discard')
  })

  it('single mode off-turn lifts an un-lifted tile', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: false, canDiscard: false }).kind).toBe('lift')
  })

  it('single mode off-turn un-lifts the lifted tile', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: true, canDiscard: false }).kind).toBe('unlift')
  })

  it('double mode raises the lift on an un-lifted tile (on or off turn)', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: false, canDiscard: true }).kind).toBe('lift')
    expect(resolveHandTileClick({ mode: 'double', isLifted: false, canDiscard: false }).kind).toBe('lift')
  })

  it('double mode confirms discard when re-tapping the lifted tile on-turn', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: true, canDiscard: true }).kind).toBe('discard')
  })

  it('double mode off-turn drops the lifted tile instead of discarding', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: true, canDiscard: false }).kind).toBe('unlift')
  })
})
