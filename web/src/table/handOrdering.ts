import { getSuitOrder } from '../utils/tileUtils'
import type { TileLike } from './types'

export function compareTileSortKey(a: TileLike, b: TileLike) {
  const suitA = getSuitOrder(a.suit)
  const suitB = getSuitOrder(b.suit)
  if (suitA !== suitB) return suitA - suitB
  return a.value - b.value
}

export function sortTiles(tiles: TileLike[]) {
  return [...tiles].sort((a, b) => {
    const cmp = compareTileSortKey(a, b)
    if (cmp !== 0) return cmp
    return a.id - b.id
  })
}

function insertTileAtRightmostOfGroup(
  order: number[],
  tile: TileLike,
  tileMap: Map<number, TileLike>,
) {
  let insertIdx = order.length
  for (let i = 0; i < order.length; i++) {
    const current = tileMap.get(order[i])
    if (current && compareTileSortKey(tile, current) < 0) {
      insertIdx = i
      break
    }
  }
  order.splice(insertIdx, 0, tile.id)
}

// Positional-stability model: preserve the previous display order wherever
// possible, so same-suit/value tiles never spontaneously swap places.
export function computeStableDisplayOrder(
  baseTiles: TileLike[],
  previousOrder: number[] | null,
): number[] {
  const tileMap = new Map(baseTiles.map((t) => [t.id, t]))

  if (!previousOrder) {
    return sortTiles(baseTiles).map((t) => t.id)
  }

  const currentIds = baseTiles.map((t) => t.id)
  const currentIdSet = new Set(currentIds)
  const previousIdSet = new Set(previousOrder)
  const removedIds = previousOrder.filter((id) => !currentIdSet.has(id))
  const addedIds = currentIds.filter((id) => !previousIdSet.has(id))
  const newOrder = previousOrder.filter((id) => currentIdSet.has(id))

  if (removedIds.length === 1 && addedIds.length === 1) {
    const removedId = removedIds[0]
    const addedId = addedIds[0]
    const addedTile = tileMap.get(addedId)
    if (!addedTile) return newOrder
    const removedPosition = previousOrder.indexOf(removedId)
    const leftTile =
      removedPosition > 0 ? tileMap.get(newOrder[removedPosition - 1]) ?? null : null
    const rightTile =
      removedPosition < newOrder.length ? tileMap.get(newOrder[removedPosition]) ?? null : null
    const fits =
      (leftTile == null || compareTileSortKey(leftTile, addedTile) <= 0) &&
      (rightTile == null || compareTileSortKey(addedTile, rightTile) <= 0)
    if (fits) {
      newOrder.splice(removedPosition, 0, addedId)
    } else {
      insertTileAtRightmostOfGroup(newOrder, addedTile, tileMap)
    }
  } else {
    for (const addedId of addedIds) {
      const tile = tileMap.get(addedId)
      if (tile) insertTileAtRightmostOfGroup(newOrder, tile, tileMap)
    }
  }

  return newOrder
}
