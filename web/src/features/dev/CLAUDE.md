# web/src/features/dev/

> Dev-only preview pages that render real components against mock data. Not linked from the app UI — reached by URL.

## Overview

These pages exist so table and settlement layout can be iterated **without deploying a live match**. They import the same components production uses; only the data is mock.

## Key Files

- **TableSample.tsx** (route `/tools/table-sample`) — Renders the real `TableBoard` with mock game data. Exposes deterministic idle, active-turn, called-hand, interrupt, multi-chii, callable-discard, round-result, match-end, and exit-dialog fixtures for visual QA without a backend. The active-turn fixture makes the self hand clickable and retains the selected tile; the Multi CHII fixture exercises the one-button hand-tile candidate picker.
- **RoundResultDemo.tsx** (route `/tools/round-result`) — Preview of the round-end payout sheet (`TableRoundResultOverlay`) so the shared live/replay settlement UI can be reviewed without playing a round. Renders a control panel (scenario · viewport preset · readiness toggle) plus a resizable `<iframe>`; the iframe loads the same route with `?embed=1` and renders only the overlay full-bleed, **so its own container drives the responsive layout** rather than the outer page. Presets include 375x667 compact-iPhone and 667x375 rotated-phone regression targets; the rotated shell is the default.
- **roundResultScenarios.ts** — Mock `RoundResultView` data for the demo, unit-tested in `roundResultScenarios.test.ts`.
- **RoundResultDemo.test.ts** — Coverage for the demo page wiring.

## Architecture Notes

- **Iterate table/layout changes here, not by deploying a live match.** That is the whole point of these routes.
- The iframe indirection in `RoundResultDemo` is load-bearing: without it the preview would inherit the outer page's viewport and the compact/rotated presets would not reproduce real phone layout.
