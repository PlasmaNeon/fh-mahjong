import { useState, type FormEvent } from 'react'
import { Button, Field, Note, ToolsRow } from '../../theme'
import { useAuth } from '../../contexts/AuthContext'
import { authenticatedFetch, type AuthPayload } from './authClient'

type Mode = 'login' | 'register'

export default function AuthTicket({ onAuthenticated, intent = 'continue' }: { onAuthenticated?: (payload: AuthPayload) => void; intent?: 'continue' | 'join table' }) {
  const { completeAuth } = useAuth()
  const [mode, setMode] = useState<Mode>('login')
  const [identifier, setIdentifier] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [username, setUsername] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event?: FormEvent) => {
    event?.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const isRegister = mode === 'register'
      const response = await authenticatedFetch(isRegister ? '/api/v1/auth/register' : '/api/v1/auth/login', 'POST', undefined, {
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isRegister ? { email, password, username } : { identifier, password }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || 'Authentication failed')
      completeAuth(data as AuthPayload)
      onAuthenticated?.(data as AuthPayload)
    } catch (err) {
      setError(err instanceof TypeError ? 'The club is offline. Check your connection and try again.' : err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="auth-ticket" onSubmit={submit}>
      <div className="auth-ticket__tabs" aria-label="Account mode" role="tablist">
        <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'is-active' : ''} onClick={() => setMode('login')}>Sign in</button>
        <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'is-active' : ''} onClick={() => setMode('register')}>Create account</button>
      </div>
      {mode === 'login' ? (
        <Field label="Username or email" value={identifier} onChange={event => setIdentifier(event.target.value)} autoComplete="username" />
      ) : (
        <>
          <Field label="Username" value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
          <Field label="Email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" style={{ marginTop: '0.85rem' }} />
          <Note>2–30 letters or numbers. Spaces, hyphens, and underscores are welcome; @ is reserved for email.</Note>
        </>
      )}
      <Field label="Password" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
      {error && <Note tone="error">{error}</Note>}
      <ToolsRow>
        <Button type="submit" variant="primary" disabled={submitting || !password || (mode === 'login' ? !identifier : !email || !username)}>
          {submitting ? 'Opening the club…' : mode === 'login' ? `Sign in and ${intent}` : `Create account and ${intent}`}
        </Button>
      </ToolsRow>
    </form>
  )
}
