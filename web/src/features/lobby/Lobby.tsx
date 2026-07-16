import { useEffect, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { useGameState } from '../../contexts/GameContext'
import { Button, Card, ClubShell, Note, PageHeader, Section, Toggle, ToolsRow } from '../../theme'
import { useAuth } from '../../contexts/AuthContext'
import type { AuthRouteState } from '../auth/authModal'
import { consumePlayIntent, rememberPlayIntent } from './navigation'

type Ruleset = 'fenghua' | 'chongci-fh'

export default function Lobby() {
  const [queueState, setQueueState] = useState<'idle' | 'joining' | 'queued' | 'leaving'>('idle')
  const [ruleset, setRuleset] = useState<Ruleset>('fenghua')
  const [showModes, setShowModes] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  const { isConnected, connect } = useSocket()
  const { gameState } = useGameState()
  const { status: authStatus, apiFetch } = useAuth()

  useEffect(() => {
    if (authStatus === 'authenticated' && !isConnected) connect()
    if (gameState?.matchId) navigate(`/match/${gameState.matchId}`)
  }, [authStatus, isConnected, gameState, navigate, connect])

  const joinQueue = async () => {
    if (authStatus === 'offline') { setError('The club is offline. Check your connection and try again.'); return }
    if (authStatus !== 'authenticated') {
      if (typeof window !== 'undefined') rememberPlayIntent(window.sessionStorage, 'quick-match')
      const state: AuthRouteState = { backgroundLocation: location, optionalAuth: true, cancelIntent: 'quick-match' }
      navigate(`/login?returnTo=${encodeURIComponent('/play')}`, { state })
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
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || 'Failed to join queue')
      setQueueState('queued')
    } catch (err) {
      setError(err instanceof TypeError ? 'The club is offline. Check your connection and try again.' : err instanceof Error ? err.message : 'Error contacting matchmaker')
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
      const data = await response.json().catch(() => ({}))
      if (response.status === 409) {
        setError(data.error || 'Your table is already forming. Stay connected.')
        setQueueState('queued')
        return
      }
      if (!response.ok) throw new Error(data.error || 'Could not cancel search')
      setQueueState('idle')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not cancel search')
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
    <ClubShell title="Play" navigationLocked={searching}>
      <Card>
        <PageHeader title="Choose a table" subtitle="今晚玩一圈 · one clear next move" />
        {error && <Note tone="error">{error}</Note>}

        {searching ? (
          <Section title="Listening for players" subtitle={ruleset === 'fenghua' ? 'Fenghua · Classic table' : 'Fenghua · Chongci table'}>
            <div className="queue-compass" aria-hidden="true"><span>東</span></div>
            <Note>{queueState === 'joining' ? 'Joining the queue…' : queueState === 'leaving' ? 'Leaving the queue safely…' : 'Searching for three players. Keep this page open.'}</Note>
            <ToolsRow><Button onClick={cancelQueue} disabled={queueState !== 'queued'}>Cancel Search</Button></ToolsRow>
          </Section>
        ) : (
          <>
            <Section title="Quick Match" subtitle="The fastest way to a live Fenghua table.">
              <Button variant="primary" onClick={() => void joinQueue()} disabled={authStatus === 'authenticated' && !isConnected}>Find Match</Button>
              {authStatus === 'authenticated' && !isConnected && <Note>Connecting to the club server before matchmaking…</Note>}
              <button type="button" className="disclosure-button" onClick={() => setShowModes(value => !value)} aria-expanded={showModes}>Game mode · {ruleset === 'fenghua' ? 'Classic' : 'Chongci'} {showModes ? '−' : '+'}</button>
              {showModes && <Toggle value={ruleset} onChange={value => setRuleset(value as Ruleset)} options={[{ value: 'fenghua', label: 'Classic' }, { value: 'chongci-fh', label: 'Chongci' }]} />}
            </Section>
            <Section title="Private Table" subtitle="Open a table now, then invite friends from the waiting room.">
              <Button onClick={() => navigate('/room/new')}>Create Private Table</Button>
            </Section>
          </>
        )}
      </Card>
    </ClubShell>
  )
}
