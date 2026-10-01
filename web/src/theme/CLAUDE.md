# web/src/theme/

> Shared design tokens, typed React primitives, Direct play menu surfaces, and scoped table skins.

## Overview

Production menu pages use Direct play's light surfaces, blue controls, and Source Sans/Noto Sans typography via `DirectShell`. The root Rainy Club tokens remain the base for legacy consumers; shared tables override their materials through `direct-table.css`. These authored themes do not follow `prefers-color-scheme`.
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
- **index.css** — the single ordered CSS surface: fonts, then `../index.css` (Tailwind, app globals, `table/roundResult.css`, `table/table-geometry.css`), then `tokens.css`, `base.css`, and `../table/table-theme.css`.
- **index.ts** — side-effect-imports `./index.css` and re-exports the primitives (the public API).
- **components/** — The typed React primitives that form the design system's public API:
  `Page`, `Shell`, `Card`, `PageHeader`, `Section`, `Button`/`ButtonLink`, `TextLink`,
  `Field`, `Note`, `Toggle`, `LoadingScreen`, `ButtonRow`, `ClubShell`, `ToolTabs`,
  `GameDialog`, `LedgerTile`/`LedgerTileRow`/`LedgerPaletteGrid`, and `InputApplyRow`. Per-component detail and accessibility contracts are in
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

## Direct play tools

`components/ToolsShell.tsx` wraps calc/shanten with a text-only brand, shared navigation and a single language control. `tokens.css` scopes the light palette to `[data-theme="direct-tools"]`; `direct-tools.css` overrides workbench materials and responsive layout inside that shell only. Ordinary menu routes now use the same light palette through `DirectShell`, including production Home, Lobby, rooms, account, and replay library. Navigation always targets real Play/Replays/Tools routes in both development and production.

`index.css` imports `table/direct-table.css` after the legacy table skin. This scoped presentation layer refreshes game dialogs and final standings independently of ordinary menu surfaces.

`direct-shell.css` adapts entry panels, ordinary menu primitives, waiting rooms, replay slips, and the auth dialog to Direct play. `components/DirectShell.tsx` owns text-only branding and responsive Play/Replays/Tools navigation; all links, including brand/Profile, become non-navigation text during a queued search.
