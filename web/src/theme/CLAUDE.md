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
- **index.ts** — side-effect-imports `index.css` and re-exports the primitives (the public API).
- **components/** — `Page`, `Shell`, `Card`, `PageHeader`, `Section`, `Button`/`ButtonLink`,
  `TextLink`, `Field`, `Note`, `Toggle`, `ToolsRow`, `ClubShell`, `ToolTabs`, and `GameDialog`.

`Field` binds every visible label to its input. Success and error `Note` messages expose
live status semantics so validation changes are announced without changing consumer props.
`LoadingScreen` accepts an optional retry action for recoverable offline states.

`ClubShell` owns ordinary-page localized club identity, the global language override, and Profile navigation; it deliberately has no
Back/breadcrumb control, leaving history navigation to the browser. Route pages must not
recreate ad-hoc Home/Play/Account link clusters. `ToolTabs` owns the
localized Scoring/Shanten switcher while preserving both tool deep links.

The bone-paper authentication popup is implemented by `features/auth/AuthDialog.tsx`, while
its material classes live in `base.css` alongside the compact home switchboard and paipu slips.

`GameDialog` is the semantic modal shell used by game exit and match-end surfaces. It
owns labelled-dialog markup, initial focus, optional Escape cancellation, the compass
mark, tone styling, and shared action layout; callers continue to own business actions.

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
