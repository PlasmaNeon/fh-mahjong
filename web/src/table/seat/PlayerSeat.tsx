import { DiscardZone } from './DiscardZone'
import { SeatBundle } from './SeatBundle'
import type { HandTileChoice, PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type PlayerSeatProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
  handTileChoice?: HandTileChoice | null
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  hiddenSlots?: Set<number>
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

export function PlayerSeat({
  direction,
  player,
  liftedTileId = null,
  onHandTileClick,
  handTileChoice = null,
  isWildTile = () => false,
  hiddenTileIds,
  hiddenSlots,
  animateDiscardTileIds,
  callableDiscard,
}: PlayerSeatProps) {
  const callableDiscardTileId =
    callableDiscard?.seat === player.seat ? callableDiscard.tileId : null
  // Self is always rendered at the bottom (getSeatDirection(viewSeat, viewSeat) === 'bottom').
  const isSelf = direction === 'bottom'

  return (
    <>
      <DiscardZone
        direction={direction}
        discards={player.discards || []}
        isWildTile={isWildTile}
        animateDiscardTileIds={animateDiscardTileIds}
        callableDiscardTileId={callableDiscardTileId}
        hiddenTileIds={hiddenTileIds}
      />
      <div className={`seat-bundle-pivot seat-bundle-pivot--${direction}`}>
        <SeatBundle
          isSelf={isSelf}
          player={player}
          direction={direction}
          interactive={isSelf && !!onHandTileClick}
          liftedTileId={liftedTileId}
          onHandTileClick={onHandTileClick}
          handTileChoice={handTileChoice}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
          hiddenSlots={hiddenSlots}
        />
      </div>
    </>
  )
}
