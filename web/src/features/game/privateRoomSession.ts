type PrivateRoomContext = {
  tableId: string
}

const PRIVATE_ROOM_CONTEXT_KEY = 'mahjong_private_room_context_v2'

function storage(): Storage | null {
  return typeof window === 'undefined' ? null : window.sessionStorage
}

export function loadPrivateRoomSession(tableId?: string): PrivateRoomContext | null {
  const store = storage()
  if (!store) return null
  try {
    const value = JSON.parse(store.getItem(PRIVATE_ROOM_CONTEXT_KEY) ?? 'null') as PrivateRoomContext | null
    if (!value?.tableId || (tableId && value.tableId !== tableId)) return null
    return value
  } catch {
    store.removeItem(PRIVATE_ROOM_CONTEXT_KEY)
    return null
  }
}

export function savePrivateRoomSession(context: PrivateRoomContext) {
  storage()?.setItem(PRIVATE_ROOM_CONTEXT_KEY, JSON.stringify(context))
}

export function clearPrivateRoomSession(tableId?: string) {
  const store = storage()
  if (!store) return
  if (!tableId || loadPrivateRoomSession()?.tableId === tableId) store.removeItem(PRIVATE_ROOM_CONTEXT_KEY)
}
