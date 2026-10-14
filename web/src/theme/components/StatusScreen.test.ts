import { createElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { renderStatic } from '../../test/renderStatic'
import LoadingScreen from './LoadingScreen'
import StatusScreen from './StatusScreen'
import { ButtonLink } from './Button'

const render = (child: ReturnType<typeof createElement>) => renderStatic(createElement(MemoryRouter, { initialEntries: ['/replay/example'] }, child))

describe('route recovery states', () => {
  it('keeps navigation and a library destination on a failed replay', () => {
    const html = render(createElement(StatusScreen, {
      title: 'Unable to open replay', description: 'Try another replay.',
      actions: createElement(ButtonLink, { to: '/replay', children: 'Back to replays' }),
    }))
    expect(html).toContain('data-theme="direct-tools"')
    expect(html).toContain('href="/replay"')
    expect(html).toContain('aria-current="page"')
    expect(html).toContain('<h1 id="page-status-title">Unable to open replay</h1>')
    expect(html).not.toContain('ledger-page')
  })
  it('announces loading without implying ongoing progress while waiting for retry', () => {
    const loading = render(createElement(LoadingScreen, { label: 'Loading replay' }))
    expect(loading).toContain('role="status"')
    expect(loading).toContain('direct-status__spinner')
    const offline = render(createElement(LoadingScreen, { label: 'Offline', onRetry: () => {} }))
    expect(offline).not.toContain('direct-status__spinner')
    expect(offline).toContain('<button')
  })
})
