# Seat Bundle (Rotation-Based) — Design

**Date:** 2026-06-04
**Status:** Approved (pending implementation plan)
**Supersedes:** the per-direction zone placement in `2026-06-04-modular-seat-layout-design.md` (the component split and pure helpers from that spec stay; only the per-direction CSS placement is replaced).

## Problem

Each player's hand / open melds / flowers are positioned by **per-direction CSS** (`.zone-hand--left` vs `--right`, `.zone-melds--left` vs `--right`, etc.). Maintaining four hand-written, mirrored rule sets is error-prone: the left and right seats have drifted out of symmetry and read as buggy. There is no single source of truth for the relative arrangement of the three zones.

## Goal

Bind the closed hand, open melds, and flower rail into **one canonical bundle** with a fixed internal layout (gaps as parameters), then place each seat's bundle with a single rigid **rotation + translation**. Because every seat renders the *identical* bundle and only the wrapper transform differs, **left/right symmetry is guaranteed by construction** — there is no per-direction layout CSS left to drift.

## Non-Goals

- Discards are **not** part of the bundle. `DiscardZone` stays separate and unchanged (it is positioned around the center).
- No change to the round-result overlay (keeps its own `pov-bottom` meld rendering).
- No change to game state, props from `Game.tsx`, scoring, the center HUD, or the `FloatingTile` draw/discard animation system (it reads `data-board-tile-id` rects in screen space; those attributes are preserved).
- The component split (`ClosedHand` / `OpenMelds` / `FlowerZone` / `meldOrdering` / `handOrdering`) and Vitest tests from the prior spec remain.

## Canonical bundle layout

The bundle is defined once, in the bottom-player orientation, tiles upright:

```
              [ flowers ]                  ← above the melds, --bundle-flower-meld-gap
[ closed hand ] —gap— [ melds ]           ← shared bottom baseline
                       ^ --bundle-hand-meld-gap
```

- **Hand** on the inner side (nearest the player edge), horizontal row.
- **Melds** to the hand's right, at `--bundle-hand-meld-gap`. Hand bottom = meld bottom (baseline-aligned).
- **Melds order:** the **first-formed meld is at the outer end** (far from the hand); reading inward toward the hand are later melds, with the newest nearest the hand. The hand→meld gap is the fixed bundle param, so a new meld appears at the inner end (at the gap) and the existing block shifts outward by one slot — i.e. with a fixed gap and first-formed-outer, the prior melds are *not* pinned (you can't have fixed-gap + first-formed-outer + existing-never-move at once; the user chose fixed-gap + first-formed-outer). The new meld animates in (fade+scale, transform-based).
- **Flowers** sit above the meld block at `--bundle-flower-meld-gap`, aligned to the meld block.

The bundle knows nothing about `direction`. Its size depends only on its content (self = `normal` tiles, opponents = `small` tiles).

## Placement & rotation

Each bundle is wrapped by `PlayerSeat` in a positioning wrapper:

- The bundle has a **player anchor** = the bottom-center of the hand (where that player sits).
- The wrapper places the player anchor at the **midpoint of that player's table edge**, offset inward by `--bundle-edge-offset`, and rotates the bundle by **θ about that anchor**:
  - bottom θ = 0°, left θ = 90°, top θ = 180°, right θ = −90° (the existing `getTileRotation(direction)` values).
- Result: the hand always lies along the player's edge, melds to *their* right, flowers toward center — automatically and identically for all four seats. Exact `transform` / `transform-origin` / translate are worked out during implementation and confirmed in the harness; the invariant to verify is that the four bundles are exact rotations of one another.

## Tile rendering

- Inside the bundle, tiles render in **canonical orientation** — always the `pov-bottom`/upright form, **no** `pov-left/right/top` per-tile rotation. The bundle's wrapper rotation provides the orientation.
- Tile **size/face stays per-seat**: self → `normal`, face-up, interactive; opponents → `small`, backs (`handBackCount`). This is driven by the existing `player.showClosedHand` / self-seat checks, not by `direction`.
- `data-board-tile-id` / `data-board-tile-role` attributes are preserved on hand/discard tiles so `FloatingTile` keeps working.

## Architecture / components (`web/src/table/seat/`)

- **New `SeatBundle.tsx`** — renders the canonical bundle: `ClosedHand` + an exposed stack (`FlowerZone` above `OpenMeldZone`), in the fixed canonical flex layout. No direction logic; no positioning.
- **`PlayerSeat.tsx`** — becomes the placement wrapper: renders `DiscardZone` (separate) + a `.seat-bundle-wrap--{dir}` wrapper around `<SeatBundle>` that applies the per-seat rotate + translate.
- **`ClosedHand.tsx`** — simplified to canonical rendering: tiles always `pov-bottom`-style (drop the `pov-${direction}` class and the per-direction drawn-offset; keep size = self `normal` / opponents `small`, the stable display order, the drawn slot, the shanten indicator).
- **`OpenMelds.tsx`** — canonical meld groups (always `seat-meld-group--bottom`-style, `pov-bottom`); `orderMelds` returns formation order; rendering places first-formed at the outer end (handled by the bundle's flex direction). Keeps the motion entrance + stable keys.
- **`FlowerZone.tsx`** — canonical flower row.
- **`OpenMeldZone.tsx`** — thin wrapper (may be folded into the exposed stack in `SeatBundle`).
- **`DiscardZone.tsx`** — unchanged.
- **`meldOrdering.ts` / `handOrdering.ts`** — unchanged (pure helpers).

## CSS

- Remove the per-direction `.zone-hand--{dir}` / `.zone-melds--{dir}` / `.zone-flowers--{dir}` placement rules.
- Add: `.seat-bundle` (canonical flex layout with `--bundle-hand-meld-gap`, `--bundle-flower-meld-gap`) and `.seat-bundle-wrap--{dir}` (one positioned + rotated rule per seat; the *only* per-direction rules, and each is a pure rotation/placement, not a layout).
- Keep tile size/`mahjong-tile`/`mahjong-tile-back`/`seat-meld-group`/`stolen-tile` rules. Keep `pov-bottom` sizing (used canonically).

## Edge cases

- **0 melds / 0 flowers:** exposed stack renders nothing; bundle is just the hand.
- **Many melds (4):** the meld block extends outward from the hand; the bundle must stay within the table after rotation — verify at 4 melds on every seat, especially that the left seat clears the upper-left wild-tile box.
- **Opponents (`showClosedHand === false`):** hand renders `handBackCount` small backs, canonical, rotated by the wrapper.
- **Self interactivity:** bottom seat is θ = 0°, so click-to-discard is unaffected.
- **Draw/discard animation:** for rotated (opponent) bundles, `getBoundingClientRect` returns the rotated tile's bounding box; `FloatingTile` already rotates the flying tile by `getTileRotation`, so it stays visually consistent — verify a real discard still animates acceptably.

## Testing / verification

- **Unit:** `meldOrdering` / `handOrdering` tests still pass (unchanged).
- **Visual (harness `/dev/seat`):** verify via measured rects that
  - the four bundles are exact rotations of each other (e.g. the left bundle's screen layout is the right bundle's mirrored through the center);
  - hand/meld baseline aligned, flowers above the melds, first-formed meld at the outer end;
  - toggling meld count animates only the new meld in;
  - nothing overflows the table at 4 melds; the left bundle clears the wild-tile box.
- **Regression:** `FloatingTile` draw/discard still fires; shanten indicator shows on the bottom seat; round-result overlay melds render; `tsc` + build clean.

## Files touched

- **New:** `web/src/table/seat/SeatBundle.tsx`
- **Edit:** `web/src/table/seat/PlayerSeat.tsx` (placement wrapper + rotation)
- **Edit:** `web/src/table/seat/ClosedHand.tsx` (canonical-only rendering)
- **Edit:** `web/src/table/seat/OpenMelds.tsx` (first-formed at outer end, canonical)
- **Edit:** `web/src/table/seat/FlowerZone.tsx` / `OpenMeldZone.tsx` (canonical)
- **Edit:** `web/src/index.css` (replace per-direction zone rules with `.seat-bundle` + `.seat-bundle-wrap--{dir}`)
