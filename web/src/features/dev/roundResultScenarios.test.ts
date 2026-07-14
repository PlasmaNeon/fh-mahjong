import { describe, it, expect } from 'vitest'
import { SCENARIO_KEYS, SCENARIO_LABELS, buildScenario } from './roundResultScenarios'

describe('buildScenario', () => {
  it('exposes a label for every scenario key', () => {
    for (const key of SCENARIO_KEYS) {
      expect(SCENARIO_LABELS[key]).toBeTruthy()
    }
  })

  it('draw scenario sets isDraw with no payouts and no breakdown', () => {
    const r = buildScenario('draw', false)
    expect(r.isDraw).toBe(true)
    expect(r.payouts ?? []).toHaveLength(0)
    expect(r.breakdown ?? []).toHaveLength(0)
  })

  for (const key of SCENARIO_KEYS.filter((k) => k !== 'draw')) {
    it(`${key} scenario: winType + breakdown + one winner, three losers, balanced`, () => {
      const r = buildScenario(key, false)
      expect(r.isDraw).toBe(false)
      expect(r.winType).toBeTruthy()
      expect((r.breakdown ?? []).length).toBeGreaterThan(0)

      const payouts = r.payouts ?? []
      expect(payouts).toHaveLength(4)
      expect(payouts.filter((p) => p.amount > 0)).toHaveLength(1) // winner
      expect(payouts.filter((p) => p.amount < 0)).toHaveLength(3) // losers
      expect(payouts.reduce((acc, p) => acc + p.amount, 0)).toBe(0)

      const breakdownSum = (r.breakdown ?? []).reduce((acc, e) => acc + e.points, 0)
      expect(r.totalScore).toBe(breakdownSum)
    })
  }

  it('long scenario has enough breakdown rows to force body scroll', () => {
    expect((buildScenario('long', false).breakdown ?? []).length).toBeGreaterThanOrEqual(10)
  })

  it('ready flag populates explicit payout statuses; default clears them', () => {
    const readyLabels = (buildScenario('tsumo', true).payouts ?? []).map((p) => p.readyLabel)
    expect(readyLabels).toContain('Ready')
    expect(readyLabels).toContain('Waiting')
    expect(readyLabels).not.toContain('...')
    expect((buildScenario('tsumo', false).payouts ?? []).every((p) => !p.readyLabel)).toBe(true)
  })
})
