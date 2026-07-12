import { game } from '../../proto/game'

const ACTION_PRIORITY: Partial<Record<game.ActionType, number>> = {
  [game.ActionType.ACTION_TSUMO]: 0,
  [game.ActionType.ACTION_RON]: 0,
  [game.ActionType.ACTION_CHII]: 1,
  [game.ActionType.ACTION_PON]: 2,
  [game.ActionType.ACTION_KAN]: 3,
  [game.ActionType.ACTION_ACCEPT_HAITEI]: 4,
  [game.ActionType.ACTION_REFUSE_HAITEI]: 5,
  [game.ActionType.ACTION_PASS]: 9,
}

export function orderTableActions<T extends { type?: game.ActionType | null }>(actions: T[]): T[] {
  const priority = (type?: game.ActionType | null) => type == null ? 6 : (ACTION_PRIORITY[type] ?? 6)
  return [...actions].sort((left, right) => priority(left.type) - priority(right.type))
}
