export type StageLayoutOptions = {
  baseHeight?: number
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
}

export const STAGE_BASE_HEIGHT = 900
export const STAGE_MIN_ASPECT = 16 / 9
export const STAGE_MAX_ASPECT = 2.39

export function computeStageLayout(
  availWidth: number,
  availHeight: number,
  opts: StageLayoutOptions = {},
): StageLayout {
  const baseHeight = opts.baseHeight ?? STAGE_BASE_HEIGHT
  const minAspect = opts.minAspect ?? STAGE_MIN_ASPECT
  const maxAspect = opts.maxAspect ?? STAGE_MAX_ASPECT

  const safeWidth = Math.max(availWidth, 1)
  const safeHeight = Math.max(availHeight, 1)

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
  }
}
