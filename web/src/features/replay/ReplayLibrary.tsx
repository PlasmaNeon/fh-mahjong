import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../../contexts/AuthContext'
import { Button, Card, ClubShell, Field, Note, PageHeader, Section, ButtonRow } from '../../theme'
import type { AuthRouteState } from '../auth/authRouteState'
import { parseReplayLocation } from './replayReference'
import { useI18n } from '../../i18n/I18nContext'
import { uploadReplay, type ReplayImport } from './studyClient'
import type { Paipu } from './replayTypes'
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
type ReplayHistoryResponse = {
  replays: ReplaySummary[]
  nextCursor: string | null
}

function placementLabel(placement: number) {
  if (placement === 1) return '1st'
  if (placement === 2) return '2nd'
  if (placement === 3) return '3rd'
  return `${placement}th`
}

function formatEndedAt(value: string, locale: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export default function ReplayLibrary() {
  const { status, apiFetch, refreshSession } = useAuth()
  const { t, language, shortLanguage } = useI18n()
  const winds = WIND_I18N_KEYS.map((key) => t(key))
  const location = useLocation()
  const navigate = useNavigate()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<Paipu | null>(null)
  const [uploadSeat, setUploadSeat] = useState(0)
  const [uploadError, setUploadError] = useState('')
  const [uploading, setUploading] = useState(false)
  const [imports, setImports] = useState<ReplayImport[]>([])
  const [importCursor, setImportCursor] = useState('')
  const [reference, setReference] = useState('')
  const [referenceError, setReferenceError] = useState('')
  const [replays, setReplays] = useState<ReplaySummary[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'loading-more' | 'ready' | 'offline' | 'error'>(
    'idle',
  )
  const [historyError, setHistoryError] = useState('')
  const [copiedMatch, setCopiedMatch] = useState('')

  const loadHistory = useCallback(
    async (cursor?: string, signal?: AbortSignal) => {
      setHistoryError('')
      setHistoryState(cursor ? 'loading-more' : 'loading')
      try {
        const query = new URLSearchParams({ limit: '20' })
        if (cursor) query.set('cursor', cursor)
        const response = await apiFetch(`/api/v1/users/me/replays?${query}`, {
          signal,
        })
        if (signal?.aborted) return
        const data = (await readJsonBody(response)) as Partial<ReplayHistoryResponse> & { error?: string }
        if (!response.ok) throw new Error(errorMessage(data, t('library.loadFailed')))
        setReplays((current) => (cursor ? [...current, ...(data.replays ?? [])] : (data.replays ?? [])))
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
    },
    [apiFetch, t],
  )

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

  const loadImports = async (cursor = '', signal?: AbortSignal) => {
    try {
      const response = await apiFetch(
        `/api/v1/replay-imports${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`,
        { signal },
      )
      const body = await response.json()
      if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`)
      if (!signal?.aborted) {
        setImports((current) => (cursor ? [...current, ...body.imports] : body.imports))
        setImportCursor(body.nextCursor)
      }
    } catch (reason) {
      if (!signal?.aborted) setUploadError(reason instanceof Error ? reason.message : String(reason))
    }
  }
  useEffect(() => {
    if (status !== 'authenticated') {
      setImports([])
      return
    }
    const controller = new AbortController()
    void loadImports('', controller.signal)
    return () => controller.abort()
  }, [status, apiFetch])
  const selectFile = async (next: File | undefined) => {
    setUploadError('')
    setFile(null)
    setPreview(null)
    if (!next) return
    try {
      if (next.size > 10 * 1024 * 1024) throw new Error('Paipu must be at most 10 MB')
      const data: Paipu = JSON.parse(await next.text())
      if (
        ![1, 2].includes(data.version) ||
        !['fenghua', 'hometown'].includes(data.ruleset) ||
        !Array.isArray(data.players) ||
        data.players.length !== 4 ||
        data.players.some(
          (p) => !p || !Number.isInteger(p.seat) || p.seat < 0 || p.seat > 3 || typeof p.name !== 'string',
        ) ||
        new Set(data.players.map((p) => p.seat)).size !== 4 ||
        !Array.isArray(data.rounds) ||
        !data.rounds.length ||
        data.rounds.some(
          (round) => !round || !Array.isArray(round.actions) || !Array.isArray(round.deals) || round.deals.length !== 4,
        )
      )
        throw new Error('Choose a completed native Fenghua paipu JSON')
      setFile(next)
      setPreview(data)
      setUploadSeat(data.players[0].seat)
    } catch (reason) {
      setUploadError(reason instanceof Error ? reason.message : String(reason))
    }
  }
  const importFile = async (analyze: boolean) => {
    if (!file || uploading) return
    setUploading(true)
    setUploadError('')
    try {
      const row = await uploadReplay(apiFetch, file)
      navigate(`/replay/import/${encodeURIComponent(row.id)}?seat=${uploadSeat}${analyze ? '&analyze=1' : ''}`)
    } catch (reason) {
      setUploadError(reason instanceof Error ? reason.message : String(reason))
      setUploading(false)
    }
  }

  const openReplay = (event: FormEvent) => {
    event.preventDefault()
    const replayLocation = parseReplayLocation(reference)
    if (!replayLocation) {
      setReferenceError(t('library.referenceError'))
      return
    }
    setReferenceError('')
    navigate(replayLocation)
  }

  const signIn = () => {
    const state: AuthRouteState = {
      backgroundLocation: location,
      optionalAuth: true,
    }
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
            <Field
              label={t('library.reference')}
              value={reference}
              onChange={(event) => setReference(event.target.value)}
              placeholder="/replay/…"
              autoComplete="off"
            />
            <Button type="submit" variant="primary">
              {t('library.openReplay')}
            </Button>
          </form>
          {referenceError && <Note tone="error">{referenceError}</Note>}
        </Section>

        <Section title={t('review.upload')} subtitle={t('review.uploadHelp')}>
          <input
            type="file"
            accept=".json,application/json"
            aria-label={t('review.upload')}
            onChange={(event) => void selectFile(event.target.files?.[0])}
          />
          {preview && (
            <>
              <p>
                {preview.matchId} · {preview.rounds.length} {t('library.rounds')}
              </p>
              <label>
                {t('review.player')}
                <select value={uploadSeat} onChange={(event) => setUploadSeat(Number(event.target.value))}>
                  {preview.players.map((p) => (
                    <option key={p.seat} value={p.seat}>
                      {p.name || `Seat ${p.seat + 1}`}
                    </option>
                  ))}
                </select>
              </label>
            </>
          )}
          {uploadError && <Note tone="error">{uploadError}</Note>}
          {status !== 'authenticated' ? (
            <Button onClick={signIn}>{t('review.signIn')}</Button>
          ) : (
            <ButtonRow>
              <Button variant="primary" disabled={!file || uploading} onClick={() => void importFile(true)}>
                {t(uploading ? 'common.loading' : 'review.analyze')}
              </Button>
              <Button disabled={!file || uploading} onClick={() => void importFile(false)}>
                {t('library.open')}
              </Button>
            </ButtonRow>
          )}
          {imports.length > 0 && (
            <>
              <h3>{t('review.imports')}</h3>
              <div className="paipu-list">
                {imports.map((row) => (
                  <article className="paipu-slip" key={row.id}>
                    <strong>{row.filename}</strong>
                    <p>
                      {row.sourceMatchId} · {formatEndedAt(row.createdAt, language)}
                    </p>
                    <Button onClick={() => navigate(`/replay/import/${encodeURIComponent(row.id)}`)}>
                      {t('library.open')}
                    </Button>
                  </article>
                ))}
              </div>
            </>
          )}
          {importCursor && <Button onClick={() => void loadImports(importCursor)}>{t('library.loadMore')}</Button>}
        </Section>

        <Section title={t('library.mine')} subtitle={t('library.mineHelp')}>
          {status === 'loading' && <Note>{t('account.checking')}</Note>}
          {status === 'anonymous' && (
            <>
              <Note>{t('library.signInHelp')}</Note>
              <ButtonRow>
                <Button variant="primary" onClick={signIn}>
                  {t('library.signIn')}
                </Button>
              </ButtonRow>
            </>
          )}
          {status === 'offline' && (
            <>
              <Note tone="error">{t('library.offline')}</Note>
              <ButtonRow>
                <Button variant="primary" onClick={() => void refreshSession()}>
                  {t('common.tryAgain')}
                </Button>
              </ButtonRow>
            </>
          )}
          {historyState === 'loading' && <Note>{t('library.loading')}</Note>}
          {(historyState === 'offline' || historyState === 'error') && (
            <>
              <Note tone="error">{historyError}</Note>
              <ButtonRow>
                <Button variant="primary" onClick={() => void loadHistory()}>
                  {t('common.tryAgain')}
                </Button>
              </ButtonRow>
            </>
          )}
          {historyState === 'ready' && replays.length === 0 && <Note>{t('library.empty')}</Note>}
          {replays.length > 0 && (
            <div className="paipu-list">
              {replays.map((replay) => (
                <article className="paipu-slip" key={replay.matchId}>
                  <div className="paipu-slip__header">
                    <div>
                      <strong>{formatEndedAt(replay.endedAt, language)}</strong>
                      <span>
                        {replay.ruleset} · {replay.roundCount}{' '}
                        {t(replay.roundCount === 1 ? 'library.round' : 'library.rounds')}
                      </span>
                    </div>
                    <div className="paipu-slip__result">
                      <strong>
                        {shortLanguage === 'zh' ? `第 ${replay.placement} 名` : placementLabel(replay.placement)}
                      </strong>
                      <span>
                        {replay.finalScore >= 0 ? '+' : ''}
                        {replay.finalScore}
                      </span>
                    </div>
                  </div>
                  <div className="paipu-slip__seat">
                    {t('library.youPlayed', {
                      wind: winds[replay.seat] ?? t('common.seat', { seat: replay.seat + 1 }),
                    })}
                  </div>
                  <div className="paipu-slip__players">
                    {replay.players.map((player) => (
                      <span key={player.seat}>
                        {winds[player.seat] ?? player.seat + 1} · {player.name || t('common.player')} ·{' '}
                        {player.finalScore}
                      </span>
                    ))}
                  </div>
                  <div className="paipu-slip__actions">
                    <Button variant="primary" onClick={() => navigate(`/replay/${encodeURIComponent(replay.matchId)}`)}>
                      {t('library.open')}
                    </Button>
                    <Button onClick={() => void copyReplay(replay.matchId)}>
                      {t(copiedMatch === replay.matchId ? 'library.copied' : 'library.copy')}
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {nextCursor && (
            <ButtonRow>
              <Button onClick={() => void loadHistory(nextCursor)} disabled={historyState === 'loading-more'}>
                {t(historyState === 'loading-more' ? 'common.loading' : 'library.loadMore')}
              </Button>
            </ButtonRow>
          )}
        </Section>
      </Card>
    </ClubShell>
  )
}
