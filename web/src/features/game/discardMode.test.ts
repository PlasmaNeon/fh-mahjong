import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadDiscardMode, parseDiscardMode, saveDiscardMode } from './discardMode'

// discardMode.ts reads window.localStorage. The node test env has no window,
// so stub one with a minimal in-memory Storage; a fresh store per test keeps
// the round-trip cases isolated without relying on jsdom.
function createStorageStub(): Storage {
  const store = new Map<string, string>()
  return {
    get length() {
      return store.size
    },
    clear: () => store.clear(),
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => {
      store.delete(key)
    },
    setItem: (key: string, value: string) => {
      store.set(key, String(value))
    },
  }
}

beforeEach(() => {
  vi.stubGlobal('window', { localStorage: createStorageStub() })
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
