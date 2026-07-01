# Opponent tedashi: drawn tile slides into the gap (slot-based)

**Date:** 2026-06-30
**Status:** Design — awaiting review
**Scope:** Frontend only (`web/src/table/*`). No proto / engine / server change.

## Goal

Make an opponent's **tedashi** (discarding a tile from hand, not the just-drawn
tile) emulate the self player's choreography:

1. the discarded tile leaves an **empty space** (a gap) in the concealed hand, and
2. the **tsumo-hai** (drawn tile) slides over and **fills that gap**,

even though an opponent's tiles are face-down backs.

Tsumogiri (discarding the just-drawn tile) is out of scope — it already flies the
discard straight from the drawn slot and has no gap to fill.

## Background / root cause

Opponent discards are already animated by a public flag, not by tile id.
`PlayerState.last_discard_from_drawn` (set by the engine) tells the client
whether a seat's most recent discard was a tsumogiri. `planTileFlights` uses it:
tsumogiri → fly the discard from the drawn slot; tedashi → fly it from a random
concealed hand slot.

The tedashi branch **also tries** to slide the drawn back into the hand
([`tileFlightPlan.ts`](../../../web/src/table/tileFlightPlan.ts) lines ~156–176),
but that part is broken in production:

- Production redaction (`redactedStateForSeat`) re-randomizes the tile-id
  obfuscation map **per broadcast** (a deliberate anti-cheat: no fake id persists
  across broadcasts, so a modified client can't track a concealed tile across
  turns or de-anonymize discards).
- The merge computes `toRect = currentRects.get(drawnId)`, where `drawnId` is the
  drawn tile's id **from the previous snapshot**. Per-broadcast rotation gives
  that tile a **different** fake id in the current frame, so the lookup returns
  `undefined` and the merge flight is silently skipped.
- The existing unit test reuses the same id (`1009`) across both snapshots, so it
  passes and hid the bug — real rotation never keeps the id stable.

So today the opponent discard flies out, but the drawn tile never fills the gap.
Because id-based tracking of opponent tiles is intentionally impossible, the fix
must be **positional (hand-slot based)**.

## Key facts the design relies on

- Opponent concealed hands render as identical `back.svg` backs, keyed by **hand
  slot index** (`slot-${index}`), so the row DOM is stable across the per-broadcast
  id churn ([`ClosedHand.tsx`](../../../web/src/table/seat/ClosedHand.tsx) line ~118).
- For a normal tedashi (a discard on the turn the opponent drew), the concealed
  rail has the **same tile count** before and after: before = `closedHand − drawn`
  (drawn split into its own slot); after = `closedHand` with the drawn merged and
  the discard removed. Both equal 13 for a standard hand. So **rail slot `i`
  occupies the same screen position** before and after — positions are stable by
  index even though ids are not.
- `FloatingTile` already renders `back.svg` when an animation has `asBack: true`.

## Approach

Drive the merge by hand-slot position instead of tile id, reusing the random slot
the discard already flies from as the single "gap" location:

- The discard flies from a random previous hand slot `index` → its rect `R`.
- The drawn back flies from the previous **drawn-slot** rect → **`R`** (same gap).
- The **current** rail slot `index` is **hidden** for the flight's duration, so an
  actual empty space is visible while the back slides in; it un-hides when the
  flight completes and the settled back takes its place.

All three use the previous snapshot's rects and the slot index — no
current-frame id lookup, so per-broadcast rotation is irrelevant.

Gate the merge + gap-hide on the previous snapshot actually having a drawn tile
for that seat. A tedashi with no preceding draw (e.g. discarding after a pon)
changes the rail count and has no tsumo-hai to slide, so it keeps today's
behavior (discard flies, no gap-fill).

### Alternatives considered

- **Server slot hint** (send the discarded tile's hand index): deterministic gap
  position, but a proto+engine change for a marginal gain over a random slot when
  the tiles are identical backs. Rejected (YAGNI).
- **Per-hand id rotation** (revert part of the security commit): re-enables the
  existing id-based merge, but weakens the anti-cheat that `be044ab` deliberately
  added. Rejected.

## Components to change

All in `web/src/table/`:

1. **`tileFlightPlan.ts`**
   - `FlyingTileAnimation`: add optional `hideHandSlot?: { direction: SeatLaneDirection; index: number }`.
   - Tedashi branch: when a previous drawn tile exists, set the merge flight's
     `toRect = R` (the discard's chosen hand-slot rect) instead of
     `currentRects.get(drawnId)`, and attach `hideHandSlot: { direction, index }`.
     Remove the broken `currentRects.get(drawnId)` path.
   - The discard flight is unchanged (still flies from `R`).

2. **`tileFlight.tsx`** (`useTileFlight`)
   - Derive `hiddenHandSlots: Map<SeatLaneDirection, Set<number>>` from the active
     flights that carry `hideHandSlot`, and return it alongside `hiddenTileIds`
     and `flights`. (Existing `hiddenTileIds` behavior unchanged.)

3. **`TableScene.tsx`** (`TableBoard`) → **`PlayerSeat.tsx`** → **`SeatBundle.tsx`** →
   **`ClosedHand.tsx`**
   - Thread the per-seat hidden slot set down to `ClosedHand`.
   - In `ClosedHand`, when rendering an anonymous opponent rail, set
     `visibility: hidden` on slot `index` if it is in the hidden set. (Self and
     non-anonymous rails unaffected.)

No changes to `types.ts` beyond the `FlyingTileAnimation`/result-type additions,
and none to the engine, proto, or server.

## Data flow (opponent tedashi, one frame transition)

```
prev snapshot: rail backs [slot0..slot12] + drawn slot D    (fake ids = map M1)
tedashi broadcast (map M2): rail backs [slot0..slot12]      (discard in pond, real id)

planTileFlights (singleNewDiscard, fromDrawn=false, prev has drawn):
  index  = random(0..12)
  R      = prev.rects[handIds[index]]        // gap position
  discard flight:  fromRect = R           -> pond
  merge   flight:  fromRect = prev drawn-slot rect -> toRect = R, asBack, hideHandSlot={dir,index}

useTileFlight: hiddenHandSlots = { dir: {index} }  (while the merge flight is airborne)
ClosedHand(dir): rail slot `index` rendered visibility:hidden  -> visible gap
on flight complete: flight removed -> slot un-hides -> settled back fills the spot
```

## Testing

Unit (`tileFlightPlan.test.ts`, vitest):

- **Tedashi under rotation** (the regression): previous drawn tile id is **absent
  from `currentRects`** (models per-broadcast rotation). Assert the merge flight is
  still produced, `asBack`, `fromRect` = drawn slot, `toRect` = `R` (the discard's
  hand-slot rect), and `hideHandSlot = { direction, index }` matching the discard's
  slot. This test fails on today's code (merge skipped) and passes after the fix.
- **Tedashi with no preceding draw**: previous snapshot has hand tiles but no
  drawn tile → discard flies, no merge flight, no `hideHandSlot`.
- **Tsumogiri**: unchanged — discard flies from the drawn slot, no merge, no
  `hideHandSlot`.
- **Multi-discard resync**: unchanged — generic anchor, no merge, no `hideHandSlot`.
- **Self seat**: unchanged — tracked flight from real position, no merge/hide.

Manual (dev, `MAHJONG_DEV_REVEAL_HANDS` off so opponents are anonymized, or on to
watch with real faces): run a bot game, watch an opponent tedashi — the discard
leaves a gap and the drawn back slides in to fill it; tsumogiri still flies from
the drawn slot; the self player's choreography is unchanged.

## Risks / notes

- **Slot-position alignment**: the merge lands at `R` = the *previous* frame's
  slot-`index` rect, used as the *current* slot-`index` position. Valid because the
  rail is left-aligned with equal count before/after a drawn tedashi. Guard
  `index` against the current rail length defensively; if counts ever differ, fall
  back to no merge (discard-only), never a mis-placed slide.
- Identical backs mean the exact gap slot is cosmetic; a random slot reads
  correctly. No attempt is made to reveal the true discarded position (it's
  concealed by design).
- Purely additive to the flight overlay; the self path and the discard flight are
  untouched.
