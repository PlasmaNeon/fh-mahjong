# PR 1 — Frontend De-duplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the duplicated code in `web/src` identified as Tier 1/Tier 2 in the design doc, without changing any rendered output or user-visible behaviour.

**Architecture:** Extract each duplicated unit into the module that already owns the concept (`utils/tileModel.ts`, `table/types.ts`, `theme/components/`, `hooks/useGameStageLayout.ts`), rewrite call sites one at a time, delete the copies. Where the duplicated code has no test coverage, a characterization test pinning current behaviour is written and seen to pass *before* the extraction.

**Tech Stack:** React 19, TypeScript, Vite 7, vitest (node environment, `renderToStaticMarkup` for components), TailwindCSS 4.

**Spec:** `worklog/specs/2026-08-16-dedup-and-naming-refactor-design.md`

**Delivered as two PRs.** The spec's PR 1 is split at the natural risk boundary, because typed
code and untyped CSS/copy fail in different ways and want different reviewers:

- **PR 1a — code de-duplication** (Tasks 1, 3-8): TypeScript, guarded by `tsc` + vitest.
- **PR 1b — CSS and copy de-duplication** (Tasks 2, 9-11): stylesheets and i18n strings, guarded
  by a built-CSS diff and by locale parity. No type checker stands behind these, so they are
  verified differently and reviewed separately.

Every task still commits independently, so the split is a push-time decision, not a rewrite.

## Global Constraints

- **Behaviour-preserving only.** No rendered-output change, no copy change, no API change. Same inputs → same outputs.
- **Gate after every task:** `cd web && npx tsc && npx vitest run`. Baseline is **28 files, 165 tests passing**; the count only ever goes up.
- **Commit per task.** Never batch two extractions into one commit.
- **No renames in this PR.** Renames are PR 2. If a file feels misnamed, leave it.
- Vitest runs in the **node** environment — component tests use `renderToStaticMarkup`, never a DOM.
- Tile notation in comments uses `1m2m3m` style, never `C1C2C3`.
- Update `CLAUDE.md` in every directory whose contents change, in the same commit.

---

### Task 1: Single `tileIdsEqual`

Two byte-identical definitions exist. `table/meldOrdering.ts:3-6` is imported by 6 modules; `table/tileFlightPlan.ts:47-50` is a second copy re-exported through `table/tileFlight.tsx:18`.

**Files:**
- Create: `web/src/table/tileId.ts`
- Modify: `web/src/table/meldOrdering.ts:1-6`, `web/src/table/tileFlightPlan.ts:47-50`
- Test: `web/src/table/meldOrdering.test.ts` (existing coverage — keep it green)

**Interfaces:**
- Produces: `export function tileIdsEqual(left: unknown, right: unknown): boolean` in `table/tileId.ts`.
- `meldOrdering.ts` and `tileFlight.tsx` keep re-exporting `tileIdsEqual`, so no consumer import changes.

- [ ] **Step 1: Create the leaf module**

```ts
// web/src/table/tileId.ts
// Tile ids arrive from three sources with different JS types: proto decoding
// (number), paipu JSON (number|string), and DOM data attributes (string).
// Comparison is therefore string-based and null-safe.
export function tileIdsEqual(left: unknown, right: unknown): boolean {
  if (left == null || right == null) return false
  return String(left) === String(right)
}
```

- [ ] **Step 2: Re-point `meldOrdering.ts`**

Replace the local definition (lines 3-6) with a re-export so its six importers keep working:

```ts
import type { MeldLike, SeatLaneDirection } from './types'
import { tileIdsEqual } from './tileId'

export { tileIdsEqual }
```

- [ ] **Step 3: Delete the copy in `tileFlightPlan.ts`**

Remove lines 47-50 and import instead:

```ts
import { tileIdsEqual } from './tileId'
```

- [ ] **Step 4: Verify no definition remains**

Run: `grep -rn "function tileIdsEqual" web/src`
Expected: exactly one hit, `web/src/table/tileId.ts`.

- [ ] **Step 5: Run the gate**

Run: `cd web && npx tsc && npx vitest run`
Expected: tsc clean; 165 tests pass (`meldOrdering.test.ts` and `tileFlightPlan.test.ts` both still green).

- [ ] **Step 6: Commit**

```bash
git add web/src/table/tileId.ts web/src/table/meldOrdering.ts web/src/table/tileFlightPlan.ts
git commit -m "refactor(web): single tileIdsEqual in table/tileId.ts"
```

---

### Task 2: Delete the orphaned legacy seat-layout CSS

`web/src/index.css` carries two complete per-direction seat-layout implementations. The BEM one (`.seat-bundle*`, `.seat-hand__*`, `.discard-lane--*`) is what the components render. The older one is referenced by zero components — verified: each family below scores 0 `.tsx`/`.ts` references while the live controls score 3-4.

**Files:**
- Modify: `web/src/index.css` (ranges 165-365, 676-772, 1178-1245 — re-locate them by selector, do not trust the line numbers after the first edit)
- Test: `web/src/table/deadCss.test.ts` (new — guards the deletion)

**Interfaces:**
- Consumes: nothing. Produces: nothing. Pure deletion plus a regression guard.

- [ ] **Step 1: Write the guard test first**

This test encodes the invariant that makes the deletion safe, and keeps it true afterwards.

```ts
// web/src/table/deadCss.test.ts
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { resolve, join } from 'node:path'

const SRC = resolve(process.cwd(), 'src')

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return entry === 'proto' ? [] : sourceFiles(full)
    return /\.tsx?$/.test(entry) ? [full] : []
  })
}

const ALL_SOURCE = sourceFiles(SRC).map((f) => readFileSync(f, 'utf8')).join('\n')
const TABLE_CSS = readFileSync(join(SRC, 'index.css'), 'utf8')

// Families removed as dead in PR 1. If one of these ever comes back, it must
// come back with a component that uses it — otherwise it is dead again.
const REMOVED = [
  'hand-container', 'hand-main-block', 'hand-inner',
  'melds-container', 'melds-main', 'flowers-container',
  'discard-pool', 'center-info-match', 'center-info-status',
]

describe('legacy seat-layout CSS', () => {
  it.each(REMOVED)('%s is absent from index.css', (cls) => {
    expect(TABLE_CSS).not.toContain(cls)
  })

  it.each(REMOVED)('%s is referenced by no component', (cls) => {
    expect(ALL_SOURCE).not.toContain(cls)
  })

  it.each(['seat-bundle', 'discard-lane', 'center-seat', 'seat-meld-group'])(
    'the live layout class %s is still used by components',
    (cls) => {
      expect(ALL_SOURCE).toContain(cls)
    },
  )
})
```

- [ ] **Step 2: Run it and watch the right half fail**

Run: `cd web && npx vitest run src/table/deadCss.test.ts`
Expected: the 9 "absent from index.css" cases FAIL (the CSS is still there); the "referenced by no component" and live-class cases PASS. That asymmetry is the proof that deletion is safe.

- [ ] **Step 3: Delete the dead rules**

Remove every rule whose selector contains one of the nine families. Locate them by selector, not line number:

```bash
cd web && grep -n "hand-container\|hand-main-block\|hand-inner\|melds-container\|melds-main\|flowers-container\|discard-pool\|center-info-match\|center-info-status" src/index.css
```

Delete each matching rule block in full, including its `@media` variants. Do NOT delete `.center-seat*`, `.seat-meld-group*`, `.pov-*`, `.stolen-tile`, `.added-kong-tile` — those are live.

- [ ] **Step 4: Run the test again**

Run: `cd web && npx vitest run src/table/deadCss.test.ts`
Expected: all cases PASS.

- [ ] **Step 5: Confirm the built stylesheet only lost dead rules**

```bash
cd web && npx vite build >/dev/null 2>&1 && ls -la dist/assets/*.css
```
Expected: build succeeds. The emitted CSS shrinks; no live selector disappears (the live-class assertions in Step 4 cover this).

- [ ] **Step 6: Run the gate and commit**

```bash
cd web && npx tsc && npx vitest run
git add web/src/index.css web/src/table/deadCss.test.ts
git commit -m "refactor(web): delete orphaned legacy seat-layout CSS"
```

---

### Task 3: Shared test helpers

Three test files re-implement CSS-rule parsing; four define their own `renderToStaticMarkup` wrapper; two build an in-memory `Storage` stub.

**Files:**
- Create: `web/src/test/cssContract.ts`, `web/src/test/renderStatic.tsx`, `web/src/test/memoryStorage.ts`
- Modify: `web/src/table/compactHandLayout.test.ts:6-18`, `web/src/table/desktopHandLayout.test.ts:6-14`, `web/src/table/roundResultOverlay.test.ts:29-31,68-80`, `web/src/features/auth/AuthDialog.test.ts:7-9`, `web/src/features/lobby/streamlinedNavigation.test.ts:10-17`, `web/src/theme/components/GameDialog.test.ts:8-19`, `web/src/features/lobby/navigation.test.ts:6-11,19-24`, `web/src/features/game/discardMode.test.ts:7-23`

**Interfaces:**
- Produces:
  - `readSourceCss(...relPaths: string[]): string` — reads files relative to `web/src`
  - `ruleBody(css: string, selector: string): string` — the declaration block for a selector
  - `pixelVariable(rule: string, name: string): number` — a `--name: 12px` value as a number
  - `renderStatic(node: ReactElement): string` — `renderToStaticMarkup` wrapped in `I18nProvider`
  - `createMemoryStorage(): Storage`

- [ ] **Step 1: Read the existing helpers before replacing them**

```bash
cd web && sed -n '1,20p' src/table/compactHandLayout.test.ts && sed -n '60,85p' src/table/roundResultOverlay.test.ts
```
The extracted versions must be behaviourally identical, including the selector escaping in `ruleBody`.

- [ ] **Step 2: Create `web/src/test/cssContract.ts`**

```ts
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** Reads stylesheet sources relative to web/src and concatenates them. */
export function readSourceCss(...relPaths: string[]): string {
  return relPaths.map((p) => readFileSync(resolve(process.cwd(), 'src', p), 'utf8')).join('\n')
}

/** Returns the declaration block of the first rule matching `selector`. */
export function ruleBody(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    .replace(/\s+/g, '\\s*')
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))
  return match ? match[1] : ''
}

/** Reads a `--name: <n>px` custom property out of a declaration block. */
export function pixelVariable(rule: string, name: string): number {
  const match = rule.match(new RegExp(`${name}\\s*:\\s*([\\d.]+)px`))
  if (!match) throw new Error(`missing ${name} in rule`)
  return Number(match[1])
}
```

- [ ] **Step 3: Create `web/src/test/renderStatic.tsx`**

```tsx
import { createElement, type ReactElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { I18nProvider } from '../i18n/I18nContext'

/** Renders a component to static markup inside the app's i18n context. */
export function renderStatic(node: ReactElement): string {
  return renderToStaticMarkup(createElement(I18nProvider, null, node))
}
```

- [ ] **Step 4: Create `web/src/test/memoryStorage.ts`**

```ts
/** A `Storage` implementation backed by a Map, for tests that touch localStorage. */
export function createMemoryStorage(): Storage {
  const map = new Map<string, string>()
  return {
    get length() { return map.size },
    clear: () => map.clear(),
    getItem: (key: string) => (map.has(key) ? map.get(key)! : null),
    key: (index: number) => Array.from(map.keys())[index] ?? null,
    removeItem: (key: string) => { map.delete(key) },
    setItem: (key: string, value: string) => { map.set(key, String(value)) },
  }
}
```

- [ ] **Step 5: Re-point one test file and run it**

Start with `src/table/desktopHandLayout.test.ts` (the smallest). Replace its local `pixelVariable` and CSS read with imports from `../test/cssContract`.

Run: `cd web && npx vitest run src/table/desktopHandLayout.test.ts`
Expected: PASS, same assertions.

- [ ] **Step 6: Re-point the remaining seven files, running each after its edit**

Run after each: `cd web && npx vitest run <that file>`
Expected: PASS each time. If an assertion changes meaning, stop — the helper is not equivalent and must be adjusted, not the test.

- [ ] **Step 7: Confirm no local copies remain**

Run: `grep -rn "function pixelVariable\|function ruleBody\|renderToStaticMarkup(createElement" web/src --include=*.test.ts --include=*.test.tsx`
Expected: no hits.

- [ ] **Step 8: Run the gate and commit**

```bash
cd web && npx tsc && npx vitest run
git add web/src/test web/src/table/*.test.ts web/src/features web/src/theme/components/GameDialog.test.ts
git commit -m "refactor(web): share CSS-contract, render and storage test helpers"
```

---

### Task 4: `useGameStageLayout` returns the stage style objects

`Game.tsx:321-333`, `Replay.tsx:174-186` and `TableSample.tsx:130-141` each rebuild the same two `CSSProperties` objects from the same layout fields. Verified byte-identical apart from formatting.

**Files:**
- Modify: `web/src/hooks/useGameStageLayout.ts` (add to the return), `web/src/features/game/Game.tsx:320-333`, `web/src/features/replay/Replay.tsx:174-186`, `web/src/features/dev/TableSample.tsx:128-141`
- Test: `web/src/hooks/stageStyles.test.ts` (new)

**Interfaces:**
- Produces: `export function stageStyles(layout: StageLayout & { availableWidth: number; availableHeight: number }): { shellStyle: CSSProperties; stageStyle: CSSProperties }` in `hooks/computeStageLayout.ts`, and `useGameStageLayout()`'s return gains `shellStyle` and `stageStyle`.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/hooks/stageStyles.test.ts
import { describe, it, expect } from 'vitest'
import { stageStyles } from './computeStageLayout'

describe('stageStyles', () => {
  const layout = {
    scaledWidth: 1280, scaledHeight: 720, stageWidth: 1600, stageHeight: 900,
    scale: 0.8, availableWidth: 1300, availableHeight: 800,
  } as Parameters<typeof stageStyles>[0]

  it('maps the scaled and available box onto CSS custom properties', () => {
    const { shellStyle } = stageStyles(layout)
    expect(shellStyle).toMatchObject({
      '--game-stage-scaled-width': '1280px',
      '--game-stage-scaled-height': '720px',
      '--game-stage-available-width': '1300px',
      '--game-stage-available-height': '800px',
    })
  })

  it('sizes the stage in design pixels and zooms it', () => {
    expect(stageStyles(layout).stageStyle).toMatchObject({
      width: '1600px', height: '900px', zoom: 0.8,
    })
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/hooks/stageStyles.test.ts`
Expected: FAIL — `stageStyles` is not exported from `./computeStageLayout`.

- [ ] **Step 3: Implement `stageStyles`**

Append to `web/src/hooks/computeStageLayout.ts`:

```ts
import type { CSSProperties } from 'react'

export type StageStyleInput = StageLayout & { availableWidth: number; availableHeight: number }

/**
 * The fixed-stage wrapper styles. `zoom` (not `transform`) is deliberate: it keeps
 * Framer Motion tile transitions in an unsurprising coordinate space.
 */
export function stageStyles(layout: StageStyleInput): {
  shellStyle: CSSProperties
  stageStyle: CSSProperties
} {
  return {
    shellStyle: {
      '--game-stage-scaled-width': `${layout.scaledWidth}px`,
      '--game-stage-scaled-height': `${layout.scaledHeight}px`,
      '--game-stage-available-width': `${layout.availableWidth}px`,
      '--game-stage-available-height': `${layout.availableHeight}px`,
    } as CSSProperties,
    stageStyle: {
      width: `${layout.stageWidth}px`,
      height: `${layout.stageHeight}px`,
      zoom: layout.scale,
    } as CSSProperties,
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/hooks/stageStyles.test.ts`
Expected: PASS (2 tests).

- [ ] **Step 5: Return the styles from the hook**

In `web/src/hooks/useGameStageLayout.ts`, replace the return block:

```ts
    const layout = computeStageLayout(bounds.width, bounds.height, options);
    const styles = stageStyles({
        ...layout,
        availableWidth: bounds.width,
        availableHeight: bounds.height,
    });

    return {
        containerRef: setContainerElement as RefCallback<HTMLDivElement>,
        availableWidth: bounds.width,
        availableHeight: bounds.height,
        ...layout,
        ...styles,
    };
```

and add `stageStyles` to the existing `computeStageLayout` import.

- [ ] **Step 6: Delete the three local copies**

In each of `Game.tsx`, `Replay.tsx`, `TableSample.tsx`: delete the local `stageShellStyle` / `stageStyle` (and `stageFrameStyle` where it is the empty object) declarations, and destructure from the hook result instead — e.g. `const { shellStyle, stageStyle } = stageLayout`. Rename the JSX usages to match. `stageFrameStyle` was `{}` in all three; drop the prop rather than pass an empty object, unless the element needs it, in which case keep `{}` inline.

- [ ] **Step 7: Run the gate**

Run: `cd web && npx tsc && npx vitest run`
Expected: tsc clean, all tests pass (167 now).

- [ ] **Step 8: Commit**

```bash
git add web/src/hooks web/src/features/game/Game.tsx web/src/features/replay/Replay.tsx web/src/features/dev/TableSample.tsx
git commit -m "refactor(web): return fixed-stage styles from useGameStageLayout"
```

---

### Task 5: Shared ledger tile primitives

`Calc.tsx:204-286` and `Shanten.tsx:106-197` define the same three presentational components. Verified: both operate on the *same* types — `CalcTileValue` and Shanten's `TileValue` are both aliases of `tileModel.TileValue`, and Shanten's `sameTile` is `tileModel.sameTileValue`.

Two behavioural deltas the shared version must preserve exactly:
1. `ShantenTile` sets `disabled={dimmed && !selected}`; `CalcTile` sets no `disabled` attribute at all.
2. `ShantenTile` renders an optional `<span className="ldg-tile__badge">`; `CalcTile` never does.

**Files:**
- Create: `web/src/theme/components/LedgerTile.tsx`
- Modify: `web/src/theme/index.ts`, `web/src/features/calc/Calc.tsx:204-286`, `web/src/features/shanten/Shanten.tsx:106-197`
- Test: `web/src/theme/components/LedgerTile.test.ts` (new — these components have no coverage today)

**Interfaces:**
- Produces:
  - `LedgerTile(props: { tile: TileValue; onClick?: () => void; size?: 'normal' | 'small' | 'palette'; selected?: boolean; dimmed?: boolean; disabled?: boolean; badge?: string })`
  - `LedgerTileRow(props: { tiles: TileDraft[]; emptyLabel: string; onTileClick: (tileId: string) => void })`
  - `LedgerPaletteGrid(props: { onTileClick: (tile: TileValue) => void; selectedTile?: TileValue | null; dimSelected?: boolean; usedCounts?: Map<string, number> })`

- [ ] **Step 1: Write the characterization test first**

This pins the *current* markup of both copies before either is touched.

```ts
// web/src/theme/components/LedgerTile.test.ts
import { describe, it, expect } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { LedgerTile, LedgerPaletteGrid } from './LedgerTile'
import { TILE_LIBRARY } from '../../utils/tileModel'

const tile = TILE_LIBRARY[0]

describe('LedgerTile', () => {
  it('composes the ldg-tile class list in order', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, size: 'palette', selected: true }),
    )
    expect(html).toContain('class="ldg-tile ldg-tile--pal ldg-tile--sel"')
  })

  it('marks a tile static when it has no click handler', () => {
    const html = renderToStaticMarkup(createElement(LedgerTile, { tile }))
    expect(html).toContain('ldg-tile--static')
  })

  it('omits the disabled attribute unless disabled is passed (Calc behaviour)', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, dimmed: true }),
    )
    expect(html).not.toContain('disabled')
  })

  it('disables when asked (Shanten behaviour)', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerTile, { tile, onClick: () => {}, dimmed: true, disabled: true }),
    )
    expect(html).toContain('disabled')
  })

  it('renders a badge only when given one', () => {
    const withBadge = renderToStaticMarkup(createElement(LedgerTile, { tile, badge: '3' }))
    expect(withBadge).toContain('ldg-tile__badge')
    const without = renderToStaticMarkup(createElement(LedgerTile, { tile }))
    expect(without).not.toContain('ldg-tile__badge')
  })
})

describe('LedgerPaletteGrid', () => {
  it('renders one button per library tile', () => {
    const html = renderToStaticMarkup(
      createElement(LedgerPaletteGrid, { onTileClick: () => {} }),
    )
    expect(html.match(/ldg-tile /g)?.length).toBe(TILE_LIBRARY.length)
  })

  it('shows a remaining-count badge only when usedCounts is supplied', () => {
    const counts = new Map<string, number>([['3-1', 1]])
    const html = renderToStaticMarkup(
      createElement(LedgerPaletteGrid, { onTileClick: () => {}, usedCounts: counts }),
    )
    expect(html).toContain('ldg-tile__badge')
    const plain = renderToStaticMarkup(createElement(LedgerPaletteGrid, { onTileClick: () => {} }))
    expect(plain).not.toContain('ldg-tile__badge')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/theme/components/LedgerTile.test.ts`
Expected: FAIL — cannot resolve `./LedgerTile`.

- [ ] **Step 3: Implement the primitives**

```tsx
// web/src/theme/components/LedgerTile.tsx
import { getTileName, getTileSvgName } from '../../utils/tileUtils'
import {
  TILE_LIBRARY, formatTile, sameTileValue, tileKey,
  type TileDraft, type TileValue,
} from '../../utils/tileModel'

export type LedgerTileSize = 'normal' | 'small' | 'palette'

/**
 * The ledger-workbench tile button shared by the calc and shanten tools.
 * `disabled` is an explicit prop rather than derived from `dimmed`: the shanten
 * palette disables exhausted tiles, while the calc palette stays clickable.
 */
export function LedgerTile({
  tile, onClick, size = 'normal', selected = false, dimmed = false, disabled, badge,
}: {
  tile: TileValue
  onClick?: () => void
  size?: LedgerTileSize
  selected?: boolean
  dimmed?: boolean
  disabled?: boolean
  badge?: string
}) {
  const cls = [
    'ldg-tile',
    size === 'small' ? 'ldg-tile--sm' : '',
    size === 'palette' ? 'ldg-tile--pal' : '',
    selected ? 'ldg-tile--sel' : '',
    dimmed ? 'ldg-tile--dim' : '',
    !onClick ? 'ldg-tile--static' : '',
  ].filter(Boolean).join(' ')

  return (
    <button type="button" className={cls} onClick={onClick} disabled={disabled} title={getTileName(tile)}>
      <img src={`/Regular_shortnames/${getTileSvgName(tile)}`} alt={getTileName(tile)} draggable="false" />
      {badge && <span className="ldg-tile__badge">{badge}</span>}
    </button>
  )
}

export function LedgerTileRow({ tiles, emptyLabel, onTileClick }: {
  tiles: TileDraft[]
  emptyLabel: string
  onTileClick: (tileId: string) => void
}) {
  if (tiles.length === 0) {
    return (
      <div className="ldg-tile-row ldg-tile-row--empty">
        <span className="ldg-note" style={{ marginTop: 0 }}>{emptyLabel}</span>
      </div>
    )
  }
  return (
    <div className="ldg-tile-row">
      {tiles.map((tile) => (
        <LedgerTile key={tile.id} tile={tile} onClick={() => onTileClick(tile.id)} />
      ))}
    </div>
  )
}

/**
 * The full 4x9+ tile palette. Passing `usedCounts` switches on the shanten
 * behaviour: a remaining-copies badge, and exhausted tiles dimmed and disabled.
 */
export function LedgerPaletteGrid({ onTileClick, selectedTile = null, dimSelected = false, usedCounts }: {
  onTileClick: (tile: TileValue) => void
  selectedTile?: TileValue | null
  dimSelected?: boolean
  usedCounts?: Map<string, number>
}) {
  return (
    <div className="ldg-palette-grid">
      {TILE_LIBRARY.map((tile) => {
        const isSelected = sameTileValue(tile, selectedTile)
        if (!usedCounts) {
          return (
            <LedgerTile
              key={formatTile(tile)} tile={tile} onClick={() => onTileClick(tile)}
              size="palette" selected={isSelected} dimmed={dimSelected && isSelected}
            />
          )
        }
        const remaining = 4 - (usedCounts.get(tileKey(tile)) ?? 0)
        const isDimmed = remaining <= 0 || (dimSelected && isSelected)
        return (
          <LedgerTile
            key={formatTile(tile)} tile={tile} onClick={() => onTileClick(tile)}
            size="palette" selected={isSelected} dimmed={isDimmed}
            disabled={isDimmed && !isSelected}
            badge={remaining < 4 ? `${remaining}` : undefined}
          />
        )
      })}
    </div>
  )
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/theme/components/LedgerTile.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Export from the theme barrel**

Add to `web/src/theme/index.ts`:

```ts
export { LedgerTile, LedgerTileRow, LedgerPaletteGrid } from './components/LedgerTile'
export type { LedgerTileSize } from './components/LedgerTile'
```

- [ ] **Step 6: Switch `Shanten.tsx` over first**

Shanten is the stricter consumer (badge + disabled), so it proves the shared API. Delete `ShantenTile`, `HandRow`, `PaletteGrid` (lines 106-197) and import the primitives. Its `<PaletteGrid usedCounts={...} .../>` becomes `<LedgerPaletteGrid usedCounts={...} .../>`; `<HandRow .../>` becomes `<LedgerTileRow .../>`; bare `<ShantenTile .../>` usages become `<LedgerTile .../>`.

Run: `cd web && npx tsc && npx vitest run`
Expected: clean.

- [ ] **Step 7: Switch `Calc.tsx` over**

Delete `CalcTile`, `TileRow`, `PaletteGrid` (lines 204-286) and import the primitives. Calc passes **no** `usedCounts` and **no** `disabled`, which reproduces its always-clickable palette exactly.

Run: `cd web && npx tsc && npx vitest run`
Expected: clean.

- [ ] **Step 8: Verify visually on the two tool pages**

```bash
cd web && npm run dev
```
Open `http://localhost:3000/tools/calc` and `http://localhost:3000/tools/shanten`. Confirm: tiles render, the palette selects, shanten still dims and disables exhausted tiles and shows remaining-count badges, calc's palette stays clickable. Stop the server.

- [ ] **Step 9: Update the directory docs and commit**

Add `LedgerTile` / `LedgerTileRow` / `LedgerPaletteGrid` to `web/src/theme/components/CLAUDE.md` and `web/src/theme/CLAUDE.md`; note in `web/src/features/calc/CLAUDE.md` and `web/src/features/shanten/CLAUDE.md` that the tile widgets now come from the theme.

```bash
git add web/src/theme web/src/features/calc web/src/features/shanten
git commit -m "refactor(web): share ledger tile primitives between calc and shanten"
```

---

### Task 6: Shared wild-tile predicate, and merge the replay steal branches

Two small, independent items in one commit-per-item task.

**Files:**
- Modify: `web/src/utils/tileModel.ts` (add), `web/src/features/game/Game.tsx:288-292`, `web/src/features/replay/Replay.tsx:169-172`, `web/src/features/shanten/Shanten.tsx:547,561`, `web/src/features/replay/replayEngine.ts:183-212,228-231`
- Test: `web/src/utils/tileModel.test.ts` (extend)

**Interfaces:**
- Produces: `export function makeWildTilePredicate(wildTiles: readonly TileValue[]): (tile: TileValue) => boolean` in `utils/tileModel.ts`.

- [ ] **Step 1: Write the failing test**

Append to `web/src/utils/tileModel.test.ts`:

```ts
describe('makeWildTilePredicate', () => {
  const wilds = [{ suit: 3, value: 5 }, { suit: 1, value: 9 }]

  it('matches tiles by suit and value', () => {
    const isWild = makeWildTilePredicate(wilds)
    expect(isWild({ suit: 3, value: 5 })).toBe(true)
    expect(isWild({ suit: 1, value: 9 })).toBe(true)
  })

  it('rejects tiles that are not wild', () => {
    const isWild = makeWildTilePredicate(wilds)
    expect(isWild({ suit: 3, value: 6 })).toBe(false)
    expect(isWild({ suit: 2, value: 5 })).toBe(false)
  })

  it('never matches when there are no wild tiles', () => {
    expect(makeWildTilePredicate([])({ suit: 3, value: 5 })).toBe(false)
  })
})
```

Add `makeWildTilePredicate` to the file's import list.

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/utils/tileModel.test.ts`
Expected: FAIL — `makeWildTilePredicate` is not exported.

- [ ] **Step 3: Implement it**

Append to `web/src/utils/tileModel.ts`:

```ts
/**
 * Builds a wild-tile (搭) test from the round's wild indicators. Callers were
 * re-inlining `${suit}-${value}` string keys; this routes them all through tileKey.
 */
export function makeWildTilePredicate(
  wildTiles: readonly TileValue[],
): (tile: TileValue) => boolean {
  const keys = new Set(wildTiles.map(tileKey))
  return (tile: TileValue) => keys.has(tileKey(tile))
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/utils/tileModel.test.ts`
Expected: PASS.

- [ ] **Step 5: Replace the inlined key sets**

In `Game.tsx`, `Replay.tsx`, `Shanten.tsx` and `replayEngine.ts`, delete the local `new Set(...map(t => `${t.suit}-${t.value}`))` construction and its `isWild` closure, and use `makeWildTilePredicate(wildTiles)` instead. Keep the local variable name `isWild` so the JSX below is untouched.

Run: `cd web && npx tsc && npx vitest run`
Expected: clean.

- [ ] **Step 6: Commit the predicate**

```bash
git add web/src/utils web/src/features
git commit -m "refactor(web): route wild-tile checks through tileModel.makeWildTilePredicate"
```

- [ ] **Step 7: Merge the identical replay steal branches**

`replayEngine.ts:183-197` (chii/pon) and `199-212` (okan) contain identical steal-from-discard logic. Read both, confirm they are identical apart from the action label, then collapse the two `case` arms into one shared arm.

Run: `cd web && npx vitest run src/features/replay`
Expected: PASS — replay tests still green.

- [ ] **Step 8: Commit**

```bash
git add web/src/features/replay/replayEngine.ts
git commit -m "refactor(web): merge identical chii/pon and okan steal branches"
```

---

### Task 7: One seat-wind label table

The wind labels exist in five spellings across nine sites: kanji for table décor, i18n keys, and en/zh literals.

**Files:**
- Create: `web/src/utils/winds.ts`
- Modify: `web/src/table/TableScene.tsx:51`, `web/src/features/game/SeatCard.tsx:31,44`, `web/src/features/replay/ReplayLibrary.tsx:38`, `web/src/features/replay/reviewUtils.ts:143-148`, `web/src/features/calc/Calc.tsx:331-336`, `web/src/features/calc/calcHelpers.ts:112-117`
- Test: `web/src/utils/winds.test.ts` (new)

**Interfaces:**
- Produces: `WIND_KANJI: readonly ['', '東', '南', '西', '北']` (1-indexed by seat wind), `WIND_I18N_KEYS: readonly ['common.east','common.south','common.west','common.north']`, `windI18nKey(wind: number): string`.

- [ ] **Step 1: Read every current site and record its exact output**

```bash
cd web && grep -rn "東\|common.east\|'East'" src --include=*.ts --include=*.tsx
```
Write the current strings down. The shared table must reproduce each caller's output character-for-character; a wind rendered `东` in one place and `東` in another is a real difference, not a typo to fix here.

- [ ] **Step 2: Write the failing test**

```ts
// web/src/utils/winds.test.ts
import { describe, it, expect } from 'vitest'
import { WIND_KANJI, WIND_I18N_KEYS, windI18nKey } from './winds'

describe('wind labels', () => {
  it('indexes kanji by seat wind, 1-based', () => {
    expect(WIND_KANJI[1]).toBe('東')
    expect(WIND_KANJI[4]).toBe('北')
  })

  it('maps seat wind to its i18n key', () => {
    expect(windI18nKey(1)).toBe('common.east')
    expect(windI18nKey(4)).toBe('common.north')
  })

  it('keeps the two tables aligned', () => {
    expect(WIND_KANJI.length).toBe(WIND_I18N_KEYS.length + 1)
  })
})
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd web && npx vitest run src/utils/winds.test.ts`
Expected: FAIL — cannot resolve `./winds`.

- [ ] **Step 4: Implement**

```ts
// web/src/utils/winds.ts
// Seat winds are 1-based in the proto (East=1, South=2, West=3, North=4), so the
// kanji table carries a leading empty slot to stay indexable by seat wind directly.
export const WIND_KANJI = ['', '東', '南', '西', '北'] as const

export const WIND_I18N_KEYS = [
  'common.east', 'common.south', 'common.west', 'common.north',
] as const

export function windI18nKey(wind: number): (typeof WIND_I18N_KEYS)[number] {
  return WIND_I18N_KEYS[wind - 1] ?? WIND_I18N_KEYS[0]
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd web && npx vitest run src/utils/winds.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Re-point the sites one at a time**

After each single-file edit run `cd web && npx tsc && npx vitest run`. If a site's rendered string would change, do **not** change it — leave that site alone and note it in the commit body. Behaviour preservation outranks consolidation.

- [ ] **Step 7: Commit**

```bash
git add web/src/utils/winds.ts web/src/utils/winds.test.ts web/src/table web/src/features
git commit -m "refactor(web): one seat-wind label table in utils/winds.ts"
```

---

### Task 8: One JSON API request/response helper

Six files repeat: POST with JSON body, `.json().catch(() => ({}))`, `data.error || <fallback>`, and a `TypeError` → offline-message mapping. Each caller's fallback string is user-visible and must survive exactly.

**Files:**
- Modify: `web/src/features/auth/authClient.ts` (add), `web/src/features/auth/Account.tsx:45-47`, `web/src/features/auth/AuthTicket.tsx:25-35`, `web/src/features/game/Table.tsx:138-155,191-201,208-218,241-251`, `web/src/features/lobby/Lobby.tsx:41-51,64-77`, `web/src/features/lobby/CreateRoom.tsx:19-25`, `web/src/features/replay/ReplayLibrary.tsx:127-129`
- Test: `web/src/features/auth/authClient.test.ts` (extend)

**Interfaces:**
- Produces, in `features/auth/authClient.ts`:
  - `readJsonBody<T = Record<string, unknown>>(res: Response): Promise<T & { error?: string }>`
  - `errorMessage(data: { error?: string }, fallback: string): string`
  - `offlineMessage(err: unknown, fallback: string): string` — returns the offline copy for a `TypeError`, otherwise `fallback`

- [ ] **Step 1: Record every caller's current error strings**

```bash
cd web && grep -rn "\.json().catch\|data.error ||\|instanceof TypeError" src/features
```
List each fallback string. These are the contract; the helper takes them as arguments and never supplies its own.

- [ ] **Step 2: Write the failing tests**

Append to `web/src/features/auth/authClient.test.ts`:

```ts
describe('readJsonBody', () => {
  it('returns the parsed body', async () => {
    const res = { json: async () => ({ error: 'nope' }) } as unknown as Response
    expect(await readJsonBody(res)).toEqual({ error: 'nope' })
  })

  it('returns an empty object when the body is not JSON', async () => {
    const res = { json: async () => { throw new Error('bad json') } } as unknown as Response
    expect(await readJsonBody(res)).toEqual({})
  })
})

describe('errorMessage', () => {
  it('prefers the server error', () => {
    expect(errorMessage({ error: 'Seat taken' }, 'Could not join')).toBe('Seat taken')
  })

  it('falls back when the server sent none', () => {
    expect(errorMessage({}, 'Could not join')).toBe('Could not join')
  })
})
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd web && npx vitest run src/features/auth/authClient.test.ts`
Expected: FAIL — the two helpers are not exported.

- [ ] **Step 4: Implement**

```ts
/** Parses a JSON response body, yielding `{}` when the body is absent or malformed. */
export async function readJsonBody<T = Record<string, unknown>>(
  res: Response,
): Promise<T & { error?: string }> {
  return (await res.json().catch(() => ({}))) as T & { error?: string }
}

/** The server's error text when it sent one, otherwise the caller's own fallback. */
export function errorMessage(data: { error?: string }, fallback: string): string {
  return data.error || fallback
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd web && npx vitest run src/features/auth/authClient.test.ts`
Expected: PASS.

- [ ] **Step 6: Re-point callers one file at a time**

Start with `CreateRoom.tsx` (smallest, one call site). After each file: `cd web && npx tsc && npx vitest run`.

Leave the `TypeError` → offline mapping alone for now if a caller's offline string differs from its siblings — an inconsistent user-facing string is a product decision, not a refactor.

- [ ] **Step 7: Commit**

```bash
git add web/src/features
git commit -m "refactor(web): share JSON response parsing across API callers"
```

---


### Task 9: Tool-page chrome primitives

Both tool pages open with the same `ClubShell` + `ToolTabs` + header + language-toggle block, retype
the input+apply row five times, and the `ldg-chooser` segmented row three times.

**Files:**
- Create: `web/src/theme/components/ToolWorkbench.tsx`, `web/src/theme/components/InputApplyRow.tsx`
- Modify: `web/src/theme/index.ts`, `web/src/features/calc/Calc.tsx:643-797`, `web/src/features/shanten/Shanten.tsx:346-481`
- Test: `web/src/theme/components/ToolWorkbench.test.ts` (new)

**Interfaces:**
- Produces: `ToolWorkbench(props: { title: string; children: ReactNode })` and
  `InputApplyRow(props: { value: string; onChange: (v: string) => void; onApply: () => void; placeholder?: string; applyLabel: string })`.

- [ ] **Step 1: Write the characterization test**

```ts
// web/src/theme/components/ToolWorkbench.test.ts
import { describe, it, expect } from 'vitest'
import { createElement } from 'react'
import { renderStatic } from '../../test/renderStatic'
import { InputApplyRow } from './InputApplyRow'

describe('InputApplyRow', () => {
  it('renders the ldg input row markup both tool pages use', () => {
    const html = renderStatic(
      createElement(InputApplyRow, {
        value: '1m2m3m', onChange: () => {}, onApply: () => {}, applyLabel: 'Apply',
      }),
    )
    expect(html).toContain('ldg-input-row')
    expect(html).toContain('ldg-input')
    expect(html).toContain('ldg-btn')
    expect(html).toContain('Apply')
    expect(html).toContain('value="1m2m3m"')
  })
})
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd web && npx vitest run src/theme/components/ToolWorkbench.test.ts`
Expected: FAIL — cannot resolve `./InputApplyRow`.

- [ ] **Step 3: Implement, copying the existing markup exactly**

Read `Calc.tsx:689-699` first and reproduce its element order, class names and attribute set
character-for-character. The component takes the label as a prop; it never supplies copy of its own.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/theme/components/ToolWorkbench.test.ts`
Expected: PASS.

- [ ] **Step 5: Re-point the five input rows and the two page headers, one at a time**

After each: `cd web && npx tsc && npx vitest run`. The `ldg-chooser` rows are structurally the
existing `Toggle` primitive — if switching one changes its rendered classes at all, leave it and
note why.

- [ ] **Step 6: Commit**

```bash
git add web/src/theme web/src/features/calc web/src/features/shanten
git commit -m "refactor(web): share tool-page workbench chrome"
```

---

### Task 10: Move the Calc and Shanten dictionaries into the locale catalog

Both pages call `useI18n()` for the language toggle but then index a private en/zh object. The two
tables overlap on 17 keys — 12 EN and 10 ZH values byte-identical — and several restate strings the
catalog already has (`language.switch`, `result.tsumo`, `nav.tools`). Because these tables sit
outside `Record<TranslationKey, string>`, `tsc` cannot enforce EN/ZH parity for them.

**Files:**
- Modify: `web/src/i18n/locales/en.ts`, `web/src/i18n/locales/zh-CN.ts`, `web/src/features/calc/Calc.tsx:51-178`, `web/src/features/shanten/Shanten.tsx:25-102`
- Test: `web/src/i18n/I18nContext.test.ts` (extend)

**Interfaces:**
- Produces: `tools.*` (shared), `calc.*`, `shanten.*` key groups in both locale files.

- [ ] **Step 1: Extract the current strings verbatim**

```bash
cd web && sed -n '51,178p' src/features/calc/Calc.tsx > /tmp/calc-copy.txt
sed -n '25,102p' src/features/shanten/Shanten.tsx > /tmp/shanten-copy.txt
```
These files are the contract. Every string must appear in the catalog unchanged — same characters,
same placeholders.

- [ ] **Step 2: Write the parity test**

```ts
// append to web/src/i18n/I18nContext.test.ts
import { en } from './locales/en'
import { zhCN } from './locales/zh-CN'

describe('tool-page copy', () => {
  it('has a zh string for every tools/calc/shanten key', () => {
    const keys = Object.keys(en).filter((k) => /^(tools|calc|shanten)\./.test(k))
    expect(keys.length).toBeGreaterThan(0)
    for (const key of keys) {
      expect(zhCN, `missing zh for ${key}`).toHaveProperty(key)
    }
  })
})
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd web && npx vitest run src/i18n/I18nContext.test.ts`
Expected: FAIL — no `tools.*` keys exist yet, so the `toBeGreaterThan(0)` assertion fails.

- [ ] **Step 4: Add the keys to `en.ts`, then `zh-CN.ts`**

Copy the strings from `/tmp/calc-copy.txt` and `/tmp/shanten-copy.txt` exactly. Shared entries go
under `tools.*`; page-specific ones under `calc.*` / `shanten.*`. Reuse existing catalog keys
(`language.switch`, `result.tsumo`, `result.ron`, `game.wildTile`, `nav.tools`) rather than adding
duplicates of strings that already exist.

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd web && npx vitest run src/i18n/I18nContext.test.ts`
Expected: PASS. `tsc` now enforces EN/ZH parity for these keys.

- [ ] **Step 6: Switch the pages over and delete the private tables**

Replace `text.foo` with `t('calc.foo')` / `t('tools.foo')`, then delete `UI_TEXT` and `TEXT`.
Replace the inline `lang === 'en' ? 'Table Tools' : '牌桌工具'` in both pages with `t('nav.tools')`.

Run: `cd web && npx tsc && npx vitest run`
Expected: clean.

- [ ] **Step 7: Check both pages in both languages**

```bash
cd web && npm run dev
```
Visit `/tools/calc` and `/tools/shanten`, toggle the language control, and confirm every label
reads exactly as before in both EN and ZH. Stop the server.

- [ ] **Step 8: Commit**

```bash
git add web/src/i18n web/src/features/calc web/src/features/shanten
git commit -m "refactor(web): move tool-page copy into the typed locale catalog"
```

---

### Task 11: Replay label mechanisms, segmented controls, compass mark

Three ad-hoc en/zh label mechanisms in the replay feature; four hand-rolled segmented controls that
duplicate the `Toggle` primitive; the `東` compass mark in three places; repeated tile-box size
blocks in `index.css`.

**Files:**
- Modify: `web/src/features/replay/*`, `web/src/theme/components/Toggle.tsx`, `web/src/index.css`
- Test: existing replay tests must stay green

- [ ] **Step 1: Inventory each site**

```bash
cd web && grep -rn "lang === 'en'\|=== 'zh'" src/features/replay
grep -rn "東" src --include=*.tsx --include=*.css
```

- [ ] **Step 2: Consolidate one mechanism at a time, gating after each**

Run after each: `cd web && npx tsc && npx vitest run`.
Any site whose rendered string or class list would change is left alone and noted.

- [ ] **Step 3: Commit**

```bash
git add web/src/features/replay web/src/theme web/src/index.css
git commit -m "refactor(web): consolidate replay labels, segmented controls and compass mark"
```

---

### Task 12: Merge `theme/base.css`'s two stacked layers

`base.css` is two passes over the same design system: a "legacy geometry" layer (lines 1-757) and a "Rainy Club skin" layer (759-1293) that re-declares 55 of the same selectors. 31 declarations are byte-identical no-ops; 90 are overridden and never reach the browser.

This is the highest-risk task in the PR, because CSS has no type checker behind it. It runs last, and it is verified by diffing built output.

**Files:**
- Modify: `web/src/theme/base.css`
- Test: built-CSS diff (below)

**Interfaces:** none — pure stylesheet consolidation.

- [ ] **Step 1: Capture the baseline built stylesheet**

```bash
cd web && npx vite build >/dev/null 2>&1 && cp dist/assets/*.css /tmp/base-before.css && wc -c /tmp/base-before.css
```

- [ ] **Step 2: List the doubly-declared selectors**

```bash
cd web && grep -n "^\s*\.\S.*{" src/theme/base.css | awk -F: '{print $2}' | sort | uniq -d
```
Expected: ~55 selectors appearing twice. Work through them one at a time.

- [ ] **Step 3: Merge one selector and re-diff**

For each duplicated selector: keep the later (skin) rule; fold in any layer-1 declaration the skin does **not** restate; delete the layer-1 rule. Some layer-1 declarations are not restated and must survive — `.ldg-input { flex: 1; min-width: 0 }` and `.ldg-toggle { display: inline-flex; overflow: hidden }` are known examples.

Never delete a line range wholesale. Grouped selectors in the skin layer (e.g. `.ldg-section-meta, .ldg-result-label, .ldg-palette-drawer__head, .ldg-debug__label`) need care so a per-selector merge does not change which declarations a member of the group picks up.

After each selector:

```bash
cd web && npx vite build >/dev/null 2>&1 && diff <(tr '}' '\n' < /tmp/base-before.css | sort) <(tr '}' '\n' < dist/assets/*.css | sort)
```
Expected: **no output.** The emitted CSS must be identical as a set of rules. Any diff means the merge changed a computed value — revert that selector and re-do it.

- [ ] **Step 4: Confirm the whole file at the end**

```bash
cd web && npx vite build >/dev/null 2>&1 && diff <(tr '}' '\n' < /tmp/base-before.css | sort) <(tr '}' '\n' < dist/assets/*.css | sort) && echo "IDENTICAL"
```
Expected: `IDENTICAL`.

- [ ] **Step 5: Check the pages by eye**

```bash
cd web && npm run dev
```
Visit `/`, `/play`, `/tools/calc`, `/tools/shanten`, `/replay`. Confirm nothing shifted. Stop the server.

- [ ] **Step 6: Run the gate and commit**

```bash
cd web && npx tsc && npx vitest run
git add web/src/theme/base.css
git commit -m "refactor(web): collapse base.css's duplicated legacy and skin layers"
```

---

### Task 13: PR wrap-up

- [ ] **Step 1: Run the full gate one more time**

```bash
cd web && npx tsc && npx vitest run
cd .. && gofmt -l . && go vet ./... && go test ./...
```
Expected: all clean. Go is unaffected by this PR but must still be green before the PR opens.

- [ ] **Step 2: Update the refactoring notes**

Append a `2026-08-16 — PR 1 (frontend)` section to `docs/refactoring-notes.md` recording: `table/tileId.ts` owns `tileIdsEqual`; `theme/components/LedgerTile.tsx` owns the ledger tile widgets; `hooks/computeStageLayout.ts` owns `stageStyles`; `utils/winds.ts` owns wind labels; `utils/tileModel.ts` owns `makeWildTilePredicate`; `test/` owns the shared test helpers. State the rule: pages must not re-implement these.

- [ ] **Step 3: Confirm the line count actually went down**

```bash
git diff --stat main...HEAD -- web/
```
Expected: deletions substantially exceed insertions.

- [ ] **Step 4: Open the PR**

```bash
git push -u origin worktree-refactor+dedup-2026-08
gh pr create --title "refactor(web): de-duplicate frontend" --body "$(cat <<'EOF'
Behaviour-preserving de-duplication of `web/src`, per
`worklog/specs/2026-08-16-dedup-and-naming-refactor-design.md` §6.1.

No rendered output, copy, or API changes. Each commit is one extraction with the
gate (`npx tsc && npx vitest run`) green.

Shared homes introduced:
- `table/tileId.ts` — the single `tileIdsEqual`
- `theme/components/LedgerTile.tsx` — the ledger tile widgets shared by calc and shanten
- `hooks/computeStageLayout.ts` — `stageStyles`, the fixed-stage wrapper styles
- `utils/winds.ts` — seat-wind labels
- `utils/tileModel.ts` — `makeWildTilePredicate`
- `test/` — shared CSS-contract, static-render and storage test helpers

Test count goes up (new characterization tests for previously untested components);
line count goes down.
EOF
)"
```
