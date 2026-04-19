// @ts-nocheck
import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getApiUrl } from '../config'
import { preloadAllTileSvgs } from '../utils/tileUtils'
import { useGameStageLayout } from '../hooks/useGameStageLayout'
import type { Paipu } from './replayTypes'
import { tileObjectFromId } from './replayTypes'
import { ReplayEngine, ReplayState } from './replayEngine'
import { TableBoard, TableRoundResultOverlay } from '../table/TableScene'

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

  useEffect(() => { preloadAllTileSvgs() }, [])

  // Fetch paipu data
  useEffect(() => {
    if (!matchId) {
      setError('No match ID provided')
      setLoading(false)
      return
    }
    fetch(getApiUrl(`/api/v1/paipu/${matchId}`))
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
        setError(`Failed to load paipu: ${err.message}`)
        setLoading(false)
      })
  }, [matchId])

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
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <h2 className="text-2xl text-green-400 animate-pulse">Loading Replay...</h2>
      </div>
    )
  }

  if (error || !engine || !paipu) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <h2 className="text-xl text-red-400">{error || 'Failed to initialize replay'}</h2>
      </div>
    )
  }

  const state: ReplayState = engine.getState()
  const actionDesc = engine.getActionDescription()

  const wildTileSet = new Set(
    (state.wildTiles || []).map(w => `${w.suit}-${w.value}`)
  )
  const isWild = (tile: ReplayTile) => wildTileSet.has(`${tile.suit}-${tile.value}`)

  const stageShellStyle = {
    '--game-stage-scaled-width': `${stageLayout.scaledWidth}px`,
    '--game-stage-scaled-height': `${stageLayout.scaledHeight}px`,
    '--game-stage-available-width': `${stageLayout.availableWidth}px`,
    '--game-stage-available-height': `${stageLayout.availableHeight}px`,
  } as React.CSSProperties

  const stageStyle = {
    width: `${stageLayout.stageWidth}px`,
    height: `${stageLayout.stageHeight}px`,
    zoom: stageLayout.scale,
  } as React.CSSProperties
  const stageFrameStyle = {} as React.CSSProperties

  const hudChips = [
    { label: `Round ${state.roundNum}` },
    { label: `${state.actionIndex + 1}/${state.totalActions}` },
  ]

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
        const calledTileId = meld.from >= 0 && meld.tiles.length > 0
          ? meld.tiles[meld.tiles.length - 1].id
          : null
        return {
          tiles: meld.tiles,
          calledTileId,
          calledDirection,
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
    <div style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {/* Table — uses same game-stage scaling system as Game.tsx */}
      <div
        className="game-stage-shell"
        ref={stageLayout.containerRef}
        style={{
          ...stageShellStyle,
          flex: '1 1 0%',
          width: 'auto',
          minWidth: 0,
          height: '100%',
          minHeight: 'unset',
        }}
      >
        <div className="game-stage-frame" style={stageFrameStyle}>
          <div className="game-stage" style={stageStyle}>
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

      {/* Control Panel */}
      <div style={{
        flex: '0 0 280px',
        width: '280px',
        minWidth: '280px',
        background: 'rgba(17, 24, 39, 0.95)',
        borderLeft: '1px solid rgba(255,255,255,0.1)',
        display: 'flex',
        flexDirection: 'column',
        padding: '16px',
        gap: '12px',
        overflowY: 'auto',
        color: '#e5e7eb',
        fontSize: '14px',
      }}>
        {/* Match Info */}
        <div style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '12px' }}>
          <div style={{ fontSize: '16px', fontWeight: 700, marginBottom: '4px' }}>Replay Viewer</div>
          <div style={{ fontSize: '12px', color: '#9ca3af' }}>{paipu.matchId}</div>
        </div>

        {/* Action Description */}
        <div style={{
          background: 'rgba(16, 185, 129, 0.15)',
          borderRadius: '8px',
          padding: '10px 12px',
          fontWeight: 600,
          textAlign: 'center',
          minHeight: '40px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          {actionDesc}
        </div>

        {/* Progress */}
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#9ca3af', marginBottom: '4px' }}>
            <span>Action {state.actionIndex + 1} / {state.totalActions}</span>
            <span>Round {engine.currentRoundIndex + 1} / {engine.totalRounds}</span>
          </div>
          <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
            <div style={{
              width: state.totalActions > 0 ? `${((state.actionIndex + 1) / state.totalActions) * 100}%` : '0%',
              height: '100%',
              background: 'linear-gradient(90deg, #10b981, #34d399)',
              borderRadius: '3px',
              transition: 'width 0.15s ease',
            }} />
          </div>
        </div>

        {/* Transport Controls */}
        <div style={{ display: 'flex', gap: '6px', justifyContent: 'center' }}>
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
              style={{
                flex: 1,
                padding: '8px 4px',
                background: i === 2 ? 'rgba(16, 185, 129, 0.3)' : 'rgba(255,255,255,0.08)',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '6px',
                color: '#e5e7eb',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 600,
              }}
            >
              {btn.label}
            </button>
          ))}
        </div>

        {/* Round Selector */}
        <div>
          <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Round</div>
          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {paipu.rounds.map((_, i) => (
              <button
                key={i}
                onClick={() => { engine.jumpToRound(i); setVersion(v => v + 1); setPlaying(false) }}
                style={{
                  padding: '4px 12px',
                  background: i === engine.currentRoundIndex ? 'rgba(16, 185, 129, 0.4)' : 'rgba(255,255,255,0.08)',
                  border: i === engine.currentRoundIndex ? '1px solid #10b981' : '1px solid rgba(255,255,255,0.15)',
                  borderRadius: '4px',
                  color: '#e5e7eb',
                  cursor: 'pointer',
                  fontSize: '13px',
                }}
              >
                {i + 1}
              </button>
            ))}
          </div>
        </div>

        {/* Perspective Selector */}
        <div>
          <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Perspective</div>
          <select
            value={viewSeat}
            onChange={e => setViewSeat(Number(e.target.value))}
            style={{
              width: '100%',
              padding: '6px 8px',
              background: 'rgba(255,255,255,0.08)',
              border: '1px solid rgba(255,255,255,0.15)',
              borderRadius: '4px',
              color: '#e5e7eb',
              fontSize: '13px',
            }}
          >
            {paipu.players.map(p => (
              <option key={p.seat} value={p.seat}>
                Seat {p.seat} — {p.name}
              </option>
            ))}
          </select>
        </div>

        {/* Show All Hands Toggle */}
        <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px' }}>
          <input
            type="checkbox"
            checked={showAllHands}
            onChange={e => setShowAllHands(e.target.checked)}
            style={{ accentColor: '#10b981' }}
          />
          Show all hands
        </label>

        {/* Scores */}
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '12px' }}>
          <div style={{ fontSize: '12px', color: '#9ca3af', marginBottom: '6px' }}>Scores</div>
          {state.players.map((p, i) => (
            <div key={i} style={{
              display: 'flex',
              justifyContent: 'space-between',
              padding: '4px 0',
              fontWeight: i === state.activeSeat ? 700 : 400,
              color: i === state.activeSeat ? '#34d399' : '#e5e7eb',
            }}>
              <span>{paipu.players[i]?.name ?? `Seat ${i}`}</span>
              <span>{p.score.toLocaleString()}</span>
            </div>
          ))}
        </div>

        {/* Keyboard Shortcuts */}
        <div style={{ marginTop: 'auto', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '12px', fontSize: '11px', color: '#6b7280' }}>
          <div>← → Step back/forward</div>
          <div>↑ ↓ Previous/next round</div>
          <div>Space Play/pause</div>
        </div>
      </div>
    </div>
  )
}
