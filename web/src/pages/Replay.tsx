// @ts-nocheck
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getApiUrl } from '../config'
import { getTileSvgName, getTileName, getSuitOrder, preloadAllTileSvgs } from '../utils/tileUtils'
import type { Paipu } from './replayTypes'
import { tileObjectFromId } from './replayTypes'
import { ReplayEngine, ReplayTile, ReplayMeld, ReplayState } from './replayEngine'

function TileImg({ tile, size = 'normal', isWild = false }: { tile: ReplayTile, size?: 'normal' | 'small', isWild?: boolean }) {
  const svgName = getTileSvgName(tile)
  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${size === 'small' ? 'small' : ''}`}
      style={{
        padding: 0, border: 'none', backgroundColor: 'transparent',
        boxShadow: isWild ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
        position: 'relative',
      }}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
        draggable="false"
      />
    </div>
  )
}

function getPositionForSeat(seat: number, viewSeat: number): string {
  const positions = ['bottom', 'right', 'top', 'left']
  return positions[(seat - viewSeat + 4) % 4]
}

function sortHand(tiles: ReplayTile[]): ReplayTile[] {
  return [...tiles].sort((a, b) => {
    const sa = getSuitOrder(a.suit), sb = getSuitOrder(b.suit)
    if (sa !== sb) return sa - sb
    if (a.value !== b.value) return a.value - b.value
    return a.id - b.id
  })
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

  const windKanji = ['', '東', '南', '西', '北']

  return (
    <div style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      {/* Table */}
      <div style={{ flex: 1, position: 'relative' }}>
        <div className="mahjong-table">
          {/* Wild tile corner */}
          {state.wildTiles && state.wildTiles.length > 0 && (
            <div className="wild-tile-corner">
              <div className="wild-tile-corner-label">Wild Tile</div>
              <div className="wild-tile-corner-face">
                <TileImg tile={state.wildTiles[0]} />
              </div>
            </div>
          )}

          {/* Center info */}
          <div className="center-info text-white text-center">
            {[0, 1, 2, 3].map(seat => {
              const pos = getPositionForSeat(seat, viewSeat)
              const player = paipu.players[seat]
              const isActive = seat === state.activeSeat
              const seatWind = ((seat - state.players[engine.currentRound.dealer]?.seat + 4) % 4) + 1
              return (
                <div key={seat} className={`center-wind center-wind-${pos} ${isActive ? 'center-wind-active' : ''}`}>
                  {windKanji[seatWind] || ''}
                </div>
              )
            })}
            <div className="center-info-stats">
              <span className="center-info-chip">Round {state.roundNum}</span>
              <span className="center-info-chip">
                {state.actionIndex + 1}/{state.totalActions}
              </span>
            </div>
          </div>

          {/* Render each player */}
          {[0, 1, 2, 3].map(seat => {
            const pos = getPositionForSeat(seat, viewSeat)
            const p = state.players[seat]
            const isViewingSeat = seat === viewSeat
            const canSee = showAllHands || isViewingSeat

            return (
              <div key={seat} className="contents">
                {/* Discard Pool */}
                <div className={`discard-pool discard-pool-${pos} ${p.discards.length === 0 ? 'discard-pool-empty' : ''}`}>
                  {p.discards.length === 0 ? (
                    <div className="discard-pool-placeholder" aria-hidden="true" />
                  ) : (
                    p.discards.map((t, i) => (
                      <div key={t.id} className={`discard-pool-tile pov-${pos} small`}>
                        <TileImg tile={t} size="small" isWild={isWild(t)} />
                      </div>
                    ))
                  )}
                </div>

                {/* Hand + Melds */}
                <div className={`hand-container-${pos} ${isViewingSeat ? 'hand-container-self' : ''}`}>
                  <div className={`hand-main-block hand-main-block-${pos} ${isViewingSeat ? 'hand-main-block-self' : ''}`}>
                    <div className={`hand-inner hand-inner-${pos}`}>
                      {canSee ? (
                        sortHand(p.hand).map(t => (
                          <div key={t.id} className={`pov-${pos} ${!isViewingSeat ? 'small' : ''}`}>
                            <TileImg tile={t} size={isViewingSeat ? 'normal' : 'small'} isWild={isWild(t)} />
                          </div>
                        ))
                      ) : (
                        Array(p.hand.length).fill(0).map((_, i) => (
                          <div key={`back-${i}`} className={`pov-${pos} small`}>
                            <div className="mahjong-tile-back small" />
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Open Melds */}
                  <div className={`melds-container-${pos}`}>
                    <div className={`melds-main melds-main-${pos}`}>
                      {((pos === 'bottom' || pos === 'top') ? [...p.melds].reverse() : p.melds).map((m, mIdx) => (
                        <div key={mIdx} className={`meld-group meld-group-${pos}`}>
                          {m.tiles.map((t, tIdx) => (
                            <div key={tIdx} className={`pov-${pos} small`}>
                              <TileImg tile={t} size="small" isWild={isWild(t)} />
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                    {p.flowers.length > 0 && (
                      <div className={`flowers-container flowers-container-${pos}`}>
                        {p.flowers.map((t, fi) => (
                          <div key={`f-${fi}`} className={`pov-${pos} small`}>
                            <TileImg tile={t} size="small" isWild={isWild(t)} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}

          {/* Round Result Overlay */}
          {state.isRoundEnd && state.result && (
            <div className="round-result-overlay">
              <div className="round-result-modal" style={{ maxWidth: '600px' }}>
                {state.result.type === 'draw' ? (
                  <div className="round-result-draw">
                    <div className="round-result-badge round-result-badge-draw">Draw</div>
                    <h2 className="round-result-title round-result-title-draw">Exhaustive Draw</h2>
                  </div>
                ) : (
                  <>
                    <div className="round-result-header-line">
                      <div className={`round-result-badge ${state.result.winType === 'tsumo' ? 'round-result-badge-tsumo' : 'round-result-badge-ron'}`}>
                        {state.result.winType === 'tsumo' ? 'TSUMO!' : 'RON!'}
                      </div>
                      <h2 className={`round-result-title ${state.result.winType === 'tsumo' ? 'round-result-title-tsumo' : 'round-result-title-ron'}`}>
                        {paipu.players[state.result.winner ?? 0]?.name ?? `Seat ${state.result.winner}`} wins
                      </h2>
                    </div>
                    {state.result.winType === 'ron' && state.result.discarder != null && (
                      <p className="round-result-subtitle">
                        From {paipu.players[state.result.discarder]?.name ?? `Seat ${state.result.discarder}`}
                      </p>
                    )}

                    {/* Winning Hand */}
                    {state.result.hand && (
                      <div className="round-result-panel round-result-panel-plain round-result-hand-panel">
                        <div className="round-result-hand-row">
                          <div className="round-result-closed-hand">
                            {state.result.hand.map(tileObjectFromId).sort((a, b) => {
                              const sa = getSuitOrder(a.suit), sb = getSuitOrder(b.suit)
                              return sa !== sb ? sa - sb : a.value - b.value
                            }).map((t, i) => (
                              <div key={i} className="pov-bottom small">
                                <TileImg tile={t} size="small" isWild={isWild(t)} />
                              </div>
                            ))}
                            {state.result.winTile != null && (
                              <div className="pov-bottom small round-result-win-tile">
                                <TileImg tile={tileObjectFromId(state.result.winTile)} size="small" isWild={isWild(tileObjectFromId(state.result.winTile))} />
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Score Breakdown */}
                    {state.result.breakdown && state.result.breakdown.length > 0 && (
                      <div className="round-result-panel">
                        <div className="round-result-breakdown-scroll">
                          <div className="round-result-breakdown-grid">
                            {state.result.breakdown.map((entry, i) => (
                              <div key={i} className="round-result-breakdown-item">
                                <div className="round-result-breakdown-name">{entry.name}</div>
                                <div className="round-result-breakdown-points">+{entry.points}</div>
                              </div>
                            ))}
                            <div className="round-result-breakdown-total-row">
                              <div>Total</div>
                              <div>{state.result.totalScore}</div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )}

                    {/* Score Changes */}
                    <div className="round-result-panel round-result-panel-plain">
                      <div className="round-result-payout-grid">
                        {state.result.scoreChanges.map((amount, i) => (
                          <div key={i} className={`round-result-payout-cell ${amount > 0 ? 'round-result-payout-positive' : 'round-result-payout-negative'}`}>
                            <div className="round-result-payout-seat">{paipu.players[i]?.name ?? `Seat ${i}`}</div>
                            <div className="round-result-payout-amount">
                              {amount > 0 ? '+' : ''}{amount}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Control Panel */}
      <div style={{
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
            { label: '▶|', action: () => { if (engine.stepForward()) setVersion(v => v + 1) } },
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
