import { describe, it, expect } from 'vitest'
import { computeStageLayout, STAGE_MAX_ASPECT, STAGE_COMPACT_BASE_HEIGHT } from './computeStageLayout'

const near = (a: number, b: number, eps = 0.5) => Math.abs(a - b) <= eps

describe('computeStageLayout', () => {
  it('uses the shorter compact design on short (phone) stages, full design otherwise', () => {
    const tall = computeStageLayout(1600, 900)
    expect(tall.compact).toBe(false)
    expect(tall.stageHeight).toBe(900)

    // Rotated phone landscape height ~390: compact design → bigger scale, still fills.
    const phone = computeStageLayout(844, 390)
    expect(phone.compact).toBe(true)
    expect(phone.stageHeight).toBe(STAGE_COMPACT_BASE_HEIGHT)
    expect(phone.scale).toBeGreaterThan(390 / 900)
    expect(near(phone.offsetX, 0)).toBe(true)
    expect(near(phone.offsetY, 0)).toBe(true)
  })


  it('matches 16:9 exactly with no bars', () => {
    const l = computeStageLayout(1600, 900)
    expect(l.stageWidth).toBe(1600)
    expect(l.offsetX).toBe(0)
    expect(l.offsetY).toBe(0)
    expect(l.scale).toBeCloseTo(1, 5)
  })

  it('fills width for an in-band 2.0 ratio (widens the design)', () => {
    const l = computeStageLayout(1920, 960)
    expect(l.stageWidth).toBeCloseTo(1800, 3) // 900 * 2.0
    expect(near(l.offsetX, 0)).toBe(true)
  })

  it('fills both axes for a 21:9 (in-band) ratio', () => {
    const l = computeStageLayout(2560, 1080) // 2.370 < CAP
    expect(near(l.offsetX, 0)).toBe(true)
    expect(near(l.offsetY, 0)).toBe(true)
  })

  it('pillarboxes beyond the cap', () => {
    const l = computeStageLayout(3840, 1080) // 3.556 > CAP
    expect(l.stageWidth).toBeCloseTo(900 * STAGE_MAX_ASPECT, 3)
    expect(l.offsetX).toBeGreaterThan(0)
    expect(near(l.offsetY, 0)).toBe(true)
  })

  it('fills width and letterboxes height below 16:9 (4:3)', () => {
    const l = computeStageLayout(1024, 768)
    expect(l.stageWidth).toBeCloseTo(1600, 3) // clamped to 16:9
    expect(near(l.offsetX, 0)).toBe(true)
    expect(l.offsetY).toBeGreaterThan(0)
  })

  it('fills width in portrait with a large vertical letterbox', () => {
    const l = computeStageLayout(400, 800)
    expect(l.stageWidth).toBeCloseTo(1600, 3)
    expect(near(l.scaledWidth, 400)).toBe(true)
    expect(l.offsetY).toBeGreaterThan(200)
  })

  it('never returns non-finite values for zero input', () => {
    const l = computeStageLayout(0, 0)
    expect(Number.isFinite(l.scale)).toBe(true)
    expect(l.scale).toBeGreaterThan(0)
  })
})
