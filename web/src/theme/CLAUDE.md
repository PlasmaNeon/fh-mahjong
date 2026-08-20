# web/src/theme/

> The app's shared Rainy Mahjong Club theme: design tokens, structural CSS, and typed React primitives.

## Overview

Single source of truth for the app-wide material language: Fraunces/Noto Serif display
type, IBM Plex UI type, ink/rain backdrops, bone-paper surfaces, jade controls, brass
focus and victory details, and seal-red danger treatment. The identity is intentionally
single-theme rather than following `prefers-color-scheme`.
The CSS is imported once globally from `web/src/main.tsx` (`import './theme/index.css'`);
the barrel `index.ts` also side-effect-imports it so importing any primitive pulls the styles.

## Decoupling contract

- Re-theme colors/fonts/spacing → edit **`tokens.css`** only (or add a `[data-theme="x"]`
  block of overrides).
- Change the look/structure → reimplement **`base.css`** + the primitive components;
  pages built from primitives stay untouched.
- The `.ledger-*` / `.ldg-*` class names are an internal implementation detail. Pages built
  from primitives never reference them. `Calc.tsx` / `Shanten.tsx` are "advanced consumers"
  that use the utility classes directly for their dense tool layouts (palettes, discard rows,
  melds, big-stat) — componentizing those was deliberately out of scope (YAGNI).

## Files

- **tokens.css** — font imports plus the six identity colours, semantic states, physical
  material colours, typography roles, radii, and shadows. This *is* the theme's values.
- **base.css** — every structural class (`.ledger-page`, `.ledger-shell`, `.ldg-page`,
  `.ldg-section`, `.ldg-tile`, `.ldg-btn`, `.ldg-input`, …) consuming the tokens.
- **index.css** — `@import`s tokens.css then base.css.
- **index.ts** — side-effect-imports `table/table-geometry.css` and re-exports the primitives (the public API).
- **components/** — The typed React primitives that form the design system's public API:
  `Page`, `Shell`, `Card`, `PageHeader`, `Section`, `Button`/`ButtonLink`, `TextLink`,
  `Field`, `Note`, `Toggle`, `LoadingScreen`, `ButtonRow`, `ClubShell`, `ToolTabs`, and
  `GameDialog`. Per-component detail and accessibility contracts are in
  [components/CLAUDE.md](components/CLAUDE.md).

The bone-paper authentication popup is implemented by `features/auth/AuthDialog.tsx`, while
its material classes live in `base.css` alongside the compact home switchboard and paipu slips.

## Usage

```tsx
import { Page, Shell, Card, PageHeader, Section, Button } from '../theme'

<Page><Shell><Card>
  <PageHeader title="Title" subtitle="副标题" nav={<TextLink to="/">Home</TextLink>} />
  <Section title="Thing" meta="0 / 4">
    <Button variant="primary">Go</Button>
  </Section>
</Card></Shell></Page>
```
