# Stage scaling: width-flexible board + phone landscape

Date: 2026-06-29
Status: approved (design)

## Problem

The game stage is a fixed 1600×900 (16:9) design scaled to fit with
`scale = min(W/1600, H/900)` and centered (`useGameStageLayout.ts`,
`.game-stage-shell` is `overflow:hidden` and flex-centered). On any window wider
than 16:9 the fit is height-bound, leaving wasted **pillarbox bars** on the left
and right — the board never uses the extra width. Majsoul-style clients instead
fill a *band* of aspect ratios and only letterbox at extreme ratios.

A separate gap: on phones, the landscape board is squeezed into portrait width
and becomes tiny. Majsoul presents phones in landscape.

## Goals

- Fill the screen width across a band of landscape aspect ratios (16:9 up to a
  cap), with no cropping and no vertical squeeze.
- Preserve today's behavior at exactly 16:9, and the "fill width + vertical
  letterbox" behavior for windows taller than 16:9 (desktop portrait, iPad
  portrait).
- On **phones only**, when held in portrait, render the board in landscape via
  CSS rotation. iPad and PC never auto-rotate.

## Non-goals (out of scope)

- A bespoke portrait layout (rearranged seats/hand) — Majsoul's dual layout.
- Filling wide-screen side space with extra UI panels (log/scoreboard). On wide
  screens the table simply spreads wider, like a larger felt.
- Real OS orientation lock (Screen Orientation API). We use CSS rotation only.
- Touchscreen ergonomics overhaul, HUD/button anchoring redesign.

## Requirements (from brainstorming)

1. Board fills the width for window aspect ratios in `[16:9, CAP]`.
2. Beyond `CAP` ("ridiculous" ultrawide) → pillarbox.
3. Window aspect below 16:9 → keep the 16:9 design, fill width, letterbox height
   (unchanged from today).
4. Phones in portrait → CSS-rotate the stage 90° to landscape. iPad/PC excluded.
5. `CAP` and the phone-detection width threshold are tunable constants.

## Design

Two independent pieces. Piece 2 feeds a landscape-shaped box to Piece 1, so the
scaler stays orientation-agnostic.

### Piece 1 — width-flexible stage scaling

Change the design size from a fixed 1600×900 to **fixed height, variable width**.
Extract the math into a pure function for unit testing.

```ts
const BASE_HEIGHT = 900            // fixed design height
const MIN_ASPECT = 16 / 9          // ≈1.778 — never narrower than 16:9
const MAX_ASPECT = 2.39            // CAP ≈ 21.5:9; covers real 21:9 monitors

export function computeStageLayout(
  availW: number,
  availH: number,
  opts: { baseHeight?: number; minAspect?: number; maxAspect?: number } = {},
) {
  const baseHeight = opts.baseHeight ?? BASE_HEIGHT
  const minAspect = opts.minAspect ?? MIN_ASPECT
  const maxAspect = opts.maxAspect ?? MAX_ASPECT

  const windowAspect = availW / availH
  const designAspect = Math.min(Math.max(windowAspect, minAspect), maxAspect)

  const stageHeight = baseHeight
  const stageWidth = baseHeight * designAspect
  const scale = Math.min(availW / stageWidth, availH / stageHeight)
  const scaledWidth = stageWidth * scale
  const scaledHeight = stageHeight * scale

  return {
    stageWidth, stageHeight, scale, scaledWidth, scaledHeight,
    offsetX: Math.max((availW - scaledWidth) / 2, 0),
    offsetY: Math.max((availH - scaledHeight) / 2, 0),
  }
}
```

Behavior across cases (verified by the unit tests below):

| window aspect | designAspect | result |
|---|---|---|
| < 16:9 (4:3, portrait) | 16:9 | fill width, vertical letterbox (unchanged) |
| 16:9 | 16:9 | exact fill (unchanged) |
| 16:9 .. CAP | = window | fill both, no bars; table spreads wider |
| > CAP | CAP | fill height, pillarbox sides |

`useGameStageLayout` keeps its current responsibilities (ResizeObserver +
`visualViewport` + `orientationchange`, the rAF-debounced bounds, the
`containerRef`) and simply delegates the per-frame math to `computeStageLayout`.
Its return shape is unchanged, so `Game.tsx`/`Replay.tsx` consume it as-is —
`stageWidth` is now dynamic, which the stage element already reads
(`stageStyle.width = stageLayout.stageWidth`).

**Why no layout rewrite is needed:** the in-stage zones are already
center/edge/corner-relative, so a wider `stageWidth` spreads them correctly:
- discard lanes: centered (`left/right: calc(50% ± center-hud-size …)`)
- seats: anchored to stage edges via `seat-bundle-pivot--{left,right,top,bottom}`
- wild-tile corner: top-left corner (`--wild-tile-top/left`)
- center HUD: centered

The only things to spot-check during implementation are any remaining
absolute-X positions (e.g. `.table-action-bar` `--action-left`); convert to
edge- or center-relative if they don't follow the width.

### Piece 2 — phone-portrait CSS rotation

Wrap `.game-stage-shell` in a `stage-rotator`. In the normal case it is a
pass-through (`width:100%; height:100dvh`). Under the phone-portrait media query
it becomes a landscape-sized, rotated box:

```css
.stage-rotator { width: 100%; height: 100dvh; }

@media (pointer: coarse) and (orientation: portrait) and (max-width: 600px) {
  .stage-rotator {
    position: fixed;
    top: 0;
    left: 0;
    width: 100dvh;
    height: 100dvw;
    transform-origin: top left;
    transform: rotate(90deg) translateY(-100%);
  }
}
```

`.game-stage-shell` fills the rotator (`width/height: 100%`). Because
`ResizeObserver` reports an element's **border-box** size (not the transformed
AABB), the hook — observing the shell — sees the landscape dimensions
(`100dvh × 100dvw`) in both the rotated and non-rotated cases. So Piece 1 needs
zero changes to support rotation.

- `max-width: 600px` (in portrait = the device's short side) includes phones
  (~390–430px) and excludes iPad portrait (768px+). Tunable.
- `(pointer: coarse)` excludes PCs with portrait windows.
- iPad/PC portrait fall through to Piece 1's fill-width + vertical letterbox.

JSX (`Game.tsx`, mirrored in `Replay.tsx`): add one wrapper element.
```
<div className="stage-rotator">
  <div className="game-stage-shell" ref={containerRef} …>
    …
  </div>
</div>
```

## Data flow

`stage-rotator` (CSS sets its box; rotated on phone-portrait) → `game-stage-shell`
(`100%` of rotator; `ResizeObserver` target) → `useGameStageLayout` reads the
shell's landscape box → `computeStageLayout` → `{stageWidth, stageHeight, scale}`
→ `game-stage` element (`width/height` = stageWidth/Height, `zoom` = scale) →
seats/discards/HUD reflow via their center/edge anchors.

## Edge cases & risks

- **Ultrawide beyond CAP:** intentional pillarbox; verify the shell's centered
  flex still centers the capped board.
- **Rotation × tile-flight animations:** `tileFlightPlan`/framer animations that
  read `getBoundingClientRect` operate inside the rotated container; coordinates
  should map through the transform, but this must be verified on a phone-portrait
  device — highest-risk item.
- **Touch input under rotation:** browsers map pointer events through CSS
  transforms automatically; verify tile taps and discards.
- **`100dvw`/`100dvh` + browser chrome:** dynamic viewport units chosen so mobile
  toolbars don't cause clipping; `visualViewport` resize already wired.
- **Resize/orientation thrash:** existing rAF debounce covers it; confirm no
  feedback loop when the rotator swaps box dimensions.
- **`zoom` vs `transform: scale`:** unchanged from today (`zoom` retained) to keep
  this change scoped to sizing, not compositing.

## Testing

- **Unit (vitest), `computeStageLayout`:** a table of window sizes →
  asserts on `stageWidth`, `scale`, and `offsetX/Y`:
  - 1600×900 (16:9) → stageWidth 1600, offsetX 0, offsetY 0.
  - 1920×960 (2.0, in band) → stageWidth 1800, offsetX 0 (fills width).
  - 2560×1080 (2.37, ≤ CAP) → fills width, offsetX ≈ 0.
  - 3840×1080 (3.56, > CAP) → designAspect = CAP, offsetX > 0 (pillarbox).
  - 1024×768 (4:3, < 16:9) → stageWidth 1600, offsetY > 0 (vertical letterbox).
  - 400×800 (portrait) → stageWidth 1600, fills width, large offsetY.
- **Manual matrix:** resize a desktop window through 4:3 → 16:9 → 21:9 → 32:9 and
  confirm no pillarbox until past CAP; confirm seats stay at the edges and the
  discard pond stays centered as it widens.
- **Phone:** portrait phone renders landscape; tile tap, discard, and a called
  meld animate correctly; iPad portrait does **not** rotate.

## Files to change

- `web/src/hooks/useGameStageLayout.ts` — extract + use `computeStageLayout`
  (new pure function, exported for tests).
- `web/src/hooks/useGameStageLayout.test.ts` — new unit tests.
- `web/src/index.css` — `.stage-rotator` rules + phone-portrait media query.
- `web/src/features/game/Game.tsx`, `web/src/features/replay/Replay.tsx` — wrap
  the shell in `.stage-rotator`.
- Spot-check `.table-action-bar` (`--action-left`) and any other absolute-X zone.
