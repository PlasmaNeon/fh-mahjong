import { useState } from 'react'
import { useGameStageLayout } from '../../table/stage/useGameStageLayout'
import { game } from '../../proto/game'
import { TableBoard } from '../../table/TableBoard'
import { TableRoundResultOverlay } from '../../table/TableRoundResultOverlay'
import type { MeldLike, PlayerTableView, TileLike } from '../../table/types'
import { GameDialog } from '../../theme'
import { eligibleChiiTileIds, resolveChiiTileClick } from '../game/chiiChoice'

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

const wildTiles: TileLike[] = [t(4, 6)]
const demoChiiActions = [
  {
    type: game.ActionType.ACTION_CHII,
    meldTiles: [selfConcealed[0], selfConcealed[1]],
  },
  {
    type: game.ActionType.ACTION_CHII,
    meldTiles: [selfConcealed[1], selfConcealed[3]],
  },
]

export default function TableSample() {
  const stageLayout = useGameStageLayout()
  const [fixture, setFixture] = useState<Fixture>('idle')
  const [liftedTileId, setLiftedTileId] = useState<number | null>(null)
  const [demoChiiChoiceOpen, setDemoChiiChoiceOpen] = useState(false)
  const [demoChiiSelectedTileId, setDemoChiiSelectedTileId] = useState<number | null>(null)
  const handInteractive = fixture === 'active' || fixture === 'called-hand'
  const tablePlayers = fixture === 'called-hand' ? calledPlayers : players
  const demoChiiEligibleIds = demoChiiChoiceOpen
    ? eligibleChiiTileIds(demoChiiActions, selfConcealed, demoChiiSelectedTileId)
    : new Set<number>()
  const demoHandChoice = demoChiiChoiceOpen
    ? {
        eligibleTileIds: demoChiiEligibleIds,
        selectedTileIds: demoChiiSelectedTileId == null
          ? new Set<number>()
          : new Set<number>([demoChiiSelectedTileId]),
      }
    : null

  const { shellStyle: stageShellStyle, stageStyle } = stageLayout

  const actionBar = fixture === 'active' || fixture === 'interrupt' || fixture === 'multi-chii' ? (
    <div className="table-action-bar">
      {fixture === 'interrupt' && <button className="table-action-btn table-action-btn-pon">PON</button>}
      {fixture === 'interrupt' && <button className="table-action-btn table-action-btn-ron">RON!</button>}
      {fixture === 'multi-chii' && demoChiiChoiceOpen && (
        <div className="chii-choice-prompt" role="status">
          <span className="chii-choice-prompt__call">CHII</span>
          <span className="chii-choice-prompt__instruction">
            {demoChiiSelectedTileId == null ? 'Pick the first tile' : 'Pick the matching tile'}
          </span>
          <button
            type="button"
            className="chii-choice-prompt__cancel"
            onClick={() => {
              setDemoChiiChoiceOpen(false)
              setDemoChiiSelectedTileId(null)
            }}
          >
            Cancel
          </button>
        </div>
      )}
      {fixture === 'multi-chii' && !demoChiiChoiceOpen && (
        <button
          className="table-action-btn table-action-btn-chii"
          onClick={() => setDemoChiiChoiceOpen(true)}
        >
          CHII
        </button>
      )}
      {fixture === 'multi-chii' && !demoChiiChoiceOpen && <button className="table-action-btn table-action-btn-pon">PON</button>}
      {fixture === 'active' && <button className="table-action-btn table-action-btn-kan">KAN</button>}
      {fixture === 'active' && <button className="table-action-btn table-action-btn-tsumo">TSUMO!</button>}
      {!(fixture === 'multi-chii' && demoChiiChoiceOpen) && <button className="table-action-btn table-action-btn-skip">SKIP</button>}
    </div>
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
    <div className="stage-rotator">
      <FixtureToolbar
        value={fixture}
        onChange={(nextFixture) => {
          setFixture(nextFixture)
          setLiftedTileId(null)
          setDemoChiiChoiceOpen(false)
          setDemoChiiSelectedTileId(null)
        }}
      />
      <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
        <div className="game-stage-frame">
          <div
            className="game-stage"
            data-discard-mode={handInteractive || demoChiiChoiceOpen ? 'double' : undefined}
            data-chii-choice={demoChiiChoiceOpen ? 'true' : undefined}
            data-compact={stageLayout.compact ? 'true' : undefined}
            style={stageStyle}
          >
            <TableBoard
              viewSeat={0}
              players={tablePlayers}
              activeSeat={fixture === 'interrupt' || fixture === 'callable' || fixture === 'multi-chii' ? 1 : 0}
              wildTiles={wildTiles}
              hudChips={[{ label: 'East 2' }, { label: '58 tiles' }]}
              actionBar={actionBar}
              liftedTileId={liftedTileId}
              onHandTileClick={demoChiiChoiceOpen
                ? (tile) => {
                    const result = resolveChiiTileClick({
                      actions: demoChiiActions,
                      hand: selfConcealed,
                      selectedTileId: demoChiiSelectedTileId,
                      clickedTile: tile,
                    })
                    if (result.kind === 'select') setDemoChiiSelectedTileId(result.tileId)
                    if (result.kind === 'submit') {
                      setDemoChiiChoiceOpen(false)
                      setDemoChiiSelectedTileId(null)
                    }
                  }
                : handInteractive
                  ? (tile) => setLiftedTileId((current) => current === tile.id ? null : tile.id)
                  : undefined}
              handTileChoice={demoHandChoice}
              callableDiscard={fixture === 'callable' || fixture === 'multi-chii' ? { seat: 1, tileId: callableTile.id } : null}
              cornerInfo={<div className="wild-tile-corner-info-tag">Fenghua</div>}
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

type Fixture = 'idle' | 'active' | 'called-hand' | 'interrupt' | 'multi-chii' | 'callable' | 'round-result' | 'match-end' | 'exit'

const FIXTURES: Array<{ value: Fixture; label: string }> = [
  { value: 'idle', label: 'Idle' },
  { value: 'active', label: 'Active turn' },
  { value: 'called-hand', label: 'Called hand' },
  { value: 'interrupt', label: 'Interrupt' },
  { value: 'multi-chii', label: 'Multi CHII' },
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
