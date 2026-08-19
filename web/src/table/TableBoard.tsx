import { useMemo, useRef } from 'react'
import type { ReactNode } from 'react'
import { CenterHud, type CenterHudSeat } from './CenterHud'
import { TileComponent } from './Tile'
import { useTileFlight } from './tileFlight'
import { PlayerSeat } from './seat/PlayerSeat'
import type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  HandTileChoice,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
} from './types'
import { useI18n } from '../i18n/I18nContext'
import { WIND_KANJI } from '../utils/winds'

export { TileComponent }
export type {
  SeatLaneDirection,
  TileLike,
  MeldLike,
  PlayerTableView,
  HudChip,
  RoundResultBreakdownEntry,
  RoundResultPayout,
  RoundResultView,
}

type TableBoardProps = {
  viewSeat: number
  players: PlayerTableView[]
  activeSeat: number
  wildTiles?: TileLike[]
  hudChips?: HudChip[]
  actionBar?: ReactNode
  cornerInfo?: ReactNode
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
  handTileChoice?: HandTileChoice | null
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

const POSITIONS: SeatLaneDirection[] = ['bottom', 'right', 'top', 'left']

export function getSeatDirection(seat: number, viewSeat: number): SeatLaneDirection {
  return POSITIONS[(seat - viewSeat + 4) % 4]
}

export function TableBoard({
  viewSeat,
  players,
  activeSeat,
  wildTiles = [],
  hudChips = [],
  actionBar = null,
  cornerInfo = null,
  liftedTileId = null,
  onHandTileClick,
  handTileChoice = null,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscard = null,
}: TableBoardProps) {
  const { t } = useI18n()
  const tableRef = useRef<HTMLDivElement | null>(null)
  const seatViews = useMemo(() => players.map((player) => ({
    player,
    direction: getSeatDirection(player.seat, viewSeat),
  })), [players, viewSeat])

  const { hiddenTileIds, hiddenHandSlots, flights } = useTileFlight({
    seatViews,
    isWildTile,
    tableRef,
  })

  return (
    <div className="mahjong-table" ref={tableRef}>
      {wildTiles.length > 0 && (
        <div className="wild-tile-corner">
          <div className="wild-tile-corner-main">
            <div className="wild-tile-corner-label">{t('game.wildTile')}</div>
            <div className="wild-tile-corner-face">
              <TileComponent tile={wildTiles[0]} size="small" noGlow />
            </div>
          </div>
          {cornerInfo && <div className="wild-tile-corner-info">{cornerInfo}</div>}
        </div>
      )}

      <CenterHud
        hudChips={hudChips}
        seats={POSITIONS.map((direction) => {
          const seat = players.find((player) => getSeatDirection(player.seat, viewSeat) === direction)
          if (!seat) return null
          return {
            direction,
            windKanji: WIND_KANJI[seat.seatWind ?? 0] || '',
            score: seat.score ?? 0,
            isActive: seat.seat === activeSeat,
          }
        }).filter((seat): seat is CenterHudSeat => seat !== null)}
      />

      {actionBar}

      {seatViews.map(({ player, direction }) => (
        <PlayerSeat
          key={`seat-${player.seat}`}
          direction={direction}
          player={player}
          liftedTileId={liftedTileId}
          onHandTileClick={onHandTileClick}
          handTileChoice={direction === 'bottom' ? handTileChoice : null}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
          hiddenSlots={hiddenHandSlots.get(direction)}
          animateDiscardTileIds={animateDiscardTileIds}
          callableDiscard={callableDiscard}
        />
      ))}

      {flights}
    </div>
  )
}
