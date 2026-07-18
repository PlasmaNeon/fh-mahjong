import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { en, type TranslationKey } from './locales/en'
import { zhCN } from './locales/zh-CN'

export type AppLanguage = 'en' | 'zh-CN'
type Variables = Record<string, string | number>

const resources: Record<AppLanguage, Record<TranslationKey, string>> = {
  en,
  'zh-CN': zhCN,
}

export function detectDeviceLanguage(languages?: readonly string[]): AppLanguage {
  const candidates = languages ?? (
    typeof navigator === 'undefined'
      ? []
      : navigator.languages?.length
        ? navigator.languages
        : [navigator.language]
  )

  for (const language of candidates) {
    const baseLanguage = language?.toLowerCase().split('-')[0]
    if (baseLanguage === 'zh') return 'zh-CN'
    if (baseLanguage === 'en') return 'en'
  }
  return 'en'
}

function formatMessage(message: string, variables: Variables = {}) {
  return message.replace(/\{(\w+)\}/g, (match, name: string) => (
    Object.prototype.hasOwnProperty.call(variables, name) ? String(variables[name]) : match
  ))
}

type I18nValue = {
  language: AppLanguage
  shortLanguage: 'en' | 'zh'
  setLanguage: (language: AppLanguage) => void
  toggleLanguage: () => void
  t: (key: TranslationKey, variables?: Variables) => string
}

const I18nContext = createContext<I18nValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<AppLanguage>(detectDeviceLanguage)

  useEffect(() => {
    document.documentElement.lang = language
    document.title = resources[language]['brand.name']
  }, [language])

  const value = useMemo<I18nValue>(() => ({
    language,
    shortLanguage: language === 'zh-CN' ? 'zh' : 'en',
    setLanguage,
    toggleLanguage: () => setLanguage(current => current === 'en' ? 'zh-CN' : 'en'),
    t: (key, variables) => formatMessage(resources[language][key], variables),
  }), [language])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n() {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside I18nProvider')
  return value
}
