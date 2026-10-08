# web/src/i18n/locales/

> Translation resources. English defines the keys; every other resource must satisfy them.

- **en.ts** — `en`, the canonical key set; it generates `TranslationKey`. New UI strings start
  here.
- **zh-CN.ts** — `zhCN: Record<TranslationKey, string>`. A key added to `en.ts` breaks `npx tsc`
  until it exists here.
- **review.ts** — the five-language `review.*` namespace (`ReviewKey`, `reviewResources`), each
  language complete.
- **reviewPatterns.ts** — localized names for all 41 scoring pattern ids in the five reviewer
  languages; unknown ids keep their recorded label.

## Rules

- Keys are flat dotted strings (`'nav.profile'`).
- The type checks only that a key exists; placeholder names must also match across languages
  (`studyUtils.test.ts` checks the reviewer namespace).
- `en.ts` and `zh-CN.ts` have the same line count; a difference means one drifted.
- The calc and shanten tools share only nine `tools.*` keys. `apply` (应用/确认), `tilePalette`
  (牌库/选牌), and `language` (English/EN) read the same in English but differ in Chinese, so they
  stay per-tool (`I18nContext.test.ts` asserts the split).
- Consume through `useI18n()`, not by importing these files.
