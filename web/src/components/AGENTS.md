# web/src/components/

> Shared "Tabletop Glass" theme primitives used by every non-game page.

## Overview

These presentational components are the single source of truth for the app's
out-of-game visual language (emerald / deep-green glass). Pages compose them
instead of repeating Tailwind class strings. They contain no business logic.

The in-game board (`Game.tsx`, `table/TableScene.tsx`, the `.mahjong-table`
styles in `index.css`, and the Replay board area) deliberately does **not** use
these — it has its own tabletop theme.

## Key Files

- **PageShell.tsx** — Full-height layered background (radial emerald glow over a
  deep teal→navy gradient) plus a centered max-width column. Props: `maxWidth`
  (default `max-w-6xl`), `className`, `children`.
- **GlassCard.tsx** — Dark translucent glass panel (`rounded-[28px]`, blurred,
  deep shadow). Props: `className` (for border tint / padding overrides),
  `children`.
- **Eyebrow.tsx** — Small black-weight uppercase label above headings.
- **PageHeading.tsx** — Large uppercase display heading.
- **Button.tsx** — `ButtonLink` (router `<Link>`) and `Button` (native button),
  both with a `variant` prop: `primary` (emerald + glow), `secondary` (cyan
  glass), `ghost` (translucent slate).

## Usage

```tsx
import PageShell from '../components/PageShell'
import GlassCard from '../components/GlassCard'
import Eyebrow from '../components/Eyebrow'
import PageHeading from '../components/PageHeading'
import { ButtonLink } from '../components/Button'

<PageShell maxWidth="max-w-7xl">
  <GlassCard>
    <Eyebrow>Matchmaking</Eyebrow>
    <PageHeading>Find A Table</PageHeading>
    <ButtonLink to="/play" variant="primary">Find Match</ButtonLink>
  </GlassCard>
</PageShell>
```
