const rawMatchID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/

function validMatchID(value: string): string | null {
  if (!rawMatchID.test(value)) return null
  return value
}

export function parseReplayReference(input: string): string | null {
  const value = input.trim()
  if (!value) return null
  if (validMatchID(value)) return value

  let url: URL
  try {
    url = new URL(value, 'https://club.invalid')
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  const match = url.pathname.match(/^\/replay\/([^/]+)\/?$/)
  if (!match) return null
  try {
    return validMatchID(decodeURIComponent(match[1]))
  } catch {
    return null
  }
}

/** Resolve pasted bookmarks to our local routes, retaining only viewer state. */
export function parseReplayLocation(input: string): string | null {
  const value = input.trim()
  if (!value) return null
  if (validMatchID(value)) return `/replay/${encodeURIComponent(value)}`

  let url: URL
  try {
    url = new URL(value, 'https://club.invalid')
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  const match = url.pathname.match(/^\/replay\/(import\/)?([^/]+)\/?$/)
  if (!match) return null
  let id: string | null
  try {
    id = validMatchID(decodeURIComponent(match[2]))
  } catch {
    return null
  }
  if (!id) return null
  const search = new URLSearchParams()
  for (const key of ['round', 'cursor', 'seat', 'study', 'advice', 'decision']) {
    const state = url.searchParams.get(key)
    if (state !== null) search.set(key, state)
  }
  const query = search.toString()
  return `/replay/${match[1] ?? ''}${encodeURIComponent(id)}${query ? `?${query}` : ''}`
}
