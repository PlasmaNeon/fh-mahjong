import { describe, expect, it } from 'vitest'
import { authRequestInit, clearLegacyCredentials, safeReturnTo, stripLegacyTokenParameter } from './authClient'

describe('safeReturnTo', () => {
  it('keeps internal application paths', () => {
    expect(safeReturnTo('/room/rain1234?seat=east')).toBe('/room/rain1234?seat=east')
    expect(safeReturnTo('/room/rain1234?token=legacy-secret&seat=east')).toBe('/room/rain1234?seat=east')
  })

  it('rejects absolute and protocol-relative redirects', () => {
    expect(safeReturnTo('https://evil.example')).toBe('/play')
    expect(safeReturnTo('//evil.example/path')).toBe('/play')
    expect(safeReturnTo('javascript:alert(1)')).toBe('/play')
  })
})

describe('authRequestInit', () => {
  it('always includes browser credentials and attaches CSRF to mutations', () => {
    expect(authRequestInit('GET', 'csrf-value')).toMatchObject({ credentials: 'include', method: 'GET' })
    const mutation = authRequestInit('POST', 'csrf-value')
    expect(mutation).toMatchObject({ credentials: 'include', method: 'POST' })
    expect(new Headers(mutation.headers).get('X-CSRF-Token')).toBe('csrf-value')
  })
})

describe('clearLegacyCredentials', () => {
  it('removes JWT and private-room credential keys', () => {
    const removed: string[] = []
    const store = { removeItem: (key: string) => removed.push(key) }
    clearLegacyCredentials(store, store)
    expect(removed).toContain('fh_token')
    expect(removed).toContain('mahjong_private_room_session_v1')
  })
})

describe('stripLegacyTokenParameter', () => {
  it('removes old room credentials while preserving other navigation state', () => {
    expect(stripLegacyTokenParameter('https://club.example/room/rain1234?token=secret&seat=east#invite'))
      .toBe('/room/rain1234?seat=east#invite')
  })
})
