import './tableSampleUnified.css'
import { useState } from 'react'
import { useGameStageLayout } from '../../table/stage/useGameStageLayout'
import { game } from '../../proto/game'
import { TableBoard } from '../../table/TableBoard'
import { TableRoundResultOverlay } from '../../table/TableRoundResultOverlay'
import type { MeldLike, PlayerTableView, TileLike } from '../../table/types'
import { GameDialog } from '../../theme'
import { CallActionBar } from '../game/CallActionBar'

// Dev-only sample page: renders the real TableBoard with mock game data so the
// table layout can be seen and iterated without a live match. Route: /tools/table-sample.
// Suits: 1=sou, 2=pin, 3=man, 4=jihai, 5=flower.

let nextId = 0
const t = (suit: number, value: number): TileLike => ({ id: nextId++, suit, value })

const selfDrawn = t(3, 7)
const selfConcealed: TileLike[] = [
  t(1, 1), t(1, 2), t(1, 3), t(1, 4),
  t(2, 2), t(2, 5), t(2, 8),
  t(3, 3), t(3, 3), t(3, 6),
  t(4, 1), t(4, 1), t(4, 5),
]

const discardsFor = (seed: number, n: number): TileLike[] =>
  Array.from({ length: n }, (_, i) => t(((seed + i) % 3) + 1, ((seed * 2 + i) % 9) + 1))

const pon = (suit: number, value: number, calledDirection: number): MeldLike => {
  const tiles = [t(suit, value), t(suit, value), t(suit, value)]
  const stolenIndex = calledDirection === 3 ? 0 : calledDirection === 2 ? 1 : 2
  return { tiles, calledTileId: tiles[stolenIndex].id, calledDirection }
}

const players: PlayerTableView[] = [
  {
    seat: 0,
    seatWind: 1,
    score: 24000,
    closedHand: [...selfConcealed, selfDrawn],
    handBackCount: 14,
    showClosedHand: true,
    drawnTileId: selfDrawn.id,
    openMelds: [],
    flowerMelds: [t(5, 1), t(5, 5)],
    discards: discardsFor(0, 9),
    shantenLabel: '向听: 2',
  },
  {
    seat: 1,
    seatWind: 2,
    score: 25000,
    closedHand: [],
    handBackCount: 13,
    showClosedHand: false,
    openMelds: [],
    flowerMelds: [],
    discards: discardsFor(3, 8),
    shantenLabel: null,
  },
  {
    seat: 2,
    seatWind: 3,
    score: 25000,
    closedHand: [],
    handBackCount: 10,
    showClosedHand: false,
    openMelds: [{ tiles: [t(3, 2), t(3, 2), t(3, 2)], calledTileId: null, calledDirection: 1 }],
    flowerMelds: [t(5, 3)],
    discards: discardsFor(6, 7),
    shantenLabel: null,
  },
  {
    // Left player mid-game: called three melds, so only a few concealed backs
    // remain. Exercises the concealed-hand reservation shrinking with meld count
    // — the regression where the first meld got shoved past the table edge.
    seat: 3,
    seatWind: 4,
    score: 26000,
    closedHand: [],
    handBackCount: 4,
    showClosedHand: false,
    openMelds: [pon(2, 3, 1), pon(2, 6, 2), pon(4, 1, 3)],
    flowerMelds: [t(5, 2)],
    discards: discardsFor(1, 8),
    shantenLabel: null,
  },
]

const calledPlayers: PlayerTableView[] = players.map((player) => player.seat === 0
  ? {
      ...player,
      closedHand: [...selfConcealed.slice(0, 10), selfDrawn],
      handBackCount: 11,
      openMelds: [pon(1, 9, 1)],
    }
  : player)

const demoKanActions = [1, 2, 3, 4].map(value => ({ type: game.ActionType.ACTION_KAN, meldTiles: Array.from({length: 4}, () => t(1, value)) }))

const wildTiles: TileLike[] = [t(4, 6)]
const demoFifthSou = t(1, 5)
const demoPonTiles = [selfConcealed[2], t(1, 3)]
const demoCalledTile = t(1, 3)
const demoChiiPlayers = players.map(player => player.seat === 0 ? { ...player, drawnTileId: null, closedHand: selfConcealed.map((tile, index) => index === 8 ? demoPonTiles[1] : index === 9 ? demoFifthSou : tile) } : player.seat === 3 ? { ...player, discards: [...(player.discards ?? []).slice(0, -1), demoCalledTile] } : player)
const demoChiiActions = [
  {
    type: game.ActionType.ACTION_CHII,
    meldTiles: [selfConcealed[0], selfConcealed[1]],
  },
  {
    type: game.ActionType.ACTION_CHII,
    meldTiles: [selfConcealed[1], selfConcealed[3]],
  },
  { type: game.ActionType.ACTION_CHII, meldTiles: [selfConcealed[3], demoFifthSou] },
]

// Dense synthetic state for geometry checks; not a rules-engine scenario.
const crowdedPlayers = players.map((player, seat) => ({
  ...player,
  discards: discardsFor(seat, 30),
}))

const flowerHeavyPlayers = players.map(player => ({
  ...player,
  openMelds: [],
  closedHand: player.seat === 0 ? [...selfConcealed, selfDrawn] : [],
  handBackCount: 14,
  flowerMelds: Array.from({ length: 8 }, (_, index) => t(5, index + 1)),
}))

const meldHeavyPlayers = players.map((player, seat) => ({
  ...player,
  closedHand: seat === 0 ? [t(4, 5), t(4, 5)] : [],
  handBackCount: 2,
  drawnTileId: null,
  openMelds: Array.from({ length: 4 }, (_, index) => {
    const tiles = Array.from({ length: 4 }, () => t((index % 3) + 1, index + 1))
    return { tiles, calledTileId: tiles[0].id, calledDirection: 1 }
  }),
  flowerMelds: Array.from({ length: 8 }, (_, index) => t(5, index + 1)),
}))

export default function TableSample() {
  const previewParams = new URLSearchParams(window.location.search)
  const initialFixture = previewParams.get('fixture')
  const cleanPreview = previewParams.get('clean') === '1'
  const rotatedPreview = previewParams.get('rotate') === '1'

  const unifiedPreview = previewParams.get('layout') === 'unified'
  const stageLayout = useGameStageLayout(unifiedPreview ? { baseHeight: 720, compactMaxHeight: Infinity } : {})
  const [fixture, setFixture] = useState<Fixture>(FIXTURES.some(f => f.value === initialFixture) ? initialFixture as Fixture : 'idle')
  const [liftedTileId, setLiftedTileId] = useState<number | null>(null)
  const [demoSubmitted, setDemoSubmitted] = useState<string | null>(null)
  const handInteractive = fixture === 'active' || fixture === 'called-hand' || fixture === 'crowded' || fixture === 'wild-hand' || fixture === 'flower-heavy'
  const tablePlayers = fixture === 'multi-chii' ? demoChiiPlayers : fixture === 'flower-heavy' ? flowerHeavyPlayers : fixture === 'called-hand' ? calledPlayers : fixture === 'crowded' ? crowdedPlayers : fixture === 'meld-heavy' ? meldHeavyPlayers : players
  const { shellStyle: stageShellStyle, stageStyle } = stageLayout

  const actionBar = ['active', 'crowded', 'interrupt', 'multi-chii', 'multi-kan'].includes(fixture) ? (
    <CallActionBar key={fixture} contextKey={fixture}
      actions={fixture === 'multi-chii' ? [...demoChiiActions, { type: game.ActionType.ACTION_PON, meldTiles: demoPonTiles }]
        : fixture === 'multi-kan' ? demoKanActions
        : fixture === 'interrupt' ? [{ type: game.ActionType.ACTION_PON }, { type: game.ActionType.ACTION_RON }]
        : [{ type: game.ActionType.ACTION_KAN }, { type: game.ActionType.ACTION_TSUMO }]}
      allowPass={fixture !== 'multi-kan'}
      onAction={action => setDemoSubmitted(`${game.ActionType[action.type!]}: ${(action.meldTiles ?? []).map(tile => tile.id).join(',')}`)}
    />
  ) : null

  const roundResult = fixture === 'round-result' ? {
    isDraw: false,
    winType: 'tsumo' as const,
    winnerLabel: 'East wins',
    closedHand: selfConcealed.slice(0, 10),
    winTile: selfDrawn,
    winningMelds: [{ tiles: [t(1, 5), t(1, 6), t(1, 7)] }],
    flowers: [t(5, 1), t(5, 5)],
    breakdown: [
      { name: 'Base point', points: 1 },
      { name: 'Tsumo', points: 1 },
      { name: 'No wilds', points: 1 },
    ],
    totalScore: 3,
    payouts: [
      { seat: 0, label: 'East', amount: 18, readyLabel: 'Ready', readyActive: true },
      { seat: 1, label: 'South', amount: -6 },
      { seat: 2, label: 'West', amount: -6 },
      { seat: 3, label: 'North', amount: -6 },
    ],
    actions: <><button className="round-result-action-btn round-result-action-btn-ready">Ready</button><button className="round-result-action-btn round-result-action-btn-exit">Exit</button></>,
  } : null

  const southPlayer = players[1]!
  const southDiscards = southPlayer.discards ?? []
  const callableTile = southDiscards[southDiscards.length - 1]!

  return (
    <div className="stage-rotator" style={rotatedPreview ? {
      position: 'fixed', top: '50%', left: '50%', width: '100dvh', height: '100dvw',
      transform: 'translate(-50%, -50%) rotate(90deg)', transformOrigin: 'center center', overflow: 'hidden',
    } : undefined}>
      {!cleanPreview && <FixtureToolbar
        value={fixture}
        onChange={(nextFixture) => {
          setFixture(nextFixture)
          setLiftedTileId(null)
          setDemoSubmitted(null)
        }}
      />}
      {demoSubmitted && !cleanPreview && <output aria-live="polite">{demoSubmitted}</output>}
      <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
        <div className="game-stage-frame">
          <div
            className="game-stage"
            data-unified={unifiedPreview ? 'true' : undefined}
            data-discard-mode={handInteractive ? 'double' : undefined}
            data-compact={stageLayout.compact ? 'true' : undefined}
            style={stageStyle}
          >
            <TableBoard
              viewSeat={0}
              players={tablePlayers}
              activeSeat={fixture === 'multi-chii' ? 3 : fixture === 'interrupt' || fixture === 'callable' ? 1 : 0}
              wildTiles={fixture === 'wild-hand' ? [selfConcealed[10]] : wildTiles}
              isWildTile={(tile) => {
                const indicator = fixture === 'wild-hand' ? selfConcealed[10] : wildTiles[0]
                return tile.suit === indicator.suit && tile.value === indicator.value
              }}
              hudChips={[{ label: 'East 2' }, { label: '58 tiles' }]}
              actionBar={actionBar}
              liftedTileId={liftedTileId}
              onHandTileClick={handInteractive ? (tile) => setLiftedTileId(current => current === tile.id ? null : tile.id) : undefined}
              callableDiscard={fixture === 'multi-chii' ? { seat: 3, tileId: demoCalledTile.id } : fixture === 'callable' ? { seat: 1, tileId: callableTile.id } : null}
            />
          </div>
        </div>
        <TableRoundResultOverlay result={roundResult} />
        {fixture === 'match-end' && <GameDialog eyebrow="Chongci · Final hand 8" title="Match over" tone="win" actions={<><button className="ldg-btn">Watch replay</button><button className="ldg-btn ldg-btn--primary">Leave table</button></>}><div className="match-standings"><table><thead><tr><th>Rank</th><th>Player</th><th>Score</th><th>Δ</th></tr></thead><tbody><tr><td className="match-standings__rank">1st</td><td>East</td><td>31,200</td><td className="match-standings__gain">+6,200</td></tr><tr><td>2nd</td><td>North</td><td>25,800</td><td className="match-standings__gain">+800</td></tr><tr><td>3rd</td><td>South</td><td>23,100</td><td className="match-standings__loss">−1,900</td></tr></tbody></table></div></GameDialog>}
        {fixture === 'exit' && <GameDialog eyebrow="Your seat will stay warm" title="Leave the match?" tone="danger" actions={<><button className="ldg-btn ldg-btn--danger">Leave match</button><button className="ldg-btn">Stay at table</button></>}><p>A bot will play your seat while you are away. You can rejoin from the room.</p></GameDialog>}
      </div>
    </div>
  )
}

type Fixture = 'multi-kan' | 'flower-heavy' | 'wild-hand' | 'meld-heavy' | 'crowded' | 'idle' | 'active' | 'called-hand' | 'interrupt' | 'multi-chii' | 'callable' | 'round-result' | 'match-end' | 'exit'

const FIXTURES: Array<{ value: Fixture; label: string }> = [
  { value: 'idle', label: 'Idle' },
  { value: 'crowded', label: 'Crowded table' },
  { value: 'meld-heavy', label: 'Four kans' },
  { value: 'active', label: 'Active turn' },
  { value: 'wild-hand', label: 'Wild tiles in hand' },
  { value: 'flower-heavy', label: 'Eight flowers' },
  { value: 'called-hand', label: 'Called hand' },
  { value: 'interrupt', label: 'Interrupt' },
  { value: 'multi-chii', label: 'Multi CHII' },
  { value: 'multi-kan', label: 'Multi KAN' },
  { value: 'callable', label: 'Callable' },
  { value: 'round-result', label: 'Round result' },
  { value: 'match-end', label: 'Match end' },
  { value: 'exit', label: 'Exit dialog' },
]

function FixtureToolbar({ value, onChange }: { value: Fixture; onChange: (value: Fixture) => void }) {
  return (
    <nav className="fixture-toolbar" aria-label="Table fixture">
      <span>UI fixtures</span>
      {FIXTURES.map((fixture) => (
        <button key={fixture.value} type="button" className={fixture.value === value ? 'is-active' : ''} onClick={() => onChange(fixture.value)}>
          {fixture.label}
        </button>
      ))}
    </nav>
  )
}
