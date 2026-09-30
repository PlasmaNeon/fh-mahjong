import { describe, expect, it } from 'vitest'
import { computeStageLayout } from '../../table/stage/computeStageLayout'
import { pixelVariable, readSourceCss, ruleBody } from '../../test/cssContract'

const rule = ruleBody(readSourceCss('src/features/dev/tableSampleUnified.css'), '.game-stage[data-unified="true"][data-compact] .mahjong-table')
const value = (name: string) => pixelVariable(rule, name)

describe('unified table preview', () => {
  it('keeps a fixed side-hand inset while four sideways kans fit in one row', () => {
    const css = readSourceCss('src/features/dev/tableSampleUnified.css')
    const sides = '.game-stage[data-unified="true"][data-compact] :is(.seat-bundle-pivot--left, .seat-bundle-pivot--right)'
    expect(ruleBody(css, sides + ' .zone-hand')).toContain('left: var(--side-hand-inset)')
    const exposed = ruleBody(css, sides + ' .seat-bundle__exposed:has(.seat-meld-group:nth-child(4)):has(.seat-meld-group > :nth-child(4))')
    const kanWidth = 3 * pixelVariable(exposed, '--tile-small-width') + pixelVariable(exposed, '--tile-small-height')
    const remainingPair = 2 * value('--tile-small-width') + 1
    const fourKans = 4 * kanWidth + 3 * pixelVariable(ruleBody(css, sides + ' .seat-bundle__exposed'), '--meld-group-gap')
    const gap = value('--bundle-span-opp') - value('--side-hand-inset') - remainingPair - fourKans
    expect(gap).toBeGreaterThanOrEqual(4)
    expect(value('--side-hand-inset')).toBe(60)
  })
  it('keeps four discard rows clear of top and lifted local hands', () => {
    const centerY = 360 - value('--center-shift')
    const outerOffset = value('--center-hud-size') / 2 + value('--discard-hud-gap')
    const riverDepth = value('--discard-tile-height') * 4
    expect(centerY - outerOffset - riverDepth - 1).toBeGreaterThanOrEqual(28 + value('--tile-small-height'))
    expect(centerY + outerOffset + riverDepth + 1).toBeLessThan(720 - value('--bundle-edge-offset') - value('--tile-height') - 22)
    const laneSize = value('--discard-tile-width') * 6 + 2
    const longSideRowEnd = centerY - laneSize / 2 + 1 + (12 - (30 - 24) / 2) * value('--discard-tile-width')
    expect(longSideRowEnd).toBeLessThan(720 - value('--bundle-edge-offset') - value('--tile-height') - 22)
  })
  for (const [width, height] of [[667, 375], [1280, 720], [2560, 1080]]) {
    it(`preserves large hand tiles and edge clearance at ${width}x${height}`, () => {
      const layout = computeStageLayout(width, height, { baseHeight: 720, compactMaxHeight: Infinity })
      expect(layout.compact).toBe(true)
      expect(value('--tile-width') * layout.scale).toBeGreaterThanOrEqual(42)
      expect(value('--tile-height') * layout.scale).toBeGreaterThanOrEqual(60)
      expect(value('--bundle-edge-offset') * layout.scale).toBeGreaterThanOrEqual(14)
      expect((layout.stageWidth - value('--bundle-span-self')) / 2 * layout.scale).toBeGreaterThanOrEqual(20)
      const rail = value('--tile-width') * 14 + 13 + 12
      expect(rail).toBeLessThan(value('--bundle-span-self'))
      const opponentBottom = layout.stageHeight / 2 - value('--center-shift') - 28 + value('--bundle-span-opp') / 2
      const liftedHandTop = layout.stageHeight - value('--bundle-edge-offset') - value('--tile-height') - 22
      expect(opponentBottom).toBeLessThan(liftedHandTop)
      const rightHandInnerEdge = layout.stageWidth - 28 - value('--tile-small-height')
      const selfHandRight = (layout.stageWidth - value('--bundle-span-self')) / 2 + rail
      expect(rightHandInnerEdge).toBeGreaterThan(selfHandRight)
      const leftPivot = layout.stageHeight / 2 - value('--center-shift') - 28
      const rightPivot = layout.stageHeight / 2 - value('--center-shift') + 28
      expect((leftPivot + rightPivot) / 2).toBe(layout.stageHeight / 2 - value('--center-shift'))
    })
  }
})
