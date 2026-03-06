function stripTrailingSlash(value: string): string {
  return value.endsWith('/') ? value.slice(0, -1) : value
}

function readEnv(name: string): string | null {
  const value = import.meta.env[name]
  if (typeof value !== 'string') {
    return null
  }

  const trimmed = value.trim()
  return trimmed ? stripTrailingSlash(trimmed) : null
}

const apiBaseUrl = readEnv('VITE_API_BASE_URL')
const wsBaseUrl = readEnv('VITE_WS_BASE_URL')

export function getApiUrl(path: string): string {
  return apiBaseUrl ? `${apiBaseUrl}${path}` : path
}

export function getWebSocketUrl(path: string): string {
  if (wsBaseUrl) {
    return `${wsBaseUrl}${path}`
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}
