import { describe, expect, it } from 'vitest'
import { pixelVariable, readSourceCss, ruleBody } from '../test/cssContract'
import { computeStageLayout } from './stage/computeStageLayout'

const css = readSourceCss('src/table/table-geometry.css')
const normal = ruleBody(css, '.game-stage .mahjong-table')
const compact = ruleBody(css, '.game-stage[data-compact="true"] .mahjong-table')

// A long individual discard pool must clear even a lifted self tile. The
// browser crowded fixture additionally checks all four actual rotated pools.
describe('late-round discard clearance', () => {
  for (const [width, height] of [[568, 320], [667, 375], [844, 390], [800, 600], [1024, 768], [1280, 720], [2560, 1080]]) {
    it(`keeps 30 discards clear of both hands at ${width}x${height}`, () => {
      const layout = computeStageLayout(width, height)
      const value = (key: string) => pixelVariable(layout.compact && compact.includes(`${key}:`) ? compact : normal, key)
      const columns = Number((layout.compact ? compact : normal).match(/--discard-columns:\s*(\d+)/)![1])
      expect(columns).toBe(6)
      const lane = value('--discard-tile-width') * columns + value('--discard-gap') * (columns - 1) + 2 * value('--discard-padding')
      const rows = 4 // Later discards extend row four rather than adding depth.
      const depth = rows * value('--discard-tile-height') + (rows - 1) * value('--discard-gap') + 2 * value('--discard-padding')
      const center = layout.stageHeight / 2 - value('--center-shift')
      const top = center - lane / 2 - value('--discard-hud-gap') - depth
      const bottom = center + lane / 2 + value('--discard-hud-gap') + depth
      const liftedHandTop = layout.stageHeight - value('--bundle-edge-offset') - value('--tile-height') - (layout.compact ? 22 : 14)
      expect(top).toBeGreaterThan(value('--bundle-edge-offset') + value('--tile-small-height'))
      expect(bottom).toBeLessThan(liftedHandTop - 4)
    })
  }
})

// Four direct kans are wider than four triplets because each includes a
// sideways called tile. Leave the concealed pair and minimum gap intact.
describe('opponent exposed rail clearance', () => {
  for (const isCompact of [false, true]) {
    it(`fits four direct kans and a concealed pair (${isCompact ? 'compact' : 'desktop'})`, () => {
      const exposed = ruleBody(css, '.game-stage .seat-bundle--opp .seat-bundle__exposed')
      const compactExposed = ruleBody(css, '.game-stage[data-compact="true"] .seat-bundle--opp .seat-bundle__exposed')
      const boardValue = (key: string) => pixelVariable(isCompact && compact.includes(`${key}:`) ? compact : normal, key)
      const exposedValue = (key: string) => pixelVariable(isCompact && compactExposed.includes(`${key}:`) ? compactExposed : exposed, key)
      const meldGap = isCompact ? exposedValue('--meld-group-gap') : boardValue('--meld-group-gap')
      const kans = 4 * (3 * exposedValue('--tile-small-width') + exposedValue('--tile-small-height')) + 3 * meldGap
      const pair = 2 * boardValue('--tile-small-width') + boardValue('--tile-gap')
      expect(kans + pair + boardValue('--bundle-min-gap')).toBeLessThanOrEqual(boardValue('--bundle-span-opp'))
    })
  }
})
