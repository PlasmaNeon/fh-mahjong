import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Button, Card, ClubShell, Field, Note, PageHeader, Section, ButtonRow } from '../../theme'
import type { AuthRouteState } from '../auth/authRouteState'
import { parseReplayReference } from './replayReference'
import { useI18n } from '../../i18n/I18nContext'
import { WIND_I18N_KEYS } from '../../utils/winds'
import { errorMessage, readJsonBody } from '../../utils/apiJson'

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

function placementLabel(placement: number) {
  if (placement === 1) return '1st'
  if (placement === 2) return '2nd'
  if (placement === 3) return '3rd'
  return `${placement}th`
}

function formatEndedAt(value: string, locale: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export default function ReplayLibrary() {
  const { status, apiFetch, refreshSession } = useAuth()
  const { t, language, shortLanguage } = useI18n()
  const winds = WIND_I18N_KEYS.map((key) => t(key))
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
      const data = await readJsonBody(response) as Partial<ReplayHistoryResponse> & { error?: string }
      if (!response.ok) throw new Error(errorMessage(data, t('library.loadFailed')))
      setReplays(current => cursor ? [...current, ...(data.replays ?? [])] : (data.replays ?? []))
      setNextCursor(data.nextCursor ?? null)
      setHistoryState('ready')
    } catch (reason) {
      if (signal?.aborted) return
      if (reason instanceof TypeError) {
        setHistoryState('offline')
        setHistoryError(t('library.historyOffline'))
      } else {
        setHistoryState('error')
        setHistoryError(reason instanceof Error ? reason.message : t('library.loadFailed'))
      }
    }
  }, [apiFetch, t])

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
      setReferenceError(t('library.referenceError'))
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
      setHistoryError(t('library.copyError'))
    }
  }

  return (
    <ClubShell title={t('nav.replay')} wide>
      <Card>
        <PageHeader title={t('nav.replay')} subtitle={t('library.subtitle')} />
        <Section title={t('library.openTitle')} subtitle={t('library.openHelp')}>
          <form className="replay-open-form" onSubmit={openReplay}>
            <Field label={t('library.reference')} value={reference} onChange={event => setReference(event.target.value)} placeholder="/replay/…" autoComplete="off" />
            <Button type="submit" variant="primary">{t('library.openReplay')}</Button>
          </form>
          {referenceError && <Note tone="error">{referenceError}</Note>}
        </Section>

        <Section title={t('library.mine')} subtitle={t('library.mineHelp')}>
          {status === 'loading' && <Note>{t('account.checking')}</Note>}
          {status === 'anonymous' && <><Note>{t('library.signInHelp')}</Note><ButtonRow><Button variant="primary" onClick={signIn}>{t('library.signIn')}</Button></ButtonRow></>}
          {status === 'offline' && <><Note tone="error">{t('library.offline')}</Note><ButtonRow><Button variant="primary" onClick={() => void refreshSession()}>{t('common.tryAgain')}</Button></ButtonRow></>}
          {historyState === 'loading' && <Note>{t('library.loading')}</Note>}
          {(historyState === 'offline' || historyState === 'error') && <><Note tone="error">{historyError}</Note><ButtonRow><Button variant="primary" onClick={() => void loadHistory()}>{t('common.tryAgain')}</Button></ButtonRow></>}
          {historyState === 'ready' && replays.length === 0 && <Note>{t('library.empty')}</Note>}
          {replays.length > 0 && (
            <div className="paipu-list">
              {replays.map(replay => (
                <article className="paipu-slip" key={replay.matchId}>
                  <div className="paipu-slip__header">
                    <div><strong>{formatEndedAt(replay.endedAt, language)}</strong><span>{replay.ruleset} · {replay.roundCount} {t(replay.roundCount === 1 ? 'library.round' : 'library.rounds')}</span></div>
                    <div className="paipu-slip__result"><strong>{shortLanguage === 'zh' ? `第 ${replay.placement} 名` : placementLabel(replay.placement)}</strong><span>{replay.finalScore >= 0 ? '+' : ''}{replay.finalScore}</span></div>
                  </div>
                  <div className="paipu-slip__seat">{t('library.youPlayed', { wind: winds[replay.seat] ?? t('common.seat', { seat: replay.seat + 1 }) })}</div>
                  <div className="paipu-slip__players">
                    {replay.players.map(player => <span key={player.seat}>{winds[player.seat] ?? player.seat + 1} · {player.name || t('common.player')} · {player.finalScore}</span>)}
                  </div>
                  <div className="paipu-slip__actions">
                    <Button variant="primary" onClick={() => navigate(`/replay/${encodeURIComponent(replay.matchId)}`)}>{t('library.open')}</Button>
                    <Button onClick={() => void copyReplay(replay.matchId)}>{t(copiedMatch === replay.matchId ? 'library.copied' : 'library.copy')}</Button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {nextCursor && <ButtonRow><Button onClick={() => void loadHistory(nextCursor)} disabled={historyState === 'loading-more'}>{t(historyState === 'loading-more' ? 'common.loading' : 'library.loadMore')}</Button></ButtonRow>}
        </Section>
      </Card>
    </ClubShell>
  )
}
