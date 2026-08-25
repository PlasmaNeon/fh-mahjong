# Discard modes (single vs. double-click) + off-turn tile lifting

**Date:** 2026-07-16
**Status:** Design approved, pending implementation plan
**Scope:** Frontend only (`web/`). No backend, proto, or rules-engine changes.

## Problem

Discarding a tile is currently a single, unconfirmed click. On your turn, a
hand tile is `interactive` and one click immediately sends `ACTION_DISCARD`
([`web/src/table/Tile.tsx`](../../web/src/table/Tile.tsx),
[`web/src/features/game/Game.tsx`](../../web/src/features/game/Game.tsx)
`onDiscard`). A misclick discards the wrong tile with no recovery.

Two related asks:

1. **Double-click discard mode** — a confirmation step so an accidental tap
   does not discard. Modeled as *tap to lift, tap the lifted tile again to
   confirm* (the classic mahjong "select then confirm" feel), **not** a
   timing-based double-click.
2. **Off-turn tile lifting** — a player can click their own hand tiles to
   "lift" (raise) them even when it is not their turn, as a planning aid.

Single-click mode must remain available, chosen via a **settings popup**.

## Decisions (from brainstorming)

- Interaction model: **tap-to-lift, tap-again-to-confirm** (no timing window).
- Default mode for players who never open settings: **double-click**.
- Setting persists **per-browser in `localStorage`**.
- Lift **carries over** into your turn: a tile lifted while waiting stays
  raised, so a single confirming tap discards it once your turn begins.
- Settings gear at **top-left** (Exit stays top-right).

## Architecture

Chosen approach: **the container owns the state machine.** `GameTable`
(`web/src/features/game/Game.tsx`) owns `liftedTileId` and `discardMode`.
`TileComponent` becomes a dumb button: it emits "this tile was clicked" and
renders an `isLifted` flag. All lift/discard decision logic lives in one place,
which trivially enforces "at most one tile lifted" and "clear lift on discard."

Rejected alternatives:

- *Tiles own their own lift/dblclick state* — scatters the state machine across
  memoized tiles; "only one lifted" and "reset on discard" become awkward.
- *Global settings context + lift hook* — YAGNI; only the live table consumes
  this, so a context adds indirection with no second consumer.

### Components

| Unit | Responsibility | Depends on |
|---|---|---|
| `discardMode.ts` (new) | `DiscardMode` type + `loadDiscardMode()` / `saveDiscardMode()` over `localStorage`; validates stored value, defaults to `'double'`. | `localStorage` |
| `handTileClick.ts` (new) | Pure `resolveHandTileClick(input) => Action` reducer encoding the click state machine. No React, no side effects. | — |
| `GameSettingsButton.tsx` (new) | Floating ⚙ gear (top-left) opening a `GameDialog` with the discard-mode toggle. | `theme` `GameDialog`, `discardMode` props |
| `GameTable` (edit, `Game.tsx`) | Owns `discardMode` + `liftedTileId` state; wires `onHandTileClick` from the reducer; renders the settings button. | above |
| `TileComponent` (edit, `Tile.tsx`) | Dumb: renders `isLifted`, emits `onClick(tile)`; `isInteractive` now means "self-hand tile" (turn-independent). | — |
| `TableScene` / `PlayerSeat` / `SeatBundle` / `ClosedHand` (edit) | Thread `onHandTileClick` + `liftedTileId` instead of `onDiscard`; make self-hand interactivity turn-independent. | — |

## The click state machine

`TileComponent` for the **self** hand is always interactive (clickable +
hover-raise), regardless of turn. Opponent hands stay non-interactive. On a
self-hand tile click, `resolveHandTileClick` returns one of
`{ discard, lift, unlift }` (every self-hand click resolves to exactly one;
opponent tiles are non-interactive and never fire):

| Situation | Result |
|---|---|
| Single mode, my turn + discard valid | `discard` (today's behavior) |
| Single mode, off-turn | `lift` (toggle: if already lifted → `unlift`) |
| Double mode, tile *is* the lifted one, my turn + discard valid | `discard`, then clear lift |
| Double mode, tile *is* the lifted one, off-turn | `unlift` (drop back down) |
| Any mode, tile is *not* the lifted one | `lift` (raise/move the lift here) |

Reducer input shape:

```
resolveHandTileClick({
  tileId: number,
  mode: 'single' | 'double',
  liftedTileId: number | null,
  canDiscard: boolean,   // my turn + phase 2 + ACTION_DISCARD valid
}) => { kind: 'discard' | 'lift' | 'unlift', tileId?: number }
```

Resolution order (unambiguous):

1. `mode === 'single'` and `canDiscard` → `discard`.
2. Otherwise, if `tileId === liftedTileId`: `canDiscard` → `discard`, else → `unlift`.
3. Otherwise → `lift`.

Container mapping of the result:

- `discard` → `handleAction(ACTION_DISCARD, tile)` and `setLiftedTileId(null)`.
- `lift` → `setLiftedTileId(tileId)`.
- `unlift` → `setLiftedTileId(null)`.

### Lift lifecycle

- At most one tile is lifted (single `liftedTileId: number \| null` in
  `GameTable`).
- Tracked **by tile id**, so it survives the hand re-sort that happens when a
  tile is drawn — this is what delivers carry-over.
- Cleared on discard and on a new-round deal. A stale id that no longer matches
  any hand tile simply renders nothing lifted (safe); no explicit cleanup
  required beyond the new-round reset.

### Stable-callback note

`onHandTileClick` reads volatile values (current turn / valid actions /
`liftedTileId`) through a ref (`stateRef.current`) so the callback identity
stays stable and does not defeat `TileComponent`'s `memo`. `setLiftedTileId`
still triggers the re-render that updates the `isLifted` flag on the affected
tiles.

## Prop threading

Today `canDiscard` + `onDiscard` thread `TableScene → PlayerSeat → SeatBundle →
ClosedHand → renderHandTile → TileComponent`. Change to:

- Thread `onHandTileClick(tile)` and `liftedTileId` along the same path.
- Self-hand interactivity becomes turn-independent: the self (bottom) closed
  hand is interactive whenever it is the viewer's own hand, not only on their
  turn. Opponent hands remain non-interactive.
- The drawn-tile slot already flows through `renderHandTile`, so it is
  liftable/discardable (tsumogiri) with no extra wiring.

`Game.tsx` keeps computing "can discard now" (activePlayer == mySeat, phase 2,
`ACTION_DISCARD` in valid actions); that boolean feeds the reducer instead of
gating interactivity.

## Visual state

- New `.mahjong-tile.lifted` in `web/src/table/table-theme.css`: a persistent
  raise (comparable to the existing `.interactive:hover` `translateY(-9px)`)
  plus a subtle brass glow so an "armed" tile is distinguishable from a plain
  hover.
- Off-turn hover-raise on self-hand tiles is now active (tiles are interactive),
  signalling they are clickable to lift.

## Settings popup

`GameSettingsButton.tsx` mirrors `ExitMatchButton.tsx`:

- Floating ⚙ control, `position: absolute; left: 1rem; top: 1rem` (own CSS
  class, e.g. `.table-settings-control`, sharing the Exit control's visual
  language), `z-index` above the board.
- Opens a `GameDialog` (`theme`) titled "Settings" containing a discard-mode
  choice: **Single-click (instant discard)** vs. **Double-click (lift, then
  confirm)**, each with a one-line description. Selecting a mode calls
  `saveDiscardMode` and updates `GameTable` state immediately.
- Framed as a general settings dialog for future toggles, but ships with only
  this one option.

## Testing

- `discardMode.test.ts` — `load` returns `'double'` when unset/invalid; round-trips
  `save`→`load`; ignores malformed stored values.
- `handTileClick.test.ts` — one case per row of the state-machine table above,
  covering single/double × on-turn/off-turn × lifted/not-lifted.

Rendering the full table is not required; the reducer is pure and covers the
behavior.

## Out of scope

- No backend, proto, or rules changes (client-only interaction).
- `/calc` and replay tools are untouched.
- No settings beyond discard mode.
- No timing-based double-click.
