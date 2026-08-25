# Mobile Round Result and Payout Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the end-of-hand payout popup fully usable on portrait phones and redesign it as a responsive Fenghua settlement ledger with an always-reachable action footer.

**Architecture:** Keep `TableRoundResultOverlay` as the shared live/replay presenter, but split its internals into a scrollable result body and a non-scrolling action footer. Move its styles out of the large global stylesheet into a focused table CSS module, size the popup from the overlay/dynamic viewport instead of the scaled game stage, and protect the DOM/CSS reachability contract with Vitest.

**Tech Stack:** React 19, TypeScript 5.9, Vitest 2, plain CSS, Vite 7.

## Global Constraints

- Scope is the end-of-hand `TableRoundResultOverlay`, not `MatchEndOverlay` and not the fixed 1600x900 board.
- Preserve the existing `RoundResultView` interface, action callbacks, tile ordering, meld ordering, payout values, ready states, and live/replay call sites.
- The action footer must be a sibling after `.round-result-scroll`; it must never be inside the scrollport.
- Popup dimensions must not reference `--game-stage-scaled-width` or `--game-stage-scaled-height`.
- Phone buttons must have a minimum 48px touch height and safe-area-aware bottom padding.
- Use only local/system font stacks and the six-color approved base palette; derived opacity and tonal variants are allowed, but add no dependency.
- Follow red-green-refactor order for every behavior change.
- Update the applicable `AGENTS.md` files whenever code or architecture in their directory changes.

---

## File Structure

- **Create:** `web/src/table/roundResultOverlay.test.ts` — DOM-structure and CSS-contract regression tests.
- **Create:** `web/src/table/roundResult.css` — all round-result overlay styling, responsive rules, and design tokens.
- **Modify:** `web/src/table/TableScene.tsx` — semantic dialog markup and body/footer split; public props remain unchanged.
- **Modify:** `web/src/index.css` — import the focused stylesheet and remove the two obsolete round-result style blocks.
- **Modify:** `web/src/table/AGENTS.md` — document the popup structure and new style/test files.
- **Modify:** `web/src/AGENTS.md` — replace the obsolete global round-result styling note with the focused module contract.

## Task 1: Lock the dialog and body/footer DOM contract with a failing test

**Files:**
- Create: `web/src/table/roundResultOverlay.test.ts`
- Test: `web/src/table/roundResultOverlay.test.ts`

**Interfaces:**
- Consumes: `TableRoundResultOverlay({ result, isWildTile? })` and `RoundResultView` from `web/src/table/TableScene.tsx`.
- Produces: a regression test that requires semantic dialog attributes and exactly two modal children in the order `round-result-scroll`, `round-result-actions`.

- [ ] **Step 1: Write the failing structure test**

Create `web/src/table/roundResultOverlay.test.ts` with:

```ts
import { Children, createElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'
import { TableRoundResultOverlay, type RoundResultView } from './TableScene'

type ElementProps = {
  children?: ReactNode
  className?: string
  role?: string
  'aria-modal'?: boolean
  'aria-labelledby'?: string
}

const result: RoundResultView = {
  isDraw: false,
  winType: 'ron',
  winnerLabel: 'Seat 2 wins',
  discarderLabel: 'From Seat 3',
  breakdown: [
    { name: 'Base Point (坐台)', points: 1 },
    { name: 'Independence (大大胡)', points: 50 },
  ],
  totalScore: 52,
  payouts: [
    { seat: 0, label: 'Seat 0', amount: -52, readyLabel: '...' },
    { seat: 1, label: 'Seat 1', amount: -52, readyLabel: 'Ready', readyActive: true },
    { seat: 2, label: 'Seat 2', amount: 208, readyLabel: 'Ready', readyActive: true },
    { seat: 3, label: 'Seat 3', amount: -104, readyLabel: '...' },
  ],
  actions: createElement('button', { type: 'button' }, 'Ready'),
}

describe('TableRoundResultOverlay', () => {
  it('keeps a labelled scroll body before a persistent action footer', () => {
    const overlay = TableRoundResultOverlay({ result }) as ReactElement<ElementProps>
    const dialog = overlay.props.children as ReactElement<ElementProps>
    const children = Children.toArray(dialog.props.children) as ReactElement<ElementProps>[]

    expect(dialog.props.role).toBe('dialog')
    expect(dialog.props['aria-modal']).toBe(true)
    expect(dialog.props['aria-labelledby']).toBe('round-result-title')
    expect(children).toHaveLength(2)
    expect(children[0].props.className).toBe('round-result-scroll')
    expect(children[1].props.className).toBe('round-result-actions')
  })
})
```

- [ ] **Step 2: Run the test and verify the expected failure**

Run from `web/`:

```bash
npm test -- src/table/roundResultOverlay.test.ts
```

Expected: FAIL because the current modal has no `role="dialog"` and its result sections/actions are not split into the required two children.

- [ ] **Step 3: Commit the red test**

```bash
git add web/src/table/roundResultOverlay.test.ts
git commit -m "test(table): reproduce unreachable round-result actions"
```

## Task 2: Restructure the shared overlay into a semantic scroll body and footer

**Files:**
- Modify: `web/src/table/TableScene.tsx:125-250`
- Test: `web/src/table/roundResultOverlay.test.ts`

**Interfaces:**
- Consumes: the unchanged `RoundResultView` fields and optional `isWildTile` predicate.
- Produces: `.round-result-modal[role=dialog]` with `.round-result-scroll` followed by optional `.round-result-actions`.

- [ ] **Step 1: Replace `TableRoundResultOverlay` with the body/footer structure**

Keep the existing function signature and local data preparation at lines 125-138. Replace its `return` block with:

```tsx
  return (
    <div className="round-result-overlay">
      <section
        className={`round-result-modal round-result-modal-${result.isDraw ? 'draw' : result.winType ?? 'draw'}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="round-result-title"
      >
        <div className="round-result-scroll" tabIndex={0}>
          {result.isDraw ? (
            <header className="round-result-heading round-result-heading-draw">
              <div className="round-result-badge round-result-badge-draw">Draw</div>
              <div>
                <div className="round-result-eyebrow">Hand settled</div>
                <h2 id="round-result-title" className="round-result-title round-result-title-draw">
                  Exhaustive Draw
                </h2>
                <p className="round-result-subtitle">No tiles remaining in the wall.</p>
              </div>
            </header>
          ) : (
            <>
              <header className="round-result-heading">
                <div className="round-result-heading-main">
                  <div className={`round-result-badge ${result.winType === 'tsumo' ? 'round-result-badge-tsumo' : 'round-result-badge-ron'}`}>
                    {result.winType === 'tsumo' ? 'Tsumo' : 'Ron'}
                  </div>
                  <div>
                    <div className="round-result-eyebrow">Hand settled</div>
                    <h2 id="round-result-title" className={`round-result-title ${result.winType === 'tsumo' ? 'round-result-title-tsumo' : 'round-result-title-ron'}`}>
                      {result.winnerLabel}
                    </h2>
                    {result.discarderLabel && (
                      <p className="round-result-subtitle">{result.discarderLabel}</p>
                    )}
                  </div>
                </div>
                <div className="round-result-total" aria-label={`Total score ${result.totalScore ?? 0}`}>
                  <span>Total</span>
                  <strong>{result.totalScore ?? 0}</strong>
                </div>
              </header>

              <section className="round-result-section round-result-hand-section" aria-label="Winning hand">
                <div className="round-result-section-label">Winning hand</div>
                <div className="round-result-hand-rack">
                  <div className="round-result-hand-row">
                    <div className="round-result-closed-hand">
                      {closedHand.map((tile) => (
                        <div key={tile.id} className="pov-bottom small">
                          <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                        </div>
                      ))}
                      {result.winTile && (
                        <div className="pov-bottom small round-result-win-tile">
                          <TileComponent tile={result.winTile} size="small" isWild={isWildTile(result.winTile)} />
                        </div>
                      )}
                    </div>

                    {winningMelds.length > 0 && (
                      <div className="round-result-melds-divider">
                        <OpenMelds melds={winningMelds} isWildTile={isWildTile} />
                      </div>
                    )}

                    {flowers.length > 0 && (
                      <div className="round-result-melds-divider">
                        {flowers.map((tile) => (
                          <div key={`fl-${tile.id}`} className="pov-bottom small">
                            <TileComponent tile={tile} size="small" isWild={isWildTile(tile)} />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </section>

              {breakdown.length > 0 && (
                <section className="round-result-section" aria-label="Scoring breakdown">
                  <div className="round-result-section-label">Score ledger</div>
                  <div className="round-result-breakdown-grid">
                    {breakdown.map((entry, index) => (
                      <div key={`${entry.name}-${index}`} className="round-result-breakdown-item">
                        <div className="round-result-breakdown-name">{entry.name}</div>
                        <div className="round-result-breakdown-points">+{entry.points}</div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <section className="round-result-section" aria-label="Seat payouts">
                <div className="round-result-section-label">Payouts</div>
                <div className="round-result-payout-grid">
                  {payouts.map((payout) => (
                    <div
                      key={`${payout.seat}-${payout.label}`}
                      className={`round-result-payout-cell ${payout.amount > 0 ? 'round-result-payout-positive' : 'round-result-payout-negative'}`}
                    >
                      <div className="round-result-payout-seat">{payout.label}</div>
                      <div className="round-result-payout-amount">
                        {payout.amount > 0 ? '+' : ''}{payout.amount}
                      </div>
                      {payout.readyLabel && (
                        <div className={`round-result-payout-ready ${payout.readyActive ? 'round-result-payout-ready-on' : ''}`}>
                          {payout.readyLabel}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            </>
          )}
        </div>

        {result.actions && (
          <div className="round-result-actions">
            {result.actions}
          </div>
        )}
      </section>
    </div>
  )
```

Do not change `RoundResultView`, `Game.tsx`, `Replay.tsx`, `OpenMelds`, or the pre-return sorting logic.

- [ ] **Step 2: Run the focused test**

```bash
cd web && npm test -- src/table/roundResultOverlay.test.ts
```

Expected: PASS (1 test).

- [ ] **Step 3: Run existing shared-table tests**

```bash
cd web && npm test -- src/table/handOrdering.test.ts src/table/meldOrdering.test.ts
```

Expected: PASS; winning-hand and meld ordering remain unchanged.

- [ ] **Step 4: Commit the component change**

```bash
git add web/src/table/TableScene.tsx
git commit -m "fix(table): keep round-result actions outside scroll body"
```

## Task 3: Add a failing CSS reachability contract

**Files:**
- Modify: `web/src/table/roundResultOverlay.test.ts`
- Test: `web/src/table/roundResultOverlay.test.ts`

**Interfaces:**
- Consumes: current `web/src/index.css` plus optional `web/src/table/roundResult.css`.
- Produces: source-level assertions for the layout properties that make Ready reachable.

- [ ] **Step 1: Add filesystem imports and the CSS test**

Add these imports at the top of `roundResultOverlay.test.ts`:

```ts
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
```

Append this code after the existing `describe` block:

```ts
function readRoundResultCss() {
  return ['src/index.css', 'src/table/roundResult.css']
    .map((path) => resolve(process.cwd(), path))
    .filter((path) => existsSync(path))
    .map((path) => readFileSync(path, 'utf8'))
    .join('\n')
}

function ruleBody(css: string, selector: string) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`))?.[1] ?? ''
}

describe('round-result CSS reachability contract', () => {
  it('sizes from the viewport and reserves a persistent action row', () => {
    const css = readRoundResultCss()

    expect(ruleBody(css, '.round-result-modal')).toContain('grid-template-rows: minmax(0, 1fr) auto')
    expect(ruleBody(css, '.round-result-scroll')).toContain('overflow-y: auto')
    expect(ruleBody(css, '.round-result-actions')).toContain('flex-shrink: 0')
    expect(css).toContain('100dvh')
    expect(css).not.toContain('--game-stage-scaled-height')
    expect(css).not.toContain('--game-stage-scaled-width')
  })
})
```

- [ ] **Step 2: Run the focused test and verify the CSS assertion fails**

```bash
cd web && npm test -- src/table/roundResultOverlay.test.ts
```

Expected: the DOM test passes and the CSS contract test FAILS because the current modal lacks the two-row grid/scroll body and still references the scaled-stage dimensions.

- [ ] **Step 3: Commit the red CSS test**

```bash
git add web/src/table/roundResultOverlay.test.ts
git commit -m "test(table): specify mobile payout reachability contract"
```

## Task 4: Implement the Fenghua settlement sheet styles

**Files:**
- Create: `web/src/table/roundResult.css`
- Modify: `web/src/index.css:1-2,922-1331,1739-1751`
- Test: `web/src/table/roundResultOverlay.test.ts`

**Interfaces:**
- Consumes: the class structure introduced in Task 2.
- Produces: centered desktop/landscape card, portrait bottom sheet, scrollable body, persistent safe-area footer, and Fenghua ledger visual tokens.

- [ ] **Step 1: Create the focused stylesheet**

Create `web/src/table/roundResult.css` with:

```css
.round-result-overlay {
  --rr-lacquer: #071d1a;
  --rr-felt: #0f4a3c;
  --rr-bone: #f2e8d5;
  --rr-jade: #74c69d;
  --rr-brass: #d6b46a;
  --rr-cinnabar: #d7665b;
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  padding: max(0.75rem, env(safe-area-inset-top, 0px))
    max(0.75rem, env(safe-area-inset-right, 0px))
    max(0.75rem, env(safe-area-inset-bottom, 0px))
    max(0.75rem, env(safe-area-inset-left, 0px));
  background:
    radial-gradient(circle at 50% 32%, rgba(116, 198, 157, 0.13), transparent 34%),
    rgba(2, 12, 11, 0.72);
}

.game-stage-shell > .round-result-overlay {
  position: absolute;
}

.round-result-modal {
  width: min(760px, calc(100% - 1.5rem));
  max-height: min(780px, calc(100dvh - 1.5rem));
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  overflow: hidden;
  color: var(--rr-bone);
  border: 1px solid rgba(214, 180, 106, 0.34);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(15, 74, 60, 0.28), transparent 34%),
    var(--rr-lacquer);
  box-shadow:
    inset 0 1px 0 rgba(242, 232, 213, 0.08),
    0 28px 80px rgba(0, 0, 0, 0.5);
}

.round-result-scroll {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  scrollbar-gutter: stable;
  padding: 1rem 1rem 0.8rem;
  outline: none;
}

.round-result-scroll:focus-visible {
  box-shadow: inset 0 0 0 2px rgba(116, 198, 157, 0.72);
}

.round-result-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  padding-bottom: 0.85rem;
  border-bottom: 1px solid rgba(214, 180, 106, 0.28);
}

.round-result-heading-main,
.round-result-heading-draw {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.round-result-heading-draw {
  justify-content: flex-start;
}

.round-result-eyebrow,
.round-result-section-label,
.round-result-total span,
.round-result-payout-seat {
  font-size: 0.65rem;
  font-weight: 800;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: rgba(242, 232, 213, 0.58);
}

.round-result-badge {
  flex: 0 0 auto;
  min-width: 48px;
  padding: 0.45rem 0.52rem;
  border: 1px solid currentColor;
  border-radius: 8px;
  font-size: 0.66rem;
  font-weight: 900;
  letter-spacing: 0.12em;
  text-align: center;
  text-transform: uppercase;
  transform: rotate(-2deg);
}

.round-result-badge-tsumo { color: var(--rr-brass); background: rgba(214, 180, 106, 0.1); }
.round-result-badge-ron { color: var(--rr-cinnabar); background: rgba(215, 102, 91, 0.1); }
.round-result-badge-draw { color: rgba(242, 232, 213, 0.72); background: rgba(242, 232, 213, 0.06); }

.round-result-title {
  margin: 0.08rem 0 0;
  font-family: "Songti SC", STSong, "Times New Roman", serif;
  font-size: clamp(1.45rem, 3vw, 2rem);
  font-weight: 700;
  letter-spacing: 0.025em;
  line-height: 1.05;
  color: var(--rr-bone);
}

.round-result-title-tsumo { color: #f1d28f; }
.round-result-title-ron { color: #efb0a8; }
.round-result-title-draw { color: var(--rr-bone); }

.round-result-subtitle {
  margin: 0.22rem 0 0;
  font-size: 0.76rem;
  color: rgba(242, 232, 213, 0.64);
}

.round-result-total {
  flex: 0 0 auto;
  display: grid;
  justify-items: end;
  font-variant-numeric: tabular-nums;
}

.round-result-total strong {
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  line-height: 1;
  color: var(--rr-brass);
}

.round-result-section {
  margin-top: 0.85rem;
}

.round-result-section-label {
  margin-bottom: 0.38rem;
}

.round-result-hand-rack {
  overflow-x: auto;
  overscroll-behavior-x: contain;
  padding: 0.55rem 0.55rem 0.72rem;
  border: 1px solid rgba(214, 180, 106, 0.28);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.18), transparent 45%),
    #d8c9ad;
  box-shadow: inset 0 -5px 0 rgba(81, 58, 36, 0.14);
}

.round-result-hand-row,
.round-result-closed-hand,
.round-result-melds-divider {
  display: flex;
  align-items: flex-end;
}

.round-result-hand-row {
  width: max-content;
  min-width: 100%;
  justify-content: center;
}

.round-result-closed-hand { gap: 2px; }
.round-result-win-tile { margin-left: 7px; }
.round-result-melds-divider {
  gap: 6px;
  margin-left: 7px;
  padding-left: 7px;
  border-left: 2px solid rgba(81, 58, 36, 0.28);
}

.round-result-breakdown-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 1rem;
  padding: 0.45rem 0.7rem;
  border-top: 1px solid rgba(214, 180, 106, 0.22);
  border-bottom: 1px solid rgba(214, 180, 106, 0.22);
}

.round-result-breakdown-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0.5rem;
  padding: 0.32rem 0;
  border-bottom: 1px dotted rgba(242, 232, 213, 0.14);
  font-size: 0.8rem;
}

.round-result-breakdown-name { color: rgba(242, 232, 213, 0.78); }
.round-result-breakdown-points {
  color: var(--rr-jade);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.round-result-payout-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.45rem;
}

.round-result-payout-cell {
  min-width: 0;
  padding: 0.6rem 0.45rem 0.5rem;
  border: 1px solid rgba(242, 232, 213, 0.12);
  border-radius: 10px;
  background: rgba(15, 74, 60, 0.2);
  text-align: center;
}

.round-result-payout-positive { border-top: 3px solid var(--rr-jade); }
.round-result-payout-negative { border-top: 3px solid var(--rr-cinnabar); }
.round-result-payout-amount {
  margin-top: 0.12rem;
  font-size: 1.1rem;
  font-weight: 900;
  font-variant-numeric: tabular-nums;
}
.round-result-payout-positive .round-result-payout-amount { color: var(--rr-jade); }
.round-result-payout-negative .round-result-payout-amount { color: #e58b81; }

.round-result-payout-ready {
  width: fit-content;
  margin: 0.3rem auto 0;
  padding: 0.1rem 0.34rem;
  border-radius: 999px;
  font-size: 0.56rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(242, 232, 213, 0.48);
  background: rgba(0, 0, 0, 0.18);
}

.round-result-payout-ready-on { color: var(--rr-jade); }

.round-result-actions {
  flex-shrink: 0;
  display: flex;
  justify-content: flex-end;
  gap: 0.55rem;
  padding: 0.75rem 1rem max(0.75rem, env(safe-area-inset-bottom, 0px));
  border-top: 1px solid rgba(214, 180, 106, 0.28);
  background: rgba(4, 24, 21, 0.98);
  box-shadow: 0 -10px 24px rgba(0, 0, 0, 0.18);
}

.round-result-action-btn {
  min-width: 132px;
  min-height: 44px;
  padding: 0.65rem 1rem;
  border: 1px solid rgba(242, 232, 213, 0.18);
  border-radius: 10px;
  color: var(--rr-bone);
  background: rgba(242, 232, 213, 0.06);
  font-size: 0.78rem;
  font-weight: 900;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  cursor: pointer;
}

.round-result-action-btn-ready {
  color: #06231d;
  border-color: var(--rr-jade);
  background: var(--rr-jade);
}

.round-result-action-btn-exit {
  color: #f3c2bc;
  border-color: rgba(215, 102, 91, 0.5);
}

.round-result-action-btn:hover { transform: translateY(-1px); }
.round-result-action-btn:focus-visible {
  outline: 3px solid rgba(214, 180, 106, 0.8);
  outline-offset: 2px;
}
.round-result-action-btn-disabled,
.round-result-action-btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
  transform: none;
}

@media (max-width: 720px) {
  .round-result-overlay {
    align-items: flex-end;
    padding: max(0.5rem, env(safe-area-inset-top, 0px)) 0 0;
  }

  .round-result-modal {
    width: 100%;
    max-height: calc(100dvh - max(0.5rem, env(safe-area-inset-top, 0px)));
    border-right: 0;
    border-bottom: 0;
    border-left: 0;
    border-radius: 22px 22px 0 0;
  }

  .round-result-scroll { padding: 0.85rem 0.8rem 0.7rem; }
  .round-result-heading { gap: 0.65rem; }
  .round-result-heading-main { gap: 0.55rem; }
  .round-result-title { font-size: clamp(1.25rem, 6vw, 1.65rem); }
  .round-result-total strong { font-size: clamp(1.5rem, 8vw, 2rem); }
  .round-result-breakdown-grid { grid-template-columns: 1fr; }
  .round-result-payout-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .round-result-hand-row { justify-content: flex-start; }

  .round-result-actions {
    display: grid;
    grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr);
    padding-right: max(0.8rem, env(safe-area-inset-right, 0px));
    padding-left: max(0.8rem, env(safe-area-inset-left, 0px));
  }

  .round-result-action-btn {
    width: 100%;
    min-width: 0;
    min-height: 48px;
  }
}

@media (orientation: landscape) and (max-height: 500px) {
  .round-result-overlay { padding: 0.35rem; }
  .round-result-modal {
    width: min(680px, calc(100% - 0.7rem));
    max-height: calc(100dvh - 0.7rem);
    border-radius: 16px;
  }
  .round-result-scroll { padding: 0.65rem 0.75rem 0.55rem; }
  .round-result-section { margin-top: 0.55rem; }
  .round-result-actions { padding: 0.5rem 0.75rem; }
}

@media (prefers-reduced-motion: reduce) {
  .round-result-action-btn { transition: none; }
}
```

- [ ] **Step 2: Import the module and remove the obsolete declarations**

At the top of `web/src/index.css`, keep Tailwind first and add:

```css
@import "tailwindcss";
@import "./table/roundResult.css";
```

Delete the complete old block beginning with:

```css
/* Round Result Modal */
.round-result-overlay {
```

and ending immediately before:

```css
.shanten-indicator {
```

Also delete the later fixed-stage overrides in full:

```css
.game-stage-shell > .round-result-overlay {
  position: absolute;
  inset: 0;
  padding-top: max(0.75rem, env(safe-area-inset-top, 0px));
  padding-right: max(0.75rem, env(safe-area-inset-right, 0px));
  padding-bottom: max(0.75rem, env(safe-area-inset-bottom, 0px));
  padding-left: max(0.75rem, env(safe-area-inset-left, 0px));
}

.game-stage-shell > .round-result-overlay .round-result-modal {
  width: min(760px, calc(var(--game-stage-scaled-width) - 1.5rem), calc(100vw - 1.5rem));
  max-height: min(86vh, calc(var(--game-stage-scaled-height) - 1.5rem), 780px);
}
```

- [ ] **Step 3: Run the focused tests**

```bash
cd web && npm test -- src/table/roundResultOverlay.test.ts
```

Expected: PASS (2 tests). The CSS contract now finds the grid, scrollport, persistent footer, dynamic viewport unit, and no scaled-stage dependency.

- [ ] **Step 4: Run the full frontend unit suite**

```bash
cd web && npm test
```

Expected: PASS with all existing and new Vitest tests.

- [ ] **Step 5: Commit the style module**

```bash
git add web/src/table/roundResult.css web/src/index.css
git commit -m "feat(table): redesign payout as responsive settlement sheet"
```

## Task 5: Update directory documentation

**Files:**
- Modify: `web/src/table/AGENTS.md`
- Modify: `web/src/AGENTS.md`

**Interfaces:**
- Consumes: the final component and stylesheet ownership from Tasks 2 and 4.
- Produces: accurate maintenance guidance for the shared result overlay.

- [ ] **Step 1: Document the table-owned result module**

Under `TableScene.tsx` in `web/src/table/AGENTS.md`, replace the existing one-line result-overlay description with:

```markdown
  - `TableRoundResultOverlay` renders the shared live/replay end-of-hand settlement dialog with a scrollable result body and a separate persistent action footer
- **roundResult.css** — Fenghua settlement-ledger styling for the shared result dialog:
  - Centers the dialog on wide/short-landscape screens and turns it into a safe-area-aware bottom sheet on portrait phones
  - Sizes from the overlay/dynamic viewport rather than the scaled 1600x900 stage, so `Ready` and `Exit` remain reachable
- **roundResultOverlay.test.ts** — protects dialog semantics plus the body/footer and CSS reachability contracts
```

Add this architecture note at the end of the file:

```markdown
- Keep `.round-result-actions` outside `.round-result-scroll`; the sibling relationship is what keeps live `Ready` / `Exit` controls reachable while long scoring content scrolls. Round-result dimensions must never depend on the fixed-stage scaled width or height variables.
```

- [ ] **Step 2: Update the source-level CSS ownership note**

In `web/src/AGENTS.md`, replace:

```markdown
  - Includes a glass round-result modal styled to match the table HUD/cards instead of the older flat dark dialog, but without backdrop blur so players can still inspect the table behind it
```

with:

```markdown
  - Imports `table/roundResult.css`, the focused Fenghua settlement-sheet module shared by live and replay; the result body scrolls independently while its action footer stays reachable on phone viewports
```

- [ ] **Step 3: Review the documentation diff**

```bash
git diff --check -- web/src/table/AGENTS.md web/src/AGENTS.md
git diff -- web/src/table/AGENTS.md web/src/AGENTS.md
```

Expected: `git diff --check` exits 0 and the diff describes the implemented ownership and invariant exactly.

- [ ] **Step 4: Commit the documentation**

```bash
git add web/src/table/AGENTS.md web/src/AGENTS.md
git commit -m "docs(table): document responsive settlement overlay"
```

## Task 6: Verify build, interaction, and responsive presentation

**Files:**
- Verify: all files changed in Tasks 1-5

**Interfaces:**
- Consumes: the completed component, style module, tests, and docs.
- Produces: fresh automated and browser evidence that the bug is fixed without shared-table regressions.

- [ ] **Step 1: Run formatting and whitespace checks**

```bash
git diff --check
```

Expected: exit 0 with no whitespace errors.

- [ ] **Step 2: Run the full frontend test suite**

```bash
cd web && npm test
```

Expected: all Vitest tests pass, including both `roundResultOverlay.test.ts` assertions.

- [ ] **Step 3: Run the production build**

```bash
cd web && npm run build
```

Expected: TypeScript and Vite exit 0 and write `web/dist`.

- [ ] **Step 4: Verify the result sheet in the browser at four sizes**

Run the normal local backend and frontend, open a live round result with at least eight breakdown rows, and inspect these exact viewport sizes:

```text
375x667   portrait compact phone
393x852   portrait modern phone
852x393   short landscape phone
1440x900  desktop
```

At each phone size verify:

```text
- The popup stays inside the visual viewport and respects the bottom safe area.
- The result body scrolls from the winner heading through all payouts.
- Ready and Exit remain visible before, during, and after body scrolling.
- Ready accepts a tap and changes to the existing Waiting... disabled state.
- The winning hand scrolls horizontally when it cannot fit without shrinking tiles.
- Positive/negative payout signs remain visible without relying on color.
- Keyboard focus is visible on the scroll body and both actions.
```

At desktop and short landscape sizes verify the modal remains centered and the same footer/body separation holds.

- [ ] **Step 5: Inspect final scope**

```bash
git status --short
git diff --stat HEAD~5..HEAD
git log --oneline -5
```

Expected: only the six planned files are changed across the five implementation commits; no protobuf, engine, replay-controller, stage-layout, or generated files are modified.

## Completion Criteria

- The original portrait-phone failure is reproducible by the new tests before implementation and passes afterward.
- `Ready` and `Exit` are reachable at 375x667 with overflowing result content.
- The popup reads as the approved Fenghua settlement ledger: lacquer/felt body, bone hand rack, jade gains, brass total, and cinnabar losses.
- Live and replay still use the same `TableRoundResultOverlay` implementation.
- `npm test`, `npm run build`, and `git diff --check` all pass with fresh output.
