# web/src/theme/components/

> The typed React primitives that make up the Rainy Mahjong Club design system's public API.

## Overview

Every component here consumes tokens from `../tokens.css` through the structural classes in `../base.css`. Route pages compose these primitives; they should never reach for the underlying `.ledger-*` / `.ldg-*` class names, which are an internal implementation detail. Re-exported through `../index.ts`, so `import { Page, Card, Button } from '../../theme'` is the intended usage.

## Key Files

### Layout
- **Page.tsx** / **Shell.tsx** / **Card.tsx** / **Section.tsx** — The page → shell → card → section nesting every route uses.
- **PageHeader.tsx** — Title, subtitle, and optional `nav` slot.
- **ClubShell.tsx** — Ordinary-page localized club identity, the global language override, and Profile navigation. **Deliberately has no Back/breadcrumb control** — history navigation is left to the browser. Route pages must not recreate ad-hoc Home/Play/Account link clusters.
- **ButtonRow.tsx** — Horizontal row of buttons/links; `end` right-aligns them. Used on account, lobby, room and replay pages.
- **ToolTabs.tsx** — The localized Scoring/Shanten switcher, preserving both tool deep links.

### Controls and content
- **Button.tsx** — `Button` and `ButtonLink` plus the `ButtonVariant` type.
- **TextLink.tsx** — Inline navigation link.
- **Field.tsx** — **Binds every visible label to its input**; use it rather than hand-rolling label/input pairs.
- **Toggle.tsx** — Boolean control.
- **Note.tsx** — Success and error messages expose live status semantics, so validation changes are announced without changing consumer props.
- **LoadingScreen.tsx** — Accepts an optional retry action for recoverable offline states.
- **GameDialog.tsx** — The semantic modal shell behind game exit and match-end surfaces. Owns labelled-dialog markup, initial focus, optional Escape cancellation, the compass mark, tone styling (`GameDialogTone`), and shared action layout; callers keep their own business actions. `handleDialogKeyDown` is exported for reuse and covered by `GameDialog.test.ts`.

## Architecture Notes

- **Re-theming colors/fonts/spacing means editing `../tokens.css` only** (or adding a `[data-theme="x"]` override block). Changing look/structure means reimplementing `../base.css` plus these components — pages stay untouched either way.
- The identity is intentionally single-theme and does **not** follow `prefers-color-scheme`.
- `Calc.tsx` and `Shanten.tsx` are deliberate exceptions: they use the utility classes directly for dense tool layouts (palettes, discard rows, melds, big-stat). Componentizing those was scoped out as YAGNI.
- `features/auth/AuthDialog.tsx` is implemented in the auth feature, but its material classes live in `../base.css` alongside the compact home switchboard and paipu slips.

## LedgerTile.tsx

The ledger-workbench tile widgets shared by the calc and shanten tool pages:

- `LedgerTile` — the `.ldg-tile` button (face image, size/selected/dimmed modifiers, optional badge)
- `LedgerTileRow` — a row of drafted tiles, or the empty-state note
- `LedgerPaletteGrid` — the full `TILE_LIBRARY` palette

`disabled` is an explicit prop, not derived from `dimmed`: the shanten palette disables
exhausted tiles while the calc palette dims the selected tile but stays clickable. Passing
`usedCounts` to `LedgerPaletteGrid` switches on the shanten behaviour (remaining-copies
badge, exhausted tiles dimmed and disabled).

Tool pages must not re-implement these — extend the primitives instead.
