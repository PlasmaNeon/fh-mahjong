import { describe, expect, it } from 'vitest'
import { detectDeviceLanguage } from './I18nContext'

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
