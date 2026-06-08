import { DiscardZone } from './DiscardZone'
import { SeatBundle } from './SeatBundle'
import type { PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type PlayerSeatProps = {
  direction: SeatLaneDirection
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  animateDiscardTileIds?: Set<number>
  callableDiscard?: { seat: number; tileId: number } | null
}

export function PlayerSeat({
  direction,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
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
          canDiscard={canDiscard}
          onDiscard={onDiscard}
          isWildTile={isWildTile}
          hiddenTileIds={hiddenTileIds}
        />
      </div>
    </>
  )
}
