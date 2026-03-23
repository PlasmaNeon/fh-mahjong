type PrivateRoomSession = {
  tableId: string
  token: string
  username: string
}

const PRIVATE_ROOM_SESSION_KEY = 'mahjong_private_room_session_v1'

function decodeTokenPayload(token: string): Record<string, unknown> | null {
  const parts = token.split('.')
  if (parts.length < 2) {
    return null
  }

  try {
    const normalized = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    return JSON.parse(window.atob(padded))
  } catch {
    return null
  }
}

function isTokenExpired(token: string): boolean {
  const payload = decodeTokenPayload(token)
  if (!payload || typeof payload.exp !== 'number') {
    return true
  }

  return payload.exp * 1000 <= Date.now()
}

export function loadPrivateRoomSession(tableId?: string): PrivateRoomSession | null {
  if (typeof window === 'undefined') {
    return null
  }

  const raw = window.localStorage.getItem(PRIVATE_ROOM_SESSION_KEY)
  if (!raw) {
    return null
  }

  try {
    const session = JSON.parse(raw) as PrivateRoomSession
    if (!session?.token || !session?.username || !session?.tableId) {
      window.localStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
      return null
    }

    if (isTokenExpired(session.token)) {
      window.localStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
      return null
    }

    if (tableId && session.tableId !== tableId) {
      return null
    }

    return session
  } catch {
    window.localStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
    return null
  }
}

export function savePrivateRoomSession(session: PrivateRoomSession) {
  if (typeof window === 'undefined') {
    return
  }

  window.localStorage.setItem(PRIVATE_ROOM_SESSION_KEY, JSON.stringify(session))
}

export function clearPrivateRoomSession(tableId?: string) {
  if (typeof window === 'undefined') {
    return
  }

  if (!tableId) {
    window.localStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
    return
  }

  const existing = loadPrivateRoomSession()
  if (existing?.tableId === tableId) {
    window.localStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
  }
}

export function getPrivateRoomToken(): string | null {
  return loadPrivateRoomSession()?.token ?? null
}
