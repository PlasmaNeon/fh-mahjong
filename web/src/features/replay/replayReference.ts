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
