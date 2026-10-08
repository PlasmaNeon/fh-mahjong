/** Accept only a room route on this app's origin; never navigate arbitrary URLs. */
export function invitationRoomPath(value: string, origin: string): string | null {
  const input = value.trim()
  if (!input || (!input.startsWith('/room/') && !/^https?:\/\//i.test(input))) return null
  try {
    const url = new URL(input, origin)
    if (url.origin !== origin || url.username || url.password || url.search || url.hash) return null
    if (!/^\/room\/[a-zA-Z0-9_-]+\/?$/.test(url.pathname) || url.pathname.replace(/\/$/, '') === '/room/new') return null
    return url.pathname.replace(/\/$/, '')
  } catch {
    return null
  }
}
