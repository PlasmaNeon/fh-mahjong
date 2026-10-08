# web/src/theme/components/

> The typed primitives — the design system's public API, re-exported from `../index.ts`
> (`import { Page, Card, Button } from '../../theme'`).

## Shells and navigation
- **DirectShell.tsx** — shared by `ClubShell` and `ToolsShell`: text-only localized brand,
  active-route Play/Replays/Tools navigation, desktop/phone placement, and navigation locking
  while a match search is queued. Takes an optional Profile slot so tools work without auth.
- **ClubShell.tsx** — auth-aware `DirectShell` with Profile navigation. No Back/breadcrumb
  control; pages must not add ad-hoc Home/Play/Account link clusters.
- **ToolsShell.tsx** — the calc/shanten shell: shared navigation, one language control, a
  screen-reader page title; tool state stays in each feature.
- **ToolTabs.tsx** — the localized Scoring/Shanten switcher.

## Layout
- **Page**, **Shell**, **Card**, **Section** — the nesting every route uses.
- **PageHeader** — title, subtitle, optional `nav` slot.
- **ButtonRow** — a row of buttons/links; `end` right-aligns.

## Controls and content
- **Button** / **ButtonLink** (`ButtonVariant`), **TextLink**, **Toggle**.
- **Field** — binds every visible label to its input; use it instead of hand-rolled pairs.
- **Note** — success/error messages with live-region semantics.
- **LoadingScreen** — optional retry action for recoverable offline states.
- **GameDialog** — the semantic modal for game exit and match end: labelled markup, initial
  focus, optional Escape, tones, shared action layout. `handleDialogKeyDown` is exported.
- **InputApplyRow** — the notation input + Apply row of the tools.
- **LedgerTile.tsx** — `LedgerTile`, `LedgerTileRow`, `LedgerPaletteGrid` for the tool pages.
  `disabled` is explicit, not derived from `dimmed`: shanten disables exhausted palette tiles,
  calc dims the selected tile but keeps it clickable. Passing `usedCounts` switches on the shanten
  behavior. Tool pages must extend these, not re-implement them.
