# Seat Bundle — Pinned Corners — Design

**Date:** 2026-06-04
**Status:** Approved (pending implementation plan)
**Refines:** `2026-06-04-seat-bundle-rotation-design.md` (the canonical rotated bundle stays; this only changes how the bundle distributes its content internally).

## Problem

The current bundle is **centered** on each edge with a constant 18–42px hand↔meld gap. Two issues:

1. A four-kong meld block forced the whole bundle to re-center, so the **closed hand slides** as melds grow.
2. Keeping the bundle within the 800px side edges at four kongs required compromises (hand-shift, then centering) that move the hand.

## Goal & invariant

Pin the two outer corners of the bundle so the layout is bounded and stable:

- **Invariant (core requirement):** the **first (leftmost) tile of the closed hand** and the **rightmost (first-formed) open meld** never change position as the meld count changes. Only the gap between hand and melds changes.
- The bundle never overflows the table edge, even at the maximum (**four kongs**).
- Left/right/top stay exactly symmetric (single canonical bundle + rotation, unchanged).

## Design

The bundle becomes a **fixed-width box** (the *span*), centered on each edge. Inside, `justify-content: space-between` pins:

- the **closed hand to the box's bottom-left** (hand tiles left-aligned, so the first tile sits at the box's left edge), and
- the **exposed stack (flowers above melds) to the box's bottom-right**, with the melds right-aligned so the **first-formed meld's outer corner sits at the box's right edge**.

The leftover space between them is the gap. As the hand or melds grow, they fill inward and the gap shrinks; the two pinned edges do not move.

```
|<------------------ span (fixed) ------------------>|
[ hand: first tile … ] ———— gap ———— [ … melds : first-formed ]
^ pinned bottom-left                       pinned bottom-right ^
```

### Meld growth (satisfies the invariant)

- Melds are rendered first-formed → newest with the meld row right-aligned and growing leftward (the existing `row-reverse` + formation order). New melds extend into the gap (left); the rightmost (first-formed) stays at the box's right edge.
- The hand is left-aligned with the existing stable display order; forming a meld removes tiles from the right of the hand, so the leftmost tile stays at the box's left edge.

### Span sizing (two values, tuned in the harness)

The span must be ≥ the widest content for that seat so the hand and melds never collide in the middle:

- `--bundle-span-self` — fits the self player's widest content: a full **13–14 normal tiles** (~800px). Self is always the bottom seat (1280px-wide edge), so it fits.
- `--bundle-span-opp` — fits the opponents' widest content: **four kongs** of small tiles (~600px), plus their (small) hand. Used by top/left/right; fits the 800px side edges.

Self (normal tiles) and opponents (small tiles) never share an edge, so the two spans never coexist on one edge. Top/left/right all use `--bundle-span-opp` + the same rotation → exact symmetry.

Exact px values are measured and tuned in the `/dev/seat` harness (using kong melds for the worst case).

## Architecture / components

Unchanged from the rotation spec except `.seat-bundle` CSS:

- **`.seat-bundle`** — was content-width + `translateX(-50%)`; becomes **fixed `width: var(--bundle-span-…)`**, `display: flex`, `justify-content: space-between`, `align-items: flex-end`, still centered via `translateX(-50%)`. The width var is chosen by an `is-self` modifier class (e.g. `.seat-bundle--self` vs `.seat-bundle--opp`) set by `SeatBundle` from its `isSelf` prop.
- **`.seat-bundle__exposed`** — unchanged (column, `align-items: flex-end`, flowers above melds).
- **`.seat-bundle .zone-melds`** — unchanged (`row-reverse`, right-aligned → first-formed at the outer/right corner).
- `SeatBundle.tsx` — add the `--self`/`--opp` modifier class to the `.seat-bundle` element based on `isSelf`.
- Pivot rotation, `PlayerSeat`, `ClosedHand`/`OpenMelds`/`FlowerZone`, discards — all unchanged.

## Edge cases

- **0 melds:** exposed not rendered; with `space-between` and a single child, the hand sits at the box's left edge (first tile pinned). The right portion is empty.
- **Full hand, 0 melds (self, ~13–14 normal tiles):** fills most of `--bundle-span-self`; must not exceed it (size the span to the full hand).
- **Four kongs:** widest meld block; hand is then ~1 tile. Content ≤ span, so a (shrunken) gap remains and nothing collides or overflows.
- **Content wider than span (mis-sized span):** would collide in the middle — prevented by sizing the span to the measured worst case; verify at both 0 melds and 4 kongs.
- **What "fixed" means:** the pinned *anchors* (hand left edge, meld right edge) don't move. Tile identities still reflow within the hand via the existing stable display order when a meld removes tiles — the anchor position is what stays put, not a specific tile glued in place.

## Testing / verification

- **Unit:** `meldOrdering`/`handOrdering` tests unchanged (still pass).
- **Visual (harness `/dev/seat`, kong melds):**
  - the first hand tile's screen position and the rightmost meld's screen position are **identical** across 0→4 melds on every seat (the invariant);
  - nothing overflows the table at 0 melds (full hand) or 4 kongs;
  - left/right/top remain exact rotations of each other;
  - the gap shrinks as melds grow.
- **Regression:** `FloatingTile` draw/discard still fires; shanten indicator on self; round-result overlay renders; `tsc` + build clean.

## Files touched

- **Edit:** `web/src/index.css` (`.seat-bundle` → fixed-span `space-between`; add `--bundle-span-self` / `--bundle-span-opp`; remove the centered-bundle comment/behavior).
- **Edit:** `web/src/table/seat/SeatBundle.tsx` (add `--self`/`--opp` modifier class from `isSelf`).
