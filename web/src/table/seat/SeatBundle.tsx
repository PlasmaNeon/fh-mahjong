import type { CSSProperties } from 'react'
import { ClosedHand } from './ClosedHand'
import { FlowerZone } from './FlowerZone'
import { OpenMeldZone } from './OpenMeldZone'
import { concealedHandReserveTiles } from './handReserve'
import type { PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type SeatBundleProps = {
  isSelf: boolean
  player: PlayerTableView
  direction: SeatLaneDirection
  interactive?: boolean
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  hiddenSlots?: Set<number>
}

// Canonical (bottom-orientation) bundle: a fixed-width box that pins the closed
// hand to its bottom-left and the exposed stack (flowers above melds) to its
// bottom-right, with the gap filling the middle. The width depends on whether
// this is the self seat (normal tiles) or an opponent (small tiles).
export function SeatBundle({
  isSelf,
  player,
  direction,
  interactive = false,
  liftedTileId = null,
  onHandTileClick,
  isWildTile = () => false,
  hiddenTileIds,
  hiddenSlots,
}: SeatBundleProps) {
  const flowers = player.flowerMelds || []
  const melds = player.openMelds || []
  const hasExposed = flowers.length > 0 || melds.length > 0

  // Reserve the concealed hand's width for its real max size given the called
  // melds (not a blanket 14 tiles). Keeps the exposed stack from shaking on a
  // draw AND from overflowing the bundle span once melds shrink the hand — the
  // latter is what shoved the first meld past the table edge. See handReserve.ts.
  const bundleStyle = {
    '--seat-hand-tiles': concealedHandReserveTiles(melds.length),
  } as CSSProperties

  return (
    <div className={`seat-bundle seat-bundle--${isSelf ? 'self' : 'opp'}`} style={bundleStyle}>
      <ClosedHand
        isSelf={isSelf}
        player={player}
        direction={direction}
        interactive={interactive}
        liftedTileId={liftedTileId}
        onHandTileClick={onHandTileClick}
        isWildTile={isWildTile}
        hiddenTileIds={hiddenTileIds}
        hiddenSlots={hiddenSlots}
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
