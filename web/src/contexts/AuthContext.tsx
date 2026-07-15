import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authenticatedFetch, clearLegacyCredentials, stripLegacyTokenParameter, type AuthPayload, type AuthUser } from '../features/auth/authClient'

type AuthStatus = 'loading' | 'authenticated' | 'anonymous' | 'offline'

type AuthContextValue = {
  status: AuthStatus
  user: AuthUser | null
  csrfToken: string
  completeAuth: (payload: AuthPayload) => void
  refreshSession: () => Promise<boolean>
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>('loading')
  const [user, setUser] = useState<AuthUser | null>(null)
  const [csrfToken, setCSRFToken] = useState('')

  const completeAuth = useCallback((payload: AuthPayload) => {
    setUser(payload.user)
    setCSRFToken(payload.csrfToken)
    setStatus('authenticated')
  }, [])

  const becomeAnonymous = useCallback(() => {
    setUser(null)
    setCSRFToken('')
    setStatus('anonymous')
  }, [])

  const becomeOffline = useCallback(() => {
    setUser(null)
    setCSRFToken('')
    setStatus('offline')
  }, [])

  const refreshSession = useCallback(async () => {
    try {
      const response = await authenticatedFetch('/api/v1/auth/session', 'GET')
      if (response.status === 401) {
        becomeAnonymous()
        return false
      }
      if (!response.ok) {
        becomeOffline()
        return false
      }
      completeAuth(await response.json() as AuthPayload)
      return true
    } catch {
      becomeOffline()
      return false
    }
  }, [becomeAnonymous, becomeOffline, completeAuth])

  useEffect(() => {
    if (typeof window !== 'undefined') {
      clearLegacyCredentials(window.localStorage, window.sessionStorage)
      const cleanedLocation = stripLegacyTokenParameter(window.location.href)
      const currentLocation = `${window.location.pathname}${window.location.search}${window.location.hash}`
      if (cleanedLocation !== currentLocation) window.history.replaceState(window.history.state, '', cleanedLocation)
    }
    void refreshSession()
  }, [refreshSession])

  const apiFetch = useCallback(async (path: string, init: RequestInit = {}) => {
    const response = await authenticatedFetch(path, init.method ?? 'GET', csrfToken, init)
    if (response.status === 401) becomeAnonymous()
    return response
  }, [becomeAnonymous, csrfToken])

  const logout = useCallback(async () => {
    if (status === 'authenticated') {
      const response = await authenticatedFetch('/api/v1/auth/session', 'DELETE', csrfToken)
      if (!response.ok && response.status !== 401) throw new Error('Could not sign out. Check your connection and try again.')
    }
    becomeAnonymous()
  }, [becomeAnonymous, csrfToken, status])

  const value = useMemo(() => ({ status, user, csrfToken, completeAuth, refreshSession, apiFetch, logout }), [status, user, csrfToken, completeAuth, refreshSession, apiFetch, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
