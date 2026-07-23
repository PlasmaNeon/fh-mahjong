import { getApiUrl } from '../../config'

export type AuthUser = {
  id: number
  // null when the account has no address on file. Email is optional and set
  // in the profile, never at registration.
  email: string | null
  username: string
  rating: number
}

export type AuthPayload = {
  user: AuthUser
  csrfToken: string
}

export type AuthMode = 'login' | 'register'

export type AuthFields = {
  identifier: string
  username: string
  password: string
}

// Registration deliberately sends no email key at all: accounts are created
// from a username and password, and an address is added later in the profile.
export function authRequestBody(mode: AuthMode, fields: AuthFields) {
  return mode === 'register'
    ? { username: fields.username, password: fields.password }
    : { identifier: fields.identifier, password: fields.password }
}

type StorageWriter = Pick<Storage, 'removeItem'>

export function safeReturnTo(value: string | null | undefined, fallback = '/play'): string {
  if (!value || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return fallback
  try {
    const parsed = new URL(value, 'https://club.invalid')
    if (parsed.origin !== 'https://club.invalid') return fallback
    parsed.searchParams.delete('token')
    return `${parsed.pathname}${parsed.search}${parsed.hash}`
  } catch {
    return fallback
  }
}

export function authRequestInit(method: string, csrfToken?: string, init: RequestInit = {}): RequestInit {
  const upperMethod = method.toUpperCase()
  const headers = new Headers(init.headers)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(upperMethod) && csrfToken) {
    headers.set('X-CSRF-Token', csrfToken)
  }
  return { ...init, method: upperMethod, credentials: 'include', headers }
}

export async function authenticatedFetch(path: string, method: string, csrfToken?: string, init: RequestInit = {}) {
  return fetch(getApiUrl(path), authRequestInit(method, csrfToken, init))
}

export function clearLegacyCredentials(local: StorageWriter, session: StorageWriter) {
  local.removeItem('fh_token')
  local.removeItem('mahjong_private_room_session_v1')
  session.removeItem('mahjong_private_room_session_v1')
}

export function stripLegacyTokenParameter(href: string): string {
  const url = new URL(href)
  url.searchParams.delete('token')
  const query = url.searchParams.toString()
  return `${url.pathname}${query ? `?${query}` : ''}${url.hash}`
}
