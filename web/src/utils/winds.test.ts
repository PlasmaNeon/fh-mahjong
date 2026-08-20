import { describe, it, expect } from 'vitest'
import { WIND_I18N_KEYS, WIND_KANJI, windI18nKey } from './winds'

describe('wind labels', () => {
  it('indexes kanji by 1-based seat wind, matching the proto (East=1)', () => {
    expect(WIND_KANJI[1]).toBe('東')
    expect(WIND_KANJI[2]).toBe('南')
    expect(WIND_KANJI[3]).toBe('西')
    expect(WIND_KANJI[4]).toBe('北')
  })

  it('keeps a blank at index 0 so callers can index by wind directly', () => {
    expect(WIND_KANJI[0]).toBe('')
  })

  it('uses traditional kanji, not the simplified forms used for jihai tile names', () => {
    // reviewUtils renders jihai TILE names with simplified 东; the table décor
    // uses traditional 東. They are deliberately different and must not merge.
    expect(WIND_KANJI[1]).not.toBe('东')
  })

  it('maps a 1-based seat wind to its i18n key', () => {
    expect(windI18nKey(1)).toBe('common.east')
    expect(windI18nKey(4)).toBe('common.north')
  })

  it('exposes the keys in seat order for callers that map the whole set', () => {
    expect(WIND_I18N_KEYS).toEqual(['common.east', 'common.south', 'common.west', 'common.north'])
  })
})
