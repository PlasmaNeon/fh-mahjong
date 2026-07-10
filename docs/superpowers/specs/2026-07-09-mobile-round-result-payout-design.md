# Mobile Round Result and Payout Redesign

**Date:** 2026-07-09
**Status:** Approved for implementation planning

## Problem

The live table deliberately renders a fixed 1600x900 landscape stage inside
`.game-stage-shell`. The end-of-hand popup is outside the scaled stage, but its
CSS still caps the popup height with `--game-stage-scaled-height`. On a portrait
phone that value is the short, scaled board height rather than the usable
viewport height.

The popup then compounds that constraint with `overflow: hidden`. Its scoring
breakdown has a small independent scroller, but the popup as a whole cannot
scroll. When the header, winning hand, breakdown, payouts, and actions exceed
the capped height, the `Ready` and `Exit` actions are clipped with no route to
reach them.

## Goals

- Keep `Ready` and `Exit` visible and tappable at every supported phone size.
- Let the result content scroll independently of the action footer.
- Size the popup from its overlay container and the dynamic viewport, never
  from the scaled 1600x900 board.
- Redesign the popup as a Fenghua Mahjong settlement ledger rather than a
  generic dark glass card.
- Preserve the shared `TableRoundResultOverlay` path used by live games and
  replays.
- Preserve all current round-result data, tile ordering, meld ordering, ready
  state, and action behavior.

## Non-Goals

- Reflowing or replacing the fixed 1600x900 table stage.
- Changing engine scoring, payouts, protobuf fields, or WebSocket actions.
- Redesigning `MatchEndOverlay`; this change is specifically the end-of-hand
  round result shown in the supplied phone screenshot.
- Adding a new font package, UI framework, or browser-test dependency.

## Approaches Considered

### A. Overflow patch only

Set `overflow-y: auto` on the current modal and remove the scaled-height cap.
This is the smallest change, but the buttons would scroll away with the result
and the current dense card hierarchy would remain difficult to scan on a phone.

### B. Responsive settlement sheet (chosen)

Split the popup into a scrollable result body and a non-scrolling action
footer. Present it as a centered settlement card on wide screens and a bottom
sheet on narrow portrait screens. This fixes reachability structurally and
creates a clear visual hierarchy without changing game data.

### C. Portrait-native table reflow

Rebuild the entire table for portrait orientation and place the result inline
with that layout. This is substantially larger, risks tile-animation and seat
geometry regressions, and is unnecessary to make the payout flow usable.

## Visual Direction: Fenghua Settlement Ledger

The popup should resemble a compact table ledger laid over green felt: quiet,
tactile, and score-focused. The signature element is a pale **bone tile rack**
that carries the winning hand across the dark ledger surface. Payouts read like
four settlement entries, with jade for gains and cinnabar for losses.

### Color tokens

- **Lacquer:** `#071d1a` — popup body and footer foundation.
- **Felt:** `#0f4a3c` — secondary surfaces and subtle depth.
- **Bone:** `#f2e8d5` — hand rack and high-priority neutral text.
- **Jade:** `#74c69d` — positive payouts, Ready, and winning emphasis.
- **Brass:** `#d6b46a` — total score and restrained dividers.
- **Cinnabar:** `#d7665b` — Ron/loss emphasis and Exit.

### Typography

- Winner/display: `Songti SC`, `STSong`, `Times New Roman`, serif. It is used
  only for the winner or draw title.
- Interface/body: the existing application sans-serif stack.
- Scores: the existing sans-serif stack with `font-variant-numeric:
  tabular-nums` so payout columns remain stable.

No remote font request is introduced.

## Layout

### Wide screens

```text
┌──────────────────────────────────────────────┐
│ RON seal   Seat 2 wins              TOTAL 52│
│ From Seat 3                                 │
├──────────────── scrollable result body ─────┤
│ [ winning hand on bone rack → ]             │
│ Scoring ledger                              │
│ Base point                           +1      │
│ One wild tile                       +1      │
│ Independence                       +50      │
│                                              │
│ Seat 0 -52  Seat 1 -52  Seat 2 +208 Seat 3 -104│
├──────────────── fixed action footer ─────────┤
│             [ Ready ]   [ Exit ]             │
└──────────────────────────────────────────────┘
```

The modal remains centered, is at most 760px wide, and never exceeds the
overlay's usable height. Only the result body scrolls.

### Portrait phones

```text
┌──────────────── viewport ────────────────┐
│                                         │
│          dimmed live table              │
│                                         │
├──────────── bottom settlement sheet ────┤
│ RON · Seat 2 wins              TOTAL 52 │
│ ┌ horizontal winning-hand rack ───────┐ │
│ └─────────────────────────────────────┘ │
│ scoring rows and 2x2 payout grid ↕      │
├─────────────────────────────────────────┤
│ [ Ready for next hand ] [ Exit ]        │
└──────────────── safe-area inset ─────────┘
```

The sheet anchors to the bottom edge, uses the full available width, respects
top and bottom safe-area insets, and leaves the footer outside the scrollport.
The winning rack may scroll horizontally instead of shrinking Mahjong tiles
below a readable size.

### Short landscape phones

The card stays centered with compact spacing. The same body/footer split is
retained, so content scrolls vertically while the actions remain visible.

## Component Structure

`TableRoundResultOverlay` keeps its existing public props and data model. Its
internal markup changes to:

```text
.round-result-overlay
  section.round-result-modal[role=dialog]
    .round-result-scroll[tabindex=0]
      header / draw state
      winning-hand rack
      scoring ledger
      payout grid
    .round-result-actions (only when actions exist)
```

The action footer must be a sibling of `.round-result-scroll`, not a child.
This is the core reachability invariant.

## Responsive and Interaction Rules

- `.round-result-modal` is a two-row grid:
  `minmax(0, 1fr) auto`.
- `.round-result-scroll` owns `overflow-y: auto`, momentum scrolling, and
  `overscroll-behavior: contain`.
- `.round-result-actions` cannot shrink and includes bottom safe-area padding.
- Modal size must not reference `--game-stage-scaled-width` or
  `--game-stage-scaled-height`.
- Buttons have a minimum 48px touch height on phones.
- The disabled Ready state remains visible and says `Waiting...`, preserving
  current behavior.
- Replay results render the same redesigned body without an empty footer.

## Accessibility

- The settlement surface is `role="dialog"` with `aria-modal="true"` and an
  `aria-labelledby` reference to the winner/draw title.
- The scroll body has `tabIndex={0}` so keyboard users can scroll it.
- Existing tile `alt` text is preserved.
- Positive and negative payouts retain explicit `+`/`-` signs; meaning does
  not depend on color alone.
- Visible `:focus-visible` rings are required on the scroll body and buttons.
- Reduced-motion users receive no modal entrance animation.

## Testing and Acceptance Criteria

Automated tests must prove:

1. The overlay renders dialog semantics and a labelled title.
2. The result body and action footer are separate siblings, with actions after
   the scroll body.
3. The CSS contract includes a vertically scrollable body, a non-shrinking
   footer, dynamic-viewport sizing, and no scaled-stage height dependency.
4. Existing hand and meld ordering tests continue to pass.

Browser verification must cover 375x667, 393x852, 852x393, and 1440x900.
At each phone size, populate enough scoring rows to overflow the body, scroll
to both ends, and confirm `Ready` remains visible and clickable throughout.

## Files Expected to Change

- `web/src/table/TableScene.tsx`
- `web/src/table/roundResultOverlay.test.ts`
- `web/src/table/roundResult.css` (new focused style module)
- `web/src/index.css`
- `web/src/table/AGENTS.md`
- `web/src/AGENTS.md`
