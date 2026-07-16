import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { AuthProvider } from '../../contexts/AuthContext'
import ClubShell from '../../theme/components/ClubShell'
import Home from './Home'

function renderAt(path: string, child: ReturnType<typeof createElement>) {
  return renderToStaticMarkup(
    createElement(AuthProvider, null,
      createElement(MemoryRouter, { initialEntries: [path] }, child),
    ),
  )
}

describe('streamlined club navigation', () => {
  it('shows functional home actions without atmospheric copy', () => {
    const markup = renderAt('/', createElement(Home))
    expect(markup).toContain('Paipu Replay')
    expect(markup).not.toContain('One more hand before the rain stops')
    expect(markup).not.toContain('Tonight at the club')
    expect(markup).not.toContain('<small>')
  })

  it('does not render a Back control in ClubShell', () => {
    const markup = renderAt('/tools/calc', createElement(ClubShell, { title: 'Scoring', children: createElement('div', null, 'Workbench') }))
    expect(markup).not.toContain('>Back<')
    expect(markup).toContain('Profile')
  })
})
