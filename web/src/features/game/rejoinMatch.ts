export type LeftMatchMarker = {
  roomId: string
  matchId: string
}

const LEFT_MATCH_KEY = 'mahjong_left_match_v1'

export function serializeLeftMatchMarker(marker: LeftMatchMarker): string {
  return JSON.stringify({ roomId: marker.roomId, matchId: marker.matchId })
}

export function parseLeftMatchMarker(raw: string | null): LeftMatchMarker | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<LeftMatchMarker>
    if (typeof parsed.roomId === 'string' && typeof parsed.matchId === 'string') {
      return { roomId: parsed.roomId, matchId: parsed.matchId }
    }
    return null
  } catch {
    return null
  }
}

// ---- sessionStorage wrappers (guarded, mirror privateRoomSession.ts) -------

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.sessionStorage
}

export function saveLeftMatchMarker(marker: LeftMatchMarker): void {
  getSessionStorage()?.setItem(LEFT_MATCH_KEY, serializeLeftMatchMarker(marker))
}

export function loadLeftMatchMarker(): LeftMatchMarker | null {
  const storage = getSessionStorage()
  if (!storage) return null
  return parseLeftMatchMarker(storage.getItem(LEFT_MATCH_KEY))
}

export function clearLeftMatchMarker(): void {
  getSessionStorage()?.removeItem(LEFT_MATCH_KEY)
}
