import { describe, expect, it } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nProvider } from '../../i18n/I18nContext'
import { reviewResources } from '../../i18n/locales/review'
import ReviewStudy, { defaultStudySettings } from './ReviewStudy'
import { agreementStats, cumulativeProxy, decisionPosition, errorRatio, tileAnnotations } from './studyUtils'
import { SEVERITY_THRESHOLDS } from './reviewUtils'
import type { ReportDecision, ReviewReport } from './reviewClient'
import type { Paipu } from './replayTypes'
const d: ReportDecision = {
  id: 'r0-d0-s0',
  seat: 0,
  round: 0,
  actionIndex: 2,
  positionIndex: 1,
  choiceSource: 'recorded',
  actualTileId: 0,
  chosenActionId: 23,
  chosenProb: 0.2,
  value: null,
  actions: [
    {
      actionId: 24,
      prob: 0.8,
      evaluation: { mean: 10, samples: 2, standardError: 1 },
    },
    {
      actionId: 23,
      prob: 0.2,
      evaluation: { mean: -10, samples: 2, standardError: 1 },
    },
  ],
}
describe('review study integrity', () => {
  it('anchors before the action and distinguishes tile zero from its duplicate', () => {
    expect(decisionPosition(d)).toBe(1)
    const annotations = tileAnnotations(
      d,
      [
        { id: 0, suit: 1, value: 1 },
        { id: 1, suit: 1, value: 1 },
      ],
      true,
      true,
      false,
      String,
    )!
    expect(annotations[0].actual).toBe(true)
    expect(annotations[1].actual).toBe(false)
    expect(annotations[0].scale).toBe(0.25)
    expect(tileAnnotations(d, [{ id: 0, suit: 1, value: 1 }], true, false, false, String)![0].actual).toBe(false)
  })
  it('uses ratio thresholds and excludes inferred choices and forced operations', () => {
    expect(errorRatio(d)).toBe(25)
    expect(
      agreementStats([d, { ...d, chosenActionId: 24, choiceSource: 'inferred' }, { ...d, actions: [d.actions[0]] }]),
    ).toMatchObject({ count: 1, agreement: 0, rating: 0 })
    expect(agreementStats([{ ...d, chosenActionId: 24 }]).rating).toBe(100)
    expect(
      agreementStats([
        {
          ...d,
          actions: d.actions.map((a) => ({ ...a, evaluation: undefined })),
        },
      ]).rating,
    ).toBe(null)
    expect(cumulativeProxy([0.1, 0.2])).toBeCloseTo(0.28)
  })
  it('hides actual, AI advice and future scores in study rendering', () => {
    const paipu = {
      players: [0, 1, 2, 3].map((seat) => ({ seat, name: `P${seat}` })),
      rounds: [
        {
          startingScores: [1, 2, 3, 4],
          result: { scoreChanges: [999, -333, -333, -333] },
        },
        { startingScores: [88777, 4, 5, 6], result: null },
      ],
      finalScores: [55666, 1, 2, 3],
    } as Paipu
    const report = {
      decisions: [d],
      generatedAt: new Date().toISOString(),
    } as ReviewReport
    const props = {
      paipu,
      report,
      decision: d,
      seat: 0,
      round: 0,
      cursor: 1,
      job: null,
      error: '',
      running: false,
      authenticated: false,
      run: () => {},
      cancel: () => {},
      jump: () => {},
      jumpRound: () => {},
      navigate: () => {},
      change: () => {},
      bookmark: () => {},
      copied: false,
      thresholds: SEVERITY_THRESHOLDS,
      onThresholds: () => {},
      settings: {
        ...defaultStudySettings,
        study: true,
        tab: 'rounds' as const,
      },
    }
    const html = renderToStaticMarkup(React.createElement(I18nProvider, null, React.createElement(ReviewStudy, props)))
    expect(html).not.toContain('55666')
    expect(html).not.toContain('88777')
    expect(html).not.toContain('999')
    const decisionHtml = renderToStaticMarkup(
      React.createElement(
        I18nProvider,
        null,
        React.createElement(ReviewStudy, {
          ...props,
          settings: { ...props.settings, tab: 'decision' },
        }),
      ),
    )
    expect(decisionHtml).not.toContain('Discard 1s')
    expect(decisionHtml).not.toContain('80.0%')
    expect(decisionHtml).not.toContain('Rank 2')
  })
  it('provides every reviewer key and matching variables in all five languages', () => {
    for (const resource of Object.values(reviewResources))
      for (const [key, value] of Object.entries(reviewResources.en)) {
        expect(resource[key as keyof typeof resource]).toBeTruthy()
        expect(resource[key as keyof typeof resource].match(/\{\w+\}/g)).toEqual(value.match(/\{\w+\}/g))
      }
  })
})

import { bookmarkIndex } from './studyUtils'
import { positionDecisionIndex } from './studyUtils'
it('preserves the selected response when multiple decisions share a replay position', () => {
  const decisions = [d, { ...d, id: 'r0-d1-s0' }, { ...d, id: 'r0-d2-s0', positionIndex: 3 }]
  expect(positionDecisionIndex(decisions, 0, 1, 'r0-d1-s0')).toBe(1)
  expect(positionDecisionIndex(decisions, 0, 1, 'missing')).toBe(0)
  expect(positionDecisionIndex(decisions, 0, 3, 'r0-d1-s0')).toBe(2)
})
it('bounds malformed bookmark fields without fractional seats or NaN cursors', () => {
  expect(bookmarkIndex('NaN', -1, 100, -1)).toBe(-1)
  expect(bookmarkIndex('1.5', 0, 3, 0)).toBe(0)
  expect(bookmarkIndex('999', 0, 3, 0)).toBe(3)
  expect(bookmarkIndex(null, -1, 100, -1)).toBe(-1)
})
