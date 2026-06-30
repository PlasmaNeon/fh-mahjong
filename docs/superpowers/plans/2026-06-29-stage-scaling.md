# Stage Scaling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the game board fill a band of landscape aspect ratios (16:9 up to ~21:9) instead of pillarboxing, and render phones in forced landscape.

**Architecture:** Replace the fixed 1600×900 design with a fixed-height, variable-width design computed by a pure `computeStageLayout()` function (unit-tested). A `.stage-rotator` wrapper CSS-rotates the stage to landscape on phones in portrait; `ResizeObserver` observes the rotated box so the scaler is orientation-agnostic.

**Tech Stack:** React 19 + TypeScript + Vite, vitest (node env), CSS (`web/src/index.css`).

## Global Constraints

- Fixed design height: `900`. Design width = `900 × clamp(windowAspect, 16/9, CAP)`.
- `CAP = 2.39` (≈21.5:9) — fills up to real 21:9 monitors, pillarbox beyond.
- `MIN_ASPECT = 16/9` — windows narrower than 16:9 keep the 16:9 design (fill width, vertical letterbox).
- No cropping of board content; widening spreads the table (no element clipping).
- Phone rotation gate: `(pointer: coarse) and (orientation: portrait) and (max-width: 600px)`. iPad/PC never rotate.
- Keep `zoom: scale` on `.game-stage` (do not switch to `transform: scale`).
- Existing callers `useGameStageLayout()` pass no arguments.
- vitest config is `environment: 'node'` — keep new tests DOM-free.

---

### Task 1: `computeStageLayout` pure function + tests

**Files:**
- Create: `web/src/hooks/computeStageLayout.ts`
- Test: `web/src/hooks/computeStageLayout.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `computeStageLayout(availWidth: number, availHeight: number, opts?: StageLayoutOptions): StageLayout`
  - `type StageLayoutOptions = { baseHeight?: number; minAspect?: number; maxAspect?: number }`
  - `type StageLayout = { stageWidth: number; stageHeight: number; scale: number; scaledWidth: number; scaledHeight: number; offsetX: number; offsetY: number }`
  - Constants `STAGE_BASE_HEIGHT = 900`, `STAGE_MIN_ASPECT = 16/9`, `STAGE_MAX_ASPECT = 2.39`

- [ ] **Step 0: Ensure deps installed**

Run: `cd web && npm install`
Expected: `node_modules/.bin/vitest` and `tsc` exist.

- [ ] **Step 1: Write the failing test**

Create `web/src/hooks/computeStageLayout.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { computeStageLayout, STAGE_MAX_ASPECT } from './computeStageLayout'

const near = (a: number, b: number, eps = 0.5) => Math.abs(a - b) <= eps

describe('computeStageLayout', () => {
  it('matches 16:9 exactly with no bars', () => {
    const l = computeStageLayout(1600, 900)
    expect(l.stageWidth).toBe(1600)
    expect(l.offsetX).toBe(0)
    expect(l.offsetY).toBe(0)
    expect(l.scale).toBeCloseTo(1, 5)
  })

  it('fills width for an in-band 2.0 ratio (widens the design)', () => {
    const l = computeStageLayout(1920, 960)
    expect(l.stageWidth).toBeCloseTo(1800, 3) // 900 * 2.0
    expect(near(l.offsetX, 0)).toBe(true)
  })

  it('fills both axes for a 21:9 (in-band) ratio', () => {
    const l = computeStageLayout(2560, 1080) // 2.370 < CAP
    expect(near(l.offsetX, 0)).toBe(true)
    expect(near(l.offsetY, 0)).toBe(true)
  })

  it('pillarboxes beyond the cap', () => {
    const l = computeStageLayout(3840, 1080) // 3.556 > CAP
    expect(l.stageWidth).toBeCloseTo(900 * STAGE_MAX_ASPECT, 3)
    expect(l.offsetX).toBeGreaterThan(0)
    expect(near(l.offsetY, 0)).toBe(true)
  })

  it('fills width and letterboxes height below 16:9 (4:3)', () => {
    const l = computeStageLayout(1024, 768)
    expect(l.stageWidth).toBeCloseTo(1600, 3) // clamped to 16:9
    expect(near(l.offsetX, 0)).toBe(true)
    expect(l.offsetY).toBeGreaterThan(0)
  })

  it('fills width in portrait with a large vertical letterbox', () => {
    const l = computeStageLayout(400, 800)
    expect(l.stageWidth).toBeCloseTo(1600, 3)
    expect(near(l.scaledWidth, 400)).toBe(true)
    expect(l.offsetY).toBeGreaterThan(200)
  })

  it('never returns non-finite values for zero input', () => {
    const l = computeStageLayout(0, 0)
    expect(Number.isFinite(l.scale)).toBe(true)
    expect(l.scale).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/hooks/computeStageLayout.test.ts`
Expected: FAIL — cannot resolve `./computeStageLayout`.

- [ ] **Step 3: Write the minimal implementation**

Create `web/src/hooks/computeStageLayout.ts`:

```ts
export type StageLayoutOptions = {
  baseHeight?: number
  minAspect?: number
  maxAspect?: number
}

export type StageLayout = {
  stageWidth: number
  stageHeight: number
  scale: number
  scaledWidth: number
  scaledHeight: number
  offsetX: number
  offsetY: number
}

export const STAGE_BASE_HEIGHT = 900
export const STAGE_MIN_ASPECT = 16 / 9
export const STAGE_MAX_ASPECT = 2.39

export function computeStageLayout(
  availWidth: number,
  availHeight: number,
  opts: StageLayoutOptions = {},
): StageLayout {
  const baseHeight = opts.baseHeight ?? STAGE_BASE_HEIGHT
  const minAspect = opts.minAspect ?? STAGE_MIN_ASPECT
  const maxAspect = opts.maxAspect ?? STAGE_MAX_ASPECT

  const safeWidth = Math.max(availWidth, 1)
  const safeHeight = Math.max(availHeight, 1)

  const windowAspect = safeWidth / safeHeight
  const designAspect = Math.min(Math.max(windowAspect, minAspect), maxAspect)

  const stageHeight = baseHeight
  const stageWidth = baseHeight * designAspect
  const scale = Math.min(safeWidth / stageWidth, safeHeight / stageHeight)
  const scaledWidth = stageWidth * scale
  const scaledHeight = stageHeight * scale

  return {
    stageWidth,
    stageHeight,
    scale,
    scaledWidth,
    scaledHeight,
    offsetX: Math.max((safeWidth - scaledWidth) / 2, 0),
    offsetY: Math.max((safeHeight - scaledHeight) / 2, 0),
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/hooks/computeStageLayout.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/computeStageLayout.ts web/src/hooks/computeStageLayout.test.ts
git commit -m "feat(web): pure computeStageLayout for width-flexible scaling"
```

---

### Task 2: Wire into `useGameStageLayout` + fix the absolute-X action bar

**Files:**
- Modify: `web/src/hooks/useGameStageLayout.ts` (replace inline math with `computeStageLayout`)
- Modify: `web/src/index.css:1416` (`--action-left`)

**Interfaces:**
- Consumes: `computeStageLayout`, `StageLayoutOptions` from Task 1.
- Produces: `useGameStageLayout(options?: StageLayoutOptions)` returning
  `{ containerRef, availableWidth, availableHeight, stageWidth, stageHeight, scale, scaledWidth, scaledHeight, offsetX, offsetY }` (same field names as before; `stageWidth` is now dynamic).

- [ ] **Step 1: Replace the hook body**

Replace the entire contents of `web/src/hooks/useGameStageLayout.ts` with:

```ts
import { useLayoutEffect, useState } from 'react';
import type { RefCallback } from 'react';
import { computeStageLayout, type StageLayoutOptions } from './computeStageLayout';

type StageBounds = {
    width: number;
    height: number;
};

export function useGameStageLayout(options: StageLayoutOptions = {}) {
    const [containerElement, setContainerElement] = useState<HTMLDivElement | null>(null);
    const [bounds, setBounds] = useState<StageBounds>({ width: 1600, height: 900 });

    useLayoutEffect(() => {
        const element = containerElement;
        if (!element) {
            return;
        }

        let frameId = 0;

        const updateBounds = () => {
            const rect = element.getBoundingClientRect();
            const nextWidth = Math.max(Math.floor(rect.width), 1);
            const nextHeight = Math.max(Math.floor(rect.height), 1);

            setBounds((previous) => {
                if (previous.width === nextWidth && previous.height === nextHeight) {
                    return previous;
                }
                return { width: nextWidth, height: nextHeight };
            });
        };

        const scheduleUpdateBounds = () => {
            if (frameId) {
                cancelAnimationFrame(frameId);
            }
            frameId = requestAnimationFrame(() => {
                frameId = 0;
                updateBounds();
            });
        };

        updateBounds();

        const resizeObserver = new ResizeObserver(() => {
            scheduleUpdateBounds();
        });
        resizeObserver.observe(element);
        if (element.parentElement) {
            resizeObserver.observe(element.parentElement);
        }

        const visualViewport = window.visualViewport;
        visualViewport?.addEventListener('resize', scheduleUpdateBounds);
        window.addEventListener('resize', scheduleUpdateBounds);
        window.addEventListener('orientationchange', scheduleUpdateBounds);

        return () => {
            if (frameId) {
                cancelAnimationFrame(frameId);
            }
            resizeObserver.disconnect();
            visualViewport?.removeEventListener('resize', scheduleUpdateBounds);
            window.removeEventListener('resize', scheduleUpdateBounds);
            window.removeEventListener('orientationchange', scheduleUpdateBounds);
        };
    }, [containerElement]);

    const layout = computeStageLayout(bounds.width, bounds.height, options);

    return {
        containerRef: setContainerElement as RefCallback<HTMLDivElement>,
        availableWidth: bounds.width,
        availableHeight: bounds.height,
        ...layout,
    };
}
```

- [ ] **Step 2: Fix the lone absolute-X position (action bar)**

In `web/src/index.css`, change line ~1416 inside `:root`/the stage variables block:

```css
  --action-left: 1106px;
```
to:
```css
  --action-left: calc(50% + 306px);
```

(1106 − 800 = 306; this keeps the action bar in the same spot at 16:9 while following the centered self-seat bundle as the stage widens. `--action-bottom` is edge-relative and stays.)

- [ ] **Step 3: Typecheck and re-run unit tests**

Run: `cd web && npx tsc && npx vitest run src/hooks/computeStageLayout.test.ts`
Expected: tsc exits 0 (no type errors in the hook or its callers); 7 tests PASS.

- [ ] **Step 4: Manual scaling check**

Run: `cd web && npm run dev`, open the game stage, and resize the browser window:
- Drag from a 16:9 shape toward wider (toward 21:9): the board should keep filling the width (no growing side bars); side seats slide to the edges, the discard pond stays centered, the action buttons stay by the self hand.
- Drag much wider than 21:9: side pillarbox bars appear (expected).
- Make the window tall/narrow (taller than 16:9): board fills width, letterbox top/bottom (unchanged).

Expected: no pillarbox until past ~21:9; no clipped seats; action bar tracks the hand.

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useGameStageLayout.ts web/src/index.css
git commit -m "feat(web): width-flexible stage via computeStageLayout; anchor action bar to center"
```

---

### Task 3: Phone-portrait CSS rotation

**Files:**
- Modify: `web/src/index.css` (add `.stage-rotator`; change `.game-stage-shell` height)
- Modify: `web/src/features/game/Game.tsx` (wrap shell)
- Modify: `web/src/features/replay/Replay.tsx` (wrap shell)

**Interfaces:**
- Consumes: the existing `.game-stage-shell` (still the `containerRef`/`ResizeObserver` target).
- Produces: a `.stage-rotator` wrapper element; no JS/TS API changes.

- [ ] **Step 1: Add the rotator CSS and make the shell fill its parent**

In `web/src/index.css`, add a new rule (place it just above the `.game-stage-shell` rule, ~line 1361):

```css
.stage-rotator {
  width: 100%;
  height: 100dvh;
}

@media (pointer: coarse) and (orientation: portrait) and (max-width: 600px) {
  .stage-rotator {
    position: fixed;
    top: 50%;
    left: 50%;
    width: 100dvh;
    height: 100dvw;
    transform: translate(-50%, -50%) rotate(90deg);
    transform-origin: center center;
    overflow: hidden;
  }
}
```

Then in the existing `.game-stage-shell` rule (~line 1361), change the height lines from:

```css
  min-height: 100dvh;
  height: 100dvh;
```
to:
```css
  min-height: 100%;
  height: 100%;
```

(The rotator now owns the viewport sizing — `100dvh` normally, `100dvh × 100dvw` rotated — and the shell fills it. `ResizeObserver` on the shell therefore reports the landscape box in both cases, so Task 1/2's scaler needs no change.)

- [ ] **Step 2: Wrap the shell in Game.tsx**

In `web/src/features/game/Game.tsx`, find the `<div className="game-stage-shell" ...>` opening tag (~line 402) and its matching close tag. Wrap the whole shell element:

```tsx
<div className="stage-rotator">
    <div className="game-stage-shell" ref={stageLayout.containerRef} style={stageShellStyle}>
        {/* ...existing shell children unchanged... */}
    </div>
</div>
```

(Add `<div className="stage-rotator">` immediately before the shell's opening tag and a matching `</div>` immediately after the shell's closing `</div>`. Do not change anything inside the shell.)

- [ ] **Step 3: Wrap the shell in Replay.tsx**

In `web/src/features/replay/Replay.tsx`, do the same: wrap its `<div className="game-stage-shell" ...>…</div>` in `<div className="stage-rotator">…</div>`.

- [ ] **Step 4: Typecheck**

Run: `cd web && npx tsc`
Expected: exits 0 (JSX still valid, balanced tags).

- [ ] **Step 5: Manual rotation check (Chrome DevTools device mode)**

Run: `cd web && npm run dev`, open the game stage, open DevTools → toggle device toolbar:
- Select a phone (e.g. iPhone 12) in **portrait**: the board renders **landscape** (rotated 90°); a tile tap and a discard still register on the correct tile.
- Rotate the emulated phone to landscape: still landscape, not double-rotated.
- Select an iPad in **portrait**: the board does **not** rotate (it fills width, letterboxes height).
- Desktop responsive at a tall/narrow size: does **not** rotate.

Expected: rotation only on the phone-portrait case; taps land correctly.

- [ ] **Step 6: Commit**

```bash
git add web/src/index.css web/src/features/game/Game.tsx web/src/features/replay/Replay.tsx
git commit -m "feat(web): force landscape on phones via stage-rotator wrapper"
```

---

## Notes for the implementer

- **Deviation from spec file list:** the spec listed the pure function inside
  `useGameStageLayout.ts`; this plan puts it in its own `computeStageLayout.ts`
  for clean isolation and DOM-free unit testing. Functionally identical.
- **Top risk (verify in Task 3 Step 5):** tile-flight/discard animations
  (`web/src/table/tileFlightPlan.ts`) read element rects; confirm they still land
  correctly under the rotated container. If a flight animation is visibly off
  only in phone-portrait, that is the place to look — but do not pre-emptively
  change it; verify first.
