import { describe, expect, it } from 'vitest'
import { roomActiveRedirectMatchId } from './roomNavigation'

describe('roomActiveRedirectMatchId', () => {
  it('redirects to the match when THIS room reports an active match', () => {
    expect(
      roomActiveRedirectMatchId({ status: 'active', matchId: 'M1' }, null),
    ).toBe('M1')
  })

  it('does NOT redirect for a still-configuring room (the bug case)', () => {
    // A configuring room comes back as a PrivateTableState with no `status`.
    // Previously the page redirected on stale global game state, dragging
    // distinct room links into the same game. It must stay put now.
    const configuring = { tableId: 'beta', state: 'configuring', matchId: '' }
    expect(roomActiveRedirectMatchId(configuring as any, null)).toBeNull()
  })

  it('does NOT redirect when the response is missing or has no matchId', () => {
    expect(roomActiveRedirectMatchId(null, null)).toBeNull()
    expect(roomActiveRedirectMatchId({ status: 'active' }, null)).toBeNull()
    expect(roomActiveRedirectMatchId({ status: 'active', matchId: '' }, null)).toBeNull()
  })

  it('does NOT redirect when the player left THIS room (show Rejoin)', () => {
    expect(
      roomActiveRedirectMatchId(
        { status: 'active', matchId: 'M1' },
        { roomId: 'alpha', matchId: 'M1' },
        'alpha',
      ),
    ).toBeNull()
  })

  it('STILL redirects when a leave marker belongs to a different room', () => {
    // A marker left in room alpha must not suppress beta's own active match.
    expect(
      roomActiveRedirectMatchId(
        { status: 'active', matchId: 'M2' },
        { roomId: 'alpha', matchId: 'M1' },
        'beta',
      ),
    ).toBe('M2')
  })
})
