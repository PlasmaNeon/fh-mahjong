export type StageLayoutOptions = {
  baseHeight?: number
  compactBaseHeight?: number
  compactMaxHeight?: number
  minAspect?: number
  maxAspect?: number
}

export type StageLayout = {
  stageWidth: number
  stageHeight: number
  scale: number
  scaledWidth: number
  scaledHeight: number
  offsetX: number
  offsetY: number
  // True on short stages (phones). The consumer sets data-compact on the stage
  // so the CSS can tighten the phone layout (see index.css) — bigger self tiles.
  compact: boolean
}

export const STAGE_BASE_HEIGHT = 900
export const STAGE_MIN_ASPECT = 16 / 9
export const STAGE_MAX_ASPECT = 2.39
// Below this available height (a phone's rotated-landscape height), switch to a
// shorter "compact" design so the same tiles scale up. Paired with the compact
// CSS overrides, which tighten the layout so the shorter design doesn't clip.
export const STAGE_COMPACT_MAX_HEIGHT = 520
export const STAGE_COMPACT_BASE_HEIGHT = 680

export function computeStageLayout(
  availWidth: number,
  availHeight: number,
  opts: StageLayoutOptions = {},
): StageLayout {
  const minAspect = opts.minAspect ?? STAGE_MIN_ASPECT
  const maxAspect = opts.maxAspect ?? STAGE_MAX_ASPECT

  const safeWidth = Math.max(availWidth, 1)
  const safeHeight = Math.max(availHeight, 1)

  const compact = safeHeight < (opts.compactMaxHeight ?? STAGE_COMPACT_MAX_HEIGHT)
  const baseHeight =
    opts.baseHeight ??
    (compact ? opts.compactBaseHeight ?? STAGE_COMPACT_BASE_HEIGHT : STAGE_BASE_HEIGHT)

  const windowAspect = safeWidth / safeHeight
  const designAspect = Math.min(Math.max(windowAspect, minAspect), maxAspect)

  const stageHeight = baseHeight
  const stageWidth = baseHeight * designAspect
  const scale = Math.min(safeWidth / stageWidth, safeHeight / stageHeight)
  const scaledWidth = stageWidth * scale
  const scaledHeight = stageHeight * scale

  return {
    stageWidth,
    stageHeight,
    scale,
    scaledWidth,
    scaledHeight,
    offsetX: Math.max((safeWidth - scaledWidth) / 2, 0),
    offsetY: Math.max((safeHeight - scaledHeight) / 2, 0),
    compact,
  }
}
