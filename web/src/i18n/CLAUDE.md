# web/src/i18n/

> Typed, dependency-free internationalization for the React frontend.

## Architecture

- `I18nContext.tsx` selects the first supported device language from `navigator.languages`, defaults to English, maps every Chinese locale variant to the available Simplified Chinese resource, and synchronizes `<html lang>`.
- `locales/en.ts` is the canonical translation-key definition. `locales/zh-CN.ts` must satisfy every English key through `Record<TranslationKey, string>`.
- `useI18n()` exposes `language`, `shortLanguage`, `t()`, and the shared language setters. User-visible components should use this context instead of inspecting `navigator` independently.
- Interpolation uses named `{variable}` placeholders. Keep placeholder names identical in both resources.

## Tests

`I18nContext.test.ts` protects locale normalization, preference ordering, and the English fallback. Server-rendered component tests that consume `useI18n()` must wrap their subject in `I18nProvider`.

The browser document title uses the localized `brand.direct` identity (Fenghua Mahjong / 奉化麻将), matching the production entry shell.

## Reviewer languages

`locales/review.ts` defines the typed `review.*` namespace for English, Simplified Chinese, Japanese, Korean and Russian. `AppLanguage` includes all five. `t` accepts ordinary keys and reviewer keys; unsupported application copy falls back to English. The chosen reviewer language persists in localStorage (no auth data). Device defaults remain English/Chinese for backward compatibility. Reviewer tests enforce complete translations and matching interpolation variables.

Japanese, Korean and Russian reviewer shell overrides localize transport, seat/HUD and settlement labels while unrelated app copy retains the English fallback.
