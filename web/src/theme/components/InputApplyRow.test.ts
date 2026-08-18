import { describe, it, expect } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { InputApplyRow } from './InputApplyRow'

const base = { value: '1m2m3m', onChange: () => {}, onApply: () => {}, applyLabel: 'Apply' }

describe('InputApplyRow', () => {
  it('renders the ldg input row both tool pages use', () => {
    const html = renderToStaticMarkup(
      createElement(InputApplyRow, { ...base, placeholder: '3z' }),
    )
    expect(html).toContain('ldg-input-row')
    expect(html).toContain('class="ldg-input"')
    expect(html).toContain('value="1m2m3m"')
    expect(html).toContain('placeholder="3z"')
    expect(html).toContain('class="ldg-btn"')
    expect(html).toContain('Apply')
  })

  it('omits the placeholder attribute when none is given', () => {
    expect(renderToStaticMarkup(createElement(InputApplyRow, base))).not.toContain('placeholder')
  })
})
