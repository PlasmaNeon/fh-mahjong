# Modular Seat Layout — Design

**Date:** 2026-06-04
**Status:** Approved (pending implementation plan)

## Problem

Each player's on-table presence is split across two unrelated places: a monolithic
`SeatLane` component (`web/src/table/TableScene.tsx` ~lines 441–589) renders closed hand,
flower rail, and open melds through one absolutely-positioned `seat-lane-shell` and a flex
chain (`seat-lane` → `seat-lane__closed` | `seat-lane__gap` | `seat-exposed`), while the
discard pool is rendered by a **separate** `DiscardLane` component in a different
`TableBoard` loop. There is no single "player" unit owning all of a seat's zones.

Concrete bugs and limitations:

1. **Open melds render off the table.** For the bottom (self) seat, `.seat-exposed--bottom`
   is `flex-direction: column` and lives inside the lane's absolutely-positioned box.
   With multiple melds the column grows and spills out of the bottom-left of the table
   (see the reported screenshot — melds stacked vertically, clipped off-screen).
2. **Wrong meld order.** Melds should read right-to-left with the **rightmost meld being
   the first one formed**, then each subsequent meld to its left. Today's ordering
   (`getOrderedOpenMelds`, ~line 311) only special-cases `bottom` and does not reliably
   produce that order.
3. **Not modular.** Hand / flowers / melds are entangled in one component and one CSS
   flex chain, and discards live in yet another component. There is no single per-player
   unit, and no way to adjust, test, or reposition one zone without touching the others.

## Goals

- Decompose the per-player rendering into a clear, modular hierarchy where every player
  has the same set of zones (closed hand, flowers, discards, open melds) under one
  `PlayerSeat`, and only `direction` differs.
- Each zone is an independent, direction-aware, independently-positioned module.
- Fix open melds: anchored within the table, ordered right-to-left (rightmost = first
  formed), no off-table overflow, for **all four seats** (mirrored corners).
- Reuse the pure meld rendering in the round-result overlay.

## Non-Goals

- No change to discard **positioning or behavior** — discards move into `PlayerSeat`
  structurally but keep their current layout, animations, and callable highlight.
- No change to scoring, the center HUD, or the floating-tile draw/discard
  animation system (`FloatingTile`, `useLayoutEffect` motion snapshotting). That system
  keys off `data-board-tile-id` / `data-board-tile-role` attributes, which the new
  components MUST preserve.
- No change to game state, props fed from `Game.tsx`, or the proto.

## Decisions (from brainstorming)

- **Meld anchor:** lower-right **region** per seat, **inset** from the table edges with
  comfortable margins — not jammed into the literal pixel corner (better UX). Bottom →
  bottom-right region, rightmost meld = first formed, growing left. The inset is a tunable
  CSS var dialed in during visual verification. Mirrored for the others (see below).
- **Positional stability:** the first-formed meld is pinned at the (inset) anchor and the
  zone grows inward, so when the meld count grows the **already-placed melds never move**.
- **Entrance animation:** the **newly-formed meld** animates in (fade + scale, a
  transform-based entrance so it does not reflow neighbours), while all existing melds
  stay perfectly still.
- **Hand + flowers:** full reposition — they become independent zones too (not just a
  code split), re-expressed as standalone per-direction anchors. Visual shifts are
  expected and must be verified. For the **bottom (self) seat**:
  - **Closed hand:** near table center but **offset slightly toward the side opposite the
    melds** (i.e. a little left), to balance the meld block on the right, leaving a
    reasonable gap between the hand and the meld zone.
  - **Flower zone:** sits **directly above the open melds** (on the inner/table-center
    side of the meld region), **growing right-to-left** like the melds, with a reasonable
    gap between the flowers and the melds.
  - So the lower-right region is a vertical stack: **flowers on top, melds below**, both
    right-anchored and growing left; the hand sits to the left with a gap. Other seats
    mirror this relationship (hand offset away from its meld region; flowers on the
    inner side of the melds, same growth direction).
  - Hand↔meld and flower↔meld gaps are tunable CSS vars.
- **Scope:** all four seats handled by the same components (mirrored corners).
- **Modularity:** standalone `OpenMelds` content component **and** a standalone
  `OpenMeldZone` positioned container, plus `ClosedHand` and `FlowerZone`, all composed
  by a `PlayerSeat` parent.

## Architecture

### Component hierarchy

```
TableBoard
└─ PlayerSeat            (×4 — one per direction; the only per-player thing TableBoard renders)
   ├─ ClosedHand         (hand tiles + drawn-tile slot; own anchor per direction)
   ├─ FlowerZone         (flower rail; own anchor per direction)
   ├─ DiscardZone        (discard pool; own anchor per direction)
   └─ OpenMeldZone       (positioned container; own anchor per direction — a table corner)
      └─ OpenMelds        (pure content: ordered meld groups + tiles)
```

`PlayerSeat` is a thin composition unit: it receives `{ direction, player, canDiscard,
onDiscard, isWildTile, hiddenTileIds, animateDiscardTileIds, callableDiscard }` and
renders the four zone components, passing each the slice it needs and the shared
`direction`. It resolves the per-seat callable discard tile itself
(`callableDiscard?.seat === player.seat ? callableDiscard.tileId : null`). It does not own
a positioned box; each zone positions itself, so the zones are fully decoupled.

### New / changed files (`web/src/table/`)

- **New `types.ts`** — shared `TileLike`, `MeldLike`, `PlayerTableView`,
  `SeatLaneDirection` (currently exported from `TableScene.tsx`). Avoids circular imports
  between the seat components.
- **New `Tile.tsx`** — extract the existing `TileComponent` (and the `WILD`/glow logic it
  already contains) so every zone can import it without depending on `TableScene`.
- **New `seat/PlayerSeat.tsx`** — composition described above.
- **New `seat/ClosedHand.tsx`** — moves `renderHandTile`, `computeStableDisplayOrder`
  usage, the drawn-tile slot, `displayOrderRef`/`lastDrawnTileId` refs, and the
  shanten indicator. Preserves `data-board-tile-id` / `data-board-tile-role` attributes
  and the framer-motion `layout` behavior exactly.
- **New `seat/FlowerZone.tsx`** — the flower rail, direction-aware, positioned on the
  inner side of the meld zone (for bottom: directly above the melds) and growing the same
  direction as the melds (right-to-left for bottom).
- **New `seat/DiscardZone.tsx`** — the discard pool, extracted verbatim from today's
  `DiscardLane`. **Structural move only:** keep the existing `discard-lane--{dir}` CSS,
  the new-discard entrance animation, the `layout="position"` reflow, the callable-discard
  highlight, and the `data-board-tile-id`/`data-board-tile-role="discard"` attributes
  (required by the `FloatingTile` motion system). Positions and behavior are unchanged;
  ownership moves from `TableBoard` into `PlayerSeat`.
- **New `seat/OpenMeldZone.tsx`** — absolutely-positioned, direction-aware container
  (`.zone-melds--{dir}`) wrapping `<OpenMelds>`.
- **New `seat/OpenMelds.tsx`** — pure content: maps ordered melds → meld groups → tiles,
  including the rotated "stolen"/called tile. Props: `{ melds, direction, isWildTile }`.
  No positioning. Reused by `OpenMeldZone` and the round-result overlay. Each meld group
  is a `motion.div` with a **stable key** (derived from meld identity — the called tile
  id, falling back to the first tile id — not the array index) and a transform-based
  entrance (`initial={{ opacity: 0, scale: .8 }}` → `animate={{ opacity: 1, scale: 1 }}`).
  Because melds only ever append and keys are stable, only the new meld mounts and plays
  the entrance; existing melds are untouched. The zone is anchored at the first-formed
  (inset) edge (e.g. right-anchored `flex-direction: row-reverse` for bottom) so the
  entrance (transform only) and the growth both leave existing melds visually fixed.
- **New `seat/meldOrdering.ts`** — pure, React-free helpers:
  - `orderMelds(melds, direction)` → melds in render order such that the first-formed
    meld lands on the correct (rightmost/inner) side for the direction.
  - `reorderMeldTiles(meld)` → per-meld tile order placing the called tile per
    `calledDirection` (moved verbatim from `TableScene`).
- **Edit `TableScene.tsx`** — remove `SeatLane` **and** the separate `DiscardLane` render
  loop (lines ~721–731); render a single `<PlayerSeat>` per seat (replacing lines 721–743)
  that owns hand, flowers, discards, and melds. Import shared
  types/`TileComponent`/`getSeatDirection` from the new modules (or re-export for
  compatibility). The round-result overlay (`TableRoundResultOverlay`, ~lines 813–840)
  swaps its inline meld loop for `<OpenMelds direction="bottom" … />`.
- **Z-order:** today all four `DiscardLane`s render before all four `SeatLane`s, so hands
  and melds stack above discards. Grouping every zone under `PlayerSeat` changes DOM
  order, so stacking must be made deterministic via explicit `z-index` per zone-type in
  CSS (discards lowest, then melds, then flowers/hand) rather than relying on render
  order. All four `PlayerSeat`s still render before the `FloatingTile` layer.
- **Edit `index.css`** — replace the `seat-lane-shell` / `seat-lane` / `seat-exposed`
  flex chain with per-zone, per-direction anchor rules. Keep tile/`pov-*`/`stolen-tile`
  rules. New classes: `.zone-hand--{dir}`, `.zone-flowers--{dir}`, `.zone-melds--{dir}`.

### Meld ordering & orientation

- Order rule (all seats): rightmost (or, for side seats, the edge nearest the player's
  hand) is the **first** formed meld; subsequent melds grow inward/away.
- Implementation: `orderMelds` returns the array in DOM order; the zone's CSS
  `flex-direction` per direction places index-0 at the correct end. This keeps the
  ordering logic pure and the direction handling in CSS.
- `reorderMeldTiles` keeps the existing called-tile placement and the `stolen-tile`
  rotation classes.

### Per-direction anchors

Each zone is `position: absolute` within the existing table positioning context (the
same context `seat-lane-shell` uses today). Anchors driven by CSS vars so they're tunable:

| Zone        | bottom (self)        | top                 | right                | left                 |
|-------------|----------------------|---------------------|----------------------|----------------------|
| ClosedHand  | bottom edge, near center, offset left (balances melds) | top edge, near center, offset right | right edge, near center, offset down | left edge, near center, offset up |
| FlowerZone  | above the melds, growing right-to-left | (mirrored) inner side of melds, same growth | (mirrored) inner side of melds, same growth | (mirrored) inner side of melds, same growth |
| DiscardZone | unchanged (`discard-lane--bottom`) | unchanged | unchanged | unchanged |
| OpenMeldZone| bottom-right region (inset), row growing left | top-left region (inset), row growing right | top-right region (inset), column growing down | bottom-left region (inset), column growing up |

For the bottom seat the meld region is a vertical stack — flower rail on top, melds below
— both right-anchored and growing left; the closed hand sits left-of-center with a gap to
that stack. Other seats mirror this.

**Upper-left wild-tile box clearance.** The `.wild-tile-corner` box is pinned at the
table's upper-left (`top: 1rem; left: 1rem`, z-index 30) and grows downward as info rows
appear. The **left seat's** zones must not overlap it: the closed-hand top edge starts
below the box, and the left meld stack (anchored lower-left, growing up) is clamped so its
upward growth stops short of the box. This is a hard layout constraint and a verification
item.

The discard zone keeps its existing `discard-lane--{dir}` positioning untouched. The meld
zone is inset from the table edges by a tunable `--meld-inset` (so it sits in the region,
not the literal corner) and gets a `max-width`/`max-height` clamp so it never leaves the
table. The flower zone shares the meld zone's anchor edge, offset to its inner side by a
tunable `--flower-meld-gap`. The closed hand is offset from center toward the side opposite
the melds, with a tunable `--hand-meld-gap` between hand and meld stack. Today's tuned
values (`--bottom-hand-*`, `--side-hand-*`, `--top-hand-*`) seed the starting points.

## Data Flow

```
Game.tsx playerViews (PlayerTableView[])  — unchanged
  └─ TableBoard: seatViews = players.map(p => ({ player, direction: getSeatDirection(...) }))
       └─ <PlayerSeat direction player … animateDiscardTileIds callableDiscard /> (×4)
            ├─ <ClosedHand direction tiles drawnTileId … />
            ├─ <FlowerZone direction flowers isWildTile />
            ├─ <DiscardZone direction discards animateDiscardTileIds callableDiscardTileId hiddenTileIds isWildTile />
            └─ <OpenMeldZone direction melds isWildTile />
                 └─ <OpenMelds melds={orderMelds(melds, direction)} direction isWildTile />
```

No prop or state changes flow up to `Game.tsx`; this is a presentational refactor.

## Edge Cases

- **Fewer than 4 players / missing seat:** `players` already omits absent seats; each
  `PlayerSeat` renders independently.
- **No melds / no flowers:** zones render nothing (empty container or null), occupying no
  space and not affecting other zones (they're independently positioned).
- **Many melds (4 kongs):** meld zone clamps within the table; tiles may shrink/wrap via
  the clamp rather than overflow off-table. Acceptable.
- **Left seat vs wild-tile box:** the left seat's hand top and upward-growing meld stack
  must stay clear of the upper-left `.wild-tile-corner` box (even at 4 melds). Clamp the
  left meld stack's top so it never reaches the box.
- **Hidden tiles (overlay animations):** `hiddenTileIds` still flows to `ClosedHand`;
  `data-board-tile-id` attributes preserved so `FloatingTile` motion keeps working.
- **`showClosedHand === false` (opponents):** `ClosedHand` renders tile backs by
  `handBackCount`, exactly as today.

## Testing / Verification

- **Unit:** `meldOrdering.ts` — `orderMelds` and `reorderMeldTiles` are pure; add tests
  (e.g. Vitest) covering ordering per direction and called-tile placement per
  `calledDirection`.
- **Visual (dev harness):** a live 4-player game needs the Go backend, so add a dev-only
  preview that mounts all four `PlayerSeat`s with mock data (hand of N tiles, 1–2 flowers,
  2–3 melds incl. a called tile). Verify in the browser preview for each direction:
  - bottom hand sits near center but offset left, balancing the melds, with a clear gap
    to the meld stack;
  - flowers sit directly above the melds, growing right-to-left, with a clear gap;
  - melds sit in the correct inset region (not jammed in the literal corner), rightmost =
    first formed, none off-table;
  - adding a meld to the mock data leaves existing melds fixed and animates only the
    new one in;
  - tile-back rendering for opponents; stolen-tile rotation correct;
  - the left seat's hand and meld stack (test with 4 melds) clear the upper-left
    wild-tile box.
  Remove the harness (or gate it behind a dev-only route) before finishing.
- **Regression:** confirm draw/discard `FloatingTile` animation still fires (relies on
  `data-board-tile-id`/`-role`), discards still animate in / highlight when callable and
  stack beneath hands+melds (z-order), shanten indicator still shows for the bottom seat,
  and the round-result overlay melds render via the shared `OpenMelds`.
- Confirm no TypeScript errors after the type extraction.

## Files Touched

- **New:** `web/src/table/types.ts`
- **New:** `web/src/table/Tile.tsx`
- **New:** `web/src/table/seat/PlayerSeat.tsx`
- **New:** `web/src/table/seat/ClosedHand.tsx`
- **New:** `web/src/table/seat/FlowerZone.tsx`
- **New:** `web/src/table/seat/DiscardZone.tsx`
- **New:** `web/src/table/seat/OpenMeldZone.tsx`
- **New:** `web/src/table/seat/OpenMelds.tsx`
- **New:** `web/src/table/seat/meldOrdering.ts`
- **New:** `web/src/table/seat/meldOrdering.test.ts` (unit tests)
- **Edit:** `web/src/table/TableScene.tsx` (remove `SeatLane` and `DiscardLane`, render `PlayerSeat`, reuse `OpenMelds` in the overlay, import from new modules)
- **Edit:** `web/src/index.css` (replace seat-lane flex chain with per-zone anchor rules; add per-zone `z-index` layering)
