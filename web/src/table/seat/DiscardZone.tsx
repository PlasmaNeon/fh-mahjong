import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { tileIdsEqual } from '../meldOrdering'
import type { SeatLaneDirection, TileLike } from '../types'

type DiscardZoneProps = {
  direction: SeatLaneDirection
  discards: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
  animateDiscardTileIds?: Set<number>
  callableDiscardTileId?: number | null
  hiddenTileIds?: Set<number>
}

export function DiscardZone({
  direction,
  discards,
  isWildTile = () => false,
  animateDiscardTileIds,
  callableDiscardTileId = null,
  hiddenTileIds,
}: DiscardZoneProps) {
  return (
    <div className={`discard-lane discard-lane--${direction} ${discards.length === 0 ? 'discard-lane--empty' : ''}`}>
      {discards.length === 0 ? (
        <div className="discard-lane__placeholder" aria-hidden="true" />
      ) : (
        discards.map((tile) => {
          const isNewDiscard = animateDiscardTileIds?.has(tile.id) ?? false
          const isCallableDiscard = tileIdsEqual(callableDiscardTileId, tile.id)

          return (
            <motion.div
              key={tile.id}
              // No scale entrance: the tile is hidden behind the flight overlay
              // while it animates in, so a scale here was invisible yet corrupted
              // the flight's destination measurement (getBoundingClientRect reads
              // the scaled-down box), making the landed tile snap to full size.
              initial={isNewDiscard ? { opacity: 0 } : false}
              animate={{ opacity: 1 }}
              transition={{
                opacity: { duration: 0.08, ease: 'easeOut' },
              }}
              className={`discard-lane__tile ${isCallableDiscard ? 'discard-lane__tile--callable' : ''}`}
              style={hiddenTileIds?.has(tile.id) ? { visibility: 'hidden' } : undefined}
            >
              <motion.div
                layout="position"
                transition={{
                  layout: { duration: 0.18, ease: 'easeOut' },
                }}
                className={`pov-${direction} small`}
                data-board-tile-id={tile.id}
                data-board-tile-role="discard"
              >
                <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} noGlow={isCallableDiscard} />
              </motion.div>
            </motion.div>
          )
        })
      )}
    </div>
  )
}
