import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
import { renderStatic } from '../../test/renderStatic'
import { DiscardZone } from './DiscardZone'

// Keep the first three rows at six and extend only row four, preserving order.
describe('discard row reservation', () => {
  for (const direction of ['bottom', 'right', 'top', 'left'] as const) {
    it(`extends the fourth row for ${direction}`, () => {
      const discards = Array.from({ length: 30 }, (_, id) => ({ id, suit: 1, value: id % 9 + 1 }))
      const html = renderStatic(createElement(DiscardZone, { direction, discards }))
      const positions = [...html.matchAll(/--discard-row:(\d+);--discard-column:(\d+)/g)]
        .map(match => [Number(match[1]), Number(match[2])])
      expect(positions).toHaveLength(30)
      expect(positions[0]).toEqual([0, 0])
      expect(positions[17]).toEqual([2, 5])
      expect(positions[18]).toEqual([3, 0])
      expect(positions[23]).toEqual([3, 5])
      expect(positions[24]).toEqual([3, 6])
      expect(positions[29]).toEqual([3, 11])
      expect(positions.every(([row]) => row < 4)).toBe(true)
    })
  }
})
