import type { CSSProperties } from 'react'
import { useGameStageLayout } from '../../hooks/useGameStageLayout'
import { TableBoard } from '../../table/TableScene'
import type { PlayerTableView, TileLike } from '../../table/types'

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
    seat: 3,
    seatWind: 4,
    score: 26000,
    closedHand: [],
    handBackCount: 13,
    showClosedHand: false,
    openMelds: [],
    flowerMelds: [],
    discards: discardsFor(1, 8),
    shantenLabel: null,
  },
]

const wildTiles: TileLike[] = [t(4, 6)]

export default function TableSample() {
  const stageLayout = useGameStageLayout()

  const stageShellStyle = {
    '--game-stage-scaled-width': `${stageLayout.scaledWidth}px`,
    '--game-stage-scaled-height': `${stageLayout.scaledHeight}px`,
    '--game-stage-available-width': `${stageLayout.availableWidth}px`,
    '--game-stage-available-height': `${stageLayout.availableHeight}px`,
  } as CSSProperties

  const stageStyle = {
    width: `${stageLayout.stageWidth}px`,
    height: `${stageLayout.stageHeight}px`,
    zoom: stageLayout.scale,
  } as CSSProperties

  return (
    <div className="stage-rotator">
      <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
        <div className="game-stage-frame">
          <div
            className="game-stage"
            data-compact={stageLayout.compact ? 'true' : undefined}
            style={stageStyle}
          >
            <TableBoard viewSeat={0} players={players} activeSeat={0} wildTiles={wildTiles} />
          </div>
        </div>
      </div>
    </div>
  )
}
