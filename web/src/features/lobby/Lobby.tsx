import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { useGameState } from '../../contexts/GameContext'
import { Button, ClubShell, Note, Section, Toggle, ButtonRow } from '../../theme'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../auth/authRouteState'
import { consumePlayIntent, rememberPlayIntent } from './playIntent'
import { useI18n } from '../../i18n/I18nContext'
import { errorMessage, readJsonBody } from '../../utils/apiJson'
import { invitationRoomPath } from './invitationLink'

type Ruleset = 'fenghua' | 'chongci-fh'

export default function Lobby() {
  const [queueState, setQueueState] = useState<'idle' | 'joining' | 'queued' | 'leaving'>('idle')
  const [ruleset, setRuleset] = useState<Ruleset>('fenghua')
  const [showModes, setShowModes] = useState(false)
  const [error, setError] = useState('')
  const [invitation, setInvitation] = useState('')
  const [invitationError, setInvitationError] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { isConnected, connect } = useSocket()
  const { gameState } = useGameState()
  const { status: authStatus, apiFetch } = useAuth()
  const { t } = useI18n()

  useEffect(() => {
    if (authStatus === 'authenticated' && !isConnected) connect()
    if (gameState?.matchId) navigate(`/match/${gameState.matchId}`)
  }, [authStatus, isConnected, gameState, navigate, connect])

  const joinQueue = async () => {
    if (authStatus === 'offline') { setError(t('auth.offline')); return }
    if (authStatus !== 'authenticated') {
      if (typeof window !== 'undefined') rememberPlayIntent(window.sessionStorage, 'quick-match')
      const state: AuthRouteState = { backgroundLocation: location, optionalAuth: true, cancelIntent: 'quick-match' }
      navigate(`/login?returnTo=${encodeURIComponent(location.pathname === '/' ? '/' : '/play')}`, { state })
      return
    }
    setError('')
    setQueueState('joining')
    try {
      const response = await apiFetch('/api/v1/matchmaking/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ruleset }),
      })
      const data = await readJsonBody(response)
      if (!response.ok) throw new Error(errorMessage(data, t('lobby.joinFailed')))
      setQueueState('queued')
    } catch (err) {
      setError(err instanceof TypeError ? t('auth.offline') : err instanceof Error ? err.message : t('lobby.contactFailed'))
      setQueueState('idle')
    }
  }

  useEffect(() => {
    if (authStatus === 'authenticated' && typeof window !== 'undefined' && consumePlayIntent(window.sessionStorage) === 'quick-match') void joinQueue()
  }, [authStatus])

  const cancelQueue = async () => {
    if (authStatus !== 'authenticated') return
    setError('')
    setQueueState('leaving')
    try {
      const response = await apiFetch('/api/v1/matchmaking/leave', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ruleset }),
      })
      const data = await readJsonBody(response)
      if (response.status === 409) {
        setError(errorMessage(data, t('lobby.forming')))
        setQueueState('queued')
        return
      }
      if (!response.ok) throw new Error(errorMessage(data, t('lobby.cancelFailed')))
      setQueueState('idle')
    } catch (err) {
      setError(err instanceof Error ? err.message : t('lobby.cancelFailed'))
      setQueueState('queued')
    }
  }

  const searching = queueState !== 'idle'

  useEffect(() => {
    if (!searching) return
    const guard = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', guard)
    return () => window.removeEventListener('beforeunload', guard)
  }, [searching])

  return (
    <ClubShell title={t('nav.play')} navigationLocked={searching}>
      <div className="direct-play">
        <h1 className="direct-tools-sr-only">{t('nav.play')}</h1>
        {error && <Note tone="error">{error}</Note>}

        {searching ? (
          <Section title={t('lobby.listening')} subtitle={t(ruleset === 'fenghua' ? 'lobby.classicTable' : 'lobby.chongciTable')}>
            <Note>{t(queueState === 'joining' ? 'lobby.joining' : queueState === 'leaving' ? 'lobby.leaving' : 'lobby.searching')}</Note>
            <ButtonRow><Button onClick={cancelQueue} disabled={queueState !== 'queued'}>{t('lobby.cancel')}</Button></ButtonRow>
          </Section>
        ) : (
          <div className="direct-play-grid">
            <Section title={t('lobby.quick')} subtitle={t('lobby.quickHelp')}>
              <Button variant="primary" onClick={() => void joinQueue()} disabled={authStatus === 'authenticated' && !isConnected}>{t('lobby.find')}</Button>
              {authStatus === 'authenticated' && !isConnected && <Note>{t('lobby.connecting')}</Note>}
              <button type="button" className="disclosure-button" onClick={() => setShowModes(value => !value)} aria-expanded={showModes}>{t('lobby.mode')} · {t(ruleset === 'fenghua' ? 'lobby.classic' : 'lobby.chongci')} {showModes ? '−' : '+'}</button>
              {showModes && <Toggle value={ruleset} onChange={value => setRuleset(value as Ruleset)} options={[{ value: 'fenghua', label: t('lobby.classic') }, { value: 'chongci-fh', label: t('lobby.chongci') }]} />}
            </Section>
            <Section title={t('lobby.private')} subtitle={t('lobby.privateHelp')}>
              <Button onClick={() => navigate('/room/new')}>{t('lobby.createPrivate')}</Button>
              <form className="direct-invitation" onSubmit={event => {
                event.preventDefault()
                const path = invitationRoomPath(invitation, window.location.origin)
                if (path) navigate(path)
                else setInvitationError(true)
              }}>
                <label htmlFor="invitation-link">{t('lobby.invitation')}</label>
                <div>
                  <input id="invitation-link" className="ldg-input" type="text" value={invitation} placeholder={t('lobby.invitationPlaceholder')} onChange={event => { setInvitation(event.target.value); setInvitationError(false) }} aria-invalid={Boolean(invitationError)} aria-describedby={invitationError ? 'invitation-error' : undefined} />
                  <Button type="submit">{t('lobby.joinInvitation')}</Button>
                </div>
                {invitationError && <div id="invitation-error"><Note tone="error">{t('lobby.invalidInvitation')}</Note></div>}
              </form>
            </Section>
          </div>
        )}
      </div>
    </ClubShell>
  )
}
