import { vi } from 'vitest'

// Ensure localStorage is available in test environment
if (typeof window === 'undefined') {
  Object.defineProperty(global, 'window', {
    value: {
      localStorage: new Map(),
    },
    writable: true,
  })
}

// Polyfill localStorage if needed
if (!global.localStorage) {
  const store = new Map<string, string>()
  global.localStorage = {
    getItem: (key: string) => store.get(key) || null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] || null,
    length: 0,
  } as any
}
