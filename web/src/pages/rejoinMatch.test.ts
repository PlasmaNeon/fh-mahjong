import { describe, expect, it } from 'vitest'
import {
  buildRejoinLink,
  extractRejoinToken,
  stripTokenFromUrl,
  parseLeftMatchMarker,
  serializeLeftMatchMarker,
} from './rejoinMatch'

describe('buildRejoinLink', () => {
  it('builds a room URL carrying the token', () => {
    expect(buildRejoinLink('https://app.test', 'ROOM42', 'jwt.abc')).toBe(
      'https://app.test/room/ROOM42?token=jwt.abc',
    )
  })

  it('url-encodes the room id and token', () => {
    expect(buildRejoinLink('https://app.test', 'a b', 'x/y')).toBe(
      'https://app.test/room/a%20b?token=x%2Fy',
    )
  })

  it('drops a trailing slash on the origin', () => {
    expect(buildRejoinLink('https://app.test/', 'R', 't')).toBe(
      'https://app.test/room/R?token=t',
    )
  })
})

describe('extractRejoinToken', () => {
  it('reads the token query param', () => {
    expect(extractRejoinToken('?token=jwt.abc')).toBe('jwt.abc')
  })

  it('returns null when there is no token', () => {
    expect(extractRejoinToken('?foo=bar')).toBeNull()
    expect(extractRejoinToken('')).toBeNull()
  })

  it('returns null for an empty token value', () => {
    expect(extractRejoinToken('?token=')).toBeNull()
  })
})

describe('stripTokenFromUrl', () => {
  it('removes the token param but keeps the path and other params', () => {
    expect(stripTokenFromUrl('https://app.test/room/R?token=jwt.abc&x=1')).toBe(
      'https://app.test/room/R?x=1',
    )
  })

  it('leaves no trailing question mark when token was the only param', () => {
    expect(stripTokenFromUrl('https://app.test/room/R?token=jwt.abc')).toBe(
      'https://app.test/room/R',
    )
  })

  it('is a no-op when there is no token param', () => {
    expect(stripTokenFromUrl('https://app.test/room/R')).toBe(
      'https://app.test/room/R',
    )
  })
})

describe('left-match marker serialization', () => {
  it('round-trips a marker', () => {
    const raw = serializeLeftMatchMarker({ roomId: 'R', matchId: 'M' })
    expect(parseLeftMatchMarker(raw)).toEqual({ roomId: 'R', matchId: 'M' })
  })

  it('returns null for null / malformed / incomplete input', () => {
    expect(parseLeftMatchMarker(null)).toBeNull()
    expect(parseLeftMatchMarker('not json')).toBeNull()
    expect(parseLeftMatchMarker('{"roomId":"R"}')).toBeNull()
    expect(parseLeftMatchMarker('{"matchId":"M"}')).toBeNull()
  })
})
