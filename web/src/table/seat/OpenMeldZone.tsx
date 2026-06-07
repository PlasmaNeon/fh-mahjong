import { OpenMelds } from './OpenMelds'
import type { MeldLike, TileLike } from '../types'

type OpenMeldZoneProps = {
  melds: MeldLike[]
  isWildTile?: (tile: TileLike) => boolean
  animateLayout?: boolean
}

export function OpenMeldZone({ melds, isWildTile, animateLayout = false }: OpenMeldZoneProps) {
  if (!melds || melds.length === 0) return null
  return (
    <div className="zone-melds">
      <OpenMelds melds={melds} isWildTile={isWildTile} animateLayout={animateLayout} />
    </div>
  )
}
