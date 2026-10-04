import type { ReportDecision, TileRisk } from './reviewClient'
import type { ReviewKey } from '../../i18n/locales/review'
import type { PlayerTableView, TileLike } from '../../table/types'
export function decisionPosition(d: ReportDecision) {
  return d.positionIndex ?? d.actionIndex - 1
}
export function positionDecisionIndex(
  decisions: ReportDecision[],
  round: number,
  cursor: number,
  selectedId?: string | null,
) {
  const matches = (d: ReportDecision) => d.round === round && decisionPosition(d) === cursor
  const selected = selectedId ? decisions.findIndex((d) => d.id === selectedId && matches(d)) : -1
  return selected >= 0 ? selected : decisions.findIndex(matches)
}
export function faceOfTile(tile: TileLike) {
  return tile.suit === 3
    ? tile.value - 1
    : tile.suit === 2
      ? tile.value + 8
      : tile.suit === 1
        ? tile.value + 17
        : tile.suit === 4
          ? tile.value + 26
          : tile.value + 33
}
export function faceLabel(face: number) {
  return face < 9
    ? `${face + 1}m`
    : face < 18
      ? `${face - 8}p`
      : face < 27
        ? `${face - 17}s`
        : face < 34
          ? `${face - 26}z`
          : `F${face - 33}`
}
export function studyActionLabel(id: number, t: (key: ReviewKey) => string) {
  if (id < 5) return t((['review.pass', 'review.tsumo', 'review.ron', 'review.accept', 'review.refuse'] as const)[id])
  if (id < 47) return `${t('review.discard')} ${faceLabel(id - 5)}`
  if (id < 81) return `${t('review.pon')} ${faceLabel(id - 47)}`
  if (id < 115) return `${t('review.kan')} ${faceLabel(id - 81)}`
  if (id < 149) return `${t('review.closedKan')} ${faceLabel(id - 115)}`
  if (id < 183) return `${t('review.upgradedKan')} ${faceLabel(id - 149)}`
  const face = Math.floor((id - 183) / 7) * 9 + ((id - 183) % 7)
  return `${t('review.chii')} ${[face, face + 1, face + 2].map(faceLabel).join(' ')}`
}
export function bestAction(d: ReportDecision) {
  return d.actions.reduce((best, a) => (a.prob > best.prob ? a : best), d.actions[0])
}
export function actualKnown(d: ReportDecision) {
  return !d.choiceSource || d.choiceSource === 'recorded'
}
export function agreementStats(decisions: ReportDecision[]) {
  const known = decisions.filter((d) => actualKnown(d) && d.actions.length > 1)
  const agreement = known.length
    ? known.filter((d) => bestAction(d)?.actionId === d.chosenActionId).length / known.length
    : null
  const normalized = known.flatMap((d) => {
    if (!d.actions.every((a) => a.evaluation)) return []
    const values = d.actions.map((a) => a.evaluation!.mean),
      low = Math.min(...values),
      high = Math.max(...values)
    const actual = d.actions.find((a) => a.actionId === d.chosenActionId)?.evaluation?.mean
    return high > low && actual != null ? [(actual - low) / (high - low)] : []
  })
  const rating = normalized.length ? 100 * (normalized.reduce((a, b) => a + b, 0) / normalized.length) ** 2 : null
  return {
    agreement,
    rating,
    count: known.length,
    ratingCount: normalized.length,
  }
}
export function errorRatio(d: ReportDecision) {
  const best = bestAction(d)
  return best?.prob > 0 ? (100 * d.chosenProb) / best.prob : 100
}
export function isStudyError(d: ReportDecision, threshold: number) {
  return actualKnown(d) && d.actions.length > 1 && errorRatio(d) < threshold
}
export function cumulativeProxy(probabilities: number[]) {
  return 1 - probabilities.reduce((product, p) => product * (1 - Math.max(0, Math.min(1, p))), 1)
}
export function riskForAction(d: ReportDecision): TileRisk | undefined {
  return d.chosenActionId >= 5 && d.chosenActionId < 47
    ? d.risk?.tiles.find((tile) => tile.face === d.chosenActionId - 5)
    : undefined
}
export function discardRiskLog(decisions: ReportDecision[]) {
  return decisions.filter(actualKnown).flatMap((d) => {
    const risk = riskForAction(d)
    const operation = d.risk?.operations.find((o) => o.actionId === d.chosenActionId)
    return risk || operation ? [{ decision: d, probability: risk?.anyRon ?? operation!.anyRon }] : []
  })
}
export function drawLog(decisions: ReportDecision[]) {
  const seen = new Set<string>()
  return decisions
    .filter((d) => d.draw)
    .filter((d) => {
      const key = `${d.round}:${d.seat}:${d.draw!.actionIndex}`
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}
export function tileAnnotations(
  d: ReportDecision | undefined,
  tiles: TileLike[],
  relative: boolean,
  advice: boolean,
  risks: boolean,
  label: (id: number) => string,
): PlayerTableView['reviewAnnotations'] {
  if (!d) return undefined
  const best = bestAction(d)
  return Object.fromEntries(
    tiles.map((tile) => {
      const face = faceOfTile(tile),
        candidate = d.actions.find((a) => a.actionId === face + 5),
        risk = d.risk?.tiles.find((r) => r.face === face)
      return [
        tile.id,
        {
          label: `${label(face + 5)}${advice && candidate ? ` · ${(candidate.prob * 100).toFixed(1)}%` : ''}${risks && risk ? ` · Ron ${(risk.anyRon * 100).toFixed(1)}%` : ''}`,
          confidence: advice ? candidate?.prob : undefined,
          scale:
            advice && candidate ? (relative && best?.prob ? candidate.prob / best.prob : candidate.prob) : undefined,
          actual: advice && actualKnown(d) && d.actualTileId === tile.id,
          best: advice && best?.actionId === face + 5,
          risk: risks ? risk?.anyRon : undefined,
          opponents: risks ? risk?.opponents.map((o) => ({ seat: o.seat, ron: o.ron })) : undefined,
        },
      ]
    }),
  )
}

export function bookmarkIndex(value: string | null, lower: number, upper: number, fallback: number) {
  const parsed = value == null ? fallback : Number(value)
  return Number.isFinite(parsed) && Number.isInteger(parsed) ? Math.max(lower, Math.min(upper, parsed)) : fallback
}
