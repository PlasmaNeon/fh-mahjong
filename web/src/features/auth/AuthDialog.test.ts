import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import AuthDialog from './AuthDialog'

describe('AuthDialog', () => {
  it('labels the popup and exposes a close control for optional login', () => {
    const markup = renderToStaticMarkup(createElement(AuthDialog, {
      title: 'Enter the club',
      subtitle: 'Sign in once.',
      dismissible: true,
      onCancel: () => undefined,
      children: createElement('form', null, 'Ticket'),
    }))
    expect(markup).toContain('role="dialog"')
    expect(markup).toContain('aria-modal="true"')
    expect(markup).toContain('aria-label="Close sign in"')
    expect(markup).toContain('Enter the club')
  })

  it('does not expose dismissal for a required continuation', () => {
    const markup = renderToStaticMarkup(createElement(AuthDialog, {
      title: 'You’ve been invited',
      subtitle: 'Sign in to continue.',
      dismissible: false,
      children: createElement('form', null, 'Ticket'),
    }))
    expect(markup).not.toContain('Close sign in')
  })
})
