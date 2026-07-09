import { afterEach, describe, expect, it, vi } from 'vitest'
import { actionLabel, decisionGap, decisionKey, decisionSeverity, selectPanelDecisions } from './reviewUtils'
import type { ReportDecision, ReviewReport } from './reviewTypes'
import { fetchReview, generateReview } from './reviewTypes'

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

  // Expected labels below are derived from internal/rl/action.go offsets:
  // DiscardBase=5 with face order man(0-8) pin(9-17) sou(18-26) jihai(27-33)
  // flower(34-41); PonBase=47; KanDirectBase=81; KanClosedBase=115;
  // KanUpgradedBase=149; ChiiBase=183 with suit offsets man=0 pin=7 sou=14.
  it('labels discards across every face group', () => {
    expect(actionLabel(14).en).toBe('Discard 1p') // 5 + 9
    expect(actionLabel(23).en).toBe('Discard 1s') // 5 + 18
    expect(actionLabel(32).en).toBe('Discard East') // 5 + 27, jihai value 1
    expect(actionLabel(32).zh).toBe('打 东')
    expect(actionLabel(39).en).toBe('Discard Spring') // 5 + 34, flower value 1
    expect(actionLabel(39).zh).toBe('打 春')
  })

  it('labels the three kan modes distinctly', () => {
    const open = actionLabel(81) // KanDirectBase + face 0
    const closed = actionLabel(115) // KanClosedBase + face 0
    const upgraded = actionLabel(149) // KanUpgradedBase + face 0
    expect(open.en).toBe('Open Kan 1m')
    expect(closed.en).toBe('Closed Kan 1m')
    expect(upgraded.en).toBe('Upgraded Kan 1m')
    expect(new Set([open.en, closed.en, upgraded.en]).size).toBe(3)
    expect(new Set([open.zh, closed.zh, upgraded.zh]).size).toBe(3)
  })

  it('labels a pon of a non-man face', () => {
    expect(actionLabel(56).en).toBe('Pon 1p') // PonBase 47 + pin face 9
  })

  it('labels a mid-range chii', () => {
    expect(actionLabel(190).en).toBe('Chii 1-2-3p') // ChiiBase 183 + pin offset 7
    expect(actionLabel(190).zh).toBe('吃 1-2-3饼')
  })
})

describe('fetchReview / generateReview', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  const report: ReviewReport = {
    schemaVersion: 1,
    matchId: 'm1',
    ruleset: 'fenghua',
    checkpointPath: '/ckpt',
    checkpointStep: 10,
    generatedAt: '2026-01-01T00:00:00Z',
    decisions: [],
    seats: [],
  }

  it('fetchReview returns null on 404', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('not found', { status: 404 })))
    await expect(fetchReview('m1')).resolves.toBeNull()
  })

  it('fetchReview returns the parsed report on 200', async () => {
    const fetchMock = vi.fn(async () => new Response(JSON.stringify(report), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(fetchReview('m1')).resolves.toEqual(report)
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/v1/matches/m1/review'))
  })

  it('generateReview throws {status, message} from the error body on 503', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      new Response(JSON.stringify({ error: 'reviewer unavailable' }), { status: 503 })))
    await expect(generateReview('m1')).rejects.toEqual({ status: 503, message: 'reviewer unavailable' })
  })

  it('generateReview throws a sensible message on a non-JSON error body', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>bad gateway</html>', { status: 502 })))
    await expect(generateReview('m1')).rejects.toEqual({ status: 502, message: 'HTTP 502' })
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
