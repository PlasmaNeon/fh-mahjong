import { describe, expect, it } from 'vitest'
import { invitationRoomPath } from './invitationLink'

const origin = 'https://mahjong.example'

describe('invitationRoomPath', () => {
  it('accepts shared same-origin invitations and local room paths', () => {
    expect(invitationRoomPath(' https://mahjong.example/room/table-123 ', origin)).toBe('/room/table-123')
    expect(invitationRoomPath('/room/table_123/', origin)).toBe('/room/table_123')
  })

  it.each([
    '', 'table-123', '/room/new', '/room/new/', '/play', '/room/',
    'https://other.example/room/table-123', '//other.example/room/table-123',
    'javascript:alert(1)', 'https://user:secret@mahjong.example/room/table-123',
    '/room/table-123?redirect=https://other.example', '/room/table-123#play',
    '/room/table%2f123', '/room/table-123/extra', '/room/../new',
  ])('rejects non-invitations: %s', input => {
    expect(invitationRoomPath(input, origin)).toBeNull()
  })
})
