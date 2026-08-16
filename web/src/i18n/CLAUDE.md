# web/src/i18n/

> Typed, dependency-free internationalization for the React frontend.

## Architecture

- `I18nContext.tsx` selects the first supported device language from `navigator.languages`, defaults to English, maps every Chinese locale variant to the available Simplified Chinese resource, and synchronizes `<html lang>`.
- `locales/en.ts` is the canonical translation-key definition. `locales/zh-CN.ts` must satisfy every English key through `Record<TranslationKey, string>`.
- `useI18n()` exposes `language`, `shortLanguage`, `t()`, and the shared language setters. User-visible components should use this context instead of inspecting `navigator` independently.
- Interpolation uses named `{variable}` placeholders. Keep placeholder names identical in both resources.

## Tests

`I18nContext.test.ts` protects locale normalization, preference ordering, and the English fallback. Server-rendered component tests that consume `useI18n()` must wrap their subject in `I18nProvider`.
