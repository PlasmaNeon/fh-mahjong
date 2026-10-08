# web/src/test/

> Shared helpers for vitest, which runs in a node environment without a DOM.

- **cssContract.ts** — `readSourceCss(...paths)` loads stylesheet sources (relative to `web/`) so
  tests can assert layout contracts on the CSS text.
- **renderStatic.tsx** — renders components with `react-dom/server` for HTML assertions.
- **memoryStorage.ts** — an in-memory `Storage` for code that persists preferences.
