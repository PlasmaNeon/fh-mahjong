# web/src/i18n/

> Typed, dependency-free internationalization.

- **I18nContext.tsx** — picks the first supported language from `navigator.languages` (every
  Chinese variant maps to Simplified Chinese; default English), syncs `<html lang>`, and sets the
  document title from `brand.direct`. `useI18n()` returns `language`, `shortLanguage`, `t()`, and
  the setters; components use it instead of reading `navigator`.
- **locales/** — resources (see `locales/CLAUDE.md`).

## Languages

The app is English and Simplified Chinese. The reviewer namespace (`review.*`) adds Japanese,
Korean, and Russian; outside it those languages fall back to English. The reviewer language
choice persists in localStorage. Device defaults stay English/Chinese.

## Rules

- Interpolation uses named `{variable}` placeholders, identical across languages.
- Server-rendered tests of components that call `useI18n()` must wrap them in `I18nProvider`.
- `I18nContext.test.ts` covers normalization, preference order, and fallback.
