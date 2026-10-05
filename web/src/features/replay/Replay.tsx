import { useEffect, useRef, useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import { getApiUrl } from '../../config'
import { preloadAllTileSvgs } from '../../utils/tileDisplay'
import { useGameStageLayout } from '../../table/stage/useGameStageLayout'
import type { Paipu } from './replayTypes'
import { tileObjectFromId } from './replayTypes'
import { ReplayEngine, ReplayState } from './replayEngine'
import { TableBoard } from '../../table/TableBoard'
import { TableRoundResultOverlay } from '../../table/TableRoundResultOverlay'
import { LoadingScreen } from '../../theme'
import ReviewStudy, { defaultStudySettings, studyHidden } from './ReviewStudy'
import type { StudySettings } from './ReviewStudy'
import type { StudySource } from './studyClient'
import type { RoundResultView } from '../../table/types'
import { useStudy } from './useStudy'
import {
  decisionPosition,
  tileAnnotations,
  studyActionLabel,
  isStudyError,
  bookmarkIndex,
  faceOfTile,
  positionDecisionIndex,
} from './studyUtils'
import type { ReportDecision } from './reviewClient'

import { SEVERITY_THRESHOLDS, decisionSeverity, type SeverityThresholds } from './reviewUtils'
import './replay.css'
import { useI18n } from '../../i18n/I18nContext'
import { reviewPatternKey } from '../../i18n/locales/review'
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
  const { t } = useI18n()
  const { apiFetch, status: authStatus } = useAuth()
  const { matchId, importId } = useParams()
  const routeLocation = useLocation()
  const navigate = useNavigate()
  const source: StudySource = {
    kind: importId ? 'import' : 'match',
    id: importId ?? matchId ?? '',
  }
  const studyJob = useStudy(source, apiFetch, authStatus === 'authenticated')
  const review = studyJob.job?.report ?? null
  const [settings, setSettings] = useState(() => {
    try {
      const threshold = bookmarkIndex(localStorage.getItem('review-threshold'), 0, 100, 100)
      return { ...defaultStudySettings, threshold }
    } catch {
      return defaultStudySettings
    }
  })
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const initialQuery = useRef(new URLSearchParams(location.search))
  const [autoAnalyze, setAutoAnalyze] = useState(initialQuery.current.get('analyze') === '1')
  const [paipu, setPaipu] = useState<Paipu | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [, setVersion] = useState(0)
  const [viewSeat, setViewSeat] = useState(bookmarkIndex(initialQuery.current.get('seat'), 0, 3, 0))
  const [showAllHands, setShowAllHands] = useState(false)
  const [playing, setPlaying] = useState(false)
  const engineRef = useRef<ReplayEngine | null>(null)
  const stageLayout = useGameStageLayout()
  const wheelRef = useRef<HTMLDivElement | null>(null)

  const [reviewThresholds, setReviewThresholds] = useState<SeverityThresholds>(SEVERITY_THRESHOLDS)

  useEffect(() => {
    preloadAllTileSvgs()
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    engineRef.current = null
    setLoading(true)
    setError(null)
    setPaipu(null)
    setPlaying(false)
    const path =
      source.kind === 'import'
        ? `/api/v1/replay-imports/${encodeURIComponent(source.id)}`
        : `/api/v1/replays/${encodeURIComponent(source.id)}`
    const request =
      source.kind === 'import'
        ? apiFetch(path, { signal: controller.signal })
        : fetch(getApiUrl(path), { signal: controller.signal })
    request
      .then(async (res) => {
        const body = await res.json()
        if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`)
        return body
      })
      .then((data: Paipu) => {
        if (controller.signal.aborted) return
        const eng = new ReplayEngine(data)
        const query = new URLSearchParams(location.search)
        const round = bookmarkIndex(query.get('round'), 0, data.rounds.length - 1, 0)
        const cursor = bookmarkIndex(query.get('cursor'), -1, data.rounds[round].actions.length - 1, -1)
        eng.jumpToAction(round, cursor)
        setViewSeat(bookmarkIndex(query.get('seat'), 0, 3, 0))
        setSettings((current) => ({
          ...current,
          study: query.get('study') === '1',
          revealed: false,
        }))
        setSelectedDecisionId(query.get('decision'))
        setPaipu(data)
        engineRef.current = eng
        setLoading(false)
        setVersion((v) => v + 1)
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setError(reason.message)
          setLoading(false)
        }
      })
    return () => controller.abort()
  }, [source.kind, source.id, apiFetch])

  useEffect(() => {
    if (autoAnalyze && authStatus === 'authenticated' && !loading) {
      setAutoAnalyze(false)
      void studyJob.run()
    }
  }, [autoAnalyze, authStatus, loading])

  const engine = engineRef.current
  useEffect(() => {
    if (!engine || loading) return
    const query = new URLSearchParams(routeLocation.search)
    const round = bookmarkIndex(query.get('round'), 0, engine.totalRounds - 1, 0)
    const cursor = bookmarkIndex(query.get('cursor'), -1, engine.paipu.rounds[round].actions.length - 1, -1)
    engine.jumpToAction(round, cursor)
    setViewSeat(bookmarkIndex(query.get('seat'), 0, 3, 0))
    setSettings((current) => ({
      ...current,
      study: query.get('study') === '1',
      advice: query.get('advice') !== '0',
      revealed: false,
    }))
    setSelectedDecisionId(query.get('decision'))
    setPlaying(false)
    setVersion((v) => v + 1)
  }, [routeLocation.search, loading])
  useEffect(() => {
    try {
      localStorage.setItem('review-threshold', String(settings.threshold))
    } catch {
      /* unavailable storage */
    }
  }, [settings.threshold])

  const refreshPosition = () => {
    setVersion((v) => v + 1)
    setSelectedDecisionId(null)
    setSettings((current) => ({ ...current, revealed: false }))
    setPlaying(false)
  }
  const jumpDecision = (d: ReportDecision) => {
    engine?.jumpToAction(d.round, decisionPosition(d))
    refreshPosition()
    setSelectedDecisionId(d.id ?? null)
  }
  const navigateDecision = (delta: number, errors = false) => {
    if (!engine || !review) return
    const state = engine.getState()
    const candidates = review.decisions.filter(
      (d) => d.seat === viewSeat && (!errors || isStudyError(d, settings.threshold)),
    )
    const at = positionDecisionIndex(candidates, engine.currentRoundIndex, state.actionIndex, selectedDecisionId)
    const next =
      at >= 0
        ? candidates[at + delta]
        : delta > 0
          ? candidates.find(
              (d) =>
                d.round > engine.currentRoundIndex ||
                (d.round === engine.currentRoundIndex && decisionPosition(d) > state.actionIndex),
            )
          : [...candidates]
              .reverse()
              .find(
                (d) =>
                  d.round < engine.currentRoundIndex ||
                  (d.round === engine.currentRoundIndex && decisionPosition(d) < state.actionIndex),
              )
    if (next) jumpDecision(next)
  }
  const bookmark = async () => {
    if (!engine) return
    const state = engine.getState(),
      query = new URLSearchParams()
    query.set('round', String(engine.currentRoundIndex))
    query.set('cursor', String(state.actionIndex))
    query.set('seat', String(viewSeat))
    query.set('study', settings.study ? '1' : '0')
    query.set('advice', settings.advice ? '1' : '0')
    const seatDecisions = review?.decisions.filter((d) => d.seat === viewSeat) ?? []
    const d =
      seatDecisions[
        positionDecisionIndex(seatDecisions, engine.currentRoundIndex, state.actionIndex, selectedDecisionId)
      ]
    if (d?.id) query.set('decision', d.id)
    const url = `${location.origin}${location.pathname}?${query}`
    navigate({ pathname: location.pathname, search: `?${query}` }, { replace: true })
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      setCopied(false)
    }
  }
  const changeSettings = (patch: Partial<StudySettings>) => {
    setSettings((current) => ({ ...current, ...patch }))
    if (patch.study === true && engine && review) {
      const state = engine.getState()
      const d = [...review.decisions]
        .reverse()
        .find(
          (d) =>
            d.seat === viewSeat && d.round === engine.currentRoundIndex && decisionPosition(d) <= state.actionIndex,
        )
      if (d) jumpDecision(d)
    }
  }
  useEffect(() => {
    if (!engine) return
    const handler = (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLElement &&
        (e.target.matches('input,select,textarea') ||
          e.target.closest('dialog[open]') ||
          (e.target.matches('button') && [' ', 'Enter'].includes(e.key)) ||
          e.target.isContentEditable)
      )
        return
      let handled = true
      if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) navigateDecision(e.key === 'ArrowUp' ? -1 : 1)
      else if (e.key === 'ArrowRight') {
        engine.stepForward()
        refreshPosition()
      } else if (e.key === 'ArrowLeft') {
        engine.stepBackward()
        refreshPosition()
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
        engine.jumpToRound(engine.currentRoundIndex + (e.key === 'ArrowUp' ? -1 : 1))
        refreshPosition()
      } else if (['PageUp', ',', 'PageDown', '.'].includes(e.key)) {
        if (!studyHidden(settings)) navigateDecision(['PageUp', ','].includes(e.key) ? -1 : 1, true)
      } else if (e.key === 'Home' || e.key === '[') {
        engine.jumpToStart()
        refreshPosition()
      } else if (e.key === 'End' || e.key === ']') {
        engine.jumpToEnd()
        refreshPosition()
      } else if (e.key === ' ') setPlaying((p) => !p)
      else if (e.key.toLowerCase() === 'h') setShowAllHands((p) => !p)
      else if (e.key.toLowerCase() === 'm') changeSettings({ advice: !settings.advice })
      else if (e.key.toLowerCase() === 'd') changeSettings({ risk: !settings.risk, tab: 'risk' })
      else if (e.key.toLowerCase() === 'e') document.querySelector<HTMLInputElement>('.review-threshold input')?.focus()
      else if (e.key.toLowerCase() === 'a') changeSettings({ logs: !settings.logs })
      else if (e.key.toLowerCase() === 'z') changeSettings({ details: !settings.details })
      else if (e.key.toLowerCase() === 'b') void bookmark()
      else if (e.key === '?') changeSettings({ help: !settings.help })
      else handled = false
      if (handled) e.preventDefault()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [engine, review, viewSeat, settings, selectedDecisionId])

  useEffect(() => {
    const table = wheelRef.current
    if (!table || !engine || !settings.wheel) return
    const wheel = (event: WheelEvent) => {
      if (document.activeElement !== table || !event.deltaY) return
      event.preventDefault()
      event.deltaY > 0 ? engine.stepForward() : engine.stepBackward()
      refreshPosition()
    }
    table.addEventListener('wheel', wheel, { passive: false })
    return () => table.removeEventListener('wheel', wheel)
  }, [engine, settings.wheel])

  // Auto-play
  useEffect(() => {
    if (!playing || !engine) return
    const interval = setInterval(() => {
      if (!engine.stepForward()) {
        setPlaying(false)
      }
      setVersion((v) => v + 1)
      setSelectedDecisionId(null)
      setSettings((current) => ({ ...current, revealed: false }))
    }, 800)
    return () => clearInterval(interval)
  }, [playing, engine])

  if (loading) {
    return <LoadingScreen label={t('replay.loading')} />
  }

  if (error || !engine || !paipu) {
    return (
      <div className="ledger-page replay-error">
        <div className="replay-error__mark" aria-hidden="true">
          西
        </div>
        <div className="replay-error__eyebrow">{t('replay.closed')}</div>
        <h1>{error || t('replay.failed')}</h1>
        <a href="/" className="replay-error__link">
          {t('replay.return')}
        </a>
      </div>
    )
  }

  const state: ReplayState = engine.getState()
  const action = engine.currentRound.actions[state.actionIndex]
  const familyIds: Record<string, number> = {
    discard: 5,
    pon: 47,
    okan: 81,
    ckan: 115,
    ukan: 149,
  }
  const actionFace =
    action?.tile != null
      ? faceOfTile(tileObjectFromId(action.tile))
      : action?.tiles?.length
        ? faceOfTile(tileObjectFromId(action.tiles[0]))
        : 0
  const actionText = !action
    ? t('review.deal')
    : action.act in familyIds
      ? studyActionLabel(familyIds[action.act] + actionFace, t)
      : action.act === 'tsumo'
        ? t('review.tsumo')
        : action.act === 'ron'
          ? t('review.ron')
          : action.act === 'chii'
            ? t('review.chii')
            : action.act === 'haiteiRefuse'
              ? t('review.refuse')
              : action.act === 'haitei'
                ? t('review.accept')
                : action.act === 'flower'
                  ? t('review.flower')
                  : t('review.draw')
  const actionDesc = action ? `${paipu.players[action.seat]?.name} · ${actionText}` : actionText
  const hidden = studyHidden(settings)
  const decision = review?.decisions.find(
    (d) =>
      d.seat === viewSeat &&
      d.round === engine.currentRoundIndex &&
      decisionPosition(d) === state.actionIndex &&
      (!selectedDecisionId || d.id === selectedDecisionId),
  )

  const isWild = makeWildTilePredicate(state.wildTiles)

  const { shellStyle: stageShellStyle, stageStyle } = stageLayout

  const hudChips = [
    { label: `${t('replay.round')} ${state.roundNum}` },
    { label: `${state.actionIndex + 1}/${state.totalActions}` },
  ]

  // Flagged decisions (disagreement/mistake) for the selected seat within the
  // current round, positioned along the action-progress bar as tick marks.
  const flaggedTicks =
    review && !hidden
      ? review.decisions
          .filter(
            (d) =>
              d.seat === viewSeat &&
              d.round === engine.currentRoundIndex &&
              (!settings.study || decisionPosition(d) <= state.actionIndex),
          )
          .map((d) => ({
            left: state.totalActions > 0 ? ((d.actionIndex + 1) / state.totalActions) * 100 : 0,
            severity: decisionSeverity(d, reviewThresholds),
            round: d.round,
            actionIndex: decisionPosition(d),
            decision: d,
          }))
          .filter((tick) => isStudyError(tick.decision, settings.threshold))
      : []

  const tickColor = { disagreement: '#f59e0b', mistake: '#ef4444' } as const

  const playerViews = [0, 1, 2, 3].map((seat) => {
    const player = state.players[seat]
    return {
      seat,
      score: player.score,
      reviewAnnotations:
        seat === viewSeat
          ? tileAnnotations(
              decision,
              player.hand,
              settings.relative,
              settings.advice && !hidden,
              settings.risk && !hidden,
              (id) => studyActionLabel(id, t),
            )
          : undefined,
      seatWind: ((seat - state.players[engine.currentRound.dealer]?.seat + 4) % 4) + 1,
      closedHand: player.hand,
      drawnTileId: player.drawnTileId,
      handBackCount: player.hand.length,
      showClosedHand: (!hidden && showAllHands) || seat === viewSeat,
      openMelds: player.melds.map((meld) => {
        const calledDirection = getCalledDirection(seat, meld.from)
        // For an upgraded pon (risky kong) the added 4th tile was pushed last, so
        // the originally-called tile sits one slot before it.
        const calledIdx = meld.addedTile != null ? meld.tiles.length - 2 : meld.tiles.length - 1
        const calledTileId = meld.from >= 0 && calledIdx >= 0 ? meld.tiles[calledIdx].id : null
        return {
          tiles: meld.tiles,
          calledTileId,
          calledDirection,
          addedTileId: meld.addedTile,
        }
      }),
      flowerMelds: player.flowers,
      discards: player.replayDiscards,
    }
  })

  const roundResultView: RoundResultView | null =
    !hidden && state.isRoundEnd && state.result
      ? state.result.type === 'draw'
        ? { isDraw: true }
        : {
            isDraw: false,
            winType: state.result.winType === 'tsumo' ? 'tsumo' : 'ron',
            winnerLabel: t('review.winner', {
              name: paipu.players[state.result.winner ?? 0]?.name ?? `Seat ${state.result.winner}`,
            }),
            discarderLabel:
              state.result.winType === 'ron' && state.result.discarder != null
                ? t('review.from', {
                    name: paipu.players[state.result.discarder]?.name ?? `Seat ${state.result.discarder}`,
                  })
                : null,
            closedHand: (state.result.hand || []).map(tileObjectFromId),
            winTile: state.result.winTile != null ? tileObjectFromId(state.result.winTile) : null,
            winningMelds: (state.result.melds || []).map((meld) => ({
              tiles: (meld.tiles || []).map(tileObjectFromId),
              calledTileId:
                meld.from != null && meld.from >= 0 && meld.tiles.length > 0 ? meld.tiles[meld.tiles.length - 1] : null,
              calledDirection: meld.from ?? 0,
            })),
            flowers: (state.result.flowers || []).map(tileObjectFromId),
            breakdown: (state.result.breakdown || []).map((entry) => ({
              patternId: entry.id,
              name: reviewPatternKey(entry.id) ? t(reviewPatternKey(entry.id)!) : entry.name,
              points: entry.points,
            })),
            totalScore: state.result.totalScore,
            payouts: (state.result.scoreChanges || []).map((amount, seat) => ({
              seat,
              label: paipu.players[seat]?.name ?? `Seat ${seat}`,
              amount,
            })),
          }
      : null

  return (
    <div className="replay-viewer">
      {/* Table — uses same game-stage scaling system as Game.tsx */}
      <div
        className="stage-rotator stage-rotator--replay replay-study-table"
        tabIndex={0}
        aria-label={t('replay.viewer')}
        ref={wheelRef}
      >
        <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
          <div className="game-stage-frame">
            <div className="game-stage" data-compact={stageLayout.compact ? 'true' : undefined} style={stageStyle}>
              <TableBoard
                viewSeat={viewSeat}
                players={playerViews}
                activeSeat={state.activeSeat}
                wildTiles={state.wildTiles || []}
                hudChips={hudChips}
                cornerInfo={
                  <div className="replay-context">
                    <span>
                      {['—', '東', '南', '西', '北'][engine.currentRound.prevailingWind]} · {t('replay.round')}{' '}
                      {state.roundNum}
                    </span>
                    <span>
                      {t('review.dice')} {engine.currentRound.dice.join('+')}
                    </span>
                    <span>
                      {t('review.wall')} {state.wallCount} · {t('review.wangpai')} {engine.currentRound.wangpaiStacks}
                    </span>
                  </div>
                }
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
        <div className="replay-action-description">{actionDesc}</div>

        {/* Progress */}
        <div>
          <div className="replay-meta-row">
            <span>
              {t('replay.action', {
                current: state.actionIndex + 1,
                total: state.totalActions,
              })}
            </span>
            <span>
              {t('replay.roundProgress', {
                current: engine.currentRoundIndex + 1,
                total: engine.totalRounds,
              })}
            </span>
          </div>
          <div className="replay-progress">
            <div className="replay-progress__track">
              <div
                className="replay-progress__fill"
                style={{
                  width: state.totalActions > 0 ? `${((state.actionIndex + 1) / state.totalActions) * 100}%` : '0%',
                }}
              />
            </div>
            {flaggedTicks.map((tick, i) => (
              <button
                key={i}
                aria-label={`R${tick.round + 1} · ${t('review.decision')}`}
                title={`R${tick.round + 1} · ${tick.severity}`}
                onClick={() => jumpDecision(tick.decision)}
                className="replay-progress__flag"
                style={{
                  left: `calc(${tick.left}% - 3px)`,
                  background: tickColor[tick.severity as 'disagreement' | 'mistake'],
                }}
              />
            ))}
          </div>
        </div>

        <input
          className="replay-timeline-input"
          type="range"
          min={-1}
          max={Math.max(-1, state.totalActions - 1)}
          value={state.actionIndex}
          aria-label={t('replay.viewer')}
          onChange={(e) => {
            engine.jumpToAction(engine.currentRoundIndex, Number(e.target.value))
            refreshPosition()
          }}
        />
        {/* Transport Controls */}
        <div className="replay-transport">
          {[
            {
              title: t('review.start'),
              label: '|◀',
              action: () => {
                engine.jumpToStart()
                setVersion((v) => v + 1)
                setPlaying(false)
              },
            },
            {
              title: t('replay.step'),
              label: '◀',
              action: () => {
                if (engine.stepBackward()) setVersion((v) => v + 1)
              },
            },
            {
              title: t('replay.playPause'),
              label: playing ? '⏸' : '▶',
              action: () => setPlaying((p) => !p),
            },
            {
              title: t('replay.step'),
              label: '▶',
              action: () => {
                if (engine.stepForward()) setVersion((v) => v + 1)
              },
            },
            {
              title: t('review.end'),
              label: '▶|',
              action: () => {
                engine.jumpToEnd()
                setVersion((v) => v + 1)
                setPlaying(false)
              },
            },
          ].map((btn, i) => (
            <button
              key={i}
              aria-label={btn.title}
              title={btn.title}
              onClick={() => {
                btn.action()
                setSettings((current) => ({ ...current, revealed: false }))
                setSelectedDecisionId(null)
              }}
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
                onClick={() => {
                  engine.jumpToRound(i)
                  setVersion((v) => v + 1)
                  setPlaying(false)
                }}
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
            onChange={(e) => {
              setViewSeat(Number(e.target.value))
              setSelectedDecisionId(null)
              setSettings((current) => ({ ...current, revealed: false }))
            }}
            className="replay-select"
          >
            {paipu.players.map((p) => (
              <option key={p.seat} value={p.seat}>
                {t('common.seat', { seat: p.seat })} — {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Show All Hands Toggle */}
        <label className="replay-check">
          <input type="checkbox" checked={showAllHands} onChange={(e) => setShowAllHands(e.target.checked)} />
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
        <ReviewStudy
          paipu={paipu}
          report={review}
          decision={decision}
          seat={viewSeat}
          round={engine.currentRoundIndex}
          cursor={state.actionIndex}
          job={studyJob.job}
          error={studyJob.error}
          running={studyJob.running}
          authenticated={authStatus === 'authenticated'}
          run={studyJob.run}
          cancel={studyJob.cancel}
          jump={jumpDecision}
          jumpRound={(r, end) => {
            engine.jumpToRound(r)
            if (end) engine.jumpToEnd()
            refreshPosition()
          }}
          navigate={navigateDecision}
          settings={settings}
          change={changeSettings}
          bookmark={bookmark}
          copied={copied}
          thresholds={reviewThresholds}
          onThresholds={setReviewThresholds}
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
