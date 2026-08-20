import { describe, expect, it } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ReviewPanel from './ReviewPanel'
import type { ReportDecision, ReviewReport } from './reviewTypes'
import { SEVERITY_THRESHOLDS } from './reviewUtils'

// NOTE: web/package.json has no @testing-library/react, and vitest.config.ts
// runs with environment: 'node' (no DOM). Per Task 7's brief, this uses
// react-dom/server (already a dependency) for a dependency-free "light
// render test" rather than a jsdom-based interaction test.

function dec(overrides: Partial<ReportDecision> = {}): ReportDecision {
  return {
    seat: 0,
    round: 0,
    actionIndex: 3,
    chosenActionId: 8, // Discard 9s
    chosenProb: 0.01,
    value: 0.2,
    actions: [
      { actionId: 5, prob: 0.8 }, // Discard 1m — the champion's preferred action
      { actionId: 6, prob: 0.15 },
      { actionId: 7, prob: 0.04 },
      { actionId: 8, prob: 0.01 },
    ],
    ...overrides,
  }
}

function fixtureReport(): ReviewReport {
  return {
    schemaVersion: 1,
    matchId: 'm1',
    ruleset: 'fenghua',
    checkpointPath: '/ckpt',
    checkpointStep: 10,
    generatedAt: '2026-01-01T00:00:00Z',
    decisions: [dec(), dec({ round: 0, actionIndex: 5, chosenActionId: 5, chosenProb: 0.8 })],
    seats: [
      { seat: 0, decisions: 2, meanChosenProb: 0.4, topGaps: [{ decision: 0, gap: 0.79 }] },
    ],
    valuesCalibrated: true,
  }
}

type PanelProps = Parameters<typeof ReviewPanel>[0]

/** Renders ReviewPanel with the common prop set, overriding only what a case cares about. */
function renderPanel(overrides: Partial<PanelProps> = {}): string {
  return renderToStaticMarkup(
    React.createElement(ReviewPanel, {
      report: fixtureReport(),
      status: 'ready',
      onRequestReview: () => {},
      viewSeat: 0,
      position: { round: 0, actionIndex: 3 },
      onJump: () => {},
      lang: 'en',
      onLangToggle: () => {},
      thresholds: SEVERITY_THRESHOLDS,
      onThresholdsChange: () => {},
      ...overrides,
    } as PanelProps),
  )
}

describe('ReviewPanel', () => {
  it('renders the severity badge and the champion top-action bar row for the decision at the current position', () => {
    const html = renderPanel()

    expect(html).toContain('Mistake') // severity badge
    expect(html).toContain('Discard 1m') // champion's top-action bar row label
  })

  it('shows the request-review button when no report exists yet', () => {
    const html = renderPanel({
      report: null,
      status: 'empty',
      position: { round: 0, actionIndex: -1 },
    })

    expect(html).toContain('Request review')
  })

  it('shows the neutral unavailable message on a 503 status', () => {
    const html = renderPanel({
      report: null,
      status: 'unavailable',
      position: { round: 0, actionIndex: -1 },
    })

    expect(html).toContain('Reviewer unavailable')
    expect(html).not.toContain('wrong')
  })

  it('shows the values-uncalibrated note and omits the sparkline when the report has null values', () => {
    const report: ReviewReport = {
      ...fixtureReport(),
      valuesCalibrated: false,
      decisions: [
        dec({ value: null }),
        dec({ round: 0, actionIndex: 5, chosenActionId: 5, chosenProb: 0.8, value: null }),
      ],
    }
    const html = renderPanel({
      report,
    })

    expect(html).toContain('Value estimates are unavailable for this policy')
    expect(html).not.toContain('review-sparkline')
  })

  // Regression (round 16, Finding 3): a cached schema-v1 report (generated
  // before valuesCalibrated existed) omits the field entirely, but always
  // carried real numeric decision values. It must render the value timeline,
  // not the uncalibrated warning.
  it('renders the value timeline (no uncalibrated warning) for a schema-v1 report missing valuesCalibrated', () => {
    const { valuesCalibrated: _drop, ...legacyReport } = fixtureReport()
    void _drop
    const report = legacyReport as ReviewReport

    const html = renderPanel({
      report,
    })

    expect(html).toContain('review-sparkline')
    expect(html).not.toContain('Value estimates are unavailable for this policy')
  })
})
