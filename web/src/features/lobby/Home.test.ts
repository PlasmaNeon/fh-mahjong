import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../../contexts/AuthContext'
import ClubShell from '../../theme/components/ClubShell'
import Home from './Home'
import ToolsShell from '../../theme/components/ToolsShell'
import { I18nProvider } from '../../i18n/I18nContext'

function renderAt(path: string, child: ReturnType<typeof createElement>) {
  return renderToStaticMarkup(
    createElement(I18nProvider, null,
      createElement(AuthProvider, null,
        createElement(MemoryRouter, { initialEntries: [path] }, child),
      ),
    ),
  )
}

describe('streamlined club navigation', () => {
  it('shows functional home actions without atmospheric copy', () => {
    const markup = renderAt('/', createElement(Home))
    expect(markup).toContain('Paipu Replay')
    expect(markup).not.toContain('One more hand before the rain stops')
    expect(markup).not.toContain('Tonight at the club')
    expect(markup).toContain('Find Match')
    expect(markup).toContain('Create Private Table')
    expect(markup).toContain('Join an invitation')
    expect(markup).toContain('data-theme="direct-tools"')
    expect(markup).not.toContain('club-home__compass')
  })

  it('keeps /play as the same functional entry', () => {
    expect(renderAt('/play', createElement(Home))).toContain('Find Match')
  })

  it('locks every app navigation link during matchmaking', () => {
    const markup = renderAt('/play', createElement(ClubShell, { navigationLocked: true, children: createElement('div', null, 'Searching') }))
    expect(markup).not.toContain('href=')
    expect(markup).toContain('Search in progress')
  })

  it('takes tool navigation to real routes in development too', () => {
    const markup = renderAt('/tools/calc', createElement(ToolsShell, { title: 'Scoring', children: createElement('div', null, 'Workbench') }))
    expect(markup).toContain('href="/"')
    expect(markup).toContain('href="/replay"')
    expect(markup).not.toContain('ui-prototype.html')
  })

  it('does not render a Back control in ClubShell', () => {
    const markup = renderAt('/tools/calc', createElement(ClubShell, { title: 'Scoring', children: createElement('div', null, 'Workbench') }))
    expect(markup).not.toContain('>Back<')
    expect(markup).toContain('Profile')
  })
})
