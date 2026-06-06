import { TileComponent } from '../Tile'
import type { TileLike } from '../types'

type FlowerZoneProps = {
  flowers: TileLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function FlowerZone({ flowers, isWildTile = () => false }: FlowerZoneProps) {
  if (!flowers || flowers.length === 0) return null
  return (
    <div className="zone-flowers">
      {flowers.map((tile, index) => (
        <div key={`f-${tile.id}-${index}`} className="pov-bottom small">
          <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
        </div>
      ))}
    </div>
  )
}
