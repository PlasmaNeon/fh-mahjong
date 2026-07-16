import { tileIdsEqual } from '../../table/meldOrdering'

// Decide whether an active lift should be dropped. Returns true when there is a
// lifted tile AND either the round changed (tile ids are recycled per round, so
// a surviving id would point at a different physical tile) or the lifted tile is
// no longer in the self hand (discarded or consumed into a meld).
export function shouldClearLift(input: {
  liftedTileId: number | null
  roundChanged: boolean
  closedHandIds: unknown[]
  drawnTileId: unknown
}): boolean {
  const { liftedTileId, roundChanged, closedHandIds, drawnTileId } = input
  if (liftedTileId == null) return false
  if (roundChanged) return true
  const inHand =
    closedHandIds.some((id) => tileIdsEqual(id, liftedTileId)) ||
    tileIdsEqual(drawnTileId, liftedTileId)
  return !inHand
}
