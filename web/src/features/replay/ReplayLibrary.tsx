import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Button, Card, ClubShell, Field, Note, PageHeader, Section, ToolsRow } from '../../theme'
import type { AuthRouteState } from '../auth/authModal'
import { parseReplayReference } from './replayReference'

type ReplayPlayer = { seat: number; name: string; finalScore: number }
type ReplaySummary = {
  matchId: string
  endedAt: string
  ruleset: string
  seat: number
  placement: number
  finalScore: number
  roundCount: number
  players: ReplayPlayer[]
}
type ReplayHistoryResponse = { replays: ReplaySummary[]; nextCursor: string | null }

const winds = ['East', 'South', 'West', 'North']

function placementLabel(placement: number) {
  if (placement === 1) return '1st'
  if (placement === 2) return '2nd'
  if (placement === 3) return '3rd'
  return `${placement}th`
}

function formatEndedAt(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export default function ReplayLibrary() {
  const { status, apiFetch, refreshSession } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [reference, setReference] = useState('')
  const [referenceError, setReferenceError] = useState('')
  const [replays, setReplays] = useState<ReplaySummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'loading-more' | 'ready' | 'offline' | 'error'>('idle')
  const [historyError, setHistoryError] = useState('')
  const [copiedMatch, setCopiedMatch] = useState('')

  const loadHistory = useCallback(async (cursor?: string, signal?: AbortSignal) => {
    setHistoryError('')
    setHistoryState(cursor ? 'loading-more' : 'loading')
    try {
      const query = new URLSearchParams({ limit: '20' })
      if (cursor) query.set('cursor', cursor)
      const response = await apiFetch(`/api/v1/users/me/replays?${query}`, { signal })
      if (signal?.aborted) return
      const data = await response.json().catch(() => ({})) as Partial<ReplayHistoryResponse> & { error?: string }
      if (!response.ok) throw new Error(data.error || 'Could not load your paipu history')
      setReplays(current => cursor ? [...current, ...(data.replays ?? [])] : (data.replays ?? []))
      setNextCursor(data.nextCursor ?? null)
      setHistoryState('ready')
    } catch (reason) {
      if (signal?.aborted) return
      if (reason instanceof TypeError) {
        setHistoryState('offline')
        setHistoryError('The club is offline. Shared paipu links can still be entered when your connection returns.')
      } else {
        setHistoryState('error')
        setHistoryError(reason instanceof Error ? reason.message : 'Could not load your paipu history')
      }
    }
  }, [apiFetch])

  useEffect(() => {
    if (status !== 'authenticated') {
      setReplays([])
      setNextCursor(null)
      setHistoryState('idle')
      return
    }
    const controller = new AbortController()
    void loadHistory(undefined, controller.signal)
    return () => controller.abort()
  }, [status, loadHistory])

  const openReplay = (event: FormEvent) => {
    event.preventDefault()
    const matchID = parseReplayReference(reference)
    if (!matchID) {
      setReferenceError('Enter a paipu ID or a link whose path is /replay/{matchId}.')
      return
    }
    setReferenceError('')
    navigate(`/replay/${encodeURIComponent(matchID)}`)
  }

  const signIn = () => {
    const state: AuthRouteState = { backgroundLocation: location, optionalAuth: true }
    navigate(`/login?returnTo=${encodeURIComponent('/replay')}`, { state })
  }

  const copyReplay = async (matchID: string) => {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/replay/${encodeURIComponent(matchID)}`)
      setCopiedMatch(matchID)
    } catch {
      setCopiedMatch('')
      setHistoryError('The replay link could not be copied. Open it and copy the address from your browser.')
    }
  }

  return (
    <ClubShell title="Paipu Replay" wide>
      <Card>
        <PageHeader title="Paipu Replay" subtitle="牌谱 · open a shared game or revisit your own" />
        <Section title="Open a paipu" subtitle="Paste a replay link or enter its match ID.">
          <form className="replay-open-form" onSubmit={openReplay}>
            <Field label="Paipu link or match ID" value={reference} onChange={event => setReference(event.target.value)} placeholder="/replay/…" autoComplete="off" />
            <Button type="submit" variant="primary">Open Replay</Button>
          </form>
          {referenceError && <Note tone="error">{referenceError}</Note>}
        </Section>

        <Section title="My Paipu" subtitle="Completed games from this account, newest first.">
          {status === 'loading' && <Note>Checking your club pass…</Note>}
          {status === 'anonymous' && <><Note>Sign in to see completed games from this account.</Note><ToolsRow><Button variant="primary" onClick={signIn}>Sign In to See My Paipu</Button></ToolsRow></>}
          {status === 'offline' && <><Note tone="error">The club is offline. Your saved history is unchanged.</Note><ToolsRow><Button variant="primary" onClick={() => void refreshSession()}>Try Again</Button></ToolsRow></>}
          {historyState === 'loading' && <Note>Loading completed games…</Note>}
          {(historyState === 'offline' || historyState === 'error') && <><Note tone="error">{historyError}</Note><ToolsRow><Button variant="primary" onClick={() => void loadHistory()}>Try Again</Button></ToolsRow></>}
          {historyState === 'ready' && replays.length === 0 && <Note>No completed paipu yet. Finish a game and it will appear here.</Note>}
          {replays.length > 0 && (
            <div className="paipu-list">
              {replays.map(replay => (
                <article className="paipu-slip" key={replay.matchId}>
                  <div className="paipu-slip__header">
                    <div><strong>{formatEndedAt(replay.endedAt)}</strong><span>{replay.ruleset} · {replay.roundCount} {replay.roundCount === 1 ? 'round' : 'rounds'}</span></div>
                    <div className="paipu-slip__result"><strong>{placementLabel(replay.placement)}</strong><span>{replay.finalScore >= 0 ? '+' : ''}{replay.finalScore}</span></div>
                  </div>
                  <div className="paipu-slip__seat">You played {winds[replay.seat] ?? `Seat ${replay.seat + 1}`}</div>
                  <div className="paipu-slip__players">
                    {replay.players.map(player => <span key={player.seat}>{winds[player.seat] ?? player.seat + 1} · {player.name || 'Player'} · {player.finalScore}</span>)}
                  </div>
                  <div className="paipu-slip__actions">
                    <Button variant="primary" onClick={() => navigate(`/replay/${encodeURIComponent(replay.matchId)}`)}>Open</Button>
                    <Button onClick={() => void copyReplay(replay.matchId)}>{copiedMatch === replay.matchId ? 'Link Copied' : 'Copy Link'}</Button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {nextCursor && <ToolsRow><Button onClick={() => void loadHistory(nextCursor)} disabled={historyState === 'loading-more'}>{historyState === 'loading-more' ? 'Loading…' : 'Load More'}</Button></ToolsRow>}
        </Section>
      </Card>
    </ClubShell>
  )
}
