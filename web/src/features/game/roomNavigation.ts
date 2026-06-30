import type { LeftMatchMarker } from './rejoinMatch'

// The backend response for GET/POST on a private room. A live match for THIS
// room comes back as { status: 'active', matchId }; a still-configuring room
// comes back as the full PrivateTableState (no `status` field).
export type RoomResponse = {
  status?: string
  matchId?: string
} | null

// roomActiveRedirectMatchId decides whether viewing /room/:roomId should
// redirect into a live match, using ONLY the room-scoped backend response for
// that specific room.
//
// This is the fix for "different room links all open the same game": the
// waiting room must never redirect based on globally-shared game state left
// over from a previously-opened room. It redirects only when the backend says
// THIS room's match is active and the player belongs to it.
//
// `currentRoomId` scopes the left-match marker: an intentional-leave marker
// suppresses the redirect only for the room it actually belongs to. The marker
// is stored globally, so without this a leave in one room would wrongly
// suppress (or show the Rejoin banner for) a different room.
//
// Returns the matchId to navigate to, or null to stay on the waiting room.
export function roomActiveRedirectMatchId(
  resp: RoomResponse,
  leftMarker: LeftMatchMarker | null,
  currentRoomId?: string,
): string | null {
  // The player intentionally left THIS room's match — show the Rejoin banner
  // instead of bouncing them straight back in. A marker for a different room
  // is ignored here.
  const leftThisRoom =
    !!leftMarker &&
    (currentRoomId === undefined || leftMarker.roomId === currentRoomId)
  if (leftThisRoom) return null
  if (
    resp &&
    resp.status === 'active' &&
    typeof resp.matchId === 'string' &&
    resp.matchId.length > 0
  ) {
    return resp.matchId
  }
  return null
}
