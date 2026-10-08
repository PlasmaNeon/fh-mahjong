# web/src/theme/

> Design tokens, structural CSS, typed primitives, and the Direct play shells.

Menu pages use the light Direct play look (Source Sans / Noto Sans, blue controls, white
surfaces) through `DirectShell`; tool pages use `ToolsShell` with the scoped
`[data-theme="direct-tools"]` palette; the table keeps its own skin
(`table/table-theme.css`, then `table/direct-table.css`). Themes ignore `prefers-color-scheme`.

## Files

- **tokens.css** — fonts, colors, semantic states, typography roles, radii, shadows. Re-theme
  here only (or add a `[data-theme="x"]` override block).
- **base.css** — every structural class (`.ledger-*`, `.ldg-*`) consuming the tokens, including
  the auth dialog's materials.
- **direct-shell.css** — adapts entry panels, menu primitives, waiting rooms, replay slips, and the
  auth dialog to Direct play.
- **direct-tools.css** — workbench materials inside `ToolsShell`.
- **index.css** — the single ordered CSS entry: fonts, `../index.css`, tokens, base, the table
  skins, the Direct play layers.
- **index.ts** — imports `index.css` and re-exports the primitives.
- **components/** — the typed primitives (see `components/CLAUDE.md`).

## Contract

- Pages compose primitives and never reference `.ledger-*` / `.ldg-*` class names directly.
  `Calc.tsx` and `Shanten.tsx` are the deliberate exceptions (dense tool layouts).
- Changing look or structure means reimplementing `base.css` and the primitives; pages stay
  untouched.

```tsx
import { Page, Shell, Card, PageHeader, Section, Button } from '../theme'

<Page><Shell><Card>
  <PageHeader title="Title" subtitle="副标题" />
  <Section title="Thing" meta="0 / 4"><Button variant="primary">Go</Button></Section>
</Card></Shell></Page>
```
