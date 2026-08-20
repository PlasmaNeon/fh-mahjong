import type { ActionProb, ReportDecision, ReviewReport } from './reviewClient'

export type Severity = 'ok' | 'disagreement' | 'mistake'

export const SEVERITY_THRESHOLDS = {
  disagreement: 0.3,
  mistake: 0.6,
  topNExempt: 3,
  topNMinProb: 0.05,
}

export type SeverityThresholds = typeof SEVERITY_THRESHOLDS

/** Top legal-action probability minus the chosen action's probability (>= 0). */
export function decisionGap(d: ReportDecision): number {
  const top = d.actions[0]?.prob ?? 0 // report actions are sorted desc
  return Math.max(0, top - d.chosenProb)
}

/**
 * Classifies how far a decision's chosen action diverged from the policy's
 * preference. A chosen action ranked in the top N (with a non-trivial
 * probability) is always exempt, checked before the gap-based tiers.
 */
export function decisionSeverity(
  d: ReportDecision,
  thresholds: SeverityThresholds = SEVERITY_THRESHOLDS,
): Severity {
  const rank = d.actions.findIndex(a => a.actionId === d.chosenActionId)
  if (rank >= 0 && rank < thresholds.topNExempt && d.chosenProb >= thresholds.topNMinProb) {
    return 'ok'
  }
  const gap = decisionGap(d)
  if (gap >= thresholds.mistake) return 'mistake'
  if (gap >= thresholds.disagreement) return 'disagreement'
  return 'ok'
}

/**
 * Normalizes `ReviewReport.valuesCalibrated` for rendering. Cached reports
 * from before the field existed (schema v1, pre-B2c) omit it entirely — but
 * those reports always carried real numeric decision values, so absence must
 * be treated as CALIBRATED (not as the uncalibrated warning) whenever numeric
 * values are actually present. An explicit `false` (a privileged-critic
 * checkpoint, whose ReportDecision.value is null everywhere) always stays
 * uncalibrated regardless of what the decisions look like.
 */
export function resolveValuesCalibrated(report: ReviewReport): boolean {
  if (report.valuesCalibrated === false) return false
  if (report.valuesCalibrated === true) return true
  return report.decisions.some(d => typeof d.value === 'number')
}

/** `${round}:${actionIndex}` — a stable key identifying one decision within a match. */
export function decisionKey(round: number, actionIndex: number): string {
  return `${round}:${actionIndex}`
}

/** Decisions for one seat, optionally narrowed to a single decisionKey. */
export function selectPanelDecisions(
  report: ReviewReport,
  seat: number,
  key?: string,
): ReportDecision[] {
  return report.decisions.filter(d => {
    if (d.seat !== seat) return false
    if (key !== undefined && decisionKey(d.round, d.actionIndex) !== key) return false
    return true
  })
}

/**
 * Groups a report's decisions by `decisionKey(round, actionIndex)`. A single
 * key can hold multiple seats' decisions (a call window where several seats
 * had a legal response to the same discard) — callers filter by seat.
 */
export function buildDecisionIndex(report: ReviewReport): Map<string, ReportDecision[]> {
  const map = new Map<string, ReportDecision[]>()
  for (const d of report.decisions) {
    const key = decisionKey(d.round, d.actionIndex)
    const existing = map.get(key)
    if (existing) existing.push(d)
    else map.set(key, [d])
  }
  return map
}

export interface BarRow extends ActionProb {
  isChosen: boolean
}

/** Top 8 legal actions by probability (already sorted desc per the report contract), plus the chosen action appended if it fell outside the top 8. */
export function selectBarRows(d: ReportDecision): BarRow[] {
  const top = d.actions.slice(0, 8).map(a => ({ ...a, isChosen: a.actionId === d.chosenActionId }))
  if (!top.some(r => r.isChosen)) {
    top.push({ actionId: d.chosenActionId, prob: d.chosenProb, isChosen: true })
  }
  return top
}

/** Counts of each severity tier across a set of decisions (e.g. one seat's decisions). */
export function severityCounts(
  decisions: ReportDecision[],
  thresholds: SeverityThresholds = SEVERITY_THRESHOLDS,
): Record<Severity, number> {
  const counts: Record<Severity, number> = { ok: 0, disagreement: 0, mistake: 0 }
  for (const d of decisions) counts[decisionSeverity(d, thresholds)]++
  return counts
}

export const SEVERITY_COLORS: Record<Severity, string> = {
  ok: '#10b981',
  disagreement: '#f59e0b',
  mistake: '#ef4444',
}

export const SEVERITY_LABELS: Record<Severity, { en: string; zh: string }> = {
  ok: { en: 'OK', zh: '正常' },
  disagreement: { en: 'Disagreement', zh: '分歧' },
  mistake: { en: 'Mistake', zh: '失误' },
}

// Action catalog for actionLabel — mirror internal/rl/action.go exactly:
// ids 0-4 = pass/tsumo/ron/accept-haitei/refuse-haitei; 5-46 discard by face
// (man 1-9, pin 1-9, sou 1-9, jihai 1-7, flower 1-8); 47-80 pon by face
// (34 faces, no flowers); 81-114 open kan; 115-148 closed kan; 149-182
// upgraded kan; 183-203 chii (3 suits x sequence starts 1-7, order
// man/pin/sou). Face order: man(0-8), pin(9-17), sou(18-26), jihai(27-33),
// flower(34-41, discard-only). jihai/flower names copied from
// web/src/utils/tileDisplay.ts's value->name mapping — do not guess.

const DISCARD_BASE = 5
const DISCARD_COUNT = 42
const PON_BASE = DISCARD_BASE + DISCARD_COUNT // 47
const PON_COUNT = 34
const KAN_DIRECT_BASE = PON_BASE + PON_COUNT // 81
const KAN_MODE_COUNT = 34
const KAN_CLOSED_BASE = KAN_DIRECT_BASE + KAN_MODE_COUNT // 115
const KAN_UPGRADED_BASE = KAN_CLOSED_BASE + KAN_MODE_COUNT // 149
const CHII_BASE = KAN_UPGRADED_BASE + KAN_MODE_COUNT // 183

// jihai value order 1-7, from tileDisplay.ts's jihaiMap / getTileName.
const JIHAI_EN = ['East', 'South', 'West', 'North', 'Haku', 'Hatsu', 'Chun']
const JIHAI_ZH = ['东', '南', '西', '北', '白', '发', '中']

// flower value order 1-8, from tileDisplay.ts's flowerNameMap / flowerSvgMap.
const FLOWER_EN = ['Spring', 'Summer', 'Autumn', 'Winter', 'Plum', 'Orchid', 'Chrysanthemum', 'Bamboo']
const FLOWER_ZH = ['春', '夏', '秋', '冬', '梅', '兰', '菊', '竹']

/** Face index (0-41) -> tile label, matching DiscardBase's 42-wide face space. */
function faceLabel42(faceIndex: number): { en: string; zh: string } {
  if (faceIndex < 9) return { en: `${faceIndex + 1}m`, zh: `${faceIndex + 1}万` }
  if (faceIndex < 18) return { en: `${faceIndex - 9 + 1}p`, zh: `${faceIndex - 9 + 1}饼` }
  if (faceIndex < 27) return { en: `${faceIndex - 18 + 1}s`, zh: `${faceIndex - 18 + 1}条` }
  if (faceIndex < 34) {
    const i = faceIndex - 27
    return { en: JIHAI_EN[i], zh: JIHAI_ZH[i] }
  }
  const i = faceIndex - 34
  return { en: FLOWER_EN[i], zh: FLOWER_ZH[i] }
}

/** Face index (0-33) -> tile label, matching the 34-wide face space (no flowers). */
function faceLabel34(faceIndex: number): { en: string; zh: string } {
  return faceLabel42(faceIndex)
}

const CHII_SUIT_EN = ['m', 'p', 's']
const CHII_SUIT_ZH = ['万', '饼', '条']

function chiiLabel(startIndex: number): { en: string; zh: string } {
  const suit = Math.floor(startIndex / 7)
  const start = (startIndex % 7) + 1
  const suitEn = CHII_SUIT_EN[suit]
  const suitZh = CHII_SUIT_ZH[suit]
  return {
    en: `Chii ${start}-${start + 1}-${start + 2}${suitEn}`,
    zh: `吃 ${start}-${start + 1}-${start + 2}${suitZh}`,
  }
}

export function actionLabel(actionId: number): { en: string; zh: string } {
  if (actionId === 0) return { en: 'Pass', zh: '过' }
  if (actionId === 1) return { en: 'Tsumo', zh: '自摸' }
  if (actionId === 2) return { en: 'Ron', zh: '荣和' }
  if (actionId === 3) return { en: 'Accept Haitei', zh: '接受海底' }
  if (actionId === 4) return { en: 'Refuse Haitei', zh: '拒绝海底' }

  if (actionId >= DISCARD_BASE && actionId < PON_BASE) {
    const { en, zh } = faceLabel42(actionId - DISCARD_BASE)
    return { en: `Discard ${en}`, zh: `打 ${zh}` }
  }
  if (actionId >= PON_BASE && actionId < KAN_DIRECT_BASE) {
    const { en, zh } = faceLabel34(actionId - PON_BASE)
    return { en: `Pon ${en}`, zh: `碰 ${zh}` }
  }
  if (actionId >= KAN_DIRECT_BASE && actionId < KAN_CLOSED_BASE) {
    const { en, zh } = faceLabel34(actionId - KAN_DIRECT_BASE)
    return { en: `Open Kan ${en}`, zh: `明杠 ${zh}` }
  }
  if (actionId >= KAN_CLOSED_BASE && actionId < KAN_UPGRADED_BASE) {
    const { en, zh } = faceLabel34(actionId - KAN_CLOSED_BASE)
    return { en: `Closed Kan ${en}`, zh: `暗杠 ${zh}` }
  }
  if (actionId >= KAN_UPGRADED_BASE && actionId < CHII_BASE) {
    const { en, zh } = faceLabel34(actionId - KAN_UPGRADED_BASE)
    return { en: `Upgraded Kan ${en}`, zh: `加杠 ${zh}` }
  }
  if (actionId >= CHII_BASE && actionId < CHII_BASE + 21) {
    return chiiLabel(actionId - CHII_BASE)
  }

  return { en: `Unknown (${actionId})`, zh: `未知 (${actionId})` }
}
