import { afterEach, describe, expect, it } from 'vitest'
import { loadDiscardMode, parseDiscardMode, saveDiscardMode } from './discardMode'

describe('parseDiscardMode', () => {
  it('accepts the two valid modes', () => {
    expect(parseDiscardMode('single')).toBe('single')
    expect(parseDiscardMode('double')).toBe('double')
  })

  it('defaults to double for null / unknown / malformed values', () => {
    expect(parseDiscardMode(null)).toBe('double')
    expect(parseDiscardMode('')).toBe('double')
    expect(parseDiscardMode('triple')).toBe('double')
    expect(parseDiscardMode('SINGLE')).toBe('double')
  })
})

describe('load/save round-trip', () => {
  afterEach(() => localStorage.clear())

  it('defaults to double when nothing is stored', () => {
    expect(loadDiscardMode()).toBe('double')
  })

  it('persists and reloads a saved mode', () => {
    saveDiscardMode('single')
    expect(loadDiscardMode()).toBe('single')
    saveDiscardMode('double')
    expect(loadDiscardMode()).toBe('double')
  })
})
