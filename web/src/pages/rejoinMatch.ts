export type LeftMatchMarker = {
  roomId: string
  matchId: string
}

const LEFT_MATCH_KEY = 'mahjong_left_match_v1'

// ---- pure helpers (unit-tested) -------------------------------------------

export function buildRejoinLink(origin: string, roomId: string, token: string): string {
  const base = origin.replace(/\/+$/, '')
  return `${base}/room/${encodeURIComponent(roomId)}?token=${encodeURIComponent(token)}`
}

export function extractRejoinToken(search: string): string | null {
  const params = new URLSearchParams(search)
  const token = params.get('token')
  return token && token.length > 0 ? token : null
}

export function stripTokenFromUrl(href: string): string {
  const url = new URL(href)
  url.searchParams.delete('token')
  const query = url.searchParams.toString()
  return `${url.origin}${url.pathname}${query ? `?${query}` : ''}${url.hash}`
}

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
