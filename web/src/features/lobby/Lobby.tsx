import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useSocket } from '../../contexts/SocketContext'
import { useGameState } from '../../contexts/GameContext'
import { getApiUrl } from '../../config'
import { Button, Card, ClubShell, Note, PageHeader, Section, Toggle, ToolsRow } from '../../theme'
import AuthTicket from '../auth/AuthTicket'
import { createPrivateTablePath } from './navigation'

type Ruleset = 'fenghua' | 'chongci-fh'

export default function Lobby() {
  const [queueState, setQueueState] = useState<'idle' | 'joining' | 'queued' | 'leaving'>('idle')
  const [ruleset, setRuleset] = useState<Ruleset>('fenghua')
  const [showModes, setShowModes] = useState(false)
  const [authPending, setAuthPending] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const { isConnected, connect } = useSocket()
  const { gameState } = useGameState()

  useEffect(() => {
    const token = localStorage.getItem('fh_token')
    if (token && !isConnected) connect(token)
    if (gameState?.matchId) navigate(`/match/${gameState.matchId}`)
  }, [isConnected, gameState, navigate, connect])

  const joinQueue = async (token = localStorage.getItem('fh_token')) => {
    if (!token) { setAuthPending(true); return }
    setError('')
    setQueueState('joining')
    try {
      const response = await fetch(getApiUrl('/api/v1/matchmaking/join'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ruleset }),
      })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.error || 'Failed to join queue')
      setQueueState('queued')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error contacting matchmaker')
      setQueueState('idle')
    }
  }

  const cancelQueue = async () => {
    const token = localStorage.getItem('fh_token')
    if (!token) return
    setError('')
    setQueueState('leaving')
    try {
      const response = await fetch(getApiUrl('/api/v1/matchmaking/leave'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
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

        {authPending ? (
          <Section title="Sign in to find a match" subtitle="You will continue searching automatically.">
            <AuthTicket onAuthenticated={token => { connect(token); setAuthPending(false); void joinQueue(token) }} />
          </Section>
        ) : searching ? (
          <Section title="Listening for players" subtitle={ruleset === 'fenghua' ? 'Fenghua · Classic table' : 'Fenghua · Chongci table'}>
            <div className="queue-compass" aria-hidden="true"><span>東</span></div>
            <Note>{queueState === 'joining' ? 'Joining the queue…' : queueState === 'leaving' ? 'Leaving the queue safely…' : 'Searching for three players. Keep this page open.'}</Note>
            <ToolsRow><Button onClick={cancelQueue} disabled={queueState !== 'queued'}>Cancel Search</Button></ToolsRow>
          </Section>
        ) : (
          <>
            <Section title="Quick Match" subtitle="The fastest way to a live Fenghua table.">
              <Button variant="primary" onClick={() => void joinQueue()} disabled={Boolean(localStorage.getItem('fh_token')) && !isConnected}>Find Match</Button>
              {Boolean(localStorage.getItem('fh_token')) && !isConnected && <Note>Connecting to the club server before matchmaking…</Note>}
              <button type="button" className="disclosure-button" onClick={() => setShowModes(value => !value)} aria-expanded={showModes}>Game mode · {ruleset === 'fenghua' ? 'Classic' : 'Chongci'} {showModes ? '−' : '+'}</button>
              {showModes && <Toggle value={ruleset} onChange={value => setRuleset(value as Ruleset)} options={[{ value: 'fenghua', label: 'Classic' }, { value: 'chongci-fh', label: 'Chongci' }]} />}
            </Section>
            <Section title="Private Table" subtitle="Open a table now, then invite friends from the waiting room.">
              <Button onClick={() => navigate(createPrivateTablePath())}>Create Private Table</Button>
            </Section>
          </>
        )}
      </Card>
    </ClubShell>
  )
}
