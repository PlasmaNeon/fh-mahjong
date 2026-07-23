import { describe, expect, it } from 'vitest'
import { game } from '../../proto/game'
import {
  collapseChiiActions,
  eligibleChiiTileIds,
  resolveChiiTileClick,
} from './chiiChoice'

const tile = (id: number, value: number) => ({ id, suit: game.Suit.SUIT_MAN, value })
const hand = [tile(20, 2), tile(30, 3), tile(31, 3), tile(50, 5), tile(60, 6)]
const lowerChii = {
  type: game.ActionType.ACTION_CHII,
  meldTiles: [tile(200, 2), tile(300, 3)],
}
const middleChii = {
  type: game.ActionType.ACTION_CHII,
  meldTiles: [tile(301, 3), tile(500, 5)],
}
const upperChii = {
  type: game.ActionType.ACTION_CHII,
  meldTiles: [tile(501, 5), tile(600, 6)],
}

describe('multi-choice chii interaction', () => {
  it('shows one CHII trigger even when the server supplies several candidates', () => {
    const ron = { type: game.ActionType.ACTION_RON, meldTiles: [] }
    const collapsed = collapseChiiActions([ron, lowerChii, middleChii, upperChii])

    expect(collapsed).toEqual([ron, lowerChii])
  })

  it('enables candidate faces in the hand, including equivalent duplicate copies', () => {
    expect([...eligibleChiiTileIds([lowerChii, middleChii, upperChii], hand, null)]).toEqual([
      20, 30, 31, 50, 60,
    ])
    expect([...eligibleChiiTileIds([lowerChii, middleChii, upperChii], hand, 31)]).toEqual([
      20, 31, 50,
    ])
  })

  it('submits the matching server action after the player picks two hand tiles', () => {
    const first = resolveChiiTileClick({
      actions: [lowerChii, middleChii, upperChii],
      hand,
      selectedTileId: null,
      clickedTile: hand[2],
    })
    expect(first).toEqual({ kind: 'select', tileId: 31 })

    const second = resolveChiiTileClick({
      actions: [lowerChii, middleChii, upperChii],
      hand,
      selectedTileId: 31,
      clickedTile: hand[3],
    })
    expect(second).toEqual({ kind: 'submit', action: middleChii })
  })

  it('lets the player tap the selected tile again to undo the first choice', () => {
    expect(resolveChiiTileClick({
      actions: [lowerChii, middleChii],
      hand,
      selectedTileId: 30,
      clickedTile: hand[1],
    })).toEqual({ kind: 'select', tileId: null })
  })
})
