import { OpenMelds } from './OpenMelds'
import type { MeldLike, TileLike } from '../types'

type OpenMeldZoneProps = {
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
}

export function OpenMeldZone({ melds, isWildTile }: OpenMeldZoneProps) {
  if (!melds || melds.length === 0) return null
  return (
    <div className="zone-melds">
      <OpenMelds melds={melds} isWildTile={isWildTile} />
    </div>
  )
}
