# web/src/table/stage/

> Fixed-stage geometry for the live board and replay.

## Overview

The board is a fixed 1600x900-ish design surface scaled as one unit, rather than a layout that
reflows each seat/discard region from viewport units. This directory owns that calculation: a pure
function, the React hook that feeds it DOM measurements, and the style objects the pages apply.

Moved here from `web/src/hooks/` in PR 2 — `computeStageLayout.ts` is not a hook, and grouping the
three files next to `table/` puts the geometry beside the presenter that consumes it.

## Key Files

- **computeStageLayout.ts** — Pure (DOM-free, unit-tested in `computeStageLayout.test.ts`) helper that maps an available width/height to the stage layout:
  - Fixed design height (`STAGE_BASE_HEIGHT = 900`); design width = `900 × clamp(windowAspect, 16/9, STAGE_MAX_ASPECT = 2.39)`; then `scale = min(availW/stageWidth, availH/stageHeight)`
  - So the board fills a *band* of landscape ratios (16:9 up to ~21:9) by spreading wider rather than pillarboxing; pillarboxes only past the cap; fills width + letterboxes height below 16:9
  - **Compact mode:** below `STAGE_COMPACT_MAX_HEIGHT` (520) available height — a phone's rotated-landscape height — it switches to the shorter `STAGE_COMPACT_BASE_HEIGHT` (680) design so the same tiles scale up, and returns `compact: true`. The consumer sets `data-compact="true"` on `.game-stage`, and `table/table-geometry.css` tightens the layout (shrinks `--tile-small-*` → `--discard-lane-size`/`--center-hud-size`, and the gaps) so the shorter design fits without clipping while the self hand grows. **`STAGE_COMPACT_BASE_HEIGHT` and those CSS overrides are tuned together** — clipping ⇒ raise base height / shrink overrides more; still too small ⇒ lower base height + shrink overrides more.
  - Exports `computeStageLayout`, the `StageLayout`/`StageLayoutOptions` types, and the `STAGE_BASE_HEIGHT`/`STAGE_MIN_ASPECT`/`STAGE_MAX_ASPECT`/`STAGE_COMPACT_MAX_HEIGHT`/`STAGE_COMPACT_BASE_HEIGHT` constants

- **useGameStageLayout.ts** — React hook wrapping `computeStageLayout` for the live game / replay stage:
  - Observes the shell size with `ResizeObserver`; also remeasures on `window.resize` / `visualViewport.resize` / `orientationchange`, scheduling the DOM read on the next animation frame so flex-layout changes settle before scale is recomputed
  - Measures `element.offsetWidth/offsetHeight` (layout box, **transform-agnostic**) — NOT `getBoundingClientRect()`, whose post-transform AABB would mis-measure the phone-portrait `.stage-rotator` rotate(90deg) as the portrait viewport and shrink the board. Keep measurement transform-agnostic.
  - Tracks the mounted shell node via a callback ref instead of assuming the ref exists on first render, so routes that start in a loading state (e.g. replay) still begin measuring once the real shell appears
  - Returns stage dimensions, scaled bounds, and centered offsets so `Game.tsx`/`Replay.tsx` keep the whole table on one coordinate system across resize/orientation/rotation

- **stageStyles(layout)** (exported from `computeStageLayout.ts`) — builds the `shellStyle` /
  `stageStyle` `CSSProperties` the three consuming pages apply. `zoom` rather than
  `transform: scale()` is deliberate: it keeps Framer Motion tile transitions in a less surprising
  coordinate space. `useGameStageLayout()` returns both alongside the raw layout, so pages never
  rebuild them (see `docs/refactoring-notes.md`, PR 1a).

## Architecture Notes

- Used for client-side prediction (zero-latency feedback); server always re-validates.
- `useGameStageLayout.ts` is intentionally game/replay-specific rather than a generic layout hook; it stops seat/hand/discard drift by scaling a fixed-height, aspect-flexible DOM stage as one unit instead of reflowing each region from viewport units, and it should prefer post-layout remeasurement over immediate resize-event reads when flex shells or side panels are involved.
- Phones in portrait get forced landscape via the `.stage-rotator` wrapper (CSS in `web/src/table/table-geometry.css`, gated `(pointer: coarse) and (orientation: portrait) and (max-width: 600px)`). Because that wraps and rotates the measured shell, the hook must read the untransformed layout box (`offsetWidth/offsetHeight`). The replay route opts out of the rotation (`.stage-rotator--replay`) so its control panel stays accessible.
