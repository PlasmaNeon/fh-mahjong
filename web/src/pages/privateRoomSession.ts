type PrivateRoomSession = {
  tableId: string
  token: string
  username: string
}

const PRIVATE_ROOM_SESSION_KEY = 'mahjong_private_room_session_v1'

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null
  }

  return window.sessionStorage
}

function getLegacyLocalStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null
  }

  return window.localStorage
}

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
  const storage = getSessionStorage()
  if (!storage) {
    return null
  }

  const raw = storage.getItem(PRIVATE_ROOM_SESSION_KEY)
  if (!raw) {
    return null
  }

  try {
    const session = JSON.parse(raw) as PrivateRoomSession
    if (!session?.token || !session?.username || !session?.tableId) {
      storage.removeItem(PRIVATE_ROOM_SESSION_KEY)
      return null
    }

    if (isTokenExpired(session.token)) {
      storage.removeItem(PRIVATE_ROOM_SESSION_KEY)
      return null
    }

    if (tableId && session.tableId !== tableId) {
      return null
    }

    return session
  } catch {
    storage.removeItem(PRIVATE_ROOM_SESSION_KEY)
    return null
  }
}

export function savePrivateRoomSession(session: PrivateRoomSession) {
  const sessionStorage = getSessionStorage()
  if (!sessionStorage) {
    return
  }

  sessionStorage.setItem(PRIVATE_ROOM_SESSION_KEY, JSON.stringify(session))
  getLegacyLocalStorage()?.removeItem(PRIVATE_ROOM_SESSION_KEY)
}

export function clearPrivateRoomSession(tableId?: string) {
  const sessionStorage = getSessionStorage()
  if (!sessionStorage) {
    return
  }

  if (!tableId) {
    sessionStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
    getLegacyLocalStorage()?.removeItem(PRIVATE_ROOM_SESSION_KEY)
    return
  }

  const existing = loadPrivateRoomSession()
  if (existing?.tableId === tableId) {
    sessionStorage.removeItem(PRIVATE_ROOM_SESSION_KEY)
  }

  getLegacyLocalStorage()?.removeItem(PRIVATE_ROOM_SESSION_KEY)
}

export function getPrivateRoomToken(): string | null {
  return loadPrivateRoomSession()?.token ?? null
}
