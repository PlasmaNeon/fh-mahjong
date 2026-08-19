# web/src/table/seat/

> The per-seat presentation primitives assembled by the shared table presenter.

## Overview

One seat's worth of tabletop, decomposed into zones. `TableBoard.tsx` composes four of these (bottom/right/top/left) into a board; live play and replay both go through that same path, so a fix here lands in both.

## Key Files

- **SeatBundle.tsx** — Assembles one seat's zones into the seat lane. The unit `TableBoard` places per position.
- **PlayerSeat.tsx** — The seat-lane composition: concealed-hand rail, flex gap, exposed meld rail, and flower rail for one seat. (Name, wind and score are rendered by `../CenterHud.tsx`, not here.)
- **ClosedHand.tsx** — Concealed-hand rail. Keeps the drawn tile in a dedicated slot next to the rail rather than folding it back into the sorted closed-hand list.
- **OpenMelds.tsx** / **OpenMeldZone.tsx** — Exposed meld rendering and its lane placement.
- **FlowerZone.tsx** — Revealed flower tiles.
- **DiscardZone.tsx** — The seat's discard tray.
- **handReserve.ts** — `concealedHandReserveTiles`: how much hand rail to reserve, so the lane does not reflow as tiles leave the hand. Unit-tested in `handReserve.test.ts`.

## Architecture Notes

- **Geometry lives in CSS, not here.** Seat lanes own concealed-hand, flex-gap, open-meld, and flower geometry as reusable bottom/right/top/left primitives in `web/src/table/table-geometry.css`; these components supply structure and data.
- Left/right lanes intentionally preserve the original main-branch semantics rather than pure rotational symmetry: right concealed hands flow `column-reverse`, left flow `column`; right exposed rails sit above the hand, left below it. Do not "fix" this into symmetry.
- Tile CSS uses positional classes (`pov-bottom`, `pov-left`, `pov-top`, `pov-right`) with a `small` modifier.
- Preview changes on `/tools/table-sample` (`features/dev/`), not by deploying a live match.
