# Tedashi / Tsumogiri Discard Animation (Redacted Opponents) — Design

**Date:** 2026-06-28
**Status:** Approved, ready for implementation planning

## Problem

In production ("release mode"), an opponent's discard animation cannot convey
whether the player did **tedashi** (discarded a tile already in hand) or
**tsumogiri** (discarded the tile they just drew). Both render identically: the
discard flies from a single generic hand-region anchor, and there is no visual
of the drawn tile filling the vacated slot.

This is public information in real mahjong (everyone sees *that* you discarded
the drawn tile vs a hand tile), so conveying it is correct. What must **not**
leak is the *true position* of a tedashi tile within the concealed hand — from
an opponent's view it should appear to come from a random place in the hand.

### Why the distinction is currently lost

"Release mode" is the production redaction path in
`Room.BroadcastState()` (`api/room.go`), gated on `isProd`
(`os.Getenv("ZEABUR") != ""`). For each opponent the broadcast replaces every
concealed tile via a per-match `TileObfuscationMap` (real id → stable fake id,
`Suit_UNKNOWN`, `Value 0`, rendered as backs). The obfuscated `DrawnTileId` is
still sent, so the frontend already renders a **separated "drawn" back** for
redacted opponents.

The frontend flight planner (`web/src/table/tileFlightPlan.ts`) tracks tiles by
id across renders. Once discarded, a tile becomes **public with its real id**,
while the opponent's hand tiles carried **fake ids**. The planner cannot bridge
fake → real, so every opponent discard falls into the "no tracked source"
branch and flies from a generic `handOrigins` anchor — tedashi and tsumogiri
become indistinguishable, and the drawn tile never visibly merges back.

The engine already knows the answer: at the discard handler in `core/game.go`,
just before `DrawnTileId` is cleared, `tsumogiri == (*DrawnTileId == discard.Id)`.
It simply isn't exposed.

## Goal

For **redacted (production) opponents only**, animate discards as:

- **Tsumogiri** — the separated drawn back flies to the discard pile; the rail
  of backs is unchanged.
- **Tedashi** — a back flies from a **random** rail slot to the discard pile,
  and the separated drawn back **slides into that vacated slot** so the hand
  re-closes.

## Scope boundary

Only the redacted-opponent path changes. The self seat and any full-info view
(local dev with real tiles, replays) already animate from the true source via
id tracking and intentionally keep showing the real position (debug views). The
new behavior lives entirely in the planner's existing "no tracked source"
branch, which fires only for fake-id (redacted) opponents — so full-info views
are untouched by construction.

## Design

### 1. Backend — one public boolean

**Proto** (`proto/game.proto`, `GameState`, next free field number 24):

```proto
// True when active_discard was the discarder's just-drawn tile (tsumogiri).
// Public info — reveals nothing about concealed tiles. Transient: valid only
// while active_discard is set.
bool active_discard_from_drawn = 24;
```

**Engine** (`core/game.go`, `ACTION_DISCARD` handling, ~line 727): compute the
flag from `DrawnTileId` *before* it is cleared, and keep it in lockstep with
`ActiveDiscard`:

```go
g.State.ActiveDiscardFromDrawn =
    player.DrawnTileId != nil && *player.DrawnTileId == int32(action.Tile.Id)
g.State.ActiveDiscard = action.Tile
```

Reset `ActiveDiscardFromDrawn = false` at every site that sets
`ActiveDiscard = nil` (the discard-clear points around lines 805 / 1004 / 1015 /
1067 / 1111) so the flag never outlives the discard it describes.

The field is set on the master state and rides through `proto.Clone` into the
redacted broadcast for free — no change to the redaction block, because it
leaks nothing beyond what is already public.

Post-call discards (Chii/Pon then discard, no draw) have `DrawnTileId == nil` →
flag false → tedashi, which is correct (you can never tsumogiri without drawing).

**No discarder-seat field is needed.** Tile ids are unique per match, so the
frontend resolves the discarder as the seat whose last discard id equals
`active_discard.id`.

### 2. Frontend — drive the flight from the flag

Plumb `activeDiscardFromDrawn` from `gameState` into flight planning
(`web/src/pages/Game.tsx` view assembly → `tileFlight` / `tileFlightPlan`).

In `planTileFlights` (`web/src/table/tileFlightPlan.ts`), the "newly revealed
discard, no tracked source" branch (`currentTile.role === 'discard'`, no
`previousTile`) becomes:

1. Resolve the discarder's **direction** (the seat whose last discard ==
   `active_discard`); read that seat's per-tile rects from the **previous
   snapshot**, which already captures opponent rects by fake id + role
   (`'drawn'` and `'hand'`).
2. **Tsumogiri** (`fromDrawn === true`): origin = that seat's `role:'drawn'`
   rect (instead of the generic hand-origin anchor).
3. **Tedashi** (`fromDrawn === false`): origin = a **randomly chosen**
   `role:'hand'` rect for that seat; **and** emit a second flight rendering a
   **face-down back** from the `'drawn'` rect → the chosen rail slot rect (the
   "tsumo-hai fills the gap").

Supporting changes:

- The flight descriptor / `FloatingTile` (`web/src/table/tileFlight.tsx`) gains
  an `asBack` flag so the merge flight renders `back.svg` instead of the tile
  face.
- **Fallback:** if the `'drawn'` / `'hand'` rects are unavailable for any
  reason, fall back to today's generic hand-origin anchor — no regression.

The random rail slot is captured once at plan time (stable for that flight);
each discard re-randomizes. The rail re-renders as N identical backs, so the
merge flight overlaying the final rail is visually seamless (all backs are
identical).

### 3. Testing

- **Go:** discard-handler unit test — tsumogiri sets `ActiveDiscardFromDrawn`
  true; tedashi and post-call discard set it false; the flag clears wherever
  `ActiveDiscard` clears. Plus `go test ./...`.
- **Frontend:** extend `tileFlightPlan` tests — for a redacted-opponent discard
  with `fromDrawn` true vs false, assert the chosen origin (drawn-slot rect vs a
  hand-slot rect) and that tedashi emits the extra `asBack` merge flight.
- **Manual:** existing Vite harness pattern with a redacted-opponent fixture;
  eyeball both cases.

## Out of scope (separate follow-up)

The `TileObfuscationMap` is fixed for the whole match (`api/room.go`, built once
in `NewRoom` via `rand.Perm(144)`). Because it never rotates and every discard
reveals one real↔fake pairing, an opponent's client can gradually de-anonymize
the map and read tiles still in hand. This is the same "don't leak concealed
positions" concern one layer down, but it is a distinct fix and is tracked
separately. The design above deliberately does **not** depend on the
obfuscation map being stable (the signal comes from the backend boolean), so
fixing the leak later will not break this feature.

## Proto regeneration

After editing `proto/game.proto`:

```bash
protoc --go_out=. --go_opt=paths=source_relative proto/game.proto
web/node_modules/.bin/pbjs -t static-module -w es6 --null-semantics -o web/src/proto/game.js proto/game.proto
web/node_modules/.bin/pbts -o web/src/proto/game.d.ts web/src/proto/game.js
```
