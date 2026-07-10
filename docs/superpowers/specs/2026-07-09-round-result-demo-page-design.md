# Round-Result Payout Sheet Demo Page — Design

**Date:** 2026-07-09
**Status:** Approved (design)
**Related:** PR #152 (`fix(web): redesign the mobile payout sheet`, branch `codex/mobile-round-result-payout`)

## Problem

PR #152 redesigns the round-end payout popup (`TableRoundResultOverlay` in
`web/src/table/TableScene.tsx` + new `web/src/table/roundResult.css`): a
scrollable result body with a persistent Ready/Exit footer, presented as a
bottom sheet on portrait phones and a centered card on desktop / short
landscape.

The only way to see the overlay today is to start a real match and play a round
to completion (win, ron, or exhaustive draw). That makes it impractical to
review the redesign — especially its responsive and scroll behavior — without a
live game. We need a dev-only demo page that renders the redesigned overlay with
curated mock data, across scenarios and viewport sizes.

## Goal

A dev-only, interactive "playground" page that previews the PR #152 overlay
without a live match:

- switch between the key result states (Tsumo win, Ron win, Exhaustive Draw, and
  a long high-score hand that exercises body scrolling);
- switch the viewport (portrait phone, short landscape, desktop) **in-page** and
  faithfully see the responsive bottom-sheet vs. centered-card difference;
- toggle the "ready" state to see the footer `Ready → Waiting…` change and the
  per-seat ready badges.

## Non-goals (YAGNI)

- No `postMessage` bridge between the page and the preview (query-param + iframe
  resize is enough).
- No per-tile / free-form hand editing — scenarios are fixed and curated.
- No persistence of the selected scenario / viewport.
- No simulated device notch; `env(safe-area-inset-*)` reads 0 inside an iframe,
  same as any desktop browser. Acceptable for a dev preview.
- Not shipped as part of PR #152 — this is a separate demo effort on its own
  branch.

## Key constraint that drives the design

PR #152's responsiveness is implemented with **real-window media queries**, not
container queries:

- `@media (max-width: 720px)` → portrait / narrow bottom-sheet layout
  (full width, rounded top corners, two-column payout grid, action footer as a
  grid).
- `@media (orientation: landscape) and (max-height: 500px)` → compact short-
  landscape card.
- Plus `100dvh` and `env(safe-area-inset-*)`.

These evaluate against the **actual browser viewport**, so a resizable `<div>`
on a desktop page cannot trigger the bottom-sheet layout — the window is wider
than 720px regardless of the div's size. To preview phone-vs-desktop in-page,
the overlay must be given a real nested viewport.

## Approach decision — viewport switcher mechanism

**Chosen: iframe device-frame (Approach A).** The playground hosts an
`<iframe>` whose width/height are set to device presets. The iframe is a real
nested browsing context, so `@media`, `100dvh`, and orientation all evaluate
against the frame size — faithful to production.

Rejected alternatives:

- **B. Single page + real browser resize / devtools** — partially faithful but
  requires leaving the page; defeats the in-page switcher requirement.
- **C. Scaled `<div>` container** — not faithful: media queries read the whole
  desktop window, so the bottom-sheet layout never triggers and the preview
  shows the *wrong* layout. Misleading; rejected.

## Architecture

Mirrors the existing dev-page pattern (`web/src/features/dev/TableSample.tsx`
routed at `/tools/table-sample`).

- **One new component:** `web/src/features/dev/RoundResultDemo.tsx`.
- **One new data module:** `web/src/features/dev/roundResultScenarios.ts` — the
  curated `RoundResultView` builders, kept separate so the vitest test and the
  component both import them.
- **One new route** in `web/src/App.tsx`: `/tools/round-result` →
  `RoundResultDemo` (public, like the other `/tools/*` routes).
- **Dual-mode via query param** (`useSearchParams`), so no second route is
  needed:
  - **Playground mode** (default, no `embed`): renders the control panel + a
    centered `<iframe src="/tools/round-result?embed=1&scenario=…&ready=…">`
    sized to the selected viewport preset.
  - **Embed mode** (`?embed=1`): renders **only** `<TableRoundResultOverlay>`
    over a dark felt backdrop, full-bleed. This is what the iframe loads, giving
    faithful media-query behavior. No control chrome.

Because the overlay's `.round-result-overlay` is `position: fixed; inset: 0`
(and is only made `absolute` when nested under `.game-stage-shell`, which embed
mode does not do), it fills the iframe viewport correctly.

### Decoupling

PR #152 does **not** change the `RoundResultView` type
(`web/src/table/types.ts`) or the overlay's props — the signature stays
`{ result, isWildTile }`. The demo therefore depends only on the stable
`RoundResultView` contract: it builds a `RoundResultView` and passes it in; the
overlay component + `roundResult.css` (both from #152) do the rendering. The
demo keeps working after #152 merges to main.

`roundResult.css` is imported globally via `web/src/index.css`
(`@import "./table/roundResult.css";`), so the styles apply on the demo route
and inside the iframe automatically — no extra import needed.

## Data flow

```
Playground (parent)                         Embed (iframe)
──────────────────                          ──────────────
state: scenario, viewport, ready
  │
  ├─ viewport ──► iframe width/height (resize only, no reload)
  │
  ├─ scenario ─┐
  ├─ ready ────┴─► iframe src query params ──► useSearchParams()
  │                (scenario change reloads         │
  │                 the iframe)                     ├─ build RoundResultView
  │                                                 │  from scenarios[scenario](ready)
  └─ controls render buttons                        └─ <TableRoundResultOverlay result=… />
                                                        (Ready button toggles to
                                                         "Waiting…" via local state)
```

- **Viewport** changes only resize the iframe element (no reload).
- **Scenario / ready** changes update the iframe `src` query params, reloading
  the iframe with fresh mock data. Simple and robust for a dev tool.
- The **Ready button** inside the overlay's `actions` footer toggles to
  `Waiting…` via local `useState` inside the embed render, mirroring
  `Game.tsx`'s `readyActions`. Exit is a no-op in the demo (does not navigate /
  close a socket).

## Mock scenarios

Four curated `RoundResultView` builders, using the same `t(suit, value)` tile
helper convention as `TableSample` (suits: 1=sou, 2=pin, 3=man, 4=jihai,
5=flower):

1. **Tsumo win** — self-draw winner, `winType: 'tsumo'`, ~4 breakdown patterns,
   full closed hand + win tile, one flower, four payouts (winner +, three −).
2. **Ron win** — `winType: 'ron'`, `discarderLabel` set, breakdown, one open
   meld in the hand rack, four payouts.
3. **Exhaustive Draw** — `isDraw: true` (renders the draw branch, no payouts /
   breakdown / hand).
4. **Long high-score hand** — 10+ breakdown entries and a large `totalScore`,
   full hand rack (closed hand + win tile + melds + flowers), four payouts. Used
   to verify the result body scrolls while the Ready/Exit footer stays pinned
   and visible.

Each builder accepts the `ready` flag to populate `readyLabel` /`readyActive`
on payouts and to seed the footer's initial Ready state.

## Error handling

Minimal — dev tool, no network, no auth. Unknown / missing `scenario` query
value defaults to `tsumo`. Unknown `ready` defaults to `false`.

## Testing & verification

- **Unit (vitest):** a small test on the scenario builders module asserting the
  invariants that matter — the Draw scenario sets `isDraw: true` with no
  payouts; each win scenario sets a `winType`, a non-empty breakdown, exactly
  four payouts with the winner's amount positive and the other three negative,
  and all payout amounts summing to zero. Keeps `npm test` / CI green.
- **Type/build:** `cd web && npx tsc --noEmit` and `npm run build` pass.
- **Manual QA:** load `/tools/round-result`; cycle all four scenarios; switch
  the three viewport presets and confirm:
  - portrait phone → rounded-top bottom-sheet, full width, two-column payouts,
    grid action footer;
  - desktop → centered card;
  - short landscape → compact card;
  - long-hand scenario → body scrolls to its end while Ready/Exit stay visible;
    tapping Ready flips it to `Waiting…`.

## Docs

- Update `web/src/features/AGENTS.md` to note the new `/tools/round-result` dev
  page (mirroring how `/tools/table-sample` is documented).
- The overlay redesign's own AGENTS.md updates ship with PR #152.

## Git / integration

- Merge `origin/codex/mobile-round-result-payout` into the demo branch
  (`claude/demo-page-pr-152-b7a7d7`) so the overlay renders the redesign. PR
  #152 touches only `TableScene.tsx`, `roundResult.css`, `index.css`, and docs —
  no overlap with the new demo files or the single `App.tsx` route line — so the
  merge is clean.
- The demo is a separate change layered on #152; it can become its own small PR
  to main after #152 lands (rebase onto main dedupes #152's commits at that
  point).

## Files touched (summary)

| File | Change |
|---|---|
| `web/src/features/dev/RoundResultDemo.tsx` | **new** — dual-mode demo component |
| `web/src/features/dev/roundResultScenarios.ts` (or inline) | **new** — mock `RoundResultView` builders |
| `web/src/features/dev/roundResultScenarios.test.ts` | **new** — minimal builder invariants test |
| `web/src/App.tsx` | **edit** — add `/tools/round-result` route + import |
| `web/src/features/AGENTS.md` | **edit** — document the new dev page |
