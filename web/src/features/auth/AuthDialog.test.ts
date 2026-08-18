import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
import AuthDialog from './AuthDialog'
import { renderStatic } from '../../test/renderStatic'

const renderDialog = (props: Parameters<typeof AuthDialog>[0]) =>
  renderStatic(createElement(AuthDialog, props))

describe('AuthDialog', () => {
  it('labels the popup and exposes a close control for optional login', () => {
    const markup = renderDialog({
      title: 'Enter the club',
      subtitle: 'Sign in once.',
      dismissible: true,
      onCancel: () => undefined,
      children: createElement('form', null, 'Ticket'),
    })
    expect(markup).toContain('role="dialog"')
    expect(markup).toContain('aria-modal="true"')
    expect(markup).toContain('aria-label="Close sign in"')
    expect(markup).toContain('Enter the club')
  })

  it('does not expose dismissal for a required continuation', () => {
    const markup = renderDialog({
      title: 'You’ve been invited',
      subtitle: 'Sign in to continue.',
      dismissible: false,
      children: createElement('form', null, 'Ticket'),
    })
    expect(markup).not.toContain('Close sign in')
  })
})
