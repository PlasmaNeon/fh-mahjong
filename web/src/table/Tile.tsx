import { memo } from 'react'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import type { TileLike } from './types'

type TileComponentProps = {
  tile: TileLike
  isInteractive?: boolean
  isLifted?: boolean
  size?: 'normal' | 'small'
  noGlow?: boolean
  isWild?: boolean
  onTileClick?: (tile: TileLike) => void
}

export const TileComponent = memo(function TileComponent({
  tile,
  isInteractive = false,
  isLifted = false,
  size = 'normal',
  noGlow = false,
  isWild = false,
  onTileClick,
}: TileComponentProps) {
  const svgName = getTileSvgName(tile)

  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${noGlow ? 'mahjong-tile--no-glow' : ''} ${isInteractive ? 'interactive' : ''} ${isLifted ? 'lifted' : ''} ${size === 'small' ? 'small' : ''}`}
      onClick={() => isInteractive && onTileClick?.(tile)}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        position: 'relative',
      }}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
        draggable="false"
      />
    </div>
  )
})
