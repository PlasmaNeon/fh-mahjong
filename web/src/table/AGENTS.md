# web/src/table/

> Shared tabletop presentation primitives for live play and replay.

## Overview

This directory owns the reusable Mahjong table renderer. The live game and replay routes should adapt their own state into these shared view models instead of maintaining independent copies of the seat, discard, meld, flower, and result-layout DOM.

## Key Files

- **TableScene.tsx** — Shared tabletop presentation module:
  - `TableBoard` composes the center HUD, wild-tile badge, action bar slot, four discard lanes, and four seat lanes
  - `SeatLane` owns one player's concealed-hand rail, flex gap, exposed meld rail, and flower rail as a single reusable layout unit
  - `DiscardLane` owns one player's discard tray, wrapping rules, callable highlight, and discard entry animation offsets
  - `TableRoundResultOverlay` renders the shared round-result modal above the scaled board
  - `getSeatDirection()` is the single source of truth for seat-to-view direction mapping

## Architecture Notes

- `SeatLane` and `DiscardLane` intentionally use the same `bottom | right | top | left` direction mapping so the hand/exposed/discard geometry cannot drift apart logically.
- The shared layout model is canonical-bottom first, but left/right seat semantics are not pure mirrors: preserve the old main-branch side-seat behavior where right concealed hands use `column-reverse`, left concealed hands use `column`, right exposed rails sit above the hand, and left exposed rails sit below it.
- Keep the drawn tile as a dedicated slot adjacent to the concealed-hand rail rather than folding it back into the sorted closed-hand list; the hand-to-drawn gap should be structural, not margin-only.
- Normalize tile-ID equality inside the shared presenter because protobuf numeric fields can arrive as wrapper values; drawn-tile splitting and stolen-tile highlighting must not depend on strict `===` against plain numbers.
- When a drawn tile merges back into the sorted concealed hand, keep it on the draw side of any identical tiles by pinning the most recent drawn tile to the end of its equal-value group instead of tie-breaking purely by raw tile ID.
- Shared-tile motion should not stack an explicit directional `x/y` entrance on the same node that owns a `layoutId` transition. Let Framer's shared-layout path own the tile node itself, and put any seat-direction entry accent on a separate wrapper around the current drawn-slot tile.
- For shared moves such as hand -> discard and drawn-slot -> sorted hand, prefer `layout=\"position\"` on the shared tile node and keep opacity/scale accents on outer wrappers. That avoids size-morph transforms making the tile feel like it moves the wrong way before settling.
- Cross-container moves that still feel wrong after those guardrails should use the table-level flying-tile overlay instead of `layoutId`. The current renderer snapshots tile rects across renders and animates explicit `hand/drawn -> discard` and `drawn -> hand` transfers in viewport space while temporarily hiding the destination tile.
- `DiscardLane` owns the tray geometry, but its shell placement must stay center-HUD-relative: side trays sit beside the HUD, top/bottom trays use a left-anchored 6-tile lane, and the 6-tile cap must be computed from the discard tile's main-axis size rather than the rotated cross-axis size.
- The center HUD should stay visually paired with the discard system: size it from the same 6-tile lane footprint and leave a deliberate HUD-to-discard gap rather than letting the trays touch the panel.
- Keep all four discard-lane shell offsets derived from that same HUD gap variable; do not leave one side on an older fixed stage offset or the panel spacing will drift.
- Discard pools stay outside `SeatLane`; table-level composition belongs in `TableBoard`, while internal spacing belongs to the lane components themselves.
