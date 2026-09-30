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

## Direct play navigation prototype

`DirectPlayPrototype.tsx` and `directPlayPrototype.css` form the standalone `/ui-prototype.html` Vite development entry. They are not imported by production and use no auth/socket providers or backend requests. Covers bilingual navigation, mock sign-in return, invitation validation, host seat filling, guest waiting, copyable prototype invitations, cancelable mock matchmaking, and in-memory room return. Phone preview uses a 393px container and the same container-query layout as narrow windows. Replays is an empty fixture; tools link to existing routes; match entry ends the demo. Refresh resets in-memory state.

The prototype uses a text-only brand and undecorated home section headings; the logo tile, tile trio and decorative wind row were removed after user feedback.

Play, Replays and Tools omit introductory page headings/subtitles. Navigation focuses the main content when no page heading is rendered.

TableSample also provides `crowded` (30 discards per seat with active controls) and `meld-heavy` (four direct kans and eight flowers per seat) synthetic stress fixtures. They test layout extremes, not simultaneous legal game states. Query parameters `fixture=<name>`, `clean=1` (hide toolbar), and `rotate=1` (force the production portrait-shell transform) enable repeatable viewport checks without touch-device media emulation.

The `wild-hand` fixture marks both East tiles in the local hand as wild, matching the center indicator, and supports lifting a tile to check selection contrast.

The `flower-heavy` fixture combines full concealed hands and eight flowers per seat without open melds, exercising flower-only rail clearance.

`TableSample?layout=unified` is the preview-only shared phone/desktop geometry. It uses one 720-high stage and one proportion set in `tableSampleUnified.css`; width grows with window aspect ratio to provide peripheral space. Self tiles remain about 43x60 at 667x375, with 15px bottom/21px left clearance. Live/replay routes keep their existing layout pending preview review. `tableSampleUnified.test.ts` covers shared scaling, hand size, edge clearance and lifted-hand separation at phone, desktop and ultrawide sizes.

Unified preview side pivots use equal/opposite 28-unit offsets about the HUD center, so left hand start and right hand start are 180-degree counterparts. Side edge inset is 28; the local exposed stack with melds has a 32-unit right margin to clear the right hand. Concealed hand anchors remain fixed across meld counts.

Unified side hands additionally have a constant 60-unit local inset (left moves down, right moves up). Side exposed tiles use 24x32 so even four sideways kans leave a 9-unit gap (2-unit gaps between meld groups) to the remaining pair. Meld length consumes the gap without changing the concealed start; melds remain on one row. Verified crowded, four-kan and flower-only fixtures at 667x375 and 1280x720.

TableSample omits the decorative Fenghua corner badge.

Unified exposed tiles prioritize legibility: opponents use 28x38 and self uses 34x46; flowers have an independent 32x42 rail. Side seats containing a four-wide kan use 26x34 at three melds and 24x32 at four to keep the fixed hand anchor and a single meld row even for direct kans.
