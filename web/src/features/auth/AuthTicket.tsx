import { useState } from 'react'
import { getApiUrl } from '../../config'
import { Button, Field, Note, ToolsRow } from '../../theme'

type Mode = 'login' | 'register'

export default function AuthTicket({ onAuthenticated }: { onAuthenticated: (token: string) => void }) {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const submit = async () => {
    setError('')
    setSubmitting(true)
    try {
      const isRegister = mode === 'register'
      const response = await fetch(getApiUrl(isRegister ? '/api/v1/auth/register' : '/api/v1/auth/login'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(isRegister ? { email, password, displayName } : { email, password }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || 'Authentication failed')
      localStorage.setItem('fh_token', data.token)
      onAuthenticated(data.token)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-ticket">
      <div className="auth-ticket__tabs" aria-label="Account mode">
        <button className={mode === 'login' ? 'is-active' : ''} onClick={() => setMode('login')}>Sign in</button>
        <button className={mode === 'register' ? 'is-active' : ''} onClick={() => setMode('register')}>Create account</button>
      </div>
      <Field label="Email" type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" />
      {mode === 'register' && <Field label="Display name" value={displayName} onChange={event => setDisplayName(event.target.value)} autoComplete="nickname" />}
      <Field label="Password" type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
      {error && <Note tone="error">{error}</Note>}
      <ToolsRow>
        <Button variant="primary" onClick={submit} disabled={submitting || !email || !password || (mode === 'register' && !displayName)}>
          {submitting ? 'Opening the club…' : mode === 'login' ? 'Sign in and continue' : 'Create account and continue'}
        </Button>
      </ToolsRow>
    </div>
  )
}
