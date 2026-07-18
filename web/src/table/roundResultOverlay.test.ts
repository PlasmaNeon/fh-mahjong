import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { TableRoundResultOverlay, type RoundResultView } from './TableScene'
import { I18nProvider } from '../i18n/I18nContext'

const result: RoundResultView = {
  isDraw: false,
  winType: 'ron',
  winnerLabel: 'Seat 2 wins',
  discarderLabel: 'From Seat 3',
  breakdown: [
    { name: 'Base Point (坐台)', points: 1 },
    { name: 'Independence (大大胡)', points: 50 },
  ],
  totalScore: 52,
  payouts: [
    { seat: 0, label: 'Seat 0', amount: -52, readyLabel: 'Waiting' },
    { seat: 1, label: 'Seat 1', amount: -52, readyLabel: 'Ready', readyActive: true },
    { seat: 2, label: 'Seat 2', amount: 208, readyLabel: 'Ready', readyActive: true },
    { seat: 3, label: 'Seat 3', amount: -104, readyLabel: 'Waiting' },
  ],
  actions: createElement('button', { type: 'button' }, 'Ready'),
}

describe('TableRoundResultOverlay', () => {
  const renderOverlay = (overlayResult: RoundResultView) => renderToStaticMarkup(
    createElement(I18nProvider, null, createElement(TableRoundResultOverlay, { result: overlayResult })),
  )

  it('keeps a labelled scroll body before a persistent action footer', () => {
    const markup = renderOverlay(result)
    expect(markup).toContain('role="dialog"')
    expect(markup).toContain('aria-modal="true"')
    expect(markup).toContain('aria-labelledby="round-result-title"')
    expect(markup.indexOf('round-result-scroll')).toBeLessThan(markup.indexOf('round-result-actions'))
  })

  it('renders four payouts as one accessible strip without a visible section title', () => {
    const markup = renderOverlay(result)

    expect(markup).toContain('aria-label="Seat payouts"')
    expect(markup).not.toContain('>Payouts<')
    expect(markup.match(/round-result-payout-cell/g)).toHaveLength(4)
    expect(markup).toContain('round-result-payout-status-dot')
    expect(markup).toContain('>Ready<')
    expect(markup).toContain('>Waiting<')
  })

  it('omits payout status when replay data has no readiness state', () => {
    const replayResult = {
      ...result,
      payouts: result.payouts?.map(({ readyLabel: _readyLabel, readyActive: _readyActive, ...payout }) => payout),
    }
    const markup = renderOverlay(replayResult)

    expect(markup).not.toContain('round-result-payout-status')
  })
})

function readRoundResultCss() {
  return ['src/index.css', 'src/table/roundResult.css']
    .map((path) => resolve(process.cwd(), path))
    .filter((path) => existsSync(path))
    .map((path) => readFileSync(path, 'utf8'))
    .join('\n')
}

function ruleBody(css: string, selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
}

describe('round-result CSS reachability contract', () => {
  it('sizes from the viewport and reserves a persistent action row', () => {
    const css = readRoundResultCss()

    expect(ruleBody(css, '.round-result-modal')).toContain('grid-template-rows: minmax(0, 1fr) auto')
    expect(ruleBody(css, '.round-result-scroll')).toContain('overflow-y: auto')
    expect(ruleBody(css, '.round-result-actions')).toContain('flex-shrink: 0')
    expect(css).toContain('100dvh')
    expect(css).not.toContain('--game-stage-scaled-height')
    expect(css).not.toContain('--game-stage-scaled-width')
  })

  it('keeps all four seat payouts in one row at the phone breakpoint', () => {
    const css = readRoundResultCss()

    expect(ruleBody(css, '.round-result-payout-grid')).toContain('grid-template-columns: repeat(4, minmax(0, 1fr))')
    expect(css).not.toContain('.round-result-payout-grid { grid-template-columns: repeat(2')
  })
})
