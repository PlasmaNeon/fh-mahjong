# Round-Result Payout Sheet Demo Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dev-only `/tools/round-result` playground that previews PR #152's redesigned round-result overlay with curated mock data, across scenarios and viewport sizes, without playing a live match.

**Architecture:** One dual-mode React component. Default mode = a control panel plus a resizable `<iframe>`; the iframe loads the same route with `?embed=1`, which renders *only* `<TableRoundResultOverlay>` full-bleed so the iframe's own viewport drives PR #152's responsive media queries. Mock `RoundResultView` data lives in a pure, unit-tested module.

**Tech Stack:** React 19, TypeScript, Vite 7, react-router-dom, Tailwind v4 (already wired via `web/src/index.css`), Vitest. No new dependencies.

## Global Constraints

- Depend only on the stable `RoundResultView` contract from `web/src/table/types.ts` and the `TableRoundResultOverlay` export from `web/src/table/TableScene.tsx`. Do **not** touch the overlay component or `roundResult.css` (those are PR #152's, already merged into this branch).
- Tile suit convention (matches `web/src/features/dev/TableSample.tsx`): `1=sou, 2=pin, 3=man, 4=jihai, 5=flower`.
- `roundResult.css` is imported globally via `web/src/index.css` (`@import "./table/roundResult.css";`) — no per-component CSS import is needed; the styles apply on the demo route and inside the iframe automatically.
- New route is public, like the other `/tools/*` routes. Dev-only tool; no auth, no network, no new deps.
- Add no new CSS file — style the control-panel chrome with Tailwind utility classes; the overlay itself is styled by `roundResult.css`.
- Viewport switching must use an `<iframe>` (nested browsing context) — a scaled `<div>` will not trigger `@media (max-width: 720px)`.

---

### Task 1: Mock scenario builders (pure module + tests)

Pure data module that produces `RoundResultView` payloads (minus the `actions` React node, which the component supplies). Kept separate from the component so it is unit-testable and reused by the iframe render.

**Files:**
- Create: `web/src/features/dev/roundResultScenarios.ts`
- Test: `web/src/features/dev/roundResultScenarios.test.ts`

**Interfaces:**
- Consumes: `RoundResultView`, `TileLike`, `MeldLike`, `RoundResultPayout` from `web/src/table/types.ts`.
- Produces:
  - `type ScenarioKey = 'tsumo' | 'ron' | 'draw' | 'long'`
  - `const SCENARIO_KEYS: ScenarioKey[]`
  - `const SCENARIO_LABELS: Record<ScenarioKey, string>`
  - `type ScenarioData = Omit<RoundResultView, 'actions'>`
  - `function buildScenario(key: ScenarioKey, ready: boolean): ScenarioData`

- [ ] **Step 1: Write the failing test**

Create `web/src/features/dev/roundResultScenarios.test.ts`:

```ts
import { describe, it, expect } from 'vitest'
import { SCENARIO_KEYS, SCENARIO_LABELS, buildScenario } from './roundResultScenarios'

describe('buildScenario', () => {
  it('exposes a label for every scenario key', () => {
    for (const key of SCENARIO_KEYS) {
      expect(SCENARIO_LABELS[key]).toBeTruthy()
    }
  })

  it('draw scenario sets isDraw with no payouts and no breakdown', () => {
    const r = buildScenario('draw', false)
    expect(r.isDraw).toBe(true)
    expect(r.payouts ?? []).toHaveLength(0)
    expect(r.breakdown ?? []).toHaveLength(0)
  })

  for (const key of SCENARIO_KEYS.filter((k) => k !== 'draw')) {
    it(`${key} scenario: winType + breakdown + one winner, three losers, balanced`, () => {
      const r = buildScenario(key, false)
      expect(r.isDraw).toBe(false)
      expect(r.winType).toBeTruthy()
      expect((r.breakdown ?? []).length).toBeGreaterThan(0)

      const payouts = r.payouts ?? []
      expect(payouts).toHaveLength(4)
      expect(payouts.filter((p) => p.amount > 0)).toHaveLength(1) // winner
      expect(payouts.filter((p) => p.amount < 0)).toHaveLength(3) // losers
      expect(payouts.reduce((acc, p) => acc + p.amount, 0)).toBe(0)
    })
  }

  it('long scenario has enough breakdown rows to force body scroll', () => {
    expect((buildScenario('long', false).breakdown ?? []).length).toBeGreaterThanOrEqual(10)
  })

  it('ready flag populates payout ready badges; default clears them', () => {
    expect((buildScenario('tsumo', true).payouts ?? []).some((p) => p.readyLabel)).toBe(true)
    expect((buildScenario('tsumo', false).payouts ?? []).every((p) => !p.readyLabel)).toBe(true)
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd web && npx vitest run src/features/dev/roundResultScenarios.test.ts`
Expected: FAIL — cannot resolve `./roundResultScenarios` (module does not exist yet).

- [ ] **Step 3: Write the implementation**

Create `web/src/features/dev/roundResultScenarios.ts`:

```ts
import type { MeldLike, RoundResultPayout, RoundResultView, TileLike } from '../../table/types'

// Dev-only mock data for the /tools/round-result preview. Suits match
// TableSample.tsx: 1=sou, 2=pin, 3=man, 4=jihai, 5=flower. These hands are for
// visual preview only — they are plausible but not validated by the rules engine.

export type ScenarioKey = 'tsumo' | 'ron' | 'draw' | 'long'

export const SCENARIO_KEYS: ScenarioKey[] = ['tsumo', 'ron', 'draw', 'long']

export const SCENARIO_LABELS: Record<ScenarioKey, string> = {
  tsumo: 'Tsumo win',
  ron: 'Ron win',
  draw: 'Exhaustive draw',
  long: 'Long high-score',
}

// The overlay owns the `actions` footer node; scenarios carry only data.
export type ScenarioData = Omit<RoundResultView, 'actions'>

// Per-seat ready badge. `ready` off => no badge (null); on => alternating
// Ready/waiting, mirroring Game.tsx's playerReady mapping.
function readyBadge(seat: number, ready: boolean): Pick<RoundResultPayout, 'readyLabel' | 'readyActive'> {
  if (!ready) return { readyLabel: null, readyActive: false }
  const active = seat % 2 === 0
  return { readyLabel: active ? 'Ready' : '...', readyActive: active }
}

// amounts must be given in seat order [0,1,2,3] and sum to zero.
function payouts(amounts: [number, number, number, number], ready: boolean): RoundResultPayout[] {
  return amounts.map((amount, seat) => ({
    seat,
    label: `Seat ${seat}`,
    amount,
    ...readyBadge(seat, ready),
  }))
}

export function buildScenario(key: ScenarioKey, ready: boolean): ScenarioData {
  let nextId = 0
  const t = (suit: number, value: number): TileLike => ({ id: nextId++, suit, value })

  switch (key) {
    case 'draw':
      return { isDraw: true }

    case 'ron': {
      const meld = [t(1, 9), t(1, 9), t(1, 9)]
      const winningMelds: MeldLike[] = [
        { tiles: meld, calledTileId: meld[2].id, calledDirection: 2 },
      ]
      return {
        isDraw: false,
        winType: 'ron',
        winnerLabel: 'Seat 1 wins',
        discarderLabel: 'From Seat 3',
        closedHand: [
          t(3, 2), t(3, 3), t(3, 4),
          t(2, 5), t(2, 6), t(2, 7),
          t(1, 5), t(1, 5),
          t(3, 7), t(3, 8),
        ],
        winTile: t(3, 9),
        winningMelds,
        flowers: [],
        breakdown: [
          { name: 'Terminal Triplet (幺九刻)', points: 2 },
          { name: 'Seat Wind (自風)', points: 1 },
          { name: 'Robbing the Kong (搶槓)', points: 8 },
        ],
        totalScore: 16,
        payouts: payouts([-3, 16, -3, -10], ready),
      }
    }

    case 'long': {
      const meld = [t(1, 3), t(1, 3), t(1, 3)]
      const winningMelds: MeldLike[] = [
        { tiles: meld, calledTileId: meld[2].id, calledDirection: 1 },
      ]
      return {
        isDraw: false,
        winType: 'tsumo',
        winnerLabel: 'Seat 2 wins',
        discarderLabel: null,
        closedHand: [
          t(1, 1), t(1, 1), t(1, 2),
          t(1, 4), t(1, 5), t(1, 6),
          t(1, 7), t(1, 8),
          t(1, 9), t(1, 9),
        ],
        winTile: t(1, 8),
        winningMelds,
        flowers: [t(5, 1), t(5, 2), t(5, 3), t(5, 4)],
        breakdown: [
          { name: 'Full Flush (清一色)', points: 24 },
          { name: 'Self-Draw (自摸)', points: 2 },
          { name: 'Concealed Triplet (暗刻)', points: 2 },
          { name: 'Flower Season 1', points: 1 },
          { name: 'Flower Season 2', points: 1 },
          { name: 'Flower Season 3', points: 1 },
          { name: 'Flower Season 4', points: 1 },
          { name: 'Kong Bonus (杠)', points: 2 },
          { name: 'Last Tile Draw (海底)', points: 8 },
          { name: 'Dealer Bonus (庄)', points: 4 },
          { name: 'Wild-Tile Pair (搭)', points: 6 },
          { name: 'All Terminals Fringe', points: 4 },
        ],
        totalScore: 96,
        payouts: payouts([-32, -32, 96, -32], ready),
      }
    }

    case 'tsumo':
    default:
      return {
        isDraw: false,
        winType: 'tsumo',
        winnerLabel: 'Seat 0 wins',
        discarderLabel: null,
        closedHand: [
          t(1, 1), t(1, 2), t(1, 3),
          t(2, 4), t(2, 5), t(2, 6),
          t(3, 7), t(3, 8), t(3, 9),
          t(1, 5), t(1, 5),
          t(2, 3), t(2, 3),
        ],
        winTile: t(2, 3),
        winningMelds: [],
        flowers: [t(5, 1)],
        breakdown: [
          { name: 'Self-Draw (自摸)', points: 2 },
          { name: 'All Sequences (平和)', points: 4 },
          { name: 'Flower (花牌)', points: 1 },
        ],
        totalScore: 24,
        payouts: payouts([24, -8, -8, -8], ready),
      }
  }
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd web && npx vitest run src/features/dev/roundResultScenarios.test.ts`
Expected: PASS — all cases green.

- [ ] **Step 5: Commit**

```bash
git add web/src/features/dev/roundResultScenarios.ts web/src/features/dev/roundResultScenarios.test.ts
git commit -m "feat(web): mock round-result scenarios for demo page"
```

---

### Task 2: Dual-mode demo component + route

The React component. Renders the playground (controls + iframe) by default and the bare overlay when `?embed=1`. Wire it into the router so both the page and its iframe resolve.

**Files:**
- Create: `web/src/features/dev/RoundResultDemo.tsx`
- Modify: `web/src/App.tsx` (add import + one `<Route>`)

**Interfaces:**
- Consumes: `buildScenario`, `SCENARIO_KEYS`, `SCENARIO_LABELS`, `ScenarioKey` from `./roundResultScenarios` (Task 1); `TableRoundResultOverlay` from `../../table/TableScene`; `useSearchParams` from `react-router-dom`.
- Produces: `export default function RoundResultDemo()` — the route element for `/tools/round-result`.

- [ ] **Step 1: Write the component**

Create `web/src/features/dev/RoundResultDemo.tsx`:

```tsx
import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { TableRoundResultOverlay } from '../../table/TableScene'
import {
  SCENARIO_KEYS,
  SCENARIO_LABELS,
  buildScenario,
  type ScenarioKey,
} from './roundResultScenarios'

// Dev-only preview for PR #152's round-result overlay. Route: /tools/round-result.
// Default = control panel + resizable iframe. The iframe loads this same route
// with ?embed=1 so its own viewport drives the responsive media queries.

const VIEWPORTS = [
  { key: 'phone', label: 'Portrait phone', width: 393, height: 852 },
  { key: 'landscape', label: 'Landscape', width: 852, height: 393 },
  { key: 'desktop', label: 'Desktop', width: 1280, height: 800 },
] as const
type ViewportKey = (typeof VIEWPORTS)[number]['key']

function isScenarioKey(value: string | null): value is ScenarioKey {
  return value !== null && (SCENARIO_KEYS as readonly string[]).includes(value)
}

// ── Embed mode: only the overlay, over a felt backdrop ──────────────────────
function EmbeddedOverlay() {
  const [params] = useSearchParams()
  const raw = params.get('scenario')
  const scenario: ScenarioKey = isScenarioKey(raw) ? raw : 'tsumo'
  const ready = params.get('ready') === '1'
  const [isReady, setIsReady] = useState(false)

  const data = useMemo(() => buildScenario(scenario, ready), [scenario, ready])

  const result = {
    ...data,
    actions: (
      <>
        <button
          onClick={() => setIsReady(true)}
          disabled={isReady}
          className={`round-result-action-btn round-result-action-btn-ready ${isReady ? 'round-result-action-btn-disabled' : ''}`}
        >
          {isReady ? 'Waiting...' : 'Ready'}
        </button>
        <button
          onClick={() => window.alert('Exit is a no-op in the demo.')}
          className="round-result-action-btn round-result-action-btn-exit"
        >
          Exit
        </button>
      </>
    ),
  }

  return (
    <div
      style={{
        minHeight: '100dvh',
        background: 'radial-gradient(circle at 50% 30%, #0f4a3c 0%, #071d1a 72%)',
      }}
    >
      <TableRoundResultOverlay result={result} />
    </div>
  )
}

// ── Playground mode: controls + iframe ──────────────────────────────────────
function segButton(active: boolean): string {
  return [
    'px-3 py-1.5 rounded-md text-sm font-semibold border transition-colors',
    active
      ? 'bg-emerald-500 border-emerald-400 text-emerald-950'
      : 'bg-white/5 border-white/15 text-white/80 hover:bg-white/10',
  ].join(' ')
}

function Playground() {
  const [scenario, setScenario] = useState<ScenarioKey>('tsumo')
  const [viewport, setViewport] = useState<ViewportKey>('phone')
  const [ready, setReady] = useState(false)

  const vp = VIEWPORTS.find((v) => v.key === viewport) ?? VIEWPORTS[0]
  const src = `/tools/round-result?embed=1&scenario=${scenario}&ready=${ready ? '1' : '0'}`

  return (
    <div className="min-h-screen p-6 flex flex-col gap-5">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold">Round-result payout preview</h1>
        <p className="text-sm text-white/60">
          Dev-only preview of the round-end payout sheet (PR #152). Not a live game.
        </p>
      </header>

      <div className="flex flex-wrap gap-6">
        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Scenario</span>
          <div className="flex flex-wrap gap-2">
            {SCENARIO_KEYS.map((key) => (
              <button key={key} className={segButton(scenario === key)} onClick={() => setScenario(key)}>
                {SCENARIO_LABELS[key]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Viewport</span>
          <div className="flex flex-wrap gap-2">
            {VIEWPORTS.map((v) => (
              <button key={v.key} className={segButton(viewport === v.key)} onClick={() => setViewport(v.key)}>
                {v.label}
                <span className="ml-1 text-white/40">
                  {v.width}×{v.height}
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-white/50">Ready badges</span>
          <button className={segButton(ready)} onClick={() => setReady((r) => !r)}>
            {ready ? 'On' : 'Off'}
          </button>
        </div>
      </div>

      <div className="flex justify-center overflow-auto rounded-xl bg-black/30 p-4">
        <iframe
          key={src}
          title="Round-result preview"
          src={src}
          style={{
            width: vp.width,
            height: vp.height,
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 12,
            background: '#071d1a',
            flex: '0 0 auto',
          }}
        />
      </div>
    </div>
  )
}

export default function RoundResultDemo() {
  const [params] = useSearchParams()
  return params.get('embed') === '1' ? <EmbeddedOverlay /> : <Playground />
}
```

- [ ] **Step 2: Wire the route into `web/src/App.tsx`**

Add the import beside the other `features/dev` import (after the `TableSample` import line):

```tsx
import TableSample from './features/dev/TableSample'
import RoundResultDemo from './features/dev/RoundResultDemo'
```

Add the route beside the other `/tools/*` routes (after the `table-sample` route line):

```tsx
                            <Route path="/tools/table-sample" element={<TableSample />} />
                            <Route path="/tools/round-result" element={<RoundResultDemo />} />
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit`
Expected: PASS — no type errors.

- [ ] **Step 4: Manual verification**

Run the dev server if not already up: `cd web && npm run dev` (Vite serves the SPA, so `/tools/round-result?embed=1&...` resolves inside the iframe).

Open `http://localhost:3000/tools/round-result` and confirm:
- The **Portrait phone** preset shows the overlay as a bottom-sheet: full width, rounded **top** corners only, two-column payout grid, action footer as a two-column grid with Ready/Exit reachable.
- The **Desktop** preset shows a centered card with all four corners rounded.
- The **Landscape** preset shows the compact card.
- The **Long high-score** scenario: the result body scrolls to its end while the Ready/Exit footer stays pinned and visible.
- The **Exhaustive draw** scenario shows the Draw heading with no hand/payouts.
- Tapping **Ready** in the preview flips it to disabled `Waiting...`.
- Toggling **Ready badges → On** shows per-seat Ready/`...` chips in the payout cells.

- [ ] **Step 5: Production build**

Run: `cd web && npm run build`
Expected: build succeeds (tsc + Vite bundle), no errors.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/dev/RoundResultDemo.tsx web/src/App.tsx
git commit -m "feat(web): /tools/round-result demo page for the payout sheet"
```

---

### Task 3: Documentation

`web/src/features/AGENTS.md` groups pages under `### folder/` subsections
(`auth/`, `lobby/`, `calc/`, `shanten/`, `replay/`, `game/`) inside a
"## Feature Folders" section. There is **no** `dev/` subsection yet — the
existing `TableSample.tsx` is currently undocumented. So this task **adds** a
`### dev/` subsection covering both the existing dev page and the new one.

**Files:**
- Modify: `web/src/features/AGENTS.md`

- [ ] **Step 1: Confirm the current structure**

Run: `grep -n "^### \`\|^## Architecture Notes" web/src/features/AGENTS.md`
Expected: lists the `### folder/` subsections ending with `### \`game/\``, followed by `## Architecture Notes`. Confirms there is no `### dev/` subsection.

- [ ] **Step 2: Insert a `dev/` subsection**

In `web/src/features/AGENTS.md`, find the end of the `### \`game/\`` subsection — the line immediately before `## Architecture Notes`:

```markdown
- **rejoinMatch.test.ts** — Vitest unit tests for the rejoin logic (11 tests).

## Architecture Notes
```

Insert the new subsection between them, so it reads:

```markdown
- **rejoinMatch.test.ts** — Vitest unit tests for the rejoin logic (11 tests).

### `dev/`

Dev-only preview pages that render real components with mock data (no live match). Not linked from the app UI; reached by URL.

- **TableSample.tsx** — Renders the real `TableBoard` with mock game data so the table layout can be iterated without a live match. Route: `/tools/table-sample`.
- **RoundResultDemo.tsx** — Preview of the round-end payout sheet (`TableRoundResultOverlay`) so PR #152's redesign can be reviewed without playing a round. Route: `/tools/round-result`. Renders a control panel (scenario · viewport preset · ready-badge toggle) plus a resizable `<iframe>`; the iframe loads the same route with `?embed=1` and renders only the overlay full-bleed, so its own viewport drives the responsive `max-width: 720px` / landscape media queries. Mock `RoundResultView` data comes from `roundResultScenarios.ts` (unit-tested in `roundResultScenarios.test.ts`).

## Architecture Notes
```

- [ ] **Step 3: Verify the edit**

Run: `grep -n "### \`dev/\`\|RoundResultDemo\|TableSample" web/src/features/AGENTS.md`
Expected: shows the new `### dev/` heading and both page entries.

- [ ] **Step 4: Commit**

```bash
git add web/src/features/AGENTS.md
git commit -m "docs(web): document the dev/ preview pages"
```

---

### Task 4: Final verification

Confirm the whole change is green before handing back.

- [ ] **Step 1: Full web test suite**

Run: `cd web && npm test`
Expected: all tests pass (includes the new `roundResultScenarios.test.ts` and the merged-in PR #152 `roundResultOverlay.test.ts`).

- [ ] **Step 2: Typecheck + build**

Run: `cd web && npx tsc --noEmit && npm run build`
Expected: both succeed.

- [ ] **Step 3: Confirm clean tree**

Run: `git status`
Expected: clean working tree; all demo commits present on the branch.

---

## Self-Review Notes

- **Spec coverage:** iframe viewport switcher (Task 2) · four scenarios incl. long-hand scroll (Task 1) · ready toggle + footer (Tasks 1 & 2) · decoupling via `RoundResultView` (Task 1 types) · global CSS import (no action needed, noted in constraints) · minimal builder test (Task 1) · AGENTS.md (Task 3) · build/typecheck verification (Tasks 2 & 4). The #152 merge is already done on this branch (prerequisite, not a plan task).
- **Payout invariant:** every win scenario yields exactly one positive and three negative payouts summing to zero — matches the Task 1 test.
- **Naming consistency:** `buildScenario`, `ScenarioKey`, `SCENARIO_KEYS`, `SCENARIO_LABELS`, `ScenarioData` are defined in Task 1 and consumed unchanged in Task 2.
