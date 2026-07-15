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
})
