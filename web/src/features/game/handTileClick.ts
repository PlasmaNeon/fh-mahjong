import type { DiscardMode } from './discardMode'

export type HandTileClickResult = { kind: 'discard' | 'lift' | 'unlift' }

// Pure state machine for a click on the viewer's own hand tile.
// - isLifted: the clicked tile is the currently-lifted one.
// - canDiscard: it is the viewer's turn and a discard is currently valid.
export function resolveHandTileClick(input: {
  mode: DiscardMode
  isLifted: boolean
  canDiscard: boolean
}): HandTileClickResult {
  const { mode, isLifted, canDiscard } = input
  if (mode === 'single' && canDiscard) return { kind: 'discard' }
  if (isLifted) return { kind: canDiscard ? 'discard' : 'unlift' }
  return { kind: 'lift' }
}
