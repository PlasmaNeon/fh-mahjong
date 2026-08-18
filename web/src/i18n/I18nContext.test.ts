import { describe, expect, it } from 'vitest'
import { detectDeviceLanguage } from './I18nContext'
import { en } from './locales/en'
import { zhCN } from './locales/zh-CN'

describe('detectDeviceLanguage', () => {
  it.each(['zh', 'zh-CN', 'zh-SG', 'zh-TW', 'zh-HK'])(
    'uses simplified Chinese resources for %s',
    language => expect(detectDeviceLanguage([language])).toBe('zh-CN'),
  )

  it('uses Chinese when it appears in the device preference list', () => {
    expect(detectDeviceLanguage(['fr-FR', 'zh-CN', 'en-US'])).toBe('zh-CN')
  })

  it('honors the first supported device preference', () => {
    expect(detectDeviceLanguage(['en-US', 'zh-CN'])).toBe('en')
  })

  it.each([{ languages: ['en-US'] }, { languages: ['ja-JP'] }, { languages: [] }])('falls back to English for $languages', ({ languages }) => {
    expect(detectDeviceLanguage(languages)).toBe('en')
  })
})

describe('tool-page copy', () => {
  it('has a zh string for every tools/calc/shanten key', () => {
    const keys = Object.keys(en).filter((k) => /^(tools|calc|shanten)\./.test(k))
    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) {
      expect(zhCN, `missing zh for ${key}`).toHaveProperty(key)
    }
  })

  it('keeps the two tool pages from sharing copy that differs in zh', () => {
    // calc says 应用 / 牌库 where shanten says 确认 / 选牌. If a later pass merges
    // these under tools.*, the Chinese UI changes silently.
    expect(en['calc.apply']).toBe(en['shanten.apply'])
    expect(zhCN['calc.apply']).not.toBe(zhCN['shanten.apply'])
    expect(zhCN['calc.tilePalette']).not.toBe(zhCN['shanten.tilePalette'])
  })
})
