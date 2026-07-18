import { describe, expect, it } from 'vitest'
import { ROUND_RESULT_VIEWPORTS } from './RoundResultDemo'

describe('round-result demo viewports', () => {
  it('includes a compact iPhone preset for short-screen QA', () => {
    expect(ROUND_RESULT_VIEWPORTS).toContainEqual({
      key: 'compact-phone',
      label: 'Compact iPhone',
      width: 375,
      height: 667,
    })
  })

  it('includes the rotated phone shell shown during live portrait play', () => {
    expect(ROUND_RESULT_VIEWPORTS).toContainEqual({
      key: 'rotated-phone',
      label: 'Rotated phone',
      width: 667,
      height: 375,
    })
  })
})
