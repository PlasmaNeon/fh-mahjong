# web/src/i18n/locales/

> The two translation resources. English is the schema; Simplified Chinese must satisfy it.

## Key Files

- **en.ts** — Exports `en`, the **canonical translation-key definition**. Its keys generate the `TranslationKey` type that everything else is checked against, so adding a UI string starts here.
- **zh-CN.ts** — Exports `zhCN` typed as `Record<TranslationKey, string>`. Because of that annotation, **a key added to `en.ts` breaks the build until `zh-CN.ts` supplies it** — `npx tsc` is the guard, not review.

## Architecture Notes

- Keys are flat dotted strings (`'nav.profile'`, `'brand.name'`), not nested objects.
- Interpolation uses named `{variable}` placeholders. **Keep placeholder names identical in both files** — the type only checks that a key exists and is a string, not that its placeholders match.
- Both files are currently 245 lines; a diff in line count is a useful smell that one drifted.
- Consumers use `useI18n()` from `../I18nContext.tsx` rather than importing these directly.
