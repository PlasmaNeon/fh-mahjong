import { describe, expect, it } from 'vitest'
import { clearPlayIntent, consumePlayIntent, rememberPlayIntent } from './navigation'
import { createMemoryStorage } from '../../test/memoryStorage'

describe('club navigation intents', () => {
  it('resumes the requested play action once and then clears it', () => {
    const store = createMemoryStorage()

    rememberPlayIntent(store, 'quick-match')
    expect(consumePlayIntent(store)).toBe('quick-match')
    expect(consumePlayIntent(store)).toBeNull()
  })

  it('clears a pending action when optional login is cancelled', () => {
    const store = createMemoryStorage()

    rememberPlayIntent(store, 'quick-match')
    clearPlayIntent(store)
    expect(consumePlayIntent(store)).toBeNull()
  })
})
