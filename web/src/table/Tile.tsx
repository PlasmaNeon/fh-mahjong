import { memo } from 'react'
import { getTileName, getTileSvgName } from '../utils/tileUtils'
import type { TileLike } from './types'

type TileComponentProps = {
  tile: TileLike
  isInteractive?: boolean
  size?: 'normal' | 'small'
  noGlow?: boolean
  isWild?: boolean
  onDiscard?: (tile: TileLike) => void
}

export const TileComponent = memo(function TileComponent({
  tile,
  isInteractive = false,
  size = 'normal',
  noGlow = false,
  isWild = false,
  onDiscard,
}: TileComponentProps) {
  const svgName = getTileSvgName(tile)

  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${isInteractive ? 'interactive' : ''} ${size === 'small' ? 'small' : ''}`}
      onClick={() => isInteractive && onDiscard?.(tile)}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        boxShadow: (isWild && !noGlow) ? '0 0 15px 6px rgba(234, 179, 8, 0.9)' : '1px 1px 3px rgba(0,0,0,0.5)',
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
