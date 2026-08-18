import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadDiscardMode, parseDiscardMode, saveDiscardMode } from './discardMode'
import { createMemoryStorage } from '../../test/memoryStorage'

beforeEach(() => {
  vi.stubGlobal('window', { localStorage: createMemoryStorage() })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

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
