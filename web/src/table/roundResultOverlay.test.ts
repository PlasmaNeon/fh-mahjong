import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { Children, createElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { TableRoundResultOverlay, type RoundResultView } from './TableScene'

type ElementProps = {
  children?: ReactNode
  className?: string
  role?: string
  'aria-modal'?: boolean
  'aria-labelledby'?: string
}

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
    { seat: 0, label: 'Seat 0', amount: -52, readyLabel: '...' },
    { seat: 1, label: 'Seat 1', amount: -52, readyLabel: 'Ready', readyActive: true },
    { seat: 2, label: 'Seat 2', amount: 208, readyLabel: 'Ready', readyActive: true },
    { seat: 3, label: 'Seat 3', amount: -104, readyLabel: '...' },
  ],
  actions: createElement('button', { type: 'button' }, 'Ready'),
}

describe('TableRoundResultOverlay', () => {
  it('keeps a labelled scroll body before a persistent action footer', () => {
    const overlay = TableRoundResultOverlay({ result }) as ReactElement<ElementProps>
    const dialog = overlay.props.children as ReactElement<ElementProps>
    const children = Children.toArray(dialog.props.children) as ReactElement<ElementProps>[]

    expect(dialog.props.role).toBe('dialog')
    expect(dialog.props['aria-modal']).toBe(true)
    expect(dialog.props['aria-labelledby']).toBe('round-result-title')
    expect(children).toHaveLength(2)
    expect(children[0].props.className).toBe('round-result-scroll')
    expect(children[1].props.className).toBe('round-result-actions')
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
})
