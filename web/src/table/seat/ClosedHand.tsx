import { useRef } from 'react'
import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { computeStableDisplayOrder } from '../handOrdering'
import { tileIdsEqual } from '../meldOrdering'
import type { PlayerTableView, SeatLaneDirection, TileLike } from '../types'

type ClosedHandProps = {
  isSelf: boolean
  player: PlayerTableView
  direction: SeatLaneDirection
  canDiscard?: boolean
  onDiscard?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
}

// Canonical (bottom-orientation) draw-in offset; the bundle's rotation reorients
// it per seat.
const DRAW_OFFSET = { x: 0, y: -30 }

export function ClosedHand({
  isSelf,
  player,
  direction,
  canDiscard = false,
  onDiscard,
  isWildTile = () => false,
  hiddenTileIds,
}: ClosedHandProps) {
  const lastDrawnTileId = useRef<number | null>(null)
  const displayOrderRef = useRef<number[] | null>(null)
  const showClosedHand = player.showClosedHand !== false
  const handTiles = player.closedHand || []
  const handBackCount = player.handBackCount ?? handTiles.length

  const hasDrawnTile = player.drawnTileId != null
  const baseTiles = [...handTiles]
  let drawnTile: TileLike | null = null

  if (hasDrawnTile) {
    const drawnTileIndex = baseTiles.findIndex((tile) => tileIdsEqual(tile.id, player.drawnTileId))
    if (drawnTileIndex !== -1) {
      drawnTile = baseTiles.splice(drawnTileIndex, 1)[0]
    }
  }

  if (drawnTile) {
    lastDrawnTileId.current = drawnTile.id
  }

  const nextDisplayOrder = computeStableDisplayOrder(baseTiles, displayOrderRef.current)
  displayOrderRef.current = nextDisplayOrder
  const baseTileMap = new Map(baseTiles.map((t) => [t.id, t]))
  const sortedBaseTiles = nextDisplayOrder
    .map((id) => baseTileMap.get(id))
    .filter((t): t is TileLike => t != null)

  const renderHandTile = (tile: TileLike, { isCurrentDrawnSlot = false }: { isCurrentDrawnSlot?: boolean } = {}) => {
    // True only on the render right after a discard, for the tile that was just
    // drawn and is now merging into the row from the separate drawn slot.
    const isMergingDrawnTile = isSelf && lastDrawnTileId.current === tile.id && !hasDrawnTile
    const isHiddenByOverlay = hiddenTileIds?.has(tile.id) ?? false

    return (
      <motion.div
        // Only the self seat (bottom, never rotated) animates layout. The shared
        // layoutId lets the just-drawn tile slide from the drawn slot into its
        // sorted in-row slot across the DOM re-parent instead of popping, and
        // also drives the normal sibling-shift. Opponents sit inside a rotated
        // pivot where framer mis-projects the layout delta and tiles jitter, so
        // they render statically (see fix #76).
        layoutId={isSelf ? `closed-hand-tile-${tile.id}` : undefined}
        key={tile.id}
        style={{
          // The merging tile slides over its neighbours, so keep it on top.
          zIndex: isMergingDrawnTile ? 30 : 10,
          visibility: isHiddenByOverlay ? 'hidden' : undefined,
        }}
        transition={{
          layout: {
            duration: isMergingDrawnTile ? 0.28 : 0.25,
            ease: 'easeInOut',
          },
        }}
        className={`pov-bottom ${!isSelf ? 'small' : ''} ${isCurrentDrawnSlot ? 'drawn-tile' : ''}`}
        data-board-tile-id={isCurrentDrawnSlot ? undefined : tile.id}
        data-board-tile-role={isCurrentDrawnSlot ? undefined : 'hand'}
      >
        <TileComponent
          tile={tile}
          isInteractive={canDiscard}
          isWild={isWildTile(tile)}
          onDiscard={onDiscard}
          size={isSelf ? 'normal' : 'small'}
        />
      </motion.div>
    )
  }

  return (
    <div className="zone-hand">
      <div className="seat-hand seat-hand--bottom">
        <div className="seat-hand__tiles seat-hand__tiles--bottom" data-seat-hand-origin={direction}>
          {showClosedHand ? (
            sortedBaseTiles.map((tile) => renderHandTile(tile))
          ) : (
            Array(handBackCount).fill(null).map((_, index) => (
              <div key={`back-${index}`} className="pov-bottom small">
                <div className="mahjong-tile-back small" />
              </div>
            ))
          )}
        </div>

        {showClosedHand && drawnTile && (
          <div
            className="seat-hand__drawn-slot seat-hand__drawn-slot--bottom"
            data-board-tile-id={drawnTile.id}
            data-board-tile-role="drawn"
          >
            <motion.div
              initial={{ opacity: 0, ...DRAW_OFFSET }}
              animate={{ opacity: 1, x: 0, y: 0 }}
              transition={{
                opacity: { duration: 0.16, ease: 'easeOut' },
                x: { duration: 0.22, ease: 'easeOut' },
                y: { duration: 0.22, ease: 'easeOut' },
              }}
            >
              {renderHandTile(drawnTile, { isCurrentDrawnSlot: true })}
            </motion.div>
          </div>
        )}
      </div>

      {isSelf && player.shantenLabel && (
        <div className="shanten-indicator">{player.shantenLabel}</div>
      )}
    </div>
  )
}
