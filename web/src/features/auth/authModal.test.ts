import { describe, expect, it } from 'vitest'
import { resolveAuthDialogMode } from './authModal'

describe('resolveAuthDialogMode', () => {
  it('keeps optional background-location login dismissible', () => {
    expect(resolveAuthDialogMode({ hasBackground: true, optional: true, returnToParam: '/play' })).toEqual({
      dismissible: true,
      closeTo: null,
    })
  })

  it('keeps protected and invitation continuations required', () => {
    expect(resolveAuthDialogMode({ hasBackground: false, optional: false, returnToParam: '/room/rain1234' })).toEqual({
      dismissible: false,
      closeTo: null,
    })
  })

  it('allows a direct optional login to return home', () => {
    expect(resolveAuthDialogMode({ hasBackground: false, optional: false, returnToParam: null })).toEqual({
      dismissible: true,
      closeTo: '/',
    })
  })
})
