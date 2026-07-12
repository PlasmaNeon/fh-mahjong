import { describe, expect, it } from 'vitest'
import { game } from '../../proto/game'
import { orderTableActions } from './actionOrdering'

describe('table action hierarchy', () => {
  it('puts wins before calls and pass last', () => {
    const actions = [
      { type: game.ActionType.ACTION_PASS },
      { type: game.ActionType.ACTION_PON },
      { type: game.ActionType.ACTION_RON },
      { type: game.ActionType.ACTION_CHII },
    ]
    expect(orderTableActions(actions).map(action => action.type)).toEqual([
      game.ActionType.ACTION_RON,
      game.ActionType.ACTION_CHII,
      game.ActionType.ACTION_PON,
      game.ActionType.ACTION_PASS,
    ])
  })
})
