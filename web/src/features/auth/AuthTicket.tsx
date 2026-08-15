import { useState, type FormEvent } from 'react'
import { Button, Field, Note, ToolsRow } from '../../theme'
import { useAuth } from '../../contexts/AuthContext'
import { authenticatedFetch, authRequestBody, type AuthMode, type AuthPayload } from './authClient'
import { useI18n } from '../../i18n/I18nContext'

export default function AuthTicket({ onAuthenticated, intent = 'continue' }: { onAuthenticated?: (payload: AuthPayload) => void; intent?: 'continue' | 'join table' }) {
  const { completeAuth } = useAuth()
  const { t } = useI18n()
  const [mode, setMode] = useState<AuthMode>('login')
  const [identifier, setIdentifier] = useState('')
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
        body: JSON.stringify(authRequestBody(mode, { identifier, username, password })),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || t('auth.failed'))
      completeAuth(data as AuthPayload)
      onAuthenticated?.(data as AuthPayload)
    } catch (err) {
      setError(err instanceof TypeError ? t('auth.offline') : err instanceof Error ? err.message : t('auth.failed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="auth-ticket" onSubmit={submit}>
      <div className="auth-ticket__tabs" aria-label={t('auth.accountMode')} role="tablist">
        <button type="button" role="tab" aria-selected={mode === 'login'} className={mode === 'login' ? 'is-active' : ''} onClick={() => setMode('login')}>{t('auth.signIn')}</button>
        <button type="button" role="tab" aria-selected={mode === 'register'} className={mode === 'register' ? 'is-active' : ''} onClick={() => setMode('register')}>{t('auth.createAccount')}</button>
      </div>
      {mode === 'login' ? (
        <Field label={t('auth.identifier')} value={identifier} onChange={event => setIdentifier(event.target.value)} autoComplete="username" />
      ) : (
        <>
          <Field label={t('auth.username')} value={username} onChange={event => setUsername(event.target.value)} autoComplete="username" />
          <Note>{t('auth.usernameHint')}</Note>
        </>
      )}
      <Field label={t('auth.password')} type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} />
      {error && <Note tone="error">{error}</Note>}
      <ToolsRow>
        <Button type="submit" variant="primary" disabled={submitting || !password || (mode === 'login' ? !identifier : !username)}>
          {submitting
            ? t('auth.opening')
            : mode === 'login'
              ? t('auth.signInContinue', { intent: t(intent === 'join table' ? 'auth.joinTable' : 'auth.continue') })
              : t('auth.createContinue', { intent: t(intent === 'join table' ? 'auth.joinTable' : 'auth.continue') })}
        </Button>
      </ToolsRow>
    </form>
  )
}
