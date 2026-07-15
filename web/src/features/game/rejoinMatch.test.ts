import { describe, expect, it } from 'vitest'
import {
  parseLeftMatchMarker,
  serializeLeftMatchMarker,
} from './rejoinMatch'

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
