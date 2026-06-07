import { ClosedHand } from './ClosedHand'
import { FlowerZone } from './FlowerZone'
import { OpenMeldZone } from './OpenMeldZone'
import type { PlayerTableView, TileLike } from '../types'

type SeatBundleProps = {
  isSelf: boolean
  player: PlayerTableView
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

// Canonical (bottom-orientation) bundle: a fixed-width box that pins the closed
// hand to its bottom-left and the exposed stack (flowers above melds) to its
// bottom-right, with the gap filling the middle. The width depends on whether
// this is the self seat (normal tiles) or an opponent (small tiles).
export function SeatBundle({
  isSelf,
  player,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: SeatBundleProps) {
  const flowers = player.flowerMelds || []
  const melds = player.openMelds || []
  const hasExposed = flowers.length > 0 || melds.length > 0

  return (
    <div className={`seat-bundle seat-bundle--${isSelf ? 'self' : 'opp'}`}>
      <ClosedHand
        isSelf={isSelf}
        player={player}
        canDiscard={canDiscard}
        onDiscard={onDiscard}
        isWildTile={isWildTile}
        hiddenTileIds={hiddenTileIds}
      />
      {hasExposed && (
        <div className="seat-bundle__exposed">
          <FlowerZone flowers={flowers} isWildTile={isWildTile} />
          <OpenMeldZone melds={melds} isWildTile={isWildTile} animateLayout={isSelf} />
        </div>
      )}
    </div>
  )
}
