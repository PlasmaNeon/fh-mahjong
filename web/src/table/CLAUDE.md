# web/src/table/

> The shared tabletop presenter. Live play and replay adapt their state into these view models;
> neither keeps its own seat, discard, meld, flower, or result markup.

Preview changes on `/tools/table-sample` and `/tools/round-result` (`features/dev/`).

## Key files

- **TableBoard.tsx** — composes the center HUD, action-bar slot, four discard zones, and four
  seat bundles. `getSeatDirection()` is the single seat → view-direction mapping. Re-exports
  `TileComponent` and the view types. `handTileChoice` turns the self rail into a call picker
  (eligible tiles rise, the first pick gets the brass edge, others dim); game flow resolves the
  candidates.
- **CenterHud.tsx** — seat names, winds, scores, round/wall chips, and the wild-indicator plaque.
- **Tile.tsx** — `TileComponent`, the single tile renderer; wild/no-glow/interactive state is
  expressed as classes so the skins own shadows and emphasis.
- **tileFlight.tsx**, **tileFlightPlan.ts** — the table-level flying-tile overlay and its pure
  planner. Both tile renderers get face URLs from `getTileSvgUrl()`.
- **TableRoundResultOverlay.tsx** + **roundResult.css** — the one live/replay settlement dialog;
  calls `orderMeldsForRecap(...)` exactly once.
- **handOrdering.ts**, **meldOrdering.ts** — concealed-hand sort and meld recap order.
- **tileId.ts** — `tileIdsEqual`, tolerant of protobuf wrapper values.
- **types.ts** — the shared view models.
- **seat/** — per-seat zones; **stage/** — fixed-stage scaling.

## CSS layers

| File | Owns |
|---|---|
| `table-geometry.css` | Fixed-stage geometry, seat coordinates, compact overrides, flight positioning |
| `table-theme.css` | Visual materials (felt, HUD, call slips, tile emphasis, plaques) |
| `direct-table.css` | The final visual layer: slate-blue table, light faces, blue controls; selected tiles get a blue outline, wilds an amber edge and 搭 badge |
| `roundResult.css` | The settlement sheet |

Geometry changes need layout and flight regression checks; do not move values between geometry and
skin files casually.

## Layout rules

- **Stage.** A 1600×900 board scaled as one unit; desktop self tiles are ~10.4% of stage height.
  Keep `--tile-width`, `--tile-height`, gaps, `--bundle-span-self`, and `--action-bottom`
  coordinated; never add viewport-pixel overrides.
- **Compact stages** (phone landscape) prioritize the local hand: larger self tiles and lift,
  smaller opponent and discard tiles (26×36 discards, 24×32 opponent exposed, 28×38 local
  exposed), and side bundles raised above the self interaction band. Change tile, gap, and bundle
  tokens as one set.
- **Seat bundle.** A fixed-width box: concealed hand pinned at one end, exposed stack (flowers
  above melds) at the other, `justify-content: space-between`. The hand reserves a fixed width of
  `concealedHandReserveTiles(meldCount) = max(2, 14 − 3·melds)` tiles. Content-sized hands make
  the flowers jump every turn; reserving a flat 14 pushes the first meld off the table.
- **Left/right asymmetry is intentional**: right concealed hands flow `column-reverse`, left
  `column`; right exposed rails sit above the hand, left below. Seat rotations are 0, −90, 180,
  +90 degrees.
- The drawn tile has its own slot beside the hand rail; when it merges back it goes to the draw
  side of identical tiles.
- **Discard zones** are center-HUD-relative: three rows of six, then a fourth row that extends
  sideways past 24 tiles. All four offsets derive from one HUD-gap variable. The HUD and pools
  share an upward offset to fit 30 discards and a lifted local tile (`discardClearance.test.ts`).
  The four-row budget follows the wall: 68–88 normal draws give the busiest seat ~18–23 discards.
- Meld data keeps formation order; the live `row-reverse` rail puts the first meld farthest from
  the hand, and the recap reverses it.
- Opponent exposed stacks have their own tile budget so four sideways kans plus a pair fit.

## Motion rules

- Do not stack an explicit `x/y` entrance on a node that owns a `layoutId`; put entrance accents
  on a wrapper. Prefer `layout="position"` for shared moves.
- Moves that still look wrong (hand/drawn → discard, drawn → hand) use the flying-tile overlay,
  which snapshots rects across renders and hides the destination while airborne.
- **Redacted opponents.** Their concealed tiles carry fake ids that change every broadcast, so
  `ClosedHand` keys backs by slot, and flights are positional: a tedashi departs from a random
  hand slot and blanks it (`hideHandSlot`), then the drawn back slides into the gap or, after a
  call, the hand collapses left. `lastDiscardFromDrawn` picks tedashi vs tsumogiri. Never match
  redacted tiles by id across frames.
- **Phone portrait** rotates the board 90° with `.stage-rotator`
  (`(pointer: coarse) and (orientation: portrait) and (max-width: 600px)`). Flights then portal
  into a wrapper with the same transform and map rects through `toRotatorLocalRect`; suspect that
  mapping if a portrait flight looks wrong.

## Round result

- Keep `.round-result-actions` outside `.round-result-scroll` so Ready/Exit stay reachable; short
  rotated phones must fit without body scrolling. Size from the overlay container, never from the
  scaled stage variables.
- The payout strip stays four equal columns (one line per seat on short phones); no 2×2 grid, no
  split body, no visible `Payouts` heading.

## Replay annotations

`PlayerTableView.reviewAnnotations` (keyed by physical tile id: probability, actual/best flags,
risk) and `TileLike.called` / `fromDrawn` are presentation-only and absent in live play. They
attach to existing wrappers without changing reserved widths or anchors. Replay owns their
styling. `RoundResultBreakdownEntry.patternId` provides stable settlement keys.
