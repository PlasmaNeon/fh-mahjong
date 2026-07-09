import { describe, expect, it } from 'vitest'
import { actionLabel, decisionGap, decisionKey, decisionSeverity, selectPanelDecisions } from './reviewUtils'
import type { ReportDecision, ReviewReport } from './reviewTypes'

function dec(actions: [number, number][], chosen: number): ReportDecision {
  return {
    seat: 0, round: 0, actionIndex: 3,
    chosenActionId: chosen,
    chosenProb: actions.find(([id]) => id === chosen)?.[1] ?? 0,
    value: 0,
    actions: actions.map(([actionId, prob]) => ({ actionId, prob })),
  }
}

describe('decisionSeverity', () => {
  it('flags a large gap as mistake', () => {
    expect(decisionSeverity(dec([[5, 0.8], [6, 0.15], [7, 0.04], [8, 0.01]], 8))).toBe('mistake')
  })
  it('flags a medium gap as disagreement', () => {
    // Chosen is rank 4 (outside the top-3 exemption) with gap 0.42.
    expect(decisionSeverity(dec([[5, 0.5], [6, 0.3], [7, 0.12], [8, 0.08]], 8))).toBe('disagreement')
  })
  it('never flags a chosen action in top-3 with >=5%', () => {
    // gap 0.75 would be "mistake", but chosen is rank 2 with 20%.
    expect(decisionSeverity(dec([[5, 0.75], [6, 0.2], [7, 0.05]], 6))).toBe('ok')
  })
  it('small gaps are ok', () => {
    expect(decisionSeverity(dec([[5, 0.4], [6, 0.35], [7, 0.25]], 7))).toBe('ok')
  })
  it('accepts an overridden thresholds parameter', () => {
    // With a stricter disagreement threshold, a small gap now counts.
    const d = dec([[5, 0.4], [6, 0.35], [7, 0.25]], 7)
    expect(decisionSeverity(d, { disagreement: 0.01, mistake: 0.6, topNExempt: 0, topNMinProb: 0.05 })).toBe('disagreement')
  })
})

describe('decisionGap', () => {
  it('is top prob minus chosen prob', () => {
    expect(decisionGap(dec([[5, 0.6], [6, 0.4]], 6))).toBeCloseTo(0.2)
  })
})

describe('actionLabel', () => {
  it('labels catalog boundaries', () => {
    expect(actionLabel(0).en).toBe('Pass')
    expect(actionLabel(5).en).toBe('Discard 1m')
    expect(actionLabel(46).en).toContain('Discard') // last flower discard
    expect(actionLabel(47).en).toContain('Pon 1m')
    expect(actionLabel(183).en).toContain('Chii')
    expect(actionLabel(203).en).toContain('Chii')
  })
})

describe('decisionKey', () => {
  it('joins round and actionIndex', () => {
    expect(decisionKey(2, 7)).toBe('2:7')
  })
})

describe('selectPanelDecisions', () => {
  const report: ReviewReport = {
    schemaVersion: 1,
    matchId: 'm1',
    ruleset: 'fenghua',
    checkpointPath: '/ckpt',
    checkpointStep: 10,
    generatedAt: '2026-01-01T00:00:00Z',
    decisions: [
      dec([[5, 0.9], [6, 0.1]], 5), // seat 0
      { ...dec([[5, 0.9], [6, 0.1]], 5), seat: 1 },
      { ...dec([[5, 0.9], [6, 0.1]], 5), seat: 0, round: 1, actionIndex: 4 },
    ],
    seats: [],
  }

  it('filters decisions by seat', () => {
    const result = selectPanelDecisions(report, 0)
    expect(result).toHaveLength(2)
    expect(result.every(d => d.seat === 0)).toBe(true)
  })

  it('filters decisions by seat and decisionKey', () => {
    const result = selectPanelDecisions(report, 0, decisionKey(1, 4))
    expect(result).toHaveLength(1)
    expect(result[0].round).toBe(1)
    expect(result[0].actionIndex).toBe(4)
  })
})
