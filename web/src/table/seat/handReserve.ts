// The seat bundle pins the concealed hand to one side and the exposed stack
// (flowers + melds) to the other via a fixed-width box. The concealed hand must
// reserve a *constant* width so the exposed stack doesn't shake as tiles are
// drawn/discarded — but that reservation has to match the hand's true maximum for
// its current meld count, not a blanket 14 tiles. Each called meld removes tiles
// from the concealed hand (engine invariant: concealed_with_draw + 3*melds == 14),
// so a hand with called melds is narrower. Reserving a full 14 tiles anyway makes
// the bundle content overflow its span, which shoves the exposed melds past the
// table edge ("first meld pushed out"). Two concealed tiles is the four-meld floor.
export function concealedHandReserveTiles(meldCount: number): number {
  return Math.max(2, 14 - 3 * meldCount)
}
