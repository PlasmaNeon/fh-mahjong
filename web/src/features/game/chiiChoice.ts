import { game } from '../../proto/game'

type ChiiTile = {
  id?: number | null
  suit?: number | null
  value?: number | null
}

export type ChiiActionLike = {
  type?: game.ActionType | null
  meldTiles?: ChiiTile[] | null
}

type ChiiSelectionResult<T extends ChiiActionLike> =
  | { kind: 'ignore' }
  | { kind: 'select'; tileId: number | null }
  | { kind: 'submit'; action: T }

const tileId = (tile: ChiiTile) => Number(tile.id)
const faceKey = (tile: ChiiTile) => `${Number(tile.suit)}-${Number(tile.value)}`

export function collapseChiiActions<T extends ChiiActionLike>(actions: T[]): T[] {
  let hasChii = false
  return actions.filter((action) => {
    if (action.type !== game.ActionType.ACTION_CHII) return true
    if (hasChii) return false
    hasChii = true
    return true
  })
}

export function eligibleChiiTileIds<T extends ChiiActionLike>(
  actions: T[],
  hand: ChiiTile[],
  selectedTileId: number | null,
): Set<number> {
  const selectedTile = selectedTileId == null
    ? null
    : hand.find((tile) => tileId(tile) === selectedTileId) ?? null
  const eligibleFaces = new Set<string>()

  for (const action of actions) {
    const meldTiles = action.meldTiles ?? []
    if (selectedTile) {
      const selectedFace = faceKey(selectedTile)
      if (!meldTiles.some((tile) => faceKey(tile) === selectedFace)) continue
      meldTiles.forEach((tile) => {
        if (faceKey(tile) !== selectedFace) eligibleFaces.add(faceKey(tile))
      })
    } else {
      meldTiles.forEach((tile) => eligibleFaces.add(faceKey(tile)))
    }
  }

  return new Set(
    hand
      .filter((tile) => (
        tileId(tile) === selectedTileId || eligibleFaces.has(faceKey(tile))
      ))
      .map(tileId),
  )
}

export function resolveChiiTileClick<T extends ChiiActionLike>({
  actions,
  hand,
  selectedTileId,
  clickedTile,
}: {
  actions: T[]
  hand: ChiiTile[]
  selectedTileId: number | null
  clickedTile: ChiiTile
}): ChiiSelectionResult<T> {
  const clickedId = tileId(clickedTile)
  const eligibleIds = eligibleChiiTileIds(actions, hand, selectedTileId)
  if (!eligibleIds.has(clickedId)) return { kind: 'ignore' }
  if (clickedId === selectedTileId) return { kind: 'select', tileId: null }
  if (selectedTileId == null) return { kind: 'select', tileId: clickedId }

  const selectedTile = hand.find((tile) => tileId(tile) === selectedTileId)
  if (!selectedTile) return { kind: 'select', tileId: clickedId }

  const selectedFaces = [faceKey(selectedTile), faceKey(clickedTile)].sort()
  const action = actions.find((candidate) => {
    const candidateFaces = (candidate.meldTiles ?? []).map(faceKey).sort()
    return candidateFaces.length === selectedFaces.length
      && candidateFaces.every((face, index) => face === selectedFaces[index])
  })

  return action ? { kind: 'submit', action } : { kind: 'select', tileId: clickedId }
}
