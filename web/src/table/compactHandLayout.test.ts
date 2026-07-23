import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { computeStageLayout } from '../hooks/computeStageLayout'

function compactTableRule() {
  const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
  return css.match(/\.game-stage\[data-compact="true"\] \.mahjong-table\s*\{([^}]*)\}/)?.[1] ?? ''
}

function tableCss() {
  return readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8')
}

function pixelVariable(rule: string, name: string) {
  const value = rule.match(new RegExp(`${name}:\\s*([\\d.]+)px`))?.[1]
  return Number(value)
}

describe('compact phone self-hand geometry', () => {
  it('keeps each self tile finger-sized while the full rail fits the rotated phone', () => {
    const rule = compactTableRule()
    const tileWidth = pixelVariable(rule, '--tile-width')
    const tileHeight = pixelVariable(rule, '--tile-height')
    const tileGap = pixelVariable(rule, '--tile-gap')
    const drawnGap = pixelVariable(rule, '--drawn-gap')
    const bundleSpan = pixelVariable(rule, '--bundle-span-self')
    const opponentBundleSpan = pixelVariable(rule, '--bundle-span-opp')
    const sideShift = pixelVariable(rule, '--bundle-side-shift')
    const edgeOffset = pixelVariable(rule, '--bundle-edge-offset')
    const phone = computeStageLayout(667, 375)
    const fullHandWidth = (tileWidth * 14) + (tileGap * 13) + drawnGap
    const selectedLift = 22
    const opponentLowerEdge = (phone.stageHeight / 2) - sideShift + (opponentBundleSpan / 2)
    const selectedHandTop = phone.stageHeight - edgeOffset - tileHeight - selectedLift

    expect(tileWidth * phone.scale).toBeGreaterThanOrEqual(40)
    expect(tileHeight * phone.scale).toBeGreaterThanOrEqual(56)
    expect(fullHandWidth * phone.scale).toBeLessThanOrEqual(667)
    expect(bundleSpan * phone.scale).toBeLessThanOrEqual(667)
    expect(opponentLowerEdge).toBeLessThanOrEqual(selectedHandTop)
    expect(tableCss()).toMatch(
      /\.game-stage\[data-compact="true"\] \.seat-bundle-pivot--left\s*\{[^}]*top:\s*calc\(50% - var\(--bundle-side-shift\)\)/s,
    )
  })
})
