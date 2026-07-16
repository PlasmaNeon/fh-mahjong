import { describe, expect, it } from 'vitest'
import { parseReplayReference } from './replayReference'

describe('parseReplayReference', () => {
  it('accepts a raw match id', () => {
    expect(parseReplayReference(' 00000000-0000-0000-0000-000000000201 ')).toBe('00000000-0000-0000-0000-000000000201')
  })

  it('extracts a local replay route without preserving query data', () => {
    expect(parseReplayReference('/replay/rain-table-7?token=ignore#round-2')).toBe('rain-table-7')
  })

  it('extracts only the replay path from an external URL', () => {
    expect(parseReplayReference('https://shared.example/replay/rain-table-8?from=friend')).toBe('rain-table-8')
  })

  it('rejects unrelated, nested, and credential-like references', () => {
    expect(parseReplayReference('https://shared.example/room/rain-table')).toBeNull()
    expect(parseReplayReference('/replay/one/more')).toBeNull()
    expect(parseReplayReference('javascript:alert(1)')).toBeNull()
    expect(parseReplayReference('')).toBeNull()
  })
})
