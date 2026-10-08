# web/src/table/seat/

> One seat's zones, composed four times by `TableBoard`. A fix here lands in live play and replay.

- **SeatBundle.tsx** — assembles a seat lane; the unit `TableBoard` places per direction. Sets
  `--seat-hand-tiles` from `handReserve.ts`.
- **PlayerSeat.tsx** — concealed rail, flex gap, exposed melds, flowers. Names, winds, and scores
  are in `../CenterHud.tsx`.
- **ClosedHand.tsx** — the concealed rail with a dedicated drawn-tile slot. Redacted backs are
  keyed by slot, not id. Accepts optional per-physical-id review annotations (absolute; they never
  change reserved width or anchors).
- **OpenMelds.tsx**, **OpenMeldZone.tsx** — exposed melds and their placement.
- **FlowerZone.tsx** — revealed flowers.
- **DiscardZone.tsx** — row/column coordinates in formation order (three rows of six, then an
  extensible fourth); CSS chooses axis and direction per rotation. Accepts optional replay
  called-footprint and tsumogiri attributes, which never claim flight destination ids.
- **handReserve.ts** — `concealedHandReserveTiles(meldCount)`.

Geometry lives in `../table-geometry.css`; these components supply structure and data. Tile
classes `pov-bottom|left|top|right` with a `small` modifier set orientation and size.
