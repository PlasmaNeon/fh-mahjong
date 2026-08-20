import { describe, it, expect } from 'vitest'
import { stageStyles, type StageStyleInput } from './computeStageLayout'

const layout: StageStyleInput = {
  stageWidth: 1600,
  stageHeight: 900,
  scale: 0.8,
  scaledWidth: 1280,
  scaledHeight: 720,
  offsetX: 10,
  offsetY: 40,
  compact: false,
  availableWidth: 1300,
  availableHeight: 800,
}

describe('stageStyles', () => {
  it('maps the scaled and available box onto CSS custom properties', () => {
    expect(stageStyles(layout).shellStyle).toMatchObject({
      '--game-stage-scaled-width': '1280px',
      '--game-stage-scaled-height': '720px',
      '--game-stage-available-width': '1300px',
      '--game-stage-available-height': '800px',
    })
  })

  it('sizes the stage in design pixels and zooms it', () => {
    expect(stageStyles(layout).stageStyle).toMatchObject({
      width: '1600px',
      height: '900px',
      zoom: 0.8,
    })
  })
})
