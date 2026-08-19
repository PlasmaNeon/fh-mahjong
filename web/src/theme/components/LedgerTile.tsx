import { getTileName, getTileSvgName } from '../../utils/tileDisplay'
import {
  TILE_LIBRARY,
  formatTile,
  sameTileValue,
  tileKey,
  type TileDraft,
  type TileValue,
} from '../../utils/tileModel'

export type LedgerTileSize = 'normal' | 'small' | 'palette'

/**
 * The ledger-workbench tile button shared by the calc and shanten tools.
 *
 * `disabled` is an explicit prop rather than derived from `dimmed`: the shanten
 * palette disables exhausted tiles, while the calc palette dims the selected
 * tile but stays clickable.
 */
export function LedgerTile({
  tile,
  onClick,
  size = 'normal',
  selected = false,
  dimmed = false,
  disabled,
  badge,
}: {
  tile: TileValue
  onClick?: () => void
  size?: LedgerTileSize
  selected?: boolean
  dimmed?: boolean
  disabled?: boolean
  badge?: string
}) {
  const svgName = getTileSvgName(tile)
  const cls = [
    'ldg-tile',
    size === 'small' ? 'ldg-tile--sm' : '',
    size === 'palette' ? 'ldg-tile--pal' : '',
    selected ? 'ldg-tile--sel' : '',
    dimmed ? 'ldg-tile--dim' : '',
    !onClick ? 'ldg-tile--static' : '',
  ].filter(Boolean).join(' ')

  return (
    <button
      type="button"
      className={cls}
      onClick={onClick}
      disabled={disabled}
      title={getTileName(tile)}
    >
      <img src={`/Regular_shortnames/${svgName}`} alt={getTileName(tile)} draggable="false" />
      {badge && <span className="ldg-tile__badge">{badge}</span>}
    </button>
  )
}

/** A row of drafted tiles, or the empty-state note when there are none. */
export function LedgerTileRow({ tiles, emptyLabel, onTileClick }: {
  tiles: TileDraft[]
  emptyLabel: string
  onTileClick: (tileId: string) => void
}) {
  if (tiles.length === 0) {
    return (
      <div className="ldg-tile-row ldg-tile-row--empty">
        <span className="ldg-note" style={{ marginTop: 0 }}>{emptyLabel}</span>
      </div>
    )
  }
  return (
    <div className="ldg-tile-row">
      {tiles.map((tile) => (
        <LedgerTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

/**
 * The full tile palette. Passing `usedCounts` switches on the shanten behaviour:
 * a remaining-copies badge, with exhausted tiles dimmed and disabled.
 */
export function LedgerPaletteGrid({
  onTileClick,
  selectedTile = null,
  dimSelected = false,
  usedCounts,
}: {
  onTileClick: (tile: TileValue) => void
  selectedTile?: TileValue | null
  dimSelected?: boolean
  usedCounts?: Map<string, number>
}) {
  return (
    <div className="ldg-palette-grid">
      {TILE_LIBRARY.map((tile) => {
        const isSelected = sameTileValue(tile, selectedTile)
        if (!usedCounts) {
          return (
            <LedgerTile
              key={formatTile(tile)}
              tile={tile}
              onClick={() => onTileClick(tile)}
              size="palette"
              selected={isSelected}
              dimmed={dimSelected && isSelected}
            />
          )
        }
        const remaining = 4 - (usedCounts.get(tileKey(tile)) ?? 0)
        const isDimmed = remaining <= 0 || (dimSelected && isSelected)
        return (
          <LedgerTile
            key={formatTile(tile)}
            tile={tile}
            onClick={() => onTileClick(tile)}
            size="palette"
            selected={isSelected}
            dimmed={isDimmed}
            disabled={isDimmed && !isSelected}
            badge={remaining < 4 ? `${remaining}` : undefined}
          />
        )
      })}
    </div>
  )
}
