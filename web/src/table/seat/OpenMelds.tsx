import { motion } from 'framer-motion'
import { TileComponent } from '../Tile'
import { reorderMeldTiles, tileIdsEqual } from '../meldOrdering'
import type { MeldLike, TileLike } from '../types'

type OpenMeldsProps = {
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
}

// Stable identity so only a newly-formed meld mounts (and plays the entrance).
function meldKey(meld: MeldLike, index: number): string {
  if (meld.calledTileId != null) return `c-${meld.calledTileId}`
  const first = meld.tiles?.[0]
  return first ? `t-${first.id}` : `i-${index}`
}

export function OpenMelds({ melds, isWildTile = () => false }: OpenMeldsProps) {
  return (
    <>
      {melds.map((meld, meldIndex) => (
        <motion.div
          key={meldKey(meld, meldIndex)}
          className="seat-meld-group seat-meld-group--bottom"
          layout
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.18, ease: 'easeOut', layout: { duration: 0.18, ease: 'easeOut' } }}
        >
          {reorderMeldTiles(meld).map((tile, tileIndex) => {
            const isStolen = tileIdsEqual(tile.id, meld.calledTileId)
            return (
              <div key={tileIndex} className={`pov-bottom small ${isStolen ? 'stolen-tile' : ''}`}>
                <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
              </div>
            )
          })}
        </motion.div>
      ))}
    </>
  )
}
