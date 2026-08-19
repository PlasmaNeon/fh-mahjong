// @ts-nocheck
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getApiUrl } from '../../config'
import { preloadAllTileSvgs } from '../../utils/tileDisplay'
import { useGameStageLayout } from '../../table/stage/useGameStageLayout'
import type { Paipu } from './replayTypes'
import { tileObjectFromId } from './replayTypes'
import { ReplayEngine, ReplayState } from './replayEngine'
import { TableBoard, TableRoundResultOverlay } from '../../table/TableScene'
import { LoadingScreen } from '../../theme'
import ReviewPanel, { type ReviewStatus } from './ReviewPanel'
import type { ReviewReport } from './reviewClient'
import { fetchReview, generateReview } from './reviewClient'
import { SEVERITY_THRESHOLDS, decisionSeverity, type SeverityThresholds } from './reviewUtils'
import './replay.css'
import { useI18n } from '../../i18n/I18nContext'
import { useAuth } from '../../contexts/AuthContext'
import { makeWildTilePredicate } from '../../utils/tileModel'

/**
 * Compute calledDirection from seat layout:
 *   1 = Right (shimocha), 2 = Across (toimen), 3 = Left (kamicha)
 */
function getCalledDirection(meldHolderSeat: number, fromSeat: number): number {
  if (fromSeat < 0) return 0 // closed
  const diff = (fromSeat - meldHolderSeat + 4) % 4
  // diff: 1=right, 2=across, 3=left
  return diff
}

export default function Replay() {
  const { shortLanguage, toggleLanguage, t } = useI18n()
  const { apiFetch } = useAuth()
  const { matchId } = useParams()
  const [paipu, setPaipu] = useState<Paipu | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  const [viewSeat, setViewSeat] = useState(0)
  const [showAllHands, setShowAllHands] = useState(true)
  const [playing, setPlaying] = useState(false)
  const engineRef = useRef<ReplayEngine | null>(null)
  const stageLayout = useGameStageLayout()

  const [review, setReview] = useState<ReviewReport | null>(null)
  const [reviewStatus, setReviewStatus] = useState<ReviewStatus>('loading')
  const [reviewError, setReviewError] = useState<string | null>(null)
  const [reviewThresholds, setReviewThresholds] = useState<SeverityThresholds>(SEVERITY_THRESHOLDS)

  useEffect(() => { preloadAllTileSvgs() }, [])

  // Fetch existing review report (if any) on mount
  useEffect(() => {
    if (!matchId) return
    let cancelled = false
    setReviewStatus('loading')
    fetchReview(matchId)
      .then(r => {
        if (cancelled) return
        setReview(r)
        setReviewStatus(r ? 'ready' : 'empty')
      })
      .catch((err: { status?: number; message?: string }) => {
        if (cancelled) return
        setReviewStatus(err.status === 503 ? 'unavailable' : 'error')
        setReviewError(err.message ?? null)
      })
    return () => { cancelled = true }
  }, [matchId])

  const handleRequestReview = () => {
    if (!matchId) return
    setReviewStatus('generating')
    setReviewError(null)
    generateReview(matchId, apiFetch)
      .then(r => {
        setReview(r)
        setReviewStatus('ready')
      })
      .catch((err: { status?: number; message?: string }) => {
        setReviewStatus(err.status === 503 ? 'unavailable' : 'error')
        setReviewError(err.message ?? null)
      })
  }

  // Fetch paipu data
  useEffect(() => {
    if (!matchId) {
      setError(t('replay.noMatch'))
      setLoading(false)
      return
    }
    fetch(getApiUrl(`/api/v1/replays/${matchId}`))
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: Paipu) => {
        setPaipu(data)
        const eng = new ReplayEngine(data)
        engineRef.current = eng
        setLoading(false)
      })
      .catch(err => {
        setError(t('replay.loadFailed', { error: err.message }))
        setLoading(false)
      })
  }, [matchId, t])

  const engine = engineRef.current

  // Keyboard controls
  useEffect(() => {
    if (!engine) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') {
        if (engine.stepForward()) setVersion(v => v + 1)
      } else if (e.key === 'ArrowLeft') {
        if (engine.stepBackward()) setVersion(v => v + 1)
      } else if (e.key === 'ArrowUp') {
        if (engine.currentRoundIndex > 0) {
          engine.jumpToRound(engine.currentRoundIndex - 1)
          setVersion(v => v + 1)
        }
      } else if (e.key === 'ArrowDown') {
        if (engine.currentRoundIndex < engine.totalRounds - 1) {
          engine.jumpToRound(engine.currentRoundIndex + 1)
          setVersion(v => v + 1)
        }
      } else if (e.key === ' ') {
        e.preventDefault()
        setPlaying(p => !p)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [engine])

  // Auto-play
  useEffect(() => {
    if (!playing || !engine) return
    const interval = setInterval(() => {
      if (!engine.stepForward()) {
        setPlaying(false)
      }
      setVersion(v => v + 1)
    }, 800)
    return () => clearInterval(interval)
  }, [playing, engine])

  if (loading) {
    return <LoadingScreen label={t('replay.loading')} />
  }

  if (error || !engine || !paipu) {
    return (
      <div className="ledger-page replay-error">
        <div className="replay-error__mark" aria-hidden="true">西</div>
        <div className="replay-error__eyebrow">{t('replay.closed')}</div>
        <h1>{error || t('replay.failed')}</h1>
        <a href="/" className="replay-error__link">{t('replay.return')}</a>
      </div>
    )
  }

  const state: ReplayState = engine.getState()
  const actionDesc = engine.getActionDescription(shortLanguage)

  const isWild = makeWildTilePredicate(state.wildTiles)

  const { shellStyle: stageShellStyle, stageStyle } = stageLayout

  const hudChips = [
    { label: `${t('replay.round')} ${state.roundNum}` },
    { label: `${state.actionIndex + 1}/${state.totalActions}` },
  ]

  // Flagged decisions (disagreement/mistake) for the selected seat within the
  // current round, positioned along the action-progress bar as tick marks.
  const flaggedTicks = review
    ? review.decisions
        .filter(d => d.seat === viewSeat && d.round === engine.currentRoundIndex)
        .map(d => ({
          left: state.totalActions > 0 ? ((d.actionIndex + 1) / state.totalActions) * 100 : 0,
          severity: decisionSeverity(d, reviewThresholds),
          round: d.round,
          actionIndex: d.actionIndex,
        }))
        .filter(tick => tick.severity !== 'ok')
    : []

  const tickColor = { disagreement: '#f59e0b', mistake: '#ef4444' } as const

  const playerViews = [0, 1, 2, 3].map((seat) => {
    const player = state.players[seat]
    return {
      seat,
      seatWind: ((seat - state.players[engine.currentRound.dealer]?.seat + 4) % 4) + 1,
      closedHand: player.hand,
      drawnTileId: player.drawnTileId,
      handBackCount: player.hand.length,
      showClosedHand: showAllHands || seat === viewSeat,
      openMelds: player.melds.map((meld) => {
        const calledDirection = getCalledDirection(seat, meld.from)
        // For an upgraded pon (risky kong) the added 4th tile was pushed last, so
        // the originally-called tile sits one slot before it.
        const calledIdx = meld.addedTile != null ? meld.tiles.length - 2 : meld.tiles.length - 1
        const calledTileId = meld.from >= 0 && calledIdx >= 0
          ? meld.tiles[calledIdx].id
          : null
        return {
          tiles: meld.tiles,
          calledTileId,
          calledDirection,
          addedTileId: meld.addedTile,
        }
      }),
      flowerMelds: player.flowers,
      discards: player.discards,
    }
  })

  const roundResultView = state.isRoundEnd && state.result ? (
    state.result.type === 'draw'
      ? { isDraw: true }
      : {
          isDraw: false,
          winType: state.result.winType === 'tsumo' ? 'tsumo' : 'ron',
          winnerLabel: `${paipu.players[state.result.winner ?? 0]?.name ?? `Seat ${state.result.winner}`} wins`,
          discarderLabel: state.result.winType === 'ron' && state.result.discarder != null
            ? `From ${paipu.players[state.result.discarder]?.name ?? `Seat ${state.result.discarder}`}`
            : null,
          closedHand: (state.result.hand || []).map(tileObjectFromId),
          winTile: state.result.winTile != null ? tileObjectFromId(state.result.winTile) : null,
          winningMelds: (state.result.melds || []).map((meld) => ({
            tiles: (meld.tiles || []).map(tileObjectFromId),
            calledTileId: meld.from != null && meld.from >= 0 && meld.tiles.length > 0
              ? meld.tiles[meld.tiles.length - 1]
              : null,
            calledDirection: meld.from ?? 0,
          })),
          flowers: (state.result.flowers || []).map(tileObjectFromId),
          breakdown: (state.result.breakdown || []).map((entry) => ({
            name: entry.name,
            points: entry.points,
          })),
          totalScore: state.result.totalScore,
          payouts: (state.result.scoreChanges || []).map((amount, seat) => ({
            seat,
            label: paipu.players[seat]?.name ?? `Seat ${seat}`,
            amount,
          })),
        }
  ) : null

  return (
    <div className="replay-viewer">
      {/* Table — uses same game-stage scaling system as Game.tsx */}
      <div className="stage-rotator stage-rotator--replay">
      <div
        className="game-stage-shell"
        ref={stageLayout.containerRef}
        style={stageShellStyle}
      >
        <div className="game-stage-frame">
          <div className="game-stage" data-compact={stageLayout.compact ? 'true' : undefined} style={stageStyle}>
            <TableBoard
              viewSeat={viewSeat}
              players={playerViews}
              activeSeat={state.activeSeat}
              wildTiles={state.wildTiles || []}
              hudChips={hudChips}
              isWildTile={isWild}
            />
          </div>
        </div>
        <TableRoundResultOverlay result={roundResultView} isWildTile={isWild} />
      </div>
      </div>

      {/* Control Panel */}
      <aside className="replay-drawer">
        {/* Match Info */}
        <div className="replay-drawer__head">
          <div className="replay-drawer__eyebrow">{t('replay.afterHand')}</div>
          <div className="replay-drawer__title">{t('replay.viewer')}</div>
          <div className="replay-drawer__match">{paipu.matchId}</div>
        </div>

        {/* Action Description */}
        <div className="replay-action-description">
          {actionDesc}
        </div>

        {/* Progress */}
        <div>
          <div className="replay-meta-row">
            <span>{t('replay.action', { current: state.actionIndex + 1, total: state.totalActions })}</span>
            <span>{t('replay.roundProgress', { current: engine.currentRoundIndex + 1, total: engine.totalRounds })}</span>
          </div>
          <div className="replay-progress">
            <div className="replay-progress__track">
              <div className="replay-progress__fill" style={{ width: state.totalActions > 0 ? `${((state.actionIndex + 1) / state.totalActions) * 100}%` : '0%' }} />
            </div>
            {flaggedTicks.map((tick, i) => (
              <div
                key={i}
                title={`R${tick.round + 1} · ${tick.severity}`}
                onClick={() => { engine.jumpToAction(tick.round, tick.actionIndex); setVersion(v => v + 1); setPlaying(false) }}
                className="replay-progress__flag"
                style={{ left: `calc(${tick.left}% - 3px)`, background: tickColor[tick.severity as 'disagreement' | 'mistake'] }}
              />
            ))}
          </div>
        </div>

        {/* Transport Controls */}
        <div className="replay-transport">
          {[
            { label: '|◀', action: () => { engine.jumpToStart(); setVersion(v => v + 1); setPlaying(false) } },
            { label: '◀', action: () => { if (engine.stepBackward()) setVersion(v => v + 1) } },
            { label: playing ? '⏸' : '▶', action: () => setPlaying(p => !p) },
            { label: '▶', action: () => { if (engine.stepForward()) setVersion(v => v + 1) } },
            { label: '▶|', action: () => { engine.jumpToEnd(); setVersion(v => v + 1); setPlaying(false) } },
          ].map((btn, i) => (
            <button
              key={i}
              onClick={btn.action}
              className={`replay-transport__button${i === 2 ? ' is-primary' : ''}`}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Round Selector */}
        <div>
          <div className="replay-control-label">{t('replay.round')}</div>
          <div className="replay-choice-row">
            {paipu.rounds.map((_, i) => (
              <button
                key={i}
                onClick={() => { engine.jumpToRound(i); setVersion(v => v + 1); setPlaying(false) }}
                className={`replay-choice${i === engine.currentRoundIndex ? ' is-active' : ''}`}
              >
                {i + 1}
              </button>
            ))}
          </div>
        </div>

        {/* Perspective Selector */}
        <div>
          <div className="replay-control-label">{t('replay.perspective')}</div>
          <select
            value={viewSeat}
            onChange={e => setViewSeat(Number(e.target.value))}
            className="replay-select"
          >
            {paipu.players.map(p => (
              <option key={p.seat} value={p.seat}>
                {t('common.seat', { seat: p.seat })} — {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Show All Hands Toggle */}
        <label className="replay-check">
          <input
            type="checkbox"
            checked={showAllHands}
            onChange={e => setShowAllHands(e.target.checked)}
          />
          {t('replay.showHands')}
        </label>

        {/* Scores */}
        <div className="replay-scores">
          <div className="replay-control-label">{t('replay.scores')}</div>
          {state.players.map((p, i) => (
            <div key={i} className={`replay-score${i === state.activeSeat ? ' is-active' : ''}`}>
              <span>{paipu.players[i]?.name ?? t('common.seat', { seat: i })}</span>
              <span>{p.score.toLocaleString()}</span>
            </div>
          ))}
        </div>

        {/* Post-game Review */}
        <ReviewPanel
          report={review}
          status={reviewStatus}
          errorMessage={reviewError}
          onRequestReview={handleRequestReview}
          viewSeat={viewSeat}
          position={{ round: engine.currentRoundIndex, actionIndex: state.actionIndex }}
          onJump={(round, actionIndex) => {
            engine.jumpToAction(round, actionIndex)
            setVersion(v => v + 1)
            setPlaying(false)
          }}
          lang={shortLanguage}
          onLangToggle={toggleLanguage}
          thresholds={reviewThresholds}
          onThresholdsChange={setReviewThresholds}
        />

        {/* Keyboard Shortcuts */}
        <div className="replay-shortcuts">
          <div>{t('replay.step')}</div>
          <div>{t('replay.roundKeys')}</div>
          <div>{t('replay.playPause')}</div>
        </div>
      </aside>
    </div>
  )
}
