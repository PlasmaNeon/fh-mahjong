# Discard Modes + Off-Turn Tile Lifting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the live game table a single-click vs. double-click (tap-to-lift, tap-again-to-confirm) discard setting, plus the ability to lift your own hand tiles even when it is not your turn, switchable via an in-game settings popup.

**Architecture:** `GameTable` (in `web/src/features/game/Game.tsx`) owns the `discardMode` and `liftedTileId` state. A pure reducer (`handTileClick.ts`) turns each self-hand tile click into a `discard` / `lift` / `unlift` decision. `TileComponent` becomes a dumb button that emits clicks and renders a `lifted` flag; the self-hand interactivity is now turn-independent. The mode persists in `localStorage` and is edited through a `GameDialog`-based settings popup mirroring `ExitMatchButton`.

**Tech Stack:** React 19 + TypeScript, Vite, Vitest, Framer Motion. All work is under `web/`. Run all commands from `web/`.

## Global Constraints

- Frontend only. **No** backend, proto, or rules-engine changes.
- Default discard mode when unset: **`'double'`**.
- Setting persists per-browser in `localStorage` under key **`mahjong_discard_mode_v1`**.
- Interaction model is **tap-to-lift, tap-again-to-confirm** — NOT a timing-based double-click.
- Lift **carries over** into your turn (tracked by tile id); it is cleared on discard and when the lifted tile leaves your hand (new-round redeal, meld, etc.).
- At most **one** tile is lifted at a time.
- Off-turn lifting applies to **both** modes and only to the **self** (bottom) hand; opponent hands stay non-interactive.
- Settings gear sits **top-left** (Exit control stays top-right).
- Compare tile ids with `tileIdsEqual` from `web/src/table/meldOrdering.ts` (ids are compared as strings; `null`-safe), never `===`.
- Run tests with `npm test` (`vitest run`); type/build check with `npx tsc --noEmit`.

---

### Task 1: Discard-mode persistence helper

Mirrors the pure-parse + guarded-storage split already used in `web/src/features/game/rejoinMatch.ts`.

**Files:**
- Create: `web/src/features/game/discardMode.ts`
- Test: `web/src/features/game/discardMode.test.ts`

**Interfaces:**
- Produces:
  - `type DiscardMode = 'single' | 'double'`
  - `parseDiscardMode(raw: string | null): DiscardMode` — returns `'double'` for anything not exactly `'single'` or `'double'`.
  - `loadDiscardMode(): DiscardMode`
  - `saveDiscardMode(mode: DiscardMode): void`

- [ ] **Step 1: Write the failing test**

Create `web/src/features/game/discardMode.test.ts`:

```ts
import { afterEach, describe, expect, it } from 'vitest'
import { loadDiscardMode, parseDiscardMode, saveDiscardMode } from './discardMode'

describe('parseDiscardMode', () => {
  it('accepts the two valid modes', () => {
    expect(parseDiscardMode('single')).toBe('single')
    expect(parseDiscardMode('double')).toBe('double')
  })

  it('defaults to double for null / unknown / malformed values', () => {
    expect(parseDiscardMode(null)).toBe('double')
    expect(parseDiscardMode('')).toBe('double')
    expect(parseDiscardMode('triple')).toBe('double')
    expect(parseDiscardMode('SINGLE')).toBe('double')
  })
})

describe('load/save round-trip', () => {
  afterEach(() => localStorage.clear())

  it('defaults to double when nothing is stored', () => {
    expect(loadDiscardMode()).toBe('double')
  })

  it('persists and reloads a saved mode', () => {
    saveDiscardMode('single')
    expect(loadDiscardMode()).toBe('single')
    saveDiscardMode('double')
    expect(loadDiscardMode()).toBe('double')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- discardMode`
Expected: FAIL — `Failed to resolve import "./discardMode"` (module does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `web/src/features/game/discardMode.ts`:

```ts
export type DiscardMode = 'single' | 'double'

const DISCARD_MODE_KEY = 'mahjong_discard_mode_v1'
const DEFAULT_MODE: DiscardMode = 'double'

export function parseDiscardMode(raw: string | null): DiscardMode {
  return raw === 'single' || raw === 'double' ? raw : DEFAULT_MODE
}

function getLocalStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  return window.localStorage
}

export function loadDiscardMode(): DiscardMode {
  const storage = getLocalStorage()
  if (!storage) return DEFAULT_MODE
  return parseDiscardMode(storage.getItem(DISCARD_MODE_KEY))
}

export function saveDiscardMode(mode: DiscardMode): void {
  getLocalStorage()?.setItem(DISCARD_MODE_KEY, mode)
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- discardMode`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/game/discardMode.ts web/src/features/game/discardMode.test.ts
git commit -m "feat(web): discard-mode localStorage helper (default double)"
```

---

### Task 2: Pure click-resolution reducer

The whole discard/lift state machine as a pure, boolean-input function so it is unit-testable without rendering.

**Files:**
- Create: `web/src/features/game/handTileClick.ts`
- Test: `web/src/features/game/handTileClick.test.ts`

**Interfaces:**
- Consumes: `DiscardMode` from `./discardMode`.
- Produces:
  - `type HandTileClickResult = { kind: 'discard' | 'lift' | 'unlift' }`
  - `resolveHandTileClick(input: { mode: DiscardMode; isLifted: boolean; canDiscard: boolean }): HandTileClickResult`
  - Semantics: `isLifted` = the clicked tile is the currently-lifted one; `canDiscard` = it is the viewer's turn and a discard is valid right now. The container already knows which tile was clicked, so the result carries only the kind.

Resolution order:
1. `mode === 'single'` and `canDiscard` → `discard`.
2. else if `isLifted` → `canDiscard ? 'discard' : 'unlift'`.
3. else → `lift`.

- [ ] **Step 1: Write the failing test**

Create `web/src/features/game/handTileClick.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { resolveHandTileClick } from './handTileClick'

describe('resolveHandTileClick', () => {
  it('single mode on-turn discards immediately (no lift step)', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: false, canDiscard: true }).kind).toBe('discard')
    // even a re-tap of the same tile just discards on-turn
    expect(resolveHandTileClick({ mode: 'single', isLifted: true, canDiscard: true }).kind).toBe('discard')
  })

  it('single mode off-turn lifts an un-lifted tile', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: false, canDiscard: false }).kind).toBe('lift')
  })

  it('single mode off-turn un-lifts the lifted tile', () => {
    expect(resolveHandTileClick({ mode: 'single', isLifted: true, canDiscard: false }).kind).toBe('unlift')
  })

  it('double mode raises the lift on an un-lifted tile (on or off turn)', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: false, canDiscard: true }).kind).toBe('lift')
    expect(resolveHandTileClick({ mode: 'double', isLifted: false, canDiscard: false }).kind).toBe('lift')
  })

  it('double mode confirms discard when re-tapping the lifted tile on-turn', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: true, canDiscard: true }).kind).toBe('discard')
  })

  it('double mode off-turn drops the lifted tile instead of discarding', () => {
    expect(resolveHandTileClick({ mode: 'double', isLifted: true, canDiscard: false }).kind).toBe('unlift')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- handTileClick`
Expected: FAIL — `Failed to resolve import "./handTileClick"`.

- [ ] **Step 3: Write minimal implementation**

Create `web/src/features/game/handTileClick.ts`:

```ts
import type { DiscardMode } from './discardMode'

export type HandTileClickResult = { kind: 'discard' | 'lift' | 'unlift' }

// Pure state machine for a click on the viewer's own hand tile.
// - isLifted: the clicked tile is the currently-lifted one.
// - canDiscard: it is the viewer's turn and a discard is currently valid.
export function resolveHandTileClick(input: {
  mode: DiscardMode
  isLifted: boolean
  canDiscard: boolean
}): HandTileClickResult {
  const { mode, isLifted, canDiscard } = input
  if (mode === 'single' && canDiscard) return { kind: 'discard' }
  if (isLifted) return { kind: canDiscard ? 'discard' : 'unlift' }
  return { kind: 'lift' }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- handTileClick`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add web/src/features/game/handTileClick.ts web/src/features/game/handTileClick.test.ts
git commit -m "feat(web): pure reducer for discard/lift click resolution"
```

---

### Task 3: Wire lift + mode through the tile hierarchy and container

One atomic interface change: `TileComponent` gains `isLifted` and renames its click callback; the `TableScene → PlayerSeat → SeatBundle → ClosedHand` thread carries `liftedTileId` + `onHandTileClick` + turn-independent `interactive`; `GameTable` owns the state and builds the handler from the Task 2 reducer. The build only compiles once every hop is updated, so they ship together.

**Files:**
- Modify: `web/src/table/Tile.tsx`
- Modify: `web/src/table/seat/ClosedHand.tsx`
- Modify: `web/src/table/seat/SeatBundle.tsx`
- Modify: `web/src/table/seat/PlayerSeat.tsx`
- Modify: `web/src/table/TableScene.tsx`
- Modify: `web/src/features/game/Game.tsx`
- Modify: `web/src/table/table-theme.css`

**Interfaces:**
- Consumes: `resolveHandTileClick` (Task 2), `loadDiscardMode` (Task 1), `tileIdsEqual` (`web/src/table/meldOrdering.ts`).
- Produces (prop contracts other hops rely on):
  - `TileComponent` props: add `isLifted?: boolean`; rename `onDiscard?: (tile) => void` → `onTileClick?: (tile) => void`.
  - `ClosedHand` / `SeatBundle` / `PlayerSeat` props: remove `canDiscard` + `onDiscard`; add `interactive?: boolean`, `liftedTileId?: number | null`, `onHandTileClick?: (tile: TileLike) => void`.
  - `TableBoard` props: remove `canDiscardSeat` + `onDiscard`; add `liftedTileId?: number | null`, `onHandTileClick?: (tile: TileLike) => void`.

- [ ] **Step 1: Update `TileComponent` (dumb button + lifted flag)**

In `web/src/table/Tile.tsx`, replace the props type and component so it renders a `lifted` class and emits `onTileClick`:

```tsx
type TileComponentProps = {
  tile: TileLike
  isInteractive?: boolean
  isLifted?: boolean
  size?: 'normal' | 'small'
  noGlow?: boolean
  isWild?: boolean
  onTileClick?: (tile: TileLike) => void
}

export const TileComponent = memo(function TileComponent({
  tile,
  isInteractive = false,
  isLifted = false,
  size = 'normal',
  noGlow = false,
  isWild = false,
  onTileClick,
}: TileComponentProps) {
  const svgName = getTileSvgName(tile)

  return (
    <div
      className={`mahjong-tile ${isWild ? 'wild-tile' : ''} ${noGlow ? 'mahjong-tile--no-glow' : ''} ${isInteractive ? 'interactive' : ''} ${isLifted ? 'lifted' : ''} ${size === 'small' ? 'small' : ''}`}
      onClick={() => isInteractive && onTileClick?.(tile)}
      style={{
        padding: 0,
        border: 'none',
        backgroundColor: 'transparent',
        position: 'relative',
      }}
    >
      <img
        src={`/Regular_shortnames/${svgName}`}
        alt={getTileName(tile)}
        style={{ width: '85%', height: '85%', display: 'block', position: 'absolute', top: '7.5%', left: '7.5%', zIndex: 2 }}
        draggable="false"
      />
    </div>
  )
})
```

(Other `TileComponent` call sites — `TableScene.tsx`, `OpenMelds.tsx`, `FlowerZone.tsx`, `DiscardZone.tsx`, `Game.tsx:274` — pass neither `onDiscard` nor `isInteractive`, so they are unaffected by the rename.)

- [ ] **Step 2: Update `ClosedHand` to thread the new props**

In `web/src/table/seat/ClosedHand.tsx`:

Add the import near the top (line 5 area, alongside `tileIdsEqual` already imported):

```tsx
// tileIdsEqual is already imported from '../meldOrdering'
```

Replace the props type (lines 9-18) and destructure (lines 24-33):

```tsx
type ClosedHandProps = {
  isSelf: boolean
  player: PlayerTableView
  direction: SeatLaneDirection
  interactive?: boolean
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
  isWildTile?: (tile: TileLike) => boolean
  hiddenTileIds?: Set<number>
  hiddenSlots?: Set<number>
}

export function ClosedHand({
  isSelf,
  player,
  direction,
  interactive = false,
  liftedTileId = null,
  onHandTileClick,
  isWildTile = () => false,
  hiddenTileIds,
  hiddenSlots,
}: ClosedHandProps) {
```

Then update the `TileComponent` render inside `renderHandTile` (lines 104-110):

```tsx
        <TileComponent
          tile={tile}
          isInteractive={interactive}
          isLifted={liftedTileId != null && tileIdsEqual(tile.id, liftedTileId)}
          isWild={isWildTile(tile)}
          onTileClick={onHandTileClick}
          size={isSelf ? 'normal' : 'small'}
        />
```

- [ ] **Step 3: Update `SeatBundle` to pass the new props through**

In `web/src/table/seat/SeatBundle.tsx`, replace `canDiscard` / `onDiscard` in the props type (lines 12-13), the destructure (lines 27-28), and the `<ClosedHand>` call (lines 51-52) with the new trio:

Props type — replace the two lines:
```tsx
  interactive?: boolean
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
```

Destructure — replace `canDiscard = false,` and `onDiscard,`:
```tsx
  interactive = false,
  liftedTileId = null,
  onHandTileClick,
```

`<ClosedHand>` call — replace `canDiscard={canDiscard}` and `onDiscard={onDiscard}`:
```tsx
        interactive={interactive}
        liftedTileId={liftedTileId}
        onHandTileClick={onHandTileClick}
```

- [ ] **Step 4: Update `PlayerSeat` to derive self-interactivity**

In `web/src/table/seat/PlayerSeat.tsx`:

Props type (lines 8-9) — replace `canDiscard` / `onDiscard`:
```tsx
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
```

Destructure (lines 20-21) — replace `canDiscard = false,` and `onDiscard,`:
```tsx
  liftedTileId = null,
  onHandTileClick,
```

`<SeatBundle>` call (lines 48-49) — replace `canDiscard={canDiscard}` and `onDiscard={onDiscard}`. `interactive` is derived here: the self (bottom) hand is always interactive regardless of turn.
```tsx
          interactive={isSelf}
          liftedTileId={liftedTileId}
          onHandTileClick={onHandTileClick}
```

(`isSelf` is already computed at line 31 as `direction === 'bottom'`.)

- [ ] **Step 5: Update `TableBoard` props and the `PlayerSeat` render**

In `web/src/table/TableScene.tsx`:

`TableBoardProps` (lines 41-42) — replace `canDiscardSeat?: number | null` and `onDiscard?: ...`:
```tsx
  liftedTileId?: number | null
  onHandTileClick?: (tile: TileLike) => void
```

Destructure (lines 63-64) — replace `canDiscardSeat = null,` and `onDiscard,`:
```tsx
  liftedTileId = null,
  onHandTileClick,
```

`<PlayerSeat>` render (lines 116-117) — replace `canDiscard={direction === 'bottom' && player.seat === canDiscardSeat}` and `onDiscard={onDiscard}`:
```tsx
          liftedTileId={liftedTileId}
          onHandTileClick={onHandTileClick}
```

- [ ] **Step 6: Add the `.lifted` visual state**

In `web/src/table/table-theme.css`, immediately after the `.mahjong-tile.interactive:hover` rule (line 212), add:

```css
.mahjong-tile.lifted { transform: translateY(-14px); filter: brightness(1.08) drop-shadow(0 0 8px rgba(230,161,92,0.85)) drop-shadow(0 12px 10px rgba(0,0,0,0.4)); z-index: 20; }
.mahjong-tile.lifted.interactive:hover { transform: translateY(-16px) rotate(-1deg); }
```

- [ ] **Step 7: Wire the container in `GameTable` (`Game.tsx`)**

Add imports near the existing `./` imports (after line 16, `import { orderTableActions } ...`):

```tsx
import { loadDiscardMode } from './discardMode';
import { resolveHandTileClick } from './handTileClick';
import { tileIdsEqual } from '../../table/meldOrdering';
```

Inside `GameTable`, next to the other `useState` calls (near line 75-76), add the state:

```tsx
    const [discardMode, setDiscardMode] = useState(loadDiscardMode);
    const [liftedTileId, setLiftedTileId] = useState<number | null>(null);
```

Replace the existing stable discard callback (lines 188-192) with the unified handler. It reads volatile values from a ref so the callback identity stays stable for the memoized `TileComponent`:

```tsx
    // "Can discard right now" mirrors the old canDiscardSeat gate.
    const canDiscardNow = gameState.activePlayer === mySeatId && gameState.phase === 2
        && validActions.some((action: any) => action.type === game.ActionType.ACTION_DISCARD);

    // Volatile inputs for the click handler, refreshed every render so the
    // handler below can stay a stable (memoized) reference.
    const clickStateRef = useRef({ discardMode, liftedTileId, canDiscardNow });
    clickStateRef.current = { discardMode, liftedTileId, canDiscardNow };

    // Unified hand-tile click: lift / confirm-discard / drop, per the reducer.
    const onHandTileClick = useCallback((tile: game.ITile) => {
        const { discardMode, liftedTileId, canDiscardNow } = clickStateRef.current;
        const isLifted = tileIdsEqual(tile.id, liftedTileId);
        const { kind } = resolveHandTileClick({ mode: discardMode, isLifted, canDiscard: canDiscardNow });
        if (kind === 'discard') {
            handleAction(game.ActionType.ACTION_DISCARD, tile);
            setLiftedTileId(null);
        } else if (kind === 'lift') {
            setLiftedTileId(tile.id);
        } else {
            setLiftedTileId(null); // unlift
        }
    }, [socket]);

    // Drop the lift once the lifted tile is no longer in the self hand
    // (discarded, melded, or a fresh round is dealt — tile ids repeat across
    // rounds, so this reset prevents a stale id lighting up a new tile).
    useEffect(() => {
        if (liftedTileId == null) return;
        const inHand = (myPlayer?.closedHand || []).some((t: any) => tileIdsEqual(t.id, liftedTileId))
            || tileIdsEqual(myPlayer?.drawnTileId, liftedTileId);
        if (!inHand) setLiftedTileId(null);
    }, [gameState, liftedTileId, myPlayer]);
```

Then update the `<TableBoard>` props (lines 449-453) — remove the `canDiscardSeat={...}` block and the `onDiscard={onDiscard}` line, and add:

```tsx
                        liftedTileId={liftedTileId}
                        onHandTileClick={onHandTileClick}
```

Leave `isWildTile`, `animateDiscardTileIds`, and `callableDiscard` as they are.

> Note: `setDiscardMode` is currently unused (Task 4 adds its consumer). That is fine within this task; `Game.tsx` starts with `// @ts-nocheck`, so an unused setter will not fail the build. If you prefer a clean intermediate, you may add the settings button in Task 4 immediately after.

- [ ] **Step 8: Verify existing tests still pass and the build type-checks**

Run: `npm test`
Expected: PASS (all existing suites plus Tasks 1-2 suites; no test imports the renamed props).

Run: `npx tsc --noEmit`
Expected: no errors. (`Game.tsx` is `// @ts-nocheck`; the strictly-typed table files must compile with the new prop names.)

- [ ] **Step 9: Manual smoke check**

Start the frontend (`npm run dev`) against a running backend, join/observe a match, and confirm:
- On your turn, **double mode** (default): first tap raises a tile (brass glow), second tap on that same tile discards it; tapping a different tile moves the lift.
- Off-turn: tapping your own tiles raises/lowers them; no discard is sent.
- A tile lifted while waiting stays raised when your turn begins (carry-over); one tap discards it.
- Opponent hands are not clickable.

- [ ] **Step 10: Commit**

```bash
git add web/src/table/Tile.tsx web/src/table/seat/ClosedHand.tsx web/src/table/seat/SeatBundle.tsx web/src/table/seat/PlayerSeat.tsx web/src/table/TableScene.tsx web/src/table/table-theme.css web/src/features/game/Game.tsx
git commit -m "feat(web): tap-to-lift discard + off-turn tile lifting"
```

---

### Task 4: Settings popup to switch discard mode

Floating ⚙ control at top-left opening a `GameDialog` with the single/double toggle, mirroring `ExitMatchButton.tsx`.

**Files:**
- Create: `web/src/features/game/GameSettingsButton.tsx`
- Modify: `web/src/features/game/Game.tsx`
- Modify: `web/src/table/table-theme.css`

**Interfaces:**
- Consumes: `DiscardMode` from `./discardMode`; `GameDialog` from `../../theme`; `discardMode` state + `setDiscardMode`/`saveDiscardMode` in `GameTable`.
- Produces: `GameSettingsButton` default export with props `{ mode: DiscardMode; onChange: (mode: DiscardMode) => void }`.

- [ ] **Step 1: Create the settings button component**

Create `web/src/features/game/GameSettingsButton.tsx`:

```tsx
import { useState } from 'react'
import { GameDialog } from '../../theme'
import type { DiscardMode } from './discardMode'

type Props = {
  mode: DiscardMode
  onChange: (mode: DiscardMode) => void
}

const OPTIONS: { value: DiscardMode; title: string; desc: string }[] = [
  { value: 'single', title: 'Single-click', desc: 'Instant discard on tap' },
  { value: 'double', title: 'Double-click', desc: 'Tap to lift, tap again to confirm' },
]

// Top-left gear control for the in-play table. Opens a settings dialog whose
// only option (for now) is the discard interaction mode.
export default function GameSettingsButton({ mode, onChange }: Props) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="table-settings-control"
        aria-label="Settings"
        style={{ top: 'calc(env(safe-area-inset-top, 0px) + 1rem)' }}
      >
        ⚙
      </button>

      {open && (
        <GameDialog
          eyebrow="Table preferences"
          title="Settings"
          onCancel={() => setOpen(false)}
          actions={
            <button type="button" onClick={() => setOpen(false)} className="ldg-btn ldg-btn--primary">
              Done
            </button>
          }
        >
          <div className="settings-field">
            <div className="settings-field__label">Discard</div>
            <div className="settings-choice">
              {OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  className={`settings-choice__option ${mode === opt.value ? 'is-active' : ''}`}
                  onClick={() => onChange(opt.value)}
                >
                  <span className="settings-choice__title">{opt.title}</span>
                  <span className="settings-choice__desc">{opt.desc}</span>
                </button>
              ))}
            </div>
          </div>
        </GameDialog>
      )}
    </>
  )
}
```

- [ ] **Step 2: Style the gear control and choice options**

In `web/src/table/table-theme.css`, after the `.table-exit-control:hover` rule (line 206), add:

```css
.table-settings-control {
  position: absolute;
  left: 1rem;
  top: 1rem;
  z-index: 40;
  width: 2.1rem;
  height: 2.1rem;
  display: grid;
  place-items: center;
  color: var(--on-dark-2);
  background: rgba(11,20,24,0.7);
  border: 1px solid rgba(210,168,95,0.2);
  border-radius: 9px 9px 9px 3px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.26);
  font-size: 1rem;
  cursor: pointer;
}
.table-settings-control:hover { color: var(--brass-light); border-color: rgba(210,168,95,0.42); }

.settings-field { display: flex; flex-direction: column; gap: 0.5rem; }
.settings-field__label {
  font-family: var(--mono);
  font-size: 0.62rem;
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--on-dark-2);
}
.settings-choice { display: flex; gap: 0.6rem; }
.settings-choice__option {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.6rem 0.7rem;
  text-align: left;
  color: var(--on-dark-2);
  background: rgba(11,20,24,0.5);
  border: 1px solid rgba(210,168,95,0.2);
  border-radius: 8px;
  cursor: pointer;
}
.settings-choice__option.is-active {
  color: var(--brass-light);
  border-color: rgba(210,168,95,0.7);
  background: rgba(210,168,95,0.12);
}
.settings-choice__title { font-weight: 600; font-size: 0.85rem; }
.settings-choice__desc { font-size: 0.7rem; opacity: 0.8; }
```

- [ ] **Step 3: Mount the button in `GameTable` and wire it to state**

In `web/src/features/game/Game.tsx`:

Add the imports (near line 11, next to `import ExitMatchButton ...`):
```tsx
import GameSettingsButton from './GameSettingsButton';
import { saveDiscardMode } from './discardMode';
```
(`loadDiscardMode` is already imported from Task 3; extend that import to include `saveDiscardMode`, or add the line above.)

In the return block, next to the `ExitMatchButton` render (lines 413-415), add the settings button. It shows whenever the match is not over (not gated on `roomId`):
```tsx
            {gameState?.phase !== 5 && (
                <GameSettingsButton
                    mode={discardMode}
                    onChange={(m) => { setDiscardMode(m); saveDiscardMode(m); }}
                />
            )}
```

- [ ] **Step 4: Verify build and existing tests**

Run: `npm test`
Expected: PASS (unchanged suites).

Run: `npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Manual smoke check**

With the frontend running: click the ⚙ (top-left), switch to **Single-click**, close the dialog, and confirm on your turn a single tap discards immediately. Reload the page and confirm the choice persisted (still single). Switch back to **Double-click** and confirm the lift/confirm flow returns. Confirm the active option is visually highlighted.

- [ ] **Step 6: Commit**

```bash
git add web/src/features/game/GameSettingsButton.tsx web/src/features/game/Game.tsx web/src/table/table-theme.css
git commit -m "feat(web): in-game settings popup to switch discard mode"
```

---

## Self-Review Notes (author checklist — already reconciled)

- **Spec coverage:** persistence + default double (Task 1); state machine incl. carry-over & off-turn lift (Task 2 + Task 3 handler/effect); turn-independent self interactivity + prop thread + `.lifted` visual (Task 3); settings popup at top-left (Task 4). All spec sections map to a task.
- **No backend/proto/`/calc`/replay changes** — confirmed; only `web/` table + game files touched.
- **Type consistency:** the prop trio `interactive` / `liftedTileId` / `onHandTileClick` is named identically across `ClosedHand`, `SeatBundle`, `PlayerSeat`, `TableBoard`; `TileComponent` uses `isLifted` + `onTileClick`; reducer input is `{ mode, isLifted, canDiscard }` everywhere.
- **Tile id comparison** uses `tileIdsEqual` (string/null-safe) in every hop, not `===`.
