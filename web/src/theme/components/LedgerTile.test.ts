import { describe, it, expect } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LedgerTile, LedgerTileRow, LedgerPaletteGrid } from './LedgerTile'
import { TILE_LIBRARY, tileKey } from '../../utils/tileModel'

const tile = TILE_LIBRARY[0]

describe('LedgerTile', () => {
  it('composes the ldg-tile class list in order', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, size: 'palette', selected: true }),
    )
    expect(html).toContain('class="ldg-tile ldg-tile--pal ldg-tile--sel"')
  })

  it('marks a tile static when it has no click handler', () => {
    expect(renderToStaticMarkup(createElement(LedgerTile, { tile }))).toContain('ldg-tile--static')
  })

  it('omits the disabled attribute unless disabled is passed (calc behaviour)', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, dimmed: true }),
    )
    expect(html).toContain('ldg-tile--dim')
    expect(html).not.toContain('disabled')
  })

  it('disables when asked (shanten behaviour)', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, dimmed: true, disabled: true }),
    )
    expect(html).toContain('disabled')
  })

  it('renders a badge only when given one', () => {
    expect(renderToStaticMarkup(createElement(LedgerTile, { tile, badge: '3' })))
      .toContain('ldg-tile__badge')
    expect(renderToStaticMarkup(createElement(LedgerTile, { tile })))
      .not.toContain('ldg-tile__badge')
  })

  it('renders the tile face image with its name as alt text', () => {
    const html = renderToStaticMarkup(createElement(LedgerTile, { tile }))
    expect(html).toContain('/Regular_shortnames/')
    expect(html).toContain('draggable="false"')
  })
})

describe('LedgerTileRow', () => {
  it('shows the empty label when there are no tiles', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTileRow, { tiles: [], emptyLabel: 'No tiles yet', onTileClick: () => {} }),
    )
    expect(html).toContain('ldg-tile-row--empty')
    expect(html).toContain('No tiles yet')
  })

  it('renders one tile per draft', () => {
    const tiles = [{ ...TILE_LIBRARY[0], id: 'a' }, { ...TILE_LIBRARY[1], id: 'b' }]
    const html = renderToStaticMarkup(
      createElement(LedgerTileRow, { tiles, emptyLabel: 'empty', onTileClick: () => {} }),
    )
    expect(html).not.toContain('ldg-tile-row--empty')
    expect(html.match(/ldg-tile[" ]/g)?.length).toBe(2)
  })
})

describe('LedgerPaletteGrid', () => {
  it('renders one button per library tile', () => {
    const html = renderToStaticMarkup(createElement(LedgerPaletteGrid, { onTileClick: () => {} }))
    expect(html.match(/class="ldg-tile /g)?.length).toBe(TILE_LIBRARY.length)
  })

  it('shows a remaining-count badge only when usedCounts is supplied', () => {
    const counts = new Map<string, number>([[tileKey(TILE_LIBRARY[0]), 1]])
    expect(renderToStaticMarkup(
      createElement(LedgerPaletteGrid, { onTileClick: () => {}, usedCounts: counts }),
    )).toContain('ldg-tile__badge')
    expect(renderToStaticMarkup(
      createElement(LedgerPaletteGrid, { onTileClick: () => {} }),
    )).not.toContain('ldg-tile__badge')
  })

  it('dims and disables an exhausted tile', () => {
    const counts = new Map<string, number>([[tileKey(TILE_LIBRARY[0]), 4]])
    const html = renderToStaticMarkup(
      createElement(LedgerPaletteGrid, { onTileClick: () => {}, usedCounts: counts }),
    )
    expect(html).toContain('ldg-tile--dim')
    expect(html).toContain('disabled')
  })
})
