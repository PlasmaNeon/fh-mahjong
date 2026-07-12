import { describe, expect, it } from 'vitest'
import { consumePlayIntent, createPrivateTablePath, rememberPlayIntent } from './navigation'

describe('club navigation intents', () => {
  it('resumes the requested play action once and then clears it', () => {
    const storage = new Map<string, string>()
    const store = {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
      removeItem: (key: string) => storage.delete(key),
    }

    rememberPlayIntent(store, 'quick-match')
    expect(consumePlayIntent(store)).toBe('quick-match')
    expect(consumePlayIntent(store)).toBeNull()
  })

  it('builds a private table route from the generated id', () => {
    expect(createPrivateTablePath(() => 'rain-123')).toBe('/room/rain-123')
  })
})
