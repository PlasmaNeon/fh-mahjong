import type { MeldLike, SeatLaneDirection } from './types'

export function tileIdsEqual(left: unknown, right: unknown): boolean {
  if (left == null || right == null) return false
  return String(left) === String(right)
}

export function reorderMeldTiles(meld: MeldLike) {
  const addedTileId = meld.addedTileId ?? -1
  // The added tile of a risky kong (加杠) is rendered stacked on the called tile,
  // so it is excluded from the inline row here.
  const displayTiles = [...(meld.tiles || [])].filter((tile) => !tileIdsEqual(tile.id, addedTileId))
  const calledTileId = meld.calledTileId ?? -1
  const calledDirection = meld.calledDirection ?? 0
  const stolenIdx = displayTiles.findIndex((tile) => tileIdsEqual(tile.id, calledTileId))

  if (stolenIdx !== -1 && calledDirection > 0) {
    const stolen = displayTiles.splice(stolenIdx, 1)[0]
    if (calledDirection === 3) displayTiles.unshift(stolen)
    else if (calledDirection === 1) displayTiles.push(stolen)
    else if (calledDirection === 2) displayTiles.splice(1, 0, stolen)
  }

  return displayTiles
}

// Melds arrive in formation order (index 0 = first formed). The seat line places
// the meld zone directly next to the closed hand, so the first-formed meld sits
// nearest the hand and each new meld is appended on the far side — existing melds
// keep their position. Formation order (identity) is correct for every direction;
// the per-direction CSS flex-direction handles which way "away from the hand" is.
export function orderMelds(melds: MeldLike[], _direction: SeatLaneDirection): MeldLike[] {
  return [...melds]
}
