import { describe, expect, it } from 'vitest'
import { parseReplayLocation, parseReplayReference } from './replayReference'

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

describe('parseReplayLocation', () => {
  it('opens private import bookmarks locally with the selected viewer state', () => {
    expect(
      parseReplayLocation(
        'https://shared.example/replay/import/native-7?round=2&cursor=22&seat=2&study=0&advice=1&decision=r2-d15-s2',
      ),
    ).toBe('/replay/import/native-7?round=2&cursor=22&seat=2&study=0&advice=1&decision=r2-d15-s2')
  })

  it('retains match bookmarks and raw match ids while dropping unrelated query data', () => {
    expect(parseReplayLocation(' table-7 ')).toBe('/replay/table-7')
    expect(parseReplayLocation('/replay/table-7?token=secret&cursor=3&analyze=1#fragment')).toBe('/replay/table-7?cursor=3')
    expect(parseReplayLocation('/replay/import/native-7?cursor=3&cursor=4')).toBe('/replay/import/native-7?cursor=3')
  })

  it('rejects invalid protocols, nested routes and encoded path separators', () => {
    for (const input of [
      '',
      'javascript:alert(1)',
      'file:///replay/import/native-7',
      '/room/native-7',
      '/replay/import/native-7/more',
      '/replay/import/native%2F7',
      '/replay/import/%',
    ]) {
      expect(parseReplayLocation(input)).toBeNull()
    }
  })
})
