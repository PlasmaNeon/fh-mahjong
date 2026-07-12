import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import GameDialog, { handleDialogKeyDown } from './GameDialog'

describe('GameDialog', () => {
  it('renders an accessible labelled modal with the selected tone', () => {
    const markup = renderToStaticMarkup(
      createElement(
        GameDialog,
        {
          eyebrow: 'Final table',
          title: 'Match over',
          tone: 'win',
          actions: createElement('button', { type: 'button' }, 'Leave'),
          children: createElement('p', null, 'East finished first.'),
        },
      ),
    )

    expect(markup).toContain('role="dialog"')
    expect(markup).toContain('aria-modal="true"')
    expect(markup).toContain('aria-labelledby=')
    expect(markup).toContain('rain-dialog--win')
    expect(markup).toContain('Final table')
    expect(markup).toContain('Match over')
    expect(markup).toContain('East finished first.')
    expect(markup).toContain('Leave')
  })

  it('only routes Escape to a provided cancel handler', () => {
    const onCancel = vi.fn()

    handleDialogKeyDown({ key: 'Enter', preventDefault: vi.fn() }, onCancel)
    expect(onCancel).not.toHaveBeenCalled()

    const preventDefault = vi.fn()
    handleDialogKeyDown({ key: 'Escape', preventDefault }, onCancel)
    expect(preventDefault).toHaveBeenCalledOnce()
    expect(onCancel).toHaveBeenCalledOnce()
  })
})
