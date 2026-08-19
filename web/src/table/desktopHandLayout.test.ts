import { describe, expect, it } from 'vitest'
import { computeStageLayout } from './stage/computeStageLayout'
import { pixelVariable, readSourceCss, ruleBody } from '../test/cssContract'

function desktopTableRule() {
  return ruleBody(readSourceCss('src/index.css'), '.game-stage .mahjong-table')
}

describe('desktop self-hand geometry', () => {
  it('scales Majsoul-sized tiles with the fixed table canvas across desktop windows', () => {
    const rule = desktopTableRule()
    const tileWidth = pixelVariable(rule, '--tile-width')
    const tileHeight = pixelVariable(rule, '--tile-height')
    const tileGap = pixelVariable(rule, '--tile-gap')
    const drawnGap = pixelVariable(rule, '--drawn-gap')
    const bundleSpan = pixelVariable(rule, '--bundle-span-self')
    const viewports = [
      [1024, 768],
      [1280, 720],
      [1920, 1080],
    ] as const

    for (const [width, height] of viewports) {
      const layout = computeStageLayout(width, height)
      const renderedTileHeight = tileHeight * layout.scale
      const fullHandWidth = ((tileWidth * 14) + (tileGap * 13) + drawnGap) * layout.scale

      expect(layout.compact).toBe(false)
      expect(renderedTileHeight / layout.scaledHeight).toBeGreaterThanOrEqual(0.1)
      expect(renderedTileHeight / layout.scaledHeight).toBeLessThanOrEqual(0.11)
      expect(fullHandWidth).toBeLessThanOrEqual(layout.scaledWidth)
      expect(bundleSpan * layout.scale).toBeLessThanOrEqual(layout.scaledWidth)
    }

    const standardDesktop = computeStageLayout(1280, 720)
    expect(tileWidth * standardDesktop.scale).toBeGreaterThanOrEqual(50)
    expect(tileHeight * standardDesktop.scale).toBeGreaterThanOrEqual(72)
  })
})
