# Shanten + Calc Redesign

## Context

The Shanten Calculator and Fenghua Calculator pages currently carry strong
"AI taste": Inter font, slate-900 dark background, every section wrapped in
an identical `rounded-3xl border border-slate-800 bg-slate-900/70 shadow-xl`
card, uppercase tracking-wide subheadings, marketing-style subtitle copy,
generic amber-on-slate palette. Each page reads as a generated SaaS
dashboard, not as part of the Fenghua product.

The redesign replaces that surface with a deliberately **simple and clear**
look in **IBM Plex Sans**, with light and dark themes that auto-switch
via `prefers-color-scheme`. One restrained accent color carries all
"success" signaling; one danger color carries all errors. No ornament, no
gradients, no card chrome that doesn't serve a function.

The approved direction was confirmed against a live preview at
`web/public/ledger-preview.html` (latest version) — that file is the
visual source of truth for what the production pages should match.

Scope is intentionally narrow — only `Shanten.tsx`, `Calc.tsx`, and a new
theme stylesheet shared by both. Game, lobby, login, room creation, and
replay flows are untouched.

## Design Direction

- **Surface:** off-white `#fafaf8` page with white `#ffffff` cards in
  light mode; warm near-black `#121110` page with elevated `#1b1a18` cards
  in dark mode.
- **Type:** IBM Plex Sans for everything Latin, IBM Plex Sans SC for
  Chinese, IBM Plex Mono for numerics. No Inter. No italics. No display
  serif.
- **Color signaling:** one muted teal accent (`#1b6d5a` light /
  `#5fbb9f` dark) for success and selected state. One danger color
  (`#b03a2e` light / `#e5685c` dark) for invalid hands and validation
  errors. No amber, no vermilion, no slate.
- **Chrome:** 1px hairline rules between sections and on cards. 6–8px
  border-radius. No gradients, no glow, no `shadow-2xl`. Tiles get a
  1px box-shadow ring + small drop shadow.
- **One primary button** per page (Calculate on Calc). Everything else is
  text-link or outline button.

## Design Tokens

Defined as CSS custom properties in a new shared stylesheet imported by
both pages.

### File: `web/src/pages/ledger-theme.css`

```css
:root {
  --page:        #fafaf8;
  --surface:     #ffffff;
  --surface-2:   #f4f3ef;
  --ink:         #171615;
  --ink-2:       #3c3a36;
  --ink-3:       #6b6863;
  --ink-4:       #a09c95;
  --rule:        #e3e1dc;
  --rule-soft:   #ededea;
  --accent:      #1b6d5a;
  --accent-soft: #e7f0ed;
  --danger:      #b03a2e;
  --danger-soft: #fbeae8;

  --btn-bg:        var(--page);
  --btn-bg-hover:  #f0efeb;

  --tile-face:     #ffffff;
  --tile-shadow:   0 0 0 1px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.08);
  --tile-shadow-h: 0 0 0 1px rgba(0,0,0,0.08), 0 3px 6px rgba(0,0,0,0.10);

  --font:  "IBM Plex Sans", "IBM Plex Sans SC", system-ui, sans-serif;
  --mono:  "IBM Plex Mono", ui-monospace, monospace;

  --col:    680px;
  --gutter: clamp(1.25rem, 4vw, 2rem);
  --space:  2.25rem;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme]) {
    --page:        #121110;
    --surface:     #1b1a18;
    --surface-2:   #232220;
    --ink:         #eae7e0;
    --ink-2:       #c8c4bd;
    --ink-3:       #8c8881;
    --ink-4:       #5e5b56;
    --rule:        #2b2926;
    --rule-soft:   #232220;
    --accent:      #5fbb9f;
    --accent-soft: #1a2a25;
    --danger:      #e5685c;
    --danger-soft: #2a1816;
    --btn-bg:        var(--surface);
    --btn-bg-hover:  #2c2a27;
    --tile-face:     #f3efe6;
    --tile-shadow:   0 0 0 1px rgba(0,0,0,0.55), 0 2px 4px rgba(0,0,0,0.45);
    --tile-shadow-h: 0 0 0 1px rgba(0,0,0,0.6),  0 5px 10px rgba(0,0,0,0.5);
  }
}
```

The preview file additionally implements `[data-theme="light"]` /
`[data-theme="dark"]` manual overrides for testing. **The production
pages do NOT need a manual toggle** — they follow OS preference only via
`prefers-color-scheme`. (If a manual toggle is wanted later it can be
added.) The HTML root must set `<meta name="color-scheme" content="light dark">`
so native inputs flip too — add this to `web/index.html`.

### Fonts

Add to the top of `ledger-theme.css`:

```css
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600;700&family=IBM+Plex+Sans+SC:wght@400;500;600;700&display=swap');
```

System fallbacks in `--font` and `--mono` ensure first paint isn't blank.

## Page Composition

Both pages share the same structure and visual elements. The preview
file `web/public/ledger-preview.html` is the canonical reference — when
in doubt, match what the preview renders.

### Shared elements

**Page shell.** `<main class="ledger-shell">` sets `var(--page)` as
background and centers a column at `max-width: 1000px` (outer) with the
actual content card at `max-width: var(--col)` (680px).

**Page header.** Inside the card:
- Left: `<h1 class="ledger-page-head__title">` — title (e.g. "Shanten")
  with a `<small>` block under it for the Chinese subtitle
  ("奉化向听").
- Right: navigation — language switcher (`中文 / English`) and the
  cross-link to the other utility (`Calculator →` / `Shanten →`).
  Both are `.text-link` elements.
- A 1px `var(--rule)` hairline beneath the header row.

**Section pattern.** Each section gets:
- `.section-row`: `<h2 class="section-title">` left (with optional
  `<small>` caption block), `.section-meta` right (typically a
  count/status in mono).
- Section body content below.
- No card around individual sections — they share the parent page card,
  separated only by vertical rhythm (`var(--space)`).

**Result block.** Set apart from the sections above by a 1px
`var(--rule)` top border and `margin-top: 2.5rem; padding-top: 1.5rem`.
Contains: `.result-row` header (label left, status right with
`--ok`/`--err` color), `.big-stat` block for the headline number, then
either breakdown list (Calc) or discard analysis rows (Shanten).

**Tiles.** Reuse existing tile SVGs from `/Regular_shortnames/*.svg`
unchanged. Render via the existing `<button>`/`<span>` pattern with the
new `.tile` class providing the box-shadow ring + drop shadow. Selected
state uses `box-shadow: 0 0 0 1.5px var(--accent), 0 1px 2px rgba(0,0,0,0.20)`
in place of the current amber ring. No glow effect. Hover: `translateY(-2px)`.

### Shanten page sections

1. **Closed hand** — `n / base–max` in section-meta. Tile row, then
   text input + Apply button, then a tools row (`+ Add tiles`, `Sort`,
   `Clear`) on the right.
2. **Wild tile** — single tile slot + Edit text-link. Tile shows
   `.tile--selected` when set.
3. **Open melds** — `.chooser` segmented control: `0 1 2 3 4`. Active
   button gets `background: var(--ink); color: var(--surface)`.
4. **Result block:**
   - Status row: `Result` label, `Tenpai` / `1-shanten` / etc. on the
     right. Tenpai uses `.result-status--ok` (accent color).
   - Big stat: `Shanten` label left, number right. Number takes
     `.big-stat__value--accent` when shanten is 0.
   - Drawn tile note + Redraw link (when present).
   - Discard analysis as `.discard-row` 4-column grid:
     `[disc tile] · shanten label · → useful tiles · count`.
     Rows separated by `border-bottom: 1px solid var(--rule-soft)`.

### Calc page sections

1. **Closed hand** — same as Shanten section 1.
2. **Win tile** — single tile slot + Edit text-link.
3. **Wild tile** — single tile slot + Edit text-link.
4. **Open melds** — list of melds, each with its own subsection
   containing: meld type/direction/called-tile selects (using `.input`
   or `.select` styling, no card around them), the meld's tile row, and
   per-meld actions (Clear, Remove). `+ Add Chii / + Pon / + Kan`
   buttons at the bottom of the section.
5. **Round context** — `.toggle` (Tsumo / Ron), seat-wind and
   prevailing-wind selects, and a flower-kong checkbox row.
6. **Flowers** — eight numbered toggle buttons (`1` – `8`). Active
   gets the same `.is-active` ink-fill as the chooser.

**Result block:**
- Status row: `Result` label, `Valid hand` / `Invalid hand` with
  ok/err colors.
- Big stat: `Total score` label, big mono number. On invalid, dim to
  `var(--ink-4)`.
- `.breakdown` list: bullet of `· pattern name … +n` rows separated by
  rule-soft hairlines.

**Calculate button** is the single filled `.btn--primary` on the page
(ink-on-surface), placed in the action area near the validation
section.

**Normalized debug summary** — `.footnote` block at the bottom with a
`▾ Show normalized request` toggle. Expanded form uses
`background: var(--surface-2)` for slight elevation, mono font, no card
border.

## Interaction Details

- **Validation errors** render as `.note.note--error` inline directly
  below the input that triggered them. No banner cards.
- **Server errors** render as `.note.note--error` in the result block
  area. No `bg-rose-500/10` panels.
- **Empty states** render as `.note` (italic-free, ink-3 color)
  in-place. No dashed-border boxes.
- **Loading state**: the primary button text changes to `Calculating…`
  and the button gets `disabled` + reduced opacity. No spinners.
- **Lang toggle** preserves all state and only swaps strings; the
  bilingual `TEXT` / `UI_TEXT` maps inside each page stay in place.
- **URL state** behavior on Shanten is preserved as-is.
- **Tile palette as drawer.** Replace the always-visible palette with
  an inline collapsible drawer revealed by `+ Add tiles` (Shanten
  closed hand / wild tile) or `+ Pick tile` (Calc win tile / wild
  tile / each open meld). Once closed, the palette is hidden. This
  removes the largest source of visual noise on the current pages.

## Files

### Create
- `web/src/pages/ledger-theme.css` — Google Fonts import, all design
  tokens as CSS custom properties (light defaults + dark via
  `prefers-color-scheme`), and the shared utility classes used by both
  pages: `.ledger-shell`, `.ledger-page`, `.ledger-page-head`,
  `.section`, `.section-row`, `.section-title`, `.section-meta`,
  `.tile-row`, `.tile`, `.tile--small`, `.tile--selected`,
  `.input-row`, `.input`, `.btn`, `.btn--primary`, `.chooser`,
  `.toggle`, `.note`, `.note--error`, `.result`, `.result-row`,
  `.result-label`, `.result-status`, `.result-status--ok`,
  `.result-status--err`, `.big-stat`, `.big-stat__label`,
  `.big-stat__value`, `.big-stat__value--accent`, `.breakdown`,
  `.discard-row`, `.text-link`, `.footnote`, `.tools-row`.

  Imported at the top of `Shanten.tsx` and `Calc.tsx` via Vite's
  side-effect import: `import './ledger-theme.css'`.

### Modify
- `web/src/pages/Shanten.tsx` — full visual rewrite. Logic preserved.
  Reuse `shantenHelpers.ts` unchanged. Component structure
  (`ShantenTile`, `HandRow`, `PaletteGrid`, `DiscardAnalysisTable`)
  stays; their wrapper JSX and classnames change to the new ledger
  classes. Strip out the AI-style help subtitles
  (`paletteHelp`, `usefulHelp`, `discardHelp`, `wildHelp`,
  `openMeldsHelp` — keep the *required* strings, drop the marketing
  copy).
- `web/src/pages/Calc.tsx` — full visual rewrite. Logic preserved.
  Reuse `calcHelpers.ts` unchanged. Same approach. Strip the
  equivalent help strings (`closedHandPaletteHelp`,
  `winTilePaletteHelp`, `wildTilePaletteHelp`, `winTileHelp`,
  `wildHelp`, `openMeldsHelp`, `activeMeldPaletteHelp`,
  `kanContextHelp`, `flowerKongHelp`, `flowerHelp`, `validationHelp`,
  `resultHelp`, `normalizedHelp`).
- `web/index.html` — add `<meta name="color-scheme" content="light dark">`.

### Do not touch
- `web/src/index.css` — keep dark game-table styles intact for the
  Game / Table / Replay / Lobby / Login routes.
- `web/src/pages/Lobby.tsx`, `Login.tsx`, `Game.tsx`, `Table.tsx`,
  `CreateRoom.tsx`, `Replay.tsx`.
- All helper files (`shantenHelpers.ts`, `calcHelpers.ts`,
  `tileUtils.ts`).
- `App.tsx` global shell `bg-gray-900` — the Shanten and Calc routes
  will set their own background via the page shell.

## Reusable Pieces

- `getTileSvgName`, `getTileName` from `web/src/utils/tileUtils.ts` —
  unchanged; tile rendering still goes through these.
- `TILE_LIBRARY`, `parseHand`, `formatHand`, `sortHand`, `sameTile`,
  `countTiles`, `remainingCount`, `encodeUrlState`, `decodeUrlState`,
  `createDraft` from `shantenHelpers.ts` — all unchanged.
- `parseTehaiInput`, `parseSingleTileInput`, `validateCalculatorState`,
  `buildCalcRequestPayload`, `normalizeCalcSuccessResponse`,
  `normalizeCalcErrorResponse`, `expectedClosedHandSize`,
  `meldRequiredTileCount`, `getMeldLabel`, `getDirectionLabel`,
  `createMeldDraft`, `createTileDraft`, `formatTile`, `formatTehai`,
  `sortTiles`, `sameTileValue`, `WIND_OPTIONS`, `FLOWER_OPTIONS`,
  `TILE_LIBRARY` from `calcHelpers.ts` — all unchanged.

## Reference Preview

The canonical visual reference is `web/public/ledger-preview.html`
(viewable at `/ledger-preview.html` when the dev server is running).
When implementing, match its rendering for type, spacing, color, tile
appearance, discard rows, and the dark-mode flip.

The preview includes a manual `Auto / Light / Dark` mode toggle at the
top. This is a preview-only convenience and is **not** part of the
production pages — those rely on OS preference alone.

After implementation, the preview file may be deleted, or kept under
`web/public/` as a reference (it ships with the static build but is
trivially small).

## Out of Scope

- The actual game table, lobby, login, room creation, replay
- Tile SVG art changes
- Backend changes; both pages keep the same `/api/v1/shanten` and
  `/api/v1/calc` contracts
- Persisting a user theme preference; the pages follow OS only
- Light-mode versions of any other page
- A keyboard shortcut for the lang toggle

## Verification

End-to-end:
1. `cd web && npm install --legacy-peer-deps && npm run dev` and open
   `/shanten`.
2. Confirm light mode (OS in light theme):
   - Off-white page; no slate panels; no `rounded-3xl` cards in DOM
     (`document.querySelectorAll('.rounded-3xl').length === 0` from
     these two pages — confirmed visually).
   - Title is IBM Plex Sans 600 with a Chinese `<small>` subtitle.
   - Sections are separated by hairlines only — no card border per
     section.
   - Build a 13-tile hand via the `+ Add tiles` drawer; useful tiles
     render in the result discard rows. Shanten=0 → the big number
     turns teal accent and status reads `Tenpai`.
   - Enter a hand by text input; apply invalid input; assert errors
     render as red-ink notes below the input, not as a banner.
   - Switch language (中文 ↔ EN); all copy swaps; URL state preserved.
3. Flip OS to dark mode (or use macOS Appearance: Dark while the page
   is open). Confirm:
   - Page transitions to near-black `#121110`; tiles remain readable
     with the bone-tinted face; teal accent brightens to `#5fbb9f`.
   - No FOUC, no white flash on hard refresh (`color-scheme` meta
     prevents this).
4. Open `/calc`.
5. Confirm same surface; compose a winning hand (e.g. seven pairs);
   submit; result shows valid status in teal, big total number, clean
   breakdown list. Trigger an invalid hand and confirm red-ink note
   and `Invalid hand` status. Expand `▾ Show normalized request` —
   monospace summary on `--surface-2` background, no card chrome.
6. Verify mobile rendering at 375px and 768px. The single column
   reflows. Tile palette drawer wraps cleanly. Section meta wraps
   below title if needed.
7. Verify the live game table (`/lobby` → join → enter) and `/lobby`
   page are visually unchanged (still using the original dark
   slate/green theme from `index.css`).
8. `cd web && npm run build` succeeds with no new TypeScript errors.
